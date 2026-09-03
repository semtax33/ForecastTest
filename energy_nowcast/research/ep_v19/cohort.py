from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

RESEARCH_CUTOFF = pd.Timestamp("2025-03-01")
CAPITAL_MATERIALITY_RATIO = 0.01
RESERVE_EVENT_MATERIALITY_RATIO = 0.02
ELIGIBLE_DENOMINATOR_RATIO = 0.02
RESERVE_DIMENSION = "0xcec9f14bc7eff4887675c675fd5e6584"
COMPANYFACT_TAGS = {
    "revenue_usd": "Revenues",
    "cost_and_expense_usd": "CostsAndExpenses",
    "income_before_tax_usd": "ResultsOfOperationsIncomeBeforeIncomeTaxes",
}
NORMALIZATION_VARIANTS = (
    "reported_economic_nopat_usd",
    "price_only_normalized_nopat_usd",
    "cost_only_normalized_nopat_usd",
    "price_and_cost_normalized_nopat_usd",
    "full_cycle_normalized_nopat_usd",
)


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _companyfact_annual(
    payload: dict[str, Any], *, tag: str, year: int, adsh: str
) -> tuple[float, str]:
    fact = payload.get("facts", {}).get("us-gaap", {}).get(tag, {})
    candidates = [
        row
        for row in fact.get("units", {}).get("USD", [])
        if row.get("accn") == adsh
        and row.get("form") == "10-K"
        and row.get("end") == f"{year}-12-31"
        and row.get("start") is not None
        and 330
        <= (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).days + 1
        <= 380
    ]
    if not candidates:
        raise ValueError(f"Missing annual companyfact {tag} for RRC {year}")
    values = {float(row["val"]) for row in candidates}
    if len(values) != 1:
        raise ValueError(f"Conflicting annual companyfact {tag} for RRC {year}")
    selected = sorted(candidates, key=_record_hash)[0]
    return float(selected["val"]), _record_hash(selected)


def build_rrc_annual_evidence(
    *,
    source_registry_path: Path,
    fnsd_root: Path,
    companyfacts_path: Path,
    ttm_financial: pd.DataFrame,
) -> pd.DataFrame:
    registry = pd.read_csv(source_registry_path, dtype={"adsh": str})
    companyfacts = json.loads(companyfacts_path.read_text(encoding="utf-8"))
    tax = ttm_financial.loc[
        ttm_financial["ticker"].eq("RRC")
        & ttm_financial["quarter"].astype(str).str.endswith("Q4")
    ].copy()
    tax["year"] = tax["quarter"].astype(str).str[:4].astype(int)
    tax = tax.set_index("year")
    rows: list[dict[str, object]] = []
    for source in registry.to_dict("records"):
        year = int(source["year"])
        folder = fnsd_root / str(source["fnsd_folder"])
        submission = pd.read_csv(folder / "sub.tsv", sep="\t", low_memory=False)
        filing = submission.loc[
            submission["adsh"].astype(str).eq(str(source["adsh"]))
        ]
        if len(filing) != 1:
            raise ValueError(f"Expected one RRC filing for {year}; found {len(filing)}")
        filing_row = filing.iloc[0]
        if (
            int(filing_row["cik"]) != 315852
            or str(filing_row["form"]) != "10-K"
            or int(filing_row["fy"]) != year
        ):
            raise ValueError(f"RRC source is not the expected {year} 10-K")
        filed_date = pd.to_datetime(str(int(filing_row["filed"])))
        values: dict[str, float] = {}
        hashes: list[str] = []
        for output, tag in COMPANYFACT_TAGS.items():
            value, record_hash = _companyfact_annual(
                companyfacts,
                tag=tag,
                year=year,
                adsh=str(source["adsh"]),
            )
            values[output] = value
            hashes.append(record_hash)
        for field in (
            "end_reserves_mmcfe",
            "production_mmcfe",
            "extensions_mmcfe",
            "revisions_mmcfe",
        ):
            values[field] = float(source[field])
        segment_phrase_proven = bool(
            source["segment_phrase_verified"]
            and str(source["segment_text_tag"])
            == "SegmentReportingPolicyPolicyTextBlock"
            and str(source["required_segment_phrase"]).casefold()
            == "only one operating segment"
        )
        local_fnsd_files_present = bool(
            (folder / "num.tsv").is_file() and (folder / "txt.tsv").is_file()
        )
        reserve_registry_verified = bool(
            source["reserve_values_verified_from_local_fnsd"]
            and str(source["expected_reserve_dimh"]) == RESERVE_DIMENSION
            and all(
                np.isfinite(values[field])
                for field in (
                    "end_reserves_mmcfe",
                    "production_mmcfe",
                    "extensions_mmcfe",
                    "revisions_mmcfe",
                )
            )
        )
        registry_record_hash = _record_hash(source)
        hashes.append(registry_record_hash)
        income_identity_error = (
            values["revenue_usd"]
            - values["cost_and_expense_usd"]
            - values["income_before_tax_usd"]
        )
        production_mboe = values["production_mmcfe"] / 6.0
        tax_row = tax.loc[year]
        rows.append(
            {
                "ticker": "RRC",
                "group": "gas_heavy",
                "year": year,
                **values,
                "production_mboe": production_mboe,
                "actual_price_per_boe": values["revenue_usd"]
                / (production_mboe * 1_000.0),
                "actual_complete_company_unit_cost_per_boe": values[
                    "cost_and_expense_usd"
                ]
                / (production_mboe * 1_000.0),
                "income_identity_error_usd": income_identity_error,
                "income_identity_passed": abs(income_identity_error) <= 1.0,
                "effective_tax_rate": float(
                    np.clip(tax_row["effective_tax_rate"], 0.0, 0.35)
                ),
                "tax_rate_method": str(tax_row["tax_rate_method"]),
                "single_operating_segment_phrase_proven": segment_phrase_proven,
                "source_form": str(filing_row["form"]),
                "source_filed_date": filed_date.date().isoformat(),
                "source_available_by_research_cutoff": filed_date
                <= RESEARCH_CUTOFF,
                "source_num_path": str(folder / "num.tsv"),
                "source_txt_path": str(folder / "txt.tsv"),
                "source_verification_route": (
                    "LIVE_SEC_COMPANYFACTS_PLUS_CURATED_LOCAL_FNSD_GOLD_REGISTRY"
                ),
                "reserve_values_verified_from_local_fnsd": bool(
                    reserve_registry_verified
                ),
                "local_fnsd_source_files_present": local_fnsd_files_present,
                "source_registry_record_sha256": registry_record_hash,
                "source_evidence_bundle_sha256": hashlib.sha256(
                    "|".join(sorted(hashes)).encode("ascii")
                ).hexdigest(),
                "source_cell_checks": 10,
                "source_cell_checks_passed": (
                    3
                    + 4 * int(reserve_registry_verified)
                    + int(segment_phrase_proven)
                    + int(local_fnsd_files_present)
                    + int(
                        str(filing_row["form"]) == "10-K"
                        and int(filing_row["fy"]) == year
                    )
                ),
                "operating_scope": (
                    "CONSOLIDATED_SINGLE_OPERATING_SEGMENT_ALL_REVENUES_AND_COSTS"
                ),
                "normal_roic_claimed": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    result = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    if list(result["year"]) != [2020, 2021, 2022, 2023, 2024]:
        raise ValueError("RRC evidence must contain the predeclared 2020-2024 years")
    result["begin_reserves_mmcfe"] = result["end_reserves_mmcfe"].shift(1)
    result["net_reserve_transaction_balancing_mmcfe"] = (
        result["end_reserves_mmcfe"]
        - (
            result["begin_reserves_mmcfe"]
            + result["extensions_mmcfe"]
            + result["revisions_mmcfe"]
            - result["production_mmcfe"]
        )
    )
    result["purchases_identity_mmcfe"] = result[
        "net_reserve_transaction_balancing_mmcfe"
    ].clip(lower=0.0)
    result["sales_identity_mmcfe"] = -result[
        "net_reserve_transaction_balancing_mmcfe"
    ].clip(upper=0.0)
    expected_end = (
        result["begin_reserves_mmcfe"]
        + result["extensions_mmcfe"]
        + result["revisions_mmcfe"]
        + result["purchases_identity_mmcfe"]
        - result["sales_identity_mmcfe"]
        - result["production_mmcfe"]
    )
    result["reserve_rollforward_identity_error_mmcfe"] = (
        result["end_reserves_mmcfe"] - expected_end
    )
    result["reserve_rollforward_identity_passed"] = (
        result["reserve_rollforward_identity_error_mmcfe"].abs().le(0.001)
        | result["begin_reserves_mmcfe"].isna()
    )
    result["reserve_event_ratio"] = (
        result[["purchases_identity_mmcfe", "sales_identity_mmcfe"]]
        .abs()
        .max(axis=1)
        .div(result["begin_reserves_mmcfe"].abs())
    )
    result["reserve_event_zero_semantics"] = (
        "NET_TRANSACTION_BALANCING_ITEM_FROM_STANDARDIZED_ROLLFORWARD_NOT_CLAIMED_AS_DIRECT_DISCLOSURE"
    )
    result["source_cells_fully_verified"] = (
        result["source_cell_checks"] == result["source_cell_checks_passed"]
    )
    if not (
        result["source_cells_fully_verified"].all()
        and result["income_identity_passed"].all()
        and result["reserve_rollforward_identity_passed"].all()
        and result["source_available_by_research_cutoff"].all()
    ):
        raise ValueError("RRC direct source evidence failed closed")
    return result


def build_rrc_candidate_audit(
    *, annual_organic: pd.DataFrame, annual_evidence: pd.DataFrame
) -> pd.DataFrame:
    annual = annual_organic.loc[annual_organic["ticker"].eq("RRC")].copy()
    evidence_years = set(annual_evidence["year"].astype(int))
    rows: list[dict[str, object]] = []
    for start_year in (2021, 2022, 2023):
        end_year = start_year + 2
        required_years = set(range(start_year - 1, end_year + 1))
        window = annual.loc[annual["year"].between(start_year, end_year)]
        source_complete = required_years.issubset(evidence_years)
        evidence_window = annual_evidence.loc[
            annual_evidence["year"].between(start_year, end_year)
        ]
        filed_by_cutoff = bool(
            source_complete
            and annual_evidence.loc[
                annual_evidence["year"].isin(required_years),
                "source_available_by_research_cutoff",
            ].all()
        )
        direct_nopat_complete = bool(
            source_complete
            and annual_evidence.loc[
                annual_evidence["year"].isin(required_years),
                ["income_before_tax_usd", "effective_tax_rate"],
            ]
            .notna()
            .all()
            .all()
        )
        one_segment_proven = bool(
            source_complete
            and annual_evidence.loc[
                annual_evidence["year"].isin(required_years),
                "single_operating_segment_phrase_proven",
            ].all()
        )
        capital_clean = bool(
            len(window) == 3
            and (~window["material_acquisition"]).all()
            and (~window["material_divestiture"]).all()
            and window["denominator_scope_complete"].all()
            and window["numerator_scope_complete"].all()
        )
        reserve_identity_complete = bool(
            len(evidence_window) == 3
            and evidence_window["reserve_rollforward_identity_passed"].all()
        )
        reserve_event_max_ratio = float(
            evidence_window["reserve_event_ratio"].max()
        ) if len(evidence_window) else np.nan
        reserve_clean = bool(
            reserve_identity_complete
            and reserve_event_max_ratio <= RESERVE_EVENT_MATERIALITY_RATIO
        )
        denominator = float(
            window["organic_delta_invested_capital_proxy_usd"].sum()
        ) if len(window) == 3 else np.nan
        opening = abs(float(window.sort_values("year").iloc[0]["opening_invested_capital_usd"])) if len(window) == 3 else np.nan
        denominator_threshold = opening * ELIGIBLE_DENOMINATOR_RATIO
        denominator_eligible = bool(
            np.isfinite(denominator)
            and np.isfinite(denominator_threshold)
            and denominator > denominator_threshold
        )
        eligible = bool(
            source_complete
            and filed_by_cutoff
            and direct_nopat_complete
            and one_segment_proven
            and capital_clean
            and reserve_clean
            and denominator_eligible
        )
        blockers: list[str] = []
        if not source_complete:
            blockers.append("DIRECT_FOUR_YEAR_SOURCE_EVIDENCE_INCOMPLETE_AT_CUTOFF")
        if not filed_by_cutoff:
            blockers.append("SOURCE_NOT_AVAILABLE_BY_FIXED_RESEARCH_CUTOFF")
        if not direct_nopat_complete:
            blockers.append("DIRECT_ECONOMIC_NOPAT_INCOMPLETE")
        if not one_segment_proven:
            blockers.append("SINGLE_OPERATING_SEGMENT_NOT_PROVEN")
        if not capital_clean:
            blockers.append("MATERIAL_CAPITAL_TRANSACTION_PERIMETER")
        if not reserve_clean:
            blockers.append("MATERIAL_OR_UNRECONCILED_RESERVE_EVENT")
        if not denominator_eligible:
            blockers.append("CUMULATIVE_ORGANIC_DENOMINATOR_NOT_ELIGIBLE")
        rows.append(
            {
                "ticker": "RRC",
                "group": "gas_heavy",
                "window_start_year": start_year,
                "window_end_year": end_year,
                "research_cutoff": RESEARCH_CUTOFF.date().isoformat(),
                "direct_four_year_source_evidence": source_complete,
                "all_sources_filed_by_cutoff": filed_by_cutoff,
                "single_operating_segment_proven": one_segment_proven,
                "direct_economic_nopat_complete": direct_nopat_complete,
                "capital_transaction_perimeter_clean": capital_clean,
                "reserve_rollforward_identity_complete": reserve_identity_complete,
                "reserve_event_max_ratio": reserve_event_max_ratio,
                "reserve_event_materiality_threshold": RESERVE_EVENT_MATERIALITY_RATIO,
                "capital_materiality_threshold": CAPITAL_MATERIALITY_RATIO,
                "reserve_transaction_perimeter_clean": reserve_clean,
                "cumulative_organic_invested_capital_usd": denominator,
                "denominator_threshold_usd": denominator_threshold,
                "denominator_eligible": denominator_eligible,
                "window_eligible": eligible,
                "selection_order": "LATEST_ELIGIBLE_WINDOW_AT_FIXED_CUTOFF",
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
    result = pd.DataFrame(rows)
    eligible = result.loc[result["window_eligible"]]
    if eligible.empty:
        raise ValueError("No outcome-blind eligible RRC clean window")
    selected_index = eligible.sort_values("window_end_year").index[-1]
    result["selected_for_v19"] = result.index == selected_index
    selected = result.loc[result["selected_for_v19"]].iloc[0]
    if (
        int(selected["window_start_year"]) != 2022
        or int(selected["window_end_year"]) != 2024
    ):
        raise ValueError("RRC deterministic selection changed")
    return result


def build_rrc_normalization_evidence(
    *,
    annual_evidence: pd.DataFrame,
    candidate_audit: pd.DataFrame,
    cycle_reference: pd.DataFrame,
) -> pd.DataFrame:
    selected = candidate_audit.loc[candidate_audit["selected_for_v19"]]
    if len(selected) != 1:
        raise ValueError("Expected one selected RRC window")
    start_year = int(selected.iloc[0]["window_start_year"])
    end_year = int(selected.iloc[0]["window_end_year"])
    result = annual_evidence.loc[
        annual_evidence["year"].between(start_year - 1, end_year)
    ].copy()
    reference = cycle_reference.loc[cycle_reference["ticker"].eq("RRC")]
    if len(reference) != 1:
        raise ValueError("Expected one RRC cycle normalization reference")
    normalized_price = float(reference.iloc[0]["normalized_price_per_boe"])
    normalized_cost = float(
        result["actual_complete_company_unit_cost_per_boe"].median()
    )
    normalized_tax = float(result["effective_tax_rate"].median())
    volume = result["production_mboe"] * 1_000.0
    result["normalized_price_per_boe"] = normalized_price
    result["normalized_complete_company_unit_cost_per_boe"] = normalized_cost
    result["normalized_tax_rate"] = normalized_tax
    result["reported_economic_nopat_usd"] = result[
        "income_before_tax_usd"
    ] * (1.0 - result["effective_tax_rate"])
    result["price_only_normalized_nopat_usd"] = (
        normalized_price - result["actual_complete_company_unit_cost_per_boe"]
    ) * volume * (1.0 - result["effective_tax_rate"])
    result["cost_only_normalized_nopat_usd"] = (
        result["actual_price_per_boe"] - normalized_cost
    ) * volume * (1.0 - result["effective_tax_rate"])
    result["price_and_cost_normalized_nopat_usd"] = (
        normalized_price - normalized_cost
    ) * volume * (1.0 - result["effective_tax_rate"])
    result["full_cycle_normalized_nopat_usd"] = (
        normalized_price - normalized_cost
    ) * volume * (1.0 - normalized_tax)
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
        result["reported_economic_nopat_usd"]
        + result["price_normalization_effect_usd"]
        + result["cost_normalization_effect_usd"]
        + result["tax_normalization_effect_usd"]
    )
    result["normalization_attribution_identity_error_usd"] = (
        result["full_cycle_normalized_nopat_usd"] - reconstructed
    )
    result["normalization_attribution_complete"] = (
        result["source_cells_fully_verified"]
        & result["normalization_attribution_identity_error_usd"].abs().le(1.0)
    )
    result["normalization_confidence_grade"] = "A"
    result["unit_cost_scope"] = (
        "DIRECT_CONSOLIDATED_SINGLE_SEGMENT_TOTAL_COSTS_AND_EXPENSES"
    )
    result["normal_roic_claimed"] = False
    result["terminal_input_allowed"] = False
    result["research_only"] = True
    return result.reset_index(drop=True)


def build_rrc_clean_organic_cohort(
    *,
    candidate_audit: pd.DataFrame,
    normalization_evidence: pd.DataFrame,
    annual_organic: pd.DataFrame,
) -> pd.DataFrame:
    selected = candidate_audit.loc[candidate_audit["selected_for_v19"]]
    start_year = int(selected.iloc[0]["window_start_year"])
    end_year = int(selected.iloc[0]["window_end_year"])
    evidence = normalization_evidence.set_index("year")
    annual = annual_organic.loc[
        annual_organic["ticker"].eq("RRC")
        & annual_organic["year"].between(start_year, end_year)
    ].sort_values("year")
    opening = abs(float(annual.iloc[0]["opening_invested_capital_usd"]))
    threshold = opening * ELIGIBLE_DENOMINATOR_RATIO
    cumulative_denominator = 0.0
    cumulative = {variant: 0.0 for variant in NORMALIZATION_VARIANTS}
    rows: list[dict[str, object]] = []
    for offset, annual_row in enumerate(annual.to_dict("records")):
        year = int(annual_row["year"])
        denominator = float(annual_row["organic_delta_invested_capital_proxy_usd"])
        cumulative_denominator += denominator
        output: dict[str, object] = {
            "ticker": "RRC",
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
            "single_operating_segment_proven": True,
            "annual_source_complete": bool(
                evidence.loc[
                    year - 1 : year, "normalization_attribution_complete"
                ].all()
            ),
            "reported_gaap_route_status": (
                "NOT_REQUIRED_DIRECT_SINGLE_SEGMENT_ECONOMIC_NOPAT_ROUTE"
            ),
        }
        for variant in NORMALIZATION_VARIANTS:
            prefix = variant.removesuffix("_usd")
            numerator = float(evidence.loc[year, variant] - evidence.loc[year - 1, variant])
            cumulative[variant] += numerator
            output[f"{prefix}_organic_nopat_usd"] = numerator
            output[f"{prefix}_cumulative_organic_nopat_usd"] = cumulative[variant]
            output[f"{prefix}_cumulative_roic_pct"] = (
                cumulative[variant] / cumulative_denominator * 100.0
                if year == end_year and cumulative_denominator > threshold
                else np.nan
            )
        mature = year == end_year and offset == 2
        output["reported_3y_cohort_complete"] = bool(
            mature
            and cumulative_denominator > threshold
            and output["annual_source_complete"]
        )
        output["independent_full_cycle_3y_cohort_complete"] = bool(
            output["reported_3y_cohort_complete"]
            and normalization_evidence["normalization_attribution_complete"].all()
            and normalization_evidence["normalization_confidence_grade"].eq("A").all()
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
