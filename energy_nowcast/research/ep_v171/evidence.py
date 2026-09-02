from __future__ import annotations

from calendar import isleap
from datetime import date
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


FACT_ROUTES: dict[str, tuple[tuple[str, ...], str]] = {
    "acquiree_net_income_since_close_usd": (
        (
            "BusinessCombinationProFormaInformationEarningsOrLossOfAcquireeSinceAcquisitionDateActual",
            "NetIncomeLoss",
            "ProfitLoss",
        ),
        "operating_dimh",
    ),
    "acquiree_revenue_since_close_usd": (
        (
            "BusinessCombinationProFormaInformationRevenueOfAcquireeSinceAcquisitionDateActual",
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ),
        "operating_dimh",
    ),
    "total_consideration_usd": (
        ("BusinessCombinationConsiderationTransferred1",),
        "consideration_dimh",
    ),
    "equity_consideration_usd": (
        (
            "BusinessCombinationConsiderationTransferredEquityInterestsIssuedAndIssuable",
            "StockIssuedDuringPeriodValueAcquisitions",
        ),
        "equity_dimh",
    ),
    "recognized_net_assets_usd": (
        ("BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedNet",),
        "ppa_dimh",
    ),
    "assumed_long_term_debt_usd": (
        (
            "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedNoncurrentLiabilitiesLongTermDebt",
        ),
        "ppa_dimh",
    ),
    "cash_acquired_usd": (
        (
            "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedCashAndEquivalents",
            "CashAcquiredFromAcquisition",
        ),
        "ppa_dimh",
    ),
    "asset_acquisition_ppe_usd": (
        (
            "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedPropertyPlantAndEquipment",
        ),
        "ppa_dimh",
    ),
}
TRANSACTION_COST_TAGS = (
    "BusinessCombinationAcquisitionRelatedCosts",
    "BusinessAcquisitionCostOfAcquiredEntityTransactionCosts",
)
INTEGRATION_COST_TAGS = ("RestructuringCosts", "RestructuringCharges")

BALANCE_ROUTES: dict[str, tuple[str, ...]] = {
    "predeal_equity_usd": (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
    "predeal_debt_current_usd": ("LongTermDebtCurrent",),
    "predeal_debt_noncurrent_usd": ("LongTermDebtNoncurrent",),
    "predeal_short_term_borrowings_usd": ("ShortTermBorrowings",),
    "predeal_cash_usd": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
}
FLOW_ROUTES: dict[str, tuple[str, ...]] = {
    "predeal_ytd_operating_income_usd": ("OperatingIncomeLoss",),
    "predeal_ytd_net_income_usd": ("NetIncomeLoss", "ProfitLoss"),
}


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _filing_row(folder: Path, adsh: str) -> pd.Series:
    submissions = pd.read_csv(folder / "sub.tsv", sep="\t", low_memory=False)
    filing = submissions.loc[submissions["adsh"].astype(str).eq(adsh)]
    if len(filing) != 1:
        raise ValueError(f"Expected one FNSD submission for {adsh}, found {len(filing)}")
    row = filing.iloc[0]
    if str(row["form"]) != "10-K":
        raise ValueError(f"Proof source must be a 10-K: {adsh}")
    return row


def _company_fact(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    *,
    accession: str,
    end: str,
    flow: bool = False,
) -> tuple[float, str, dict[str, Any] | None]:
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    for route_priority, tag in enumerate(tags):
        records = facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
        for record in records:
            if record.get("accn") != accession or record.get("end") != end:
                continue
            duration = 0
            if flow and record.get("start"):
                duration = (pd.Timestamp(end) - pd.Timestamp(record["start"])).days + 1
            candidates.append((-route_priority, duration, record, tag))
    if not candidates:
        return np.nan, "", None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, selected, tag = candidates[0]
    selected_with_tag = dict(selected)
    selected_with_tag["tag"] = tag
    return float(selected["val"]), tag, selected_with_tag


def _target_predeal_proof(
    *, companyfacts_root: Path, event: dict[str, Any]
) -> dict[str, Any]:
    cik = str(event.get("target_cik") or "")
    if not cik or cik == "PRIVATE_UNAVAILABLE":
        return {
            "target_public_companyfacts_available": False,
            "predeal_book_basis_status": "LOCKED_PRIVATE_TARGET_PREDEAL_BOOK_BASIS_UNAVAILABLE",
        }
    target_path = companyfacts_root / f"CIK{cik.zfill(10)}.json"
    facts = json.loads(target_path.read_text(encoding="utf-8"))
    accession = str(event["target_accession"])
    balance_date = str(event["target_balance_date"])
    output: dict[str, Any] = {
        "target_public_companyfacts_available": True,
        "target_entity_name": facts.get("entityName", ""),
        "predeal_balance_date": balance_date,
        "predeal_accession": accession,
        "predeal_companyfacts_path": str(target_path),
    }
    hashes: list[str] = []
    source_records: list[dict[str, Any]] = []
    for name, tags in BALANCE_ROUTES.items():
        value, tag, record = _company_fact(
            facts, tags, accession=accession, end=balance_date
        )
        output[name] = value
        output[f"{name}_source_tag"] = tag
        output[f"{name}_record_sha256"] = _record_hash(record) if record else ""
        if record:
            hashes.append(output[f"{name}_record_sha256"])
            source_records.append(record)
    for name, tags in FLOW_ROUTES.items():
        value, tag, record = _company_fact(
            facts, tags, accession=accession, end=balance_date, flow=True
        )
        output[name] = value
        output[f"{name}_source_tag"] = tag
        output[f"{name}_record_sha256"] = _record_hash(record) if record else ""
        if record:
            hashes.append(output[f"{name}_record_sha256"])
            source_records.append(record)

    equity = output["predeal_equity_usd"]
    debt_parts = [
        output["predeal_debt_current_usd"],
        output["predeal_debt_noncurrent_usd"],
        output["predeal_short_term_borrowings_usd"],
    ]
    debt = sum(value for value in debt_parts if pd.notna(value))
    cash = output["predeal_cash_usd"]
    balance_complete = pd.notna(equity) and pd.notna(cash) and any(
        pd.notna(value) for value in debt_parts
    )
    output["predeal_total_debt_usd"] = debt if balance_complete else np.nan
    output["predeal_book_invested_capital_usd"] = (
        equity + debt - cash if balance_complete else np.nan
    )
    filed_dates = {str(record.get("filed", "")) for record in source_records}
    output["predeal_filing_date"] = max(filed_dates) if filed_dates else ""
    output["predeal_filed_before_close"] = bool(
        filed_dates
        and pd.Timestamp(output["predeal_filing_date"])
        < pd.Timestamp(str(event["event_close_date"]))
    )
    output["predeal_book_basis_status"] = (
        "PROVEN_PUBLIC_TARGET_LAST_PREDEAL_10Q"
        if balance_complete and output["predeal_filed_before_close"]
        else "LOCKED_INCOMPLETE_OR_NOT_POINT_IN_TIME_PREDEAL_BOOK_BASIS"
    )
    net_income_record = next(
        (
            record
            for record in source_records
            if record.get("tag") in FLOW_ROUTES["predeal_ytd_net_income_usd"]
            and record.get("start")
        ),
        None,
    )
    if net_income_record:
        duration = (
            pd.Timestamp(net_income_record["end"])
            - pd.Timestamp(net_income_record["start"])
        ).days + 1
        year_days = 366 if isleap(pd.Timestamp(balance_date).year) else 365
        output["predeal_ytd_ownership_days"] = duration
        output["predeal_ytd_net_income_annualized_usd"] = (
            output["predeal_ytd_net_income_usd"] * year_days / duration
        )
    else:
        output["predeal_ytd_ownership_days"] = np.nan
        output["predeal_ytd_net_income_annualized_usd"] = np.nan
    output["predeal_operating_contribution_comparability_status"] = (
        "DIAGNOSTIC_TARGET_GAAP_VS_ACQUIRER_POST_CLOSE_NET_INCOME_NOT_SAME_PERIMETER"
        if pd.notna(output.get("predeal_ytd_operating_income_usd"))
        else "LOCKED_NO_PREDEAL_OPERATING_CONTRIBUTION"
    )
    output["predeal_evidence_bundle_sha256"] = hashlib.sha256(
        "|".join(sorted(hashes)).encode("ascii")
    ).hexdigest()
    return output


def build_acquisition_proof(
    *, registry_path: Path, fnsd_root: Path, companyfacts_root: Path
) -> pd.DataFrame:
    registry = pd.read_csv(registry_path, dtype=str, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    numeric_cache: dict[tuple[Path, str], list[dict[str, str]]] = {}
    text_cache: dict[tuple[Path, str], list[dict[str, str]]] = {}
    for event in registry.to_dict("records"):
        folder = fnsd_root / event["fnsd_folder"]
        adsh = event["adsh"]
        filing = _filing_row(folder, adsh)
        num_key = (folder / "num.tsv", adsh)
        txt_key = (folder / "txt.tsv", adsh)
        numeric_cache.setdefault(num_key, _adsh_records(*num_key))
        text_cache.setdefault(txt_key, _adsh_records(*txt_key))
        numeric = numeric_cache[num_key]
        text_records = text_cache[txt_key]
        output: dict[str, Any] = dict(event)
        output["fiscal_year"] = int(event["fiscal_year"])
        hashes: list[str] = []
        for name, (tags, dimension_column) in FACT_ROUTES.items():
            dimension = event.get(dimension_column, "")
            if dimension:
                value, tag, record_hash = _select_numeric_fact(
                    numeric, tags, dimension_hash=dimension
                )
            else:
                value, tag, record_hash = np.nan, "", ""
            output[name] = value
            output[f"{name}_source_tag"] = tag
            output[f"{name}_record_sha256"] = record_hash
            if record_hash:
                hashes.append(record_hash)
        for name, tags, dimension_column in (
            ("acquisition_related_cost_usd", TRANSACTION_COST_TAGS, "transaction_cost_dimh"),
            ("integration_restructuring_cost_usd", INTEGRATION_COST_TAGS, "integration_cost_dimh"),
        ):
            dimension = event.get(dimension_column, "")
            if dimension:
                value, tag, record_hash = _select_numeric_fact(
                    numeric, tags, dimension_hash=dimension
                )
            else:
                value, tag, record_hash = np.nan, "", ""
            output[name] = value
            output[f"{name}_source_tag"] = tag
            output[f"{name}_record_sha256"] = record_hash
            if record_hash:
                hashes.append(record_hash)

        disclosure, disclosure_hash = _select_text_record(
            text_records, event["classification_text_tag"]
        )
        output["classification_phrase_proven"] = (
            event["classification_phrase"].casefold() in disclosure.casefold()
        )
        output["classification_disclosure_record_sha256"] = disclosure_hash
        if disclosure_hash:
            hashes.append(disclosure_hash)
        output.update(
            _target_predeal_proof(
                companyfacts_root=companyfacts_root, event=event
            )
        )
        if output.get("predeal_evidence_bundle_sha256"):
            hashes.append(str(output["predeal_evidence_bundle_sha256"]))

        close = pd.Timestamp(event["event_close_date"])
        fiscal_end = pd.Timestamp(date(close.year, 12, 31))
        ownership_days = (fiscal_end - close).days + 1
        fiscal_days = 366 if isleap(close.year) else 365
        output["ownership_days_in_fiscal_year"] = ownership_days
        output["fiscal_year_days"] = fiscal_days
        output["ownership_fraction"] = ownership_days / fiscal_days
        post_close_net_income = output["acquiree_net_income_since_close_usd"]
        post_close_revenue = output["acquiree_revenue_since_close_usd"]
        output["full_year_normalized_acquiree_net_income_usd"] = (
            post_close_net_income / output["ownership_fraction"]
            if pd.notna(post_close_net_income)
            else np.nan
        )
        output["full_year_normalized_acquiree_revenue_usd"] = (
            post_close_revenue / output["ownership_fraction"]
            if pd.notna(post_close_revenue)
            else np.nan
        )
        output["ownership_normalization_status"] = (
            "NORMALIZED_CALENDAR_DAYS_POST_CLOSE_NET_INCOME_PROXY_NOT_NOPAT"
            if pd.notna(post_close_net_income)
            else "LOCKED_NO_SEPARATE_POST_CLOSE_NET_INCOME"
        )

        business = event["event_type"] == "business_combination"
        net_assets = output["recognized_net_assets_usd"]
        debt = output["assumed_long_term_debt_usd"]
        acquired_cash = output["cash_acquired_usd"]
        ppa_scope_complete = business and all(
            pd.notna(value) for value in (net_assets, debt, acquired_cash)
        )
        if ppa_scope_complete:
            acquired_capital = net_assets + debt - acquired_cash
            capital_semantics = "PPA_NET_ASSETS_PLUS_ASSUMED_DEBT_MINUS_ACQUIRED_CASH"
        elif business and pd.notna(net_assets):
            acquired_capital = net_assets
            capital_semantics = "PPA_NET_ASSETS_PROXY_MISSING_EXPLICIT_DEBT_OR_CASH"
        elif event["event_type"] == "asset_acquisition" and pd.notna(
            output["asset_acquisition_ppe_usd"]
        ):
            acquired_capital = output["asset_acquisition_ppe_usd"]
            capital_semantics = "ASSET_ACQUISITION_PPE_ONLY_LOWER_BOUND"
        else:
            acquired_capital = np.nan
            capital_semantics = "LOCKED_NO_ACQUIRED_CAPITAL_EVIDENCE"
        output["acquired_invested_capital_usd"] = acquired_capital
        output["acquired_capital_scope_complete"] = ppa_scope_complete
        output["acquired_capital_semantics"] = capital_semantics
        predeal_book = output.get("predeal_book_invested_capital_usd", np.nan)
        step_up_proven = ppa_scope_complete and pd.notna(predeal_book)
        output["purchase_accounting_step_up_usd"] = (
            acquired_capital - predeal_book if step_up_proven else np.nan
        )
        output["purchase_accounting_step_up_pct_of_predeal_book"] = (
            output["purchase_accounting_step_up_usd"] / predeal_book * 100.0
            if step_up_proven and predeal_book != 0
            else np.nan
        )
        output["purchase_accounting_step_up_proven"] = step_up_proven
        output["purchase_accounting_step_up_status"] = (
            "PROVEN_PPA_ECONOMIC_CAPITAL_MINUS_PUBLIC_TARGET_PREDEAL_BOOK_CAPITAL"
            if step_up_proven
            else (
                "LOCKED_PPA_DEBT_OR_CASH_SCOPE_INCOMPLETE"
                if business and pd.notna(predeal_book)
                else str(output.get("predeal_book_basis_status", "LOCKED_NO_PREDEAL_BOOK_BASIS"))
            )
        )
        output["normalized_acquiree_return_proxy_pct"] = (
            output["full_year_normalized_acquiree_net_income_usd"]
            / acquired_capital
            * 100.0
            if business
            and ppa_scope_complete
            and pd.notna(output["full_year_normalized_acquiree_net_income_usd"])
            and acquired_capital > 0
            else np.nan
        )
        output["normalized_acquiree_return_semantics"] = (
            "FULL_YEAR_NORMALIZED_NET_INCOME_OVER_PPA_ECONOMIC_CAPITAL_NOT_NOPAT_ROIC"
            if pd.notna(output["normalized_acquiree_return_proxy_pct"])
            else "LOCKED_INCOMPLETE_NUMERATOR_OR_CAPITAL_SCOPE"
        )
        output["acquired_nopat_directly_disclosed"] = False
        output["organic_company_roic_validated"] = False
        output["terminal_input_allowed"] = False
        output["filing_date"] = pd.Timestamp(
            str(int(float(filing["filed"])))
        ).date().isoformat()
        output["source_form"] = str(filing["form"])
        output["source_num_path"] = str(folder / "num.tsv")
        output["source_txt_path"] = str(folder / "txt.tsv")
        output["source_evidence_bundle_sha256"] = hashlib.sha256(
            "|".join(sorted(hashes)).encode("ascii")
        ).hexdigest()
        output["research_only"] = True
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(drop=True)


def _display_amount_present(disclosure: str, value: float) -> bool:
    millions = value / 1_000_000.0
    million_text = f"$ {millions:,.0f} million"
    compact_million_text = f"${millions:,.0f} million"
    billions = value / 1_000_000_000.0
    billion_text = f"$ {billions:.1f} billion"
    compact_billion_text = f"${billions:.1f} billion"
    normalized = " ".join(disclosure.split())
    return any(
        candidate in normalized
        for candidate in (
            million_text,
            compact_million_text,
            billion_text,
            compact_billion_text,
        )
    )


def build_divestiture_proof(
    *, registry_path: Path, fnsd_root: Path, annual_organic: pd.DataFrame
) -> pd.DataFrame:
    registry = pd.read_csv(registry_path, dtype={"adsh": str})
    rows: list[dict[str, Any]] = []
    for event in registry.to_dict("records"):
        folder = fnsd_root / str(event["fnsd_folder"])
        adsh = str(event["adsh"])
        filing = _filing_row(folder, adsh)
        disclosure, disclosure_hash = _select_text_record(
            _adsh_records(folder / "txt.tsv", adsh), str(event["text_tag"])
        )
        annual = annual_organic.loc[
            annual_organic["ticker"].eq(event["ticker"])
            & annual_organic["year"].eq(int(event["fiscal_year"]))
        ]
        if len(annual) != 1:
            raise ValueError(f"Missing annual tax row for divestiture {event['event_name']}")
        tax_rate = float(annual.iloc[0]["effective_tax_rate"])
        output = dict(event)
        output["classification_phrase_proven"] = (
            str(event["proof_phrase"]).casefold() in disclosure.casefold()
        )
        output["numeric_values_reconciled_to_disclosure"] = all(
            _display_amount_present(disclosure, float(event[column]))
            for column in (
                "net_proceeds_usd",
                "divested_book_invested_capital_usd",
                "pre_tax_operating_contribution_usd",
            )
        )
        output["effective_tax_rate"] = tax_rate
        output["divested_after_tax_operating_contribution_proxy_usd"] = (
            float(event["pre_tax_operating_contribution_usd"])
            * (1.0 - np.clip(tax_rate, 0.0, 0.35))
        )
        output["divested_nopat_directly_disclosed"] = False
        output["divestiture_proof_status"] = (
            "BOOK_CAPITAL_AND_AFTER_TAX_EARNINGS_PROXY_PROVEN_NOT_NOPAT"
            if output["classification_phrase_proven"]
            and output["numeric_values_reconciled_to_disclosure"]
            else "LOCKED_DISCLOSURE_RECONCILIATION_FAILED"
        )
        output["filing_date"] = pd.Timestamp(
            str(int(float(filing["filed"])))
        ).date().isoformat()
        output["source_form"] = str(filing["form"])
        output["source_disclosure_record_sha256"] = disclosure_hash
        output["source_txt_path"] = str(folder / "txt.tsv")
        output["research_only"] = True
        output["terminal_input_allowed"] = False
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(drop=True)
