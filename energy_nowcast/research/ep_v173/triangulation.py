from __future__ import annotations

from calendar import isleap
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v17.fnsd import (
    _adsh_records,
    _select_numeric_fact,
    _select_text_record,
)


TRIANGULATION_TOLERANCE_PCT = 10.0


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _select_company_fact(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    *,
    accession: str,
    end: str,
    flow: bool,
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
            if record.get("accn") != accession or record.get("end") != end:
                continue
            duration = 0
            if flow:
                if not record.get("start"):
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


def _annualized_nopat_routes(
    *,
    net_income: float,
    interest_expense: float,
    operating_income: float,
    income_tax: float,
    pretax_income: float,
    observation_days: float,
    year_days: int,
) -> dict[str, Any]:
    if pd.isna(pretax_income) and pd.notna(net_income) and pd.notna(income_tax):
        pretax_for_tax = net_income + income_tax
        tax_source = "INFERRED_NET_INCOME_PLUS_TAX"
    else:
        pretax_for_tax = pretax_income
        tax_source = "DIRECT_PRETAX_AND_TAX_FACTS"
    tax_rate = (
        float(np.clip(abs(income_tax / pretax_for_tax), 0.0, 0.35))
        if pd.notna(income_tax)
        and pd.notna(pretax_for_tax)
        and pretax_for_tax != 0
        else np.nan
    )
    annualization = (
        year_days / observation_days
        if pd.notna(observation_days) and observation_days > 0
        else np.nan
    )
    route_a = (
        (net_income + interest_expense * (1.0 - tax_rate)) * annualization
        if all(
            pd.notna(value)
            for value in (net_income, interest_expense, tax_rate, annualization)
        )
        else np.nan
    )
    route_b = (
        operating_income * (1.0 - tax_rate) * annualization
        if all(
            pd.notna(value)
            for value in (operating_income, tax_rate, annualization)
        )
        else np.nan
    )
    midpoint_abs = (
        (abs(route_a) + abs(route_b)) / 2.0
        if pd.notna(route_a) and pd.notna(route_b)
        else np.nan
    )
    symmetric_gap_pct = (
        abs(route_a - route_b) / midpoint_abs * 100.0
        if pd.notna(midpoint_abs) and midpoint_abs > 0
        else np.nan
    )
    triangulated = bool(
        pd.notna(symmetric_gap_pct)
        and symmetric_gap_pct <= TRIANGULATION_TOLERANCE_PCT
    )
    midpoint = (
        (route_a + route_b) / 2.0
        if pd.notna(route_a) and pd.notna(route_b)
        else np.nan
    )
    return {
        "predeal_pretax_income_for_tax_rate_usd": pretax_for_tax,
        "predeal_normalized_tax_rate": tax_rate,
        "predeal_normalized_tax_rate_source": tax_source,
        "predeal_observation_days": observation_days,
        "predeal_annualization_factor": annualization,
        "route_a_net_income_plus_after_tax_interest_usd": route_a,
        "route_b_operating_income_after_tax_usd": route_b,
        "route_a_b_symmetric_gap_pct": symmetric_gap_pct,
        "triangulation_tolerance_pct": TRIANGULATION_TOLERANCE_PCT,
        "two_route_nopat_triangulated": triangulated,
        "triangulated_nopat_midpoint_usd": midpoint if triangulated else np.nan,
        "triangulation_status": (
            "EVIDENCE_TRIANGULATED_NOPAT"
            if triangulated
            else "LOCKED_ROUTE_DIVERGENCE_ABOVE_PREDECLARED_TOLERANCE"
            if pd.notna(symmetric_gap_pct)
            else "LOCKED_FEWER_THAN_TWO_COMPARABLE_NOPAT_ROUTES"
        ),
    }


def build_energen_historical_evidence(
    *,
    registry_path: Path,
    fnsd_root: Path,
    companyfacts_root: Path,
) -> pd.DataFrame:
    registry = pd.read_csv(registry_path, dtype=str, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    for event in registry.to_dict("records"):
        folder = fnsd_root / event["buyer_fnsd_folder"]
        accession = event["buyer_adsh"]
        submissions = pd.read_csv(folder / "sub.tsv", sep="\t", low_memory=False)
        filing = submissions.loc[submissions["adsh"].astype(str).eq(accession)]
        if len(filing) != 1 or str(filing.iloc[0]["form"]) != "10-K":
            raise ValueError(f"Historical deal source is not one 10-K: {accession}")
        numeric = _adsh_records(folder / "num.tsv", accession)
        text = _adsh_records(folder / "txt.tsv", accession)
        operating_dim = event["operating_dimh"]
        direct_cost_dim = event["direct_cost_dimh"]
        ppa_dim = event["ppa_dimh"]
        evidence_hashes: list[str] = []

        def numeric_fact(
            tags: tuple[str, ...], dimension: str
        ) -> tuple[float, str, str]:
            value, tag, record_hash = _select_numeric_fact(
                numeric, tags, dimension_hash=dimension
            )
            if record_hash:
                evidence_hashes.append(record_hash)
            return value, tag, record_hash

        acquiree_revenue, revenue_tag, revenue_hash = numeric_fact(
            (
                "BusinessCombinationProFormaInformationRevenueOfAcquireeSinceAcquisitionDateActual",
            ),
            operating_dim,
        )
        direct_operating_expense, direct_cost_tag, direct_cost_hash = numeric_fact(
            (
                "BusinessCombinationProFormaInformationDirectOperatingExpensessinceAcquisitionDateActual",
            ),
            direct_cost_dim,
        )
        consideration, consideration_tag, consideration_hash = numeric_fact(
            (
                "BusinessCombinationConsiderationTransferredEquityInterestsIssuedAndIssuable",
                "BusinessCombinationConsiderationTransferred1",
            ),
            operating_dim,
        )
        ppa_assets, ppa_assets_tag, ppa_assets_hash = numeric_fact(
            ("BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedAssets",),
            ppa_dim,
        )
        ppa_liabilities, ppa_liabilities_tag, ppa_liabilities_hash = numeric_fact(
            ("BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedLiabilities",),
            ppa_dim,
        )
        assumed_debt, assumed_debt_tag, assumed_debt_hash = numeric_fact(
            (
                "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedCurrentLiabilitiesLongTermDebt",
                "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedNoncurrentLiabilitiesLongTermDebt",
            ),
            ppa_dim,
        )
        disclosure, disclosure_hash = _select_text_record(
            text, event["classification_text_tag"]
        )
        if disclosure_hash:
            evidence_hashes.append(disclosure_hash)
        classification_proven = (
            event["classification_phrase"].casefold() in disclosure.casefold()
        )

        target_path = companyfacts_root / f"CIK{event['target_cik'].zfill(10)}.json"
        facts = json.loads(target_path.read_text(encoding="utf-8"))
        target_accession = event["target_accession"]
        target_end = event["target_balance_date"]
        routes: dict[str, tuple[str, ...]] = {
            "net_income": ("NetIncomeLoss", "ProfitLoss"),
            "interest_expense": ("InterestExpense", "InterestExpenseNonOperating"),
            "operating_income": ("OperatingIncomeLoss",),
            "income_tax": ("IncomeTaxExpenseBenefit",),
            "pretax_income": (
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest",
            ),
            "cash": (
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            ),
            "equity": (
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                "StockholdersEquity",
            ),
            "debt_current": ("LongTermDebtCurrent",),
            "debt_noncurrent": ("LongTermDebtNoncurrent",),
        }
        target_values: dict[str, float] = {}
        target_tags: dict[str, str] = {}
        target_hashes: dict[str, str] = {}
        flow_names = {
            "net_income",
            "interest_expense",
            "operating_income",
            "income_tax",
            "pretax_income",
        }
        selected_flow_record: dict[str, Any] | None = None
        for name, tags in routes.items():
            value, tag, record = _select_company_fact(
                facts,
                tags,
                accession=target_accession,
                end=target_end,
                flow=name in flow_names,
            )
            target_values[name] = value
            target_tags[name] = tag
            target_hashes[name] = _record_hash(record) if record else ""
            if target_hashes[name]:
                evidence_hashes.append(target_hashes[name])
            if name == "net_income":
                selected_flow_record = record
        observation_days = (
            (
                pd.Timestamp(selected_flow_record["end"])
                - pd.Timestamp(selected_flow_record["start"])
            ).days
            + 1
            if selected_flow_record
            else np.nan
        )
        year_days = 366 if isleap(pd.Timestamp(target_end).year) else 365
        nopat_routes = _annualized_nopat_routes(
            net_income=target_values["net_income"],
            interest_expense=target_values["interest_expense"],
            operating_income=target_values["operating_income"],
            income_tax=target_values["income_tax"],
            pretax_income=target_values["pretax_income"],
            observation_days=observation_days,
            year_days=year_days,
        )
        recognized_net_assets = ppa_assets - ppa_liabilities
        cash_proxy = target_values["cash"]
        acquired_capital = recognized_net_assets + assumed_debt - cash_proxy
        post_close_direct_operating_contribution = (
            acquiree_revenue - direct_operating_expense
        )
        output: dict[str, Any] = {
            "ticker": event["ticker"],
            "fiscal_year": int(event["fiscal_year"]),
            "event_name": event["event_name"],
            "event_type": event["event_type"],
            "event_close_date": event["event_close_date"],
            "target_cik": event["target_cik"],
            "target_entity_name": facts.get("entityName", ""),
            "target_balance_date": target_end,
            "target_accession": target_accession,
            "classification_phrase_proven": classification_proven,
            "acquiree_revenue_since_close_usd": acquiree_revenue,
            "acquiree_revenue_since_close_usd_source_tag": revenue_tag,
            "acquiree_revenue_since_close_usd_record_sha256": revenue_hash,
            "post_close_direct_operating_expense_usd": direct_operating_expense,
            "post_close_direct_operating_expense_source_tag": direct_cost_tag,
            "post_close_direct_operating_expense_record_sha256": direct_cost_hash,
            "post_close_direct_operating_source_dimension_status": (
                "DISCLOSURE_RECONCILED_XBRL_CONTEXT_DIFFERS_FROM_REVENUE_CONTEXT"
                if direct_cost_dim != operating_dim
                else "SAME_XBRL_CONTEXT_AS_ACQUIREE_REVENUE"
            ),
            "post_close_direct_operating_contribution_usd": post_close_direct_operating_contribution,
            "post_close_direct_operating_contribution_status": "NOT_NOPAT_DDA_GA_TAX_SCOPE_MISSING",
            "total_consideration_usd": consideration,
            "total_consideration_usd_source_tag": consideration_tag,
            "total_consideration_usd_record_sha256": consideration_hash,
            "recognized_net_assets_usd": recognized_net_assets,
            "ppa_assets_usd": ppa_assets,
            "ppa_assets_source_tag": ppa_assets_tag,
            "ppa_assets_record_sha256": ppa_assets_hash,
            "ppa_liabilities_usd": ppa_liabilities,
            "ppa_liabilities_source_tag": ppa_liabilities_tag,
            "ppa_liabilities_record_sha256": ppa_liabilities_hash,
            "assumed_long_term_debt_usd": assumed_debt,
            "assumed_long_term_debt_source_tag": assumed_debt_tag,
            "assumed_long_term_debt_record_sha256": assumed_debt_hash,
            "cash_acquired_proxy_usd": cash_proxy,
            "cash_acquired_proxy_semantics": "PUBLIC_TARGET_LAST_PREDEAL_BALANCE_NOT_PPA_CASH_FACT",
            "acquired_invested_capital_usd": acquired_capital,
            "acquired_capital_scope_complete": False,
            "acquired_capital_proxy_ready": True,
            "acquired_capital_semantics": "PPA_NET_ASSETS_PLUS_ASSUMED_DEBT_MINUS_PREDEAL_TARGET_CASH_PROXY",
            "predeal_ytd_net_income_usd": target_values["net_income"],
            "predeal_ytd_interest_expense_usd": target_values["interest_expense"],
            "predeal_ytd_operating_income_usd": target_values["operating_income"],
            "predeal_ytd_income_tax_usd": target_values["income_tax"],
            "predeal_ytd_pretax_income_usd": target_values["pretax_income"],
            "predeal_cash_usd": target_values["cash"],
            "predeal_equity_usd": target_values["equity"],
            "predeal_debt_current_usd": target_values["debt_current"],
            "predeal_debt_noncurrent_usd": target_values["debt_noncurrent"],
            "source_filing_date": pd.Timestamp(
                str(int(float(filing.iloc[0]["filed"])))
            ).date().isoformat(),
            "source_num_path": str(folder / "num.tsv"),
            "source_txt_path": str(folder / "txt.tsv"),
            "source_target_companyfacts_path": str(target_path),
            "source_evidence_bundle_sha256": hashlib.sha256(
                "|".join(sorted(evidence_hashes)).encode("ascii")
            ).hexdigest(),
            "target_evidence_record_count": len(evidence_hashes),
            "organic_company_roic_validated": False,
            "terminal_input_allowed": False,
            "research_only": True,
        }
        for name, tag in target_tags.items():
            output[f"predeal_{name}_source_tag"] = tag
            output[f"predeal_{name}_record_sha256"] = target_hashes[name]
        output.update(nopat_routes)
        output["triangulated_acquiree_nopat_return_proxy_pct"] = (
            nopat_routes["triangulated_nopat_midpoint_usd"]
            / acquired_capital
            * 100.0
            if nopat_routes["two_route_nopat_triangulated"]
            and acquired_capital > 0
            else np.nan
        )
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(
        drop=True
    )


def build_nopat_triangulation(
    *,
    acquisition_proof: pd.DataFrame,
    acquiree_nopat: pd.DataFrame,
    historical_evidence: pd.DataFrame,
) -> pd.DataFrame:
    nopat_lookup = acquiree_nopat.set_index(["ticker", "fiscal_year"])
    rows: list[dict[str, Any]] = []
    for event in acquisition_proof.to_dict("records"):
        ticker = str(event["ticker"])
        year = int(event["fiscal_year"])
        nap = nopat_lookup.loc[(ticker, year)]
        observation_days = event.get("predeal_ytd_ownership_days", np.nan)
        year_days = 366 if isleap(pd.Timestamp(str(event.get("target_balance_date") or f"{year}-12-31")).year) else 365
        routes = _annualized_nopat_routes(
            net_income=event.get("predeal_ytd_net_income_usd", np.nan),
            interest_expense=nap.get("predeal_ytd_interest_expense_usd", np.nan),
            operating_income=event.get("predeal_ytd_operating_income_usd", np.nan),
            income_tax=nap.get("predeal_ytd_income_tax_usd", np.nan),
            pretax_income=nap.get("predeal_ytd_pretax_income_usd", np.nan),
            observation_days=observation_days,
            year_days=year_days,
        )
        bridge_ready = bool(nap.get("acquiree_nopat_bridge_ready", False))
        bridge_value = nap.get(
            "acquiree_full_year_normalized_nopat_bridge_usd", np.nan
        )
        acquired_capital = event.get("acquired_invested_capital_usd", np.nan)
        rows.append(
            {
                "ticker": ticker,
                "fiscal_year": year,
                "event_name": event["event_name"],
                "target_public_companyfacts_available": bool(
                    event.get("target_public_companyfacts_available", False)
                ),
                "target_period_end": event.get("target_balance_date", ""),
                **routes,
                "evidence_backed_nopat_bridge": bridge_ready,
                "evidence_backed_nopat_bridge_usd": bridge_value,
                "evidence_backed_nopat_bridge_semantics": (
                    "POST_CLOSE_NET_INCOME_PLUS_PREDEAL_YIELD_AFTER_TAX_INTEREST_PROXY"
                    if bridge_ready
                    else str(nap.get("acquiree_nopat_bridge_status", ""))
                ),
                "acquired_invested_capital_usd": acquired_capital,
                "evidence_backed_acquisition_return_proxy_pct": (
                    bridge_value / acquired_capital * 100.0
                    if bridge_ready
                    and pd.notna(acquired_capital)
                    and acquired_capital > 0
                    else np.nan
                ),
                "triangulation_economic_run_rate_positive": bool(
                    routes["two_route_nopat_triangulated"]
                    and routes["triangulated_nopat_midpoint_usd"] > 0
                ),
                "direct_nopat_disclosed": False,
                "organic_company_roic_validated": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    for historical in historical_evidence.to_dict("records"):
        routes = {
            key: historical[key]
            for key in (
                "predeal_pretax_income_for_tax_rate_usd",
                "predeal_normalized_tax_rate",
                "predeal_normalized_tax_rate_source",
                "predeal_observation_days",
                "predeal_annualization_factor",
                "route_a_net_income_plus_after_tax_interest_usd",
                "route_b_operating_income_after_tax_usd",
                "route_a_b_symmetric_gap_pct",
                "triangulation_tolerance_pct",
                "two_route_nopat_triangulated",
                "triangulated_nopat_midpoint_usd",
                "triangulation_status",
            )
        }
        bridge_ready = bool(historical["two_route_nopat_triangulated"])
        bridge_value = historical["triangulated_nopat_midpoint_usd"]
        acquired_capital = historical["acquired_invested_capital_usd"]
        rows.append(
            {
                "ticker": historical["ticker"],
                "fiscal_year": int(historical["fiscal_year"]),
                "event_name": historical["event_name"],
                "target_public_companyfacts_available": True,
                "target_period_end": historical["target_balance_date"],
                **routes,
                "evidence_backed_nopat_bridge": bridge_ready,
                "evidence_backed_nopat_bridge_usd": bridge_value,
                "evidence_backed_nopat_bridge_semantics": "PREDEAL_TARGET_SAME_PERIOD_TWO_ROUTE_RUN_RATE_NOT_POST_CLOSE_CONTRIBUTION",
                "acquired_invested_capital_usd": acquired_capital,
                "evidence_backed_acquisition_return_proxy_pct": (
                    bridge_value / acquired_capital * 100.0
                    if bridge_ready and acquired_capital > 0
                    else np.nan
                ),
                "triangulation_economic_run_rate_positive": bool(
                    bridge_ready and bridge_value > 0
                ),
                "direct_nopat_disclosed": False,
                "organic_company_roic_validated": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(
        drop=True
    )
