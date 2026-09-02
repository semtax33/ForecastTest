from __future__ import annotations

from calendar import isleap
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


INTEREST_TAGS = ("InterestExpense", "InterestExpenseNonOperating")
TAX_TAGS = ("IncomeTaxExpenseBenefit",)
PRETAX_TAGS = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest",
)
NONOPERATING_TAGS = (
    "OtherNonoperatingIncomeExpense",
    "NonoperatingIncomeExpense",
)


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _select_ytd_fact(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    *,
    accession: str,
    end: str,
) -> tuple[float, str, dict[str, Any] | None]:
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    for priority, tag in enumerate(tags):
        records = (
            facts.get("facts", {})
            .get("us-gaap", {})
            .get(tag, {})
            .get("units", {})
            .get("USD", [])
        )
        for record in records:
            if (
                record.get("accn") != accession
                or record.get("end") != end
                or not record.get("start")
            ):
                continue
            duration = (
                pd.Timestamp(record["end"]) - pd.Timestamp(record["start"])
            ).days + 1
            candidates.append((-priority, duration, record, tag))
    if not candidates:
        return np.nan, "", None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, selected, tag = candidates[0]
    selected_with_tag = dict(selected)
    selected_with_tag["tag"] = tag
    return float(selected["val"]), tag, selected_with_tag


def build_acquiree_nopat_reconciliation(
    *, acquisition_proof: pd.DataFrame, companyfacts_root: Path
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for event in acquisition_proof.to_dict("records"):
        output: dict[str, Any] = {
            "ticker": event["ticker"],
            "fiscal_year": int(event["fiscal_year"]),
            "event_name": event["event_name"],
            "event_type": event["event_type"],
            "event_close_date": event["event_close_date"],
            "ownership_fraction": event["ownership_fraction"],
            "acquiree_net_income_since_close_usd": event[
                "acquiree_net_income_since_close_usd"
            ],
            "full_year_normalized_acquiree_net_income_usd": event[
                "full_year_normalized_acquiree_net_income_usd"
            ],
            "assumed_long_term_debt_usd": event["assumed_long_term_debt_usd"],
            "acquired_invested_capital_usd": event[
                "acquired_invested_capital_usd"
            ],
            "company_year_contamination_status": event[
                "company_year_contamination_status"
            ],
        }
        target_cik = str(event.get("target_cik") or "")
        if not target_cik or target_cik == "PRIVATE_UNAVAILABLE":
            output.update(
                {
                    "target_financing_evidence_available": False,
                    "predeal_ytd_interest_expense_usd": np.nan,
                    "predeal_ytd_income_tax_usd": np.nan,
                    "predeal_ytd_pretax_income_usd": np.nan,
                    "predeal_ytd_nonoperating_income_expense_usd": np.nan,
                    "predeal_normalized_tax_rate": np.nan,
                    "predeal_interest_annualization_factor": np.nan,
                    "predeal_annualized_interest_expense_usd": np.nan,
                    "predeal_implied_interest_rate": np.nan,
                    "acquired_full_year_pretax_interest_proxy_usd": np.nan,
                    "acquired_current_period_after_tax_interest_proxy_usd": np.nan,
                    "acquired_full_year_after_tax_interest_proxy_usd": np.nan,
                    "acquiree_current_period_nopat_bridge_usd": np.nan,
                    "acquiree_full_year_normalized_nopat_bridge_usd": np.nan,
                    "acquiree_nopat_return_proxy_pct": np.nan,
                    "nonoperating_adjustment_applied": False,
                    "nonoperating_adjustment_status": "LOCKED_PRIVATE_TARGET_NONOPERATING_SCOPE_UNAVAILABLE",
                    "acquiree_nopat_directly_disclosed": False,
                    "acquiree_nopat_bridge_ready": False,
                    "acquiree_nopat_bridge_status": "LOCKED_PRIVATE_TARGET_FINANCING_AND_NONOPERATING_SCOPE_UNAVAILABLE",
                    "source_evidence_bundle_sha256": "",
                    "organic_company_roic_validated": False,
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
            rows.append(output)
            continue

        companyfacts_path = companyfacts_root / f"CIK{target_cik.zfill(10)}.json"
        facts = json.loads(companyfacts_path.read_text(encoding="utf-8"))
        accession = str(event["target_accession"])
        end = str(event["target_balance_date"])
        selected: dict[str, tuple[float, str, dict[str, Any] | None]] = {
            "interest_expense": _select_ytd_fact(
                facts, INTEREST_TAGS, accession=accession, end=end
            ),
            "income_tax": _select_ytd_fact(facts, TAX_TAGS, accession=accession, end=end),
            "pretax_income": _select_ytd_fact(
                facts, PRETAX_TAGS, accession=accession, end=end
            ),
            "nonoperating_income_expense": _select_ytd_fact(
                facts, NONOPERATING_TAGS, accession=accession, end=end
            ),
        }
        hashes: list[str] = []
        for name, (value, tag, record) in selected.items():
            output[f"predeal_ytd_{name}_usd"] = value
            output[f"predeal_ytd_{name}_source_tag"] = tag
            output[f"predeal_ytd_{name}_record_sha256"] = (
                _record_hash(record) if record else ""
            )
            if record:
                hashes.append(output[f"predeal_ytd_{name}_record_sha256"])

        interest_record = selected["interest_expense"][2]
        if interest_record:
            interest_days = (
                pd.Timestamp(interest_record["end"])
                - pd.Timestamp(interest_record["start"])
            ).days + 1
            year_days = 366 if isleap(pd.Timestamp(end).year) else 365
            annualization_factor = year_days / interest_days
        else:
            interest_days = np.nan
            annualization_factor = np.nan
        output["predeal_interest_observation_days"] = interest_days
        output["predeal_interest_annualization_factor"] = annualization_factor
        output["predeal_annualized_interest_expense_usd"] = (
            output["predeal_ytd_interest_expense_usd"] * annualization_factor
            if pd.notna(output["predeal_ytd_interest_expense_usd"])
            else np.nan
        )
        predeal_debt = event.get("predeal_total_debt_usd", np.nan)
        output["predeal_total_debt_usd"] = predeal_debt
        output["predeal_implied_interest_rate"] = (
            output["predeal_annualized_interest_expense_usd"] / predeal_debt
            if pd.notna(predeal_debt) and predeal_debt > 0
            else np.nan
        )
        pretax = output["predeal_ytd_pretax_income_usd"]
        tax = output["predeal_ytd_income_tax_usd"]
        if pd.isna(pretax) and pd.notna(event.get("predeal_ytd_net_income_usd")):
            pretax = float(event["predeal_ytd_net_income_usd"]) + tax
            tax_source = "INFERRED_NET_INCOME_PLUS_TAX"
        else:
            tax_source = "DIRECT_PRETAX_AND_TAX_FACTS"
        normalized_tax_rate = (
            float(np.clip(abs(tax / pretax), 0.0, 0.35))
            if pd.notna(tax) and pd.notna(pretax) and pretax != 0
            else np.nan
        )
        output["predeal_ytd_pretax_income_for_tax_rate_usd"] = pretax
        output["predeal_normalized_tax_rate"] = normalized_tax_rate
        output["predeal_normalized_tax_rate_source"] = tax_source

        acquired_debt = output["assumed_long_term_debt_usd"]
        full_year_interest = (
            acquired_debt * output["predeal_implied_interest_rate"]
            if pd.notna(acquired_debt)
            and pd.notna(output["predeal_implied_interest_rate"])
            else np.nan
        )
        full_year_after_tax_interest = (
            full_year_interest * (1.0 - normalized_tax_rate)
            if pd.notna(full_year_interest) and pd.notna(normalized_tax_rate)
            else np.nan
        )
        current_after_tax_interest = (
            full_year_after_tax_interest * float(output["ownership_fraction"])
            if pd.notna(full_year_after_tax_interest)
            else np.nan
        )
        output["acquired_full_year_pretax_interest_proxy_usd"] = full_year_interest
        output["acquired_full_year_after_tax_interest_proxy_usd"] = (
            full_year_after_tax_interest
        )
        output["acquired_current_period_after_tax_interest_proxy_usd"] = (
            current_after_tax_interest
        )
        bridge_ready = all(
            pd.notna(value)
            for value in (
                output["acquiree_net_income_since_close_usd"],
                output["full_year_normalized_acquiree_net_income_usd"],
                full_year_after_tax_interest,
                current_after_tax_interest,
                output["acquired_invested_capital_usd"],
            )
        )
        output["acquiree_current_period_nopat_bridge_usd"] = (
            output["acquiree_net_income_since_close_usd"]
            + current_after_tax_interest
            if bridge_ready
            else np.nan
        )
        output["acquiree_full_year_normalized_nopat_bridge_usd"] = (
            output["full_year_normalized_acquiree_net_income_usd"]
            + full_year_after_tax_interest
            if bridge_ready
            else np.nan
        )
        acquired_capital = output["acquired_invested_capital_usd"]
        output["acquiree_nopat_return_proxy_pct"] = (
            output["acquiree_full_year_normalized_nopat_bridge_usd"]
            / acquired_capital
            * 100.0
            if bridge_ready and acquired_capital > 0
            else np.nan
        )
        output["target_financing_evidence_available"] = True
        output["nonoperating_adjustment_applied"] = False
        output["nonoperating_adjustment_status"] = (
            "EVIDENCE_CAPTURED_NOT_APPLIED_PREDEAL_PERIOD_NOT_TRANSFERABLE_TO_POST_CLOSE"
            if pd.notna(output["predeal_ytd_nonoperating_income_expense_usd"])
            else "NO_SEPARATE_NONOPERATING_FACT_IDENTIFIED"
        )
        output["acquiree_nopat_directly_disclosed"] = False
        output["acquiree_nopat_bridge_ready"] = bridge_ready
        output["acquiree_nopat_bridge_status"] = (
            "BRIDGED_NET_INCOME_PLUS_AFTER_TAX_INTEREST_PREDEAL_YIELD_PROXY_NONOPERATING_UNAPPLIED"
            if bridge_ready
            else "LOCKED_INCOMPLETE_INTEREST_TAX_DEBT_OR_NET_INCOME_SCOPE"
        )
        output["source_companyfacts_path"] = str(companyfacts_path)
        output["source_evidence_bundle_sha256"] = hashlib.sha256(
            "|".join(sorted(hashes)).encode("ascii")
        ).hexdigest()
        output["organic_company_roic_validated"] = False
        output["terminal_input_allowed"] = False
        output["research_only"] = True
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(drop=True)
