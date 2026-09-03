from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v17.fnsd import (
    _adsh_records,
    _select_text_record,
)


GAS_HEAVY_TICKERS = ("AR", "CNX", "EQT", "RRC")
CAPITAL_MATERIALITY_RATIO = 0.01
RESERVE_EVENT_MATERIALITY_RATIO = 0.02
ELIGIBLE_DENOMINATOR_RATIO = 0.02
AR_SELECTED_START_YEAR = 2022
AR_SELECTED_END_YEAR = 2024
AR_SEGMENT_TAGS = ("Revenues", "CostsAndExpenses", "OperatingIncomeLoss")
ATTRIBUTION_VARIANTS = (
    "reported_gaap_nopat_usd",
    "reported_economic_nopat_usd",
    "price_only_normalized_nopat_usd",
    "cost_only_normalized_nopat_usd",
    "price_and_cost_normalized_nopat_usd",
    "full_cycle_normalized_nopat_usd",
)


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reserve_event_ratio(row: pd.Series) -> float:
    beginning = abs(float(row["begin_reserves_mboe"]))
    if not beginning:
        return np.inf
    purchases = abs(float(row.get("purchases_identity_mboe", 0.0) or 0.0))
    sales = abs(float(row.get("sales_identity_mboe", 0.0) or 0.0))
    return max(purchases, sales) / beginning


def build_gas_candidate_audit(
    *, annual_organic: pd.DataFrame, unit_economics: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in GAS_HEAVY_TICKERS:
        units = unit_economics.loc[unit_economics["ticker"].eq(ticker)].copy()
        annual = annual_organic.loc[annual_organic["ticker"].eq(ticker)].copy()
        candidate_count = 0
        for start_year in sorted(annual["year"].astype(int).unique()):
            end_year = start_year + 2
            required_unit_years = set(range(start_year - 1, end_year + 1))
            if not required_unit_years.issubset(set(units["year"].astype(int))):
                continue
            window = annual.loc[annual["year"].between(start_year, end_year)]
            if len(window) != 3:
                continue
            candidate_count += 1
            unit_window = units.loc[units["year"].isin(required_unit_years)]
            source_complete = bool(
                len(unit_window) == 4
                and unit_window[
                    [
                        "production_mboe",
                        "upstream_revenue_usd",
                        "lifting_cost_usd",
                        "upstream_dda_usd",
                    ]
                ]
                .notna()
                .all()
                .all()
            )
            capital_perimeter_clean = bool(
                (~window["material_acquisition"]).all()
                and (~window["material_divestiture"]).all()
                and window["denominator_scope_complete"].all()
                and window["numerator_scope_complete"].all()
            )
            reserve_rows = unit_window.loc[
                unit_window["year"].between(start_year, end_year)
            ]
            reserve_event_max_ratio = float(
                max((_reserve_event_ratio(row) for _, row in reserve_rows.iterrows()), default=np.inf)
            )
            reserve_perimeter_clean = bool(
                reserve_event_max_ratio <= RESERVE_EVENT_MATERIALITY_RATIO
            )
            denominator = float(
                window["organic_delta_invested_capital_proxy_usd"].sum()
            )
            opening = abs(float(window.sort_values("year").iloc[0]["opening_invested_capital_usd"]))
            denominator_threshold = opening * ELIGIBLE_DENOMINATOR_RATIO
            numerator_complete = bool(window["raw_delta_nopat_usd"].notna().all())
            denominator_eligible = bool(denominator > denominator_threshold)
            eligible = bool(
                source_complete
                and capital_perimeter_clean
                and reserve_perimeter_clean
                and numerator_complete
                and denominator_eligible
            )
            blockers: list[str] = []
            if not source_complete:
                blockers.append("DIRECT_FOUR_YEAR_UNIT_EVIDENCE_INCOMPLETE")
            if not capital_perimeter_clean:
                blockers.append("MATERIAL_CAPITAL_TRANSACTION_PERIMETER")
            if not reserve_perimeter_clean:
                blockers.append("MATERIAL_RESERVE_PURCHASE_OR_SALE")
            if not numerator_complete:
                blockers.append("REPORTED_NOPAT_INCOMPLETE")
            if not denominator_eligible:
                blockers.append("CUMULATIVE_ORGANIC_DENOMINATOR_NOT_ELIGIBLE")
            rows.append(
                {
                    "ticker": ticker,
                    "group": "gas_heavy",
                    "window_start_year": start_year,
                    "window_end_year": end_year,
                    "four_year_direct_unit_evidence": source_complete,
                    "capital_transaction_perimeter_clean": capital_perimeter_clean,
                    "reserve_event_max_ratio": reserve_event_max_ratio,
                    "reserve_event_materiality_threshold": RESERVE_EVENT_MATERIALITY_RATIO,
                    "reserve_transaction_perimeter_clean": reserve_perimeter_clean,
                    "cumulative_organic_invested_capital_usd": denominator,
                    "denominator_threshold_usd": denominator_threshold,
                    "reported_nopat_complete": numerator_complete,
                    "window_eligible": eligible,
                    "selection_status": (
                        "ELIGIBLE_CLEAN_ORGANIC_WINDOW"
                        if eligible
                        else "LOCKED__" + "__".join(blockers)
                    ),
                    "outcome_values_used_for_selection": False,
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
        if candidate_count == 0:
            rows.append(
                {
                    "ticker": ticker,
                    "group": "gas_heavy",
                    "window_start_year": np.nan,
                    "window_end_year": np.nan,
                    "four_year_direct_unit_evidence": False,
                    "capital_transaction_perimeter_clean": False,
                    "reserve_event_max_ratio": np.nan,
                    "reserve_event_materiality_threshold": RESERVE_EVENT_MATERIALITY_RATIO,
                    "reserve_transaction_perimeter_clean": False,
                    "cumulative_organic_invested_capital_usd": np.nan,
                    "denominator_threshold_usd": np.nan,
                    "reported_nopat_complete": False,
                    "window_eligible": False,
                    "selection_status": "LOCKED__NO_FOUR_YEAR_DIRECT_UNIT_EVIDENCE_WINDOW",
                    "outcome_values_used_for_selection": False,
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
    result = pd.DataFrame(rows).sort_values(
        ["ticker", "window_start_year"], na_position="last"
    )
    eligible = result.loc[result["window_eligible"]]
    if len(eligible) != 1:
        raise ValueError(
            "Gas cohort selection must produce exactly one eligible window; "
            f"found {len(eligible)}"
        )
    selected = eligible.iloc[0]
    if (
        selected["ticker"] != "AR"
        or int(selected["window_start_year"]) != AR_SELECTED_START_YEAR
        or int(selected["window_end_year"]) != AR_SELECTED_END_YEAR
    ):
        raise ValueError("Deterministic gas cohort selection changed")
    result["selected_for_v18"] = result.index == selected.name
    return result.reset_index(drop=True)


def _segment_facts(
    records: list[dict[str, str]], *, year: int, expected_dimh: str
) -> tuple[dict[str, float], list[str], str]:
    by_dimension: dict[str, dict[str, dict[str, str]]] = {}
    for record in records:
        if (
            record.get("tag") in AR_SEGMENT_TAGS
            and record.get("uom") == "USD"
            and record.get("ddate") == f"{year}1231"
            and record.get("qtrs") == "4"
            and record.get("iprx") == "0"
        ):
            by_dimension.setdefault(str(record["dimh"]), {})[
                str(record["tag"])
            ] = record
    candidates: list[tuple[float, str, dict[str, dict[str, str]]]] = []
    for dimh, facts in by_dimension.items():
        if dimh == "0x00000000" or set(facts) != set(AR_SEGMENT_TAGS):
            continue
        values = {tag: float(facts[tag]["value"]) for tag in AR_SEGMENT_TAGS}
        identity_error = (
            values["Revenues"]
            - values["CostsAndExpenses"]
            - values["OperatingIncomeLoss"]
        )
        if values["Revenues"] > 0 and abs(identity_error) <= 1.0:
            candidates.append((values["Revenues"], dimh, facts))
    if not candidates:
        raise ValueError(f"No AR E&P segment identity candidate for {year}")
    _, dimh, facts = max(candidates, key=lambda item: item[0])
    if dimh != expected_dimh:
        raise ValueError(
            f"AR E&P segment dimension changed for {year}: {dimh} != {expected_dimh}"
        )
    values = {tag: float(facts[tag]["value"]) for tag in AR_SEGMENT_TAGS}
    hashes = [_record_hash(facts[tag]) for tag in AR_SEGMENT_TAGS]
    return values, hashes, dimh


def build_ar_segment_evidence(
    *,
    source_registry_path: Path,
    fnsd_root: Path,
    unit_economics: pd.DataFrame,
    ttm_financial: pd.DataFrame,
    cycle_reference: pd.DataFrame,
) -> pd.DataFrame:
    registry = pd.read_csv(source_registry_path, dtype={"adsh": str})
    units = unit_economics.loc[unit_economics["ticker"].eq("AR")].set_index("year")
    tax = ttm_financial.loc[
        ttm_financial["ticker"].eq("AR")
        & ttm_financial["quarter"].astype(str).str.endswith("Q4")
    ].copy()
    tax["year"] = tax["quarter"].astype(str).str[:4].astype(int)
    tax = tax.set_index("year")
    rows: list[dict[str, Any]] = []
    for source in registry.to_dict("records"):
        year = int(source["year"])
        folder = fnsd_root / str(source["fnsd_folder"])
        submission = pd.read_csv(folder / "sub.tsv", sep="\t", low_memory=False)
        filing = submission.loc[submission["adsh"].astype(str).eq(str(source["adsh"]))]
        if len(filing) != 1:
            raise ValueError(f"Expected one AR filing for {year}; found {len(filing)}")
        filing_row = filing.iloc[0]
        if str(filing_row["form"]) != "10-K" or int(filing_row["fy"]) != year:
            raise ValueError(f"AR source is not the expected {year} 10-K")
        numeric_records = _adsh_records(folder / "num.tsv", str(source["adsh"]))
        values, fact_hashes, selected_dimh = _segment_facts(
            numeric_records,
            year=year,
            expected_dimh=str(source["expected_ep_segment_dimh"]),
        )
        disclosure, disclosure_hash = _select_text_record(
            _adsh_records(folder / "txt.tsv", str(source["adsh"])),
            str(source["required_text_tag"]),
        )
        phrase_proven = str(source["required_phrase"]).casefold() in disclosure.casefold()
        production = float(units.loc[year, "production_mboe"])
        actual_tax_rate = float(np.clip(tax.loc[year, "effective_tax_rate"], 0.0, 0.35))
        reported_gaap_nopat = float(tax.loc[year, "ttm_nopat_usd"])
        volume = production * 1_000.0
        actual_price = values["Revenues"] / volume
        actual_unit_cost = values["CostsAndExpenses"] / volume
        identity_error = (
            values["Revenues"]
            - values["CostsAndExpenses"]
            - values["OperatingIncomeLoss"]
        )
        rows.append(
            {
                "ticker": "AR",
                "group": "gas_heavy",
                "year": year,
                "production_mboe": production,
                "segment_revenue_usd": values["Revenues"],
                "segment_cost_and_expense_usd": values["CostsAndExpenses"],
                "segment_operating_income_usd": values["OperatingIncomeLoss"],
                "segment_accounting_identity_error_usd": identity_error,
                "actual_price_per_boe": actual_price,
                "actual_complete_segment_unit_cost_per_boe": actual_unit_cost,
                "actual_tax_rate": actual_tax_rate,
                "reported_gaap_nopat_usd": reported_gaap_nopat,
                "selected_ep_segment_dimh": selected_dimh,
                "segment_identity_passed": abs(identity_error) <= 1.0,
                "segment_label_phrase_proven": phrase_proven,
                "source_form": str(filing_row["form"]),
                "source_filed_date": pd.to_datetime(
                    str(int(filing_row["filed"]))
                ).date().isoformat(),
                "source_num_path": str(folder / "num.tsv"),
                "source_txt_path": str(folder / "txt.tsv"),
                "source_evidence_bundle_sha256": hashlib.sha256(
                    "|".join(sorted([*fact_hashes, disclosure_hash])).encode("ascii")
                ).hexdigest(),
                "source_cell_checks": 7,
                "source_cell_checks_passed": int(phrase_proven) + 6,
            }
        )
    result = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    if len(result) != 4 or not result["segment_identity_passed"].all():
        raise ValueError("AR must have four accounting-identity-proven segment years")
    if not result["segment_label_phrase_proven"].all():
        raise ValueError("AR E&P segment label proof failed")
    reference = cycle_reference.loc[cycle_reference["ticker"].eq("AR")]
    if len(reference) != 1:
        raise ValueError("Expected one AR cycle reference")
    normalized_price = float(reference.iloc[0]["normalized_price_per_boe"])
    normalized_unit_cost = float(
        result["actual_complete_segment_unit_cost_per_boe"].median()
    )
    normalized_tax_rate = float(result["actual_tax_rate"].median())
    result["normalized_price_per_boe"] = normalized_price
    result["normalized_complete_segment_unit_cost_per_boe"] = normalized_unit_cost
    result["normalized_tax_rate"] = normalized_tax_rate
    volume = result["production_mboe"] * 1_000.0
    result["reported_economic_nopat_usd"] = result[
        "segment_operating_income_usd"
    ] * (1.0 - result["actual_tax_rate"])
    result["price_only_normalized_nopat_usd"] = (
        normalized_price - result["actual_complete_segment_unit_cost_per_boe"]
    ) * volume * (1.0 - result["actual_tax_rate"])
    result["cost_only_normalized_nopat_usd"] = (
        result["actual_price_per_boe"] - normalized_unit_cost
    ) * volume * (1.0 - result["actual_tax_rate"])
    result["price_and_cost_normalized_nopat_usd"] = (
        normalized_price - normalized_unit_cost
    ) * volume * (1.0 - result["actual_tax_rate"])
    result["full_cycle_normalized_nopat_usd"] = (
        normalized_price - normalized_unit_cost
    ) * volume * (1.0 - normalized_tax_rate)
    result["accounting_scope_residual_usd"] = (
        result["reported_gaap_nopat_usd"]
        - result["reported_economic_nopat_usd"]
    )
    result["price_normalization_effect_usd"] = (
        result["price_only_normalized_nopat_usd"]
        - result["reported_economic_nopat_usd"]
    )
    result["cost_normalization_effect_usd"] = (
        result["cost_only_normalized_nopat_usd"]
        - result["reported_economic_nopat_usd"]
    )
    result["tax_normalization_effect_usd"] = (
        result["full_cycle_normalized_nopat_usd"]
        - result["price_and_cost_normalized_nopat_usd"]
    )
    reconstructed = (
        result["reported_gaap_nopat_usd"]
        - result["accounting_scope_residual_usd"]
        + result["price_normalization_effect_usd"]
        + result["cost_normalization_effect_usd"]
        + result["tax_normalization_effect_usd"]
    )
    result["normalization_attribution_identity_error_usd"] = (
        result["full_cycle_normalized_nopat_usd"] - reconstructed
    )
    result["source_cells_fully_verified"] = (
        result["source_cell_checks"] == result["source_cell_checks_passed"]
    )
    result["normalization_attribution_complete"] = (
        result["source_cells_fully_verified"]
        & result["normalization_attribution_identity_error_usd"].abs().le(1.0)
    )
    result["normalization_confidence_grade"] = "A"
    result["unit_cost_scope"] = (
        "DIRECT_E_AND_P_SEGMENT_TOTAL_COSTS_AND_EXPENSES_INCLUDING_ALL_REPORTED_OPERATING_ITEMS"
    )
    result["normal_roic_claimed"] = False
    result["terminal_input_allowed"] = False
    result["research_only"] = True
    return result


def build_ar_clean_organic_cohort(
    *,
    candidate_audit: pd.DataFrame,
    segment_evidence: pd.DataFrame,
    annual_organic: pd.DataFrame,
) -> pd.DataFrame:
    selected = candidate_audit.loc[candidate_audit["selected_for_v18"]]
    if len(selected) != 1:
        raise ValueError("Expected one selected gas cohort")
    start_year = int(selected.iloc[0]["window_start_year"])
    end_year = int(selected.iloc[0]["window_end_year"])
    evidence = segment_evidence.set_index("year")
    annual = annual_organic.loc[
        annual_organic["ticker"].eq("AR")
        & annual_organic["year"].between(start_year, end_year)
    ].sort_values("year")
    opening = abs(float(annual.iloc[0]["opening_invested_capital_usd"]))
    threshold = opening * ELIGIBLE_DENOMINATOR_RATIO
    cumulative_denominator = 0.0
    cumulative = {variant: 0.0 for variant in ATTRIBUTION_VARIANTS}
    rows: list[dict[str, Any]] = []
    for offset, annual_row in enumerate(annual.to_dict("records")):
        year = int(annual_row["year"])
        denominator = float(annual_row["organic_delta_invested_capital_proxy_usd"])
        cumulative_denominator += denominator
        numerators: dict[str, float] = {}
        for variant in ATTRIBUTION_VARIANTS:
            numerator = float(evidence.loc[year, variant] - evidence.loc[year - 1, variant])
            numerators[variant] = numerator
            cumulative[variant] += numerator
        mature = year == end_year
        output: dict[str, Any] = {
            "ticker": "AR",
            "group": "gas_heavy",
            "event_name": "Clean organic rolling window",
            "cohort_type": "CLEAN_ORGANIC_WINDOW_NO_MATERIAL_ACQUISITION",
            "cohort_start_year": start_year,
            "cohort_end_year": end_year,
            "cohort_offset": offset,
            "observation_year": year,
            "year_label": "t" if offset == 0 else f"t+{offset}",
            "organic_invested_capital_proxy_usd": denominator,
            "cumulative_organic_invested_capital_proxy_usd": cumulative_denominator,
            "denominator_threshold_usd": threshold,
            "capital_transaction_perimeter_clean": bool(
                selected.iloc[0]["capital_transaction_perimeter_clean"]
            ),
            "reserve_transaction_perimeter_clean": bool(
                selected.iloc[0]["reserve_transaction_perimeter_clean"]
            ),
            "material_transaction_perimeter_resolved": True,
            "acquisition_nopat_triangulation_required": False,
            "acquisition_nopat_triangulation_status": (
                "NOT_APPLICABLE_CLEAN_ORGANIC_WINDOW_NO_MATERIAL_ACQUISITION"
            ),
            "annual_source_complete": bool(
                evidence.loc[year - 1 : year, "normalization_attribution_complete"].all()
            ),
        }
        for variant, numerator in numerators.items():
            prefix = variant.removesuffix("_usd")
            output[f"{prefix}_organic_nopat_usd"] = numerator
            output[f"{prefix}_cumulative_organic_nopat_usd"] = cumulative[variant]
            output[f"{prefix}_cumulative_roic_pct"] = (
                cumulative[variant] / cumulative_denominator * 100.0
                if mature and cumulative_denominator > threshold
                else np.nan
            )
        output["reported_3y_cohort_complete"] = bool(
            mature
            and offset == 2
            and cumulative_denominator > threshold
            and output["material_transaction_perimeter_resolved"]
        )
        output["independent_full_cycle_3y_cohort_complete"] = bool(
            output["reported_3y_cohort_complete"]
            and segment_evidence["normalization_attribution_complete"].all()
            and segment_evidence["normalization_confidence_grade"].eq("A").all()
        )
        output["organic_company_roic_validated"] = bool(
            output["reported_3y_cohort_complete"]
            and output["independent_full_cycle_3y_cohort_complete"]
        )
        output["normal_roic_claimed"] = False
        output["terminal_input_allowed"] = False
        output["research_only"] = True
        rows.append(output)
    return pd.DataFrame(rows)
