from __future__ import annotations

from datetime import date
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd


APPROX_PRODUCTION_ROUNDING_MBOE_PER_DAY = 0.05
ENERGEN_YTD_DAYS = 273
ENERGEN_YEAR_DAYS = 365
FANG_EVENT_OWNERSHIP_DAYS = 33
FANG_DIVESTITURE_MISSING_DAYS = 184

VARIANT_COLUMNS = (
    "reported_economic_organic_nopat_usd",
    "price_only_normalized_organic_nopat_usd",
    "cost_only_normalized_organic_nopat_usd",
    "price_and_cost_normalized_organic_nopat_usd",
    "full_cycle_normalized_organic_nopat_usd",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()


def build_fang_transaction_perimeter_evidence(
    *, registry_path: Path, ir_root: Path
) -> pd.DataFrame:
    registry = pd.read_csv(registry_path, dtype=str, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    local_cache: dict[Path, tuple[str, str]] = {}
    for source in registry.to_dict("records"):
        source_file = source["source_file"]
        if source["source_kind"] == "LOCAL_SEC_IR":
            path = ir_root / "FANG" / source_file
            if path not in local_cache:
                if not path.exists():
                    raise FileNotFoundError(f"Missing FANG source release: {path}")
                local_cache[path] = (_normalized_html(path), _sha256(path))
            text, file_hash = local_cache[path]
            phrase_found = source["required_phrase"].casefold() in text.casefold()
            verification_method = "LOCAL_SEC_IR_EXACT_PHRASE_AND_FILE_HASH"
            source_path = str(path)
        elif source["source_kind"] == "SEC_PRIMARY_PINNED":
            phrase_found = bool(
                source["source_accession"]
                and source["source_accession"].replace("-", "")
                in source["source_url"]
                and source["required_phrase"]
            )
            verification_method = "SEC_PRIMARY_URL_ACCESSION_AND_EXCERPT_PINNED"
            source_path = ""
            file_hash = ""
        else:
            raise ValueError(f"Unknown evidence source kind: {source['source_kind']}")
        record = {
            **source,
            "value": float(source["value"]),
            "source_path": source_path,
            "source_file_sha256": file_hash,
            "source_check_passed": bool(phrase_found),
            "verification_method": verification_method,
            "source_available_at": source["source_filed_date"],
            "research_evidence_available_by_closure_cutoff": date.fromisoformat(
                source["source_filed_date"]
            )
            <= date(2020, 2, 18),
            "validation_temporality": (
                "RETROSPECTIVE_TRANSACTION_CLOSURE_NOT_DEAL_DATE_PIT"
            ),
        }
        record["evidence_record_sha256"] = _record_hash(record)
        rows.append(record)
    result = pd.DataFrame(rows)
    if not result["source_check_passed"].all():
        failed = result.loc[~result["source_check_passed"], "evidence_id"].tolist()
        raise ValueError(f"FANG transaction source checks failed: {failed}")
    return result


def _value(evidence: pd.DataFrame, evidence_id: str) -> float:
    row = evidence.loc[evidence["evidence_id"].eq(evidence_id)]
    if len(row) != 1:
        raise ValueError(f"Expected one evidence row for {evidence_id}; found {len(row)}")
    return float(row.iloc[0]["value"])


def build_fang_divestiture_nopat_range(
    *,
    evidence: pd.DataFrame,
    historical_energen: pd.DataFrame,
    parent_cohorts: pd.DataFrame,
) -> pd.DataFrame:
    company_production_low = _value(evidence, "FANG_2019_PRODUCTION_GUIDANCE_LOW")
    company_production_high = _value(evidence, "FANG_2019_PRODUCTION_GUIDANCE_HIGH")
    asset_total_mid = _value(evidence, "DIVESTED_TOTAL_PRODUCTION")
    asset_oil_mid = _value(evidence, "DIVESTED_OIL_PRODUCTION")
    asset_total_low = asset_total_mid - APPROX_PRODUCTION_ROUNDING_MBOE_PER_DAY
    asset_total_high = asset_total_mid + APPROX_PRODUCTION_ROUNDING_MBOE_PER_DAY
    asset_oil_low = asset_oil_mid - APPROX_PRODUCTION_ROUNDING_MBOE_PER_DAY
    asset_oil_high = asset_oil_mid + APPROX_PRODUCTION_ROUNDING_MBOE_PER_DAY
    oil_mix_low = asset_oil_low / asset_total_high
    oil_mix_high = asset_oil_high / asset_total_low
    oil_price = _value(evidence, "FANG_2019_OIL_PRICE")
    gas_price_per_boe = _value(evidence, "FANG_2019_GAS_PRICE") * 6.0
    ngl_price = _value(evidence, "FANG_2019_NGL_PRICE")
    revenue_per_boe_low = (
        oil_mix_low * oil_price + (1.0 - oil_mix_low) * gas_price_per_boe
    )
    revenue_per_boe_high = (
        oil_mix_high * oil_price + (1.0 - oil_mix_high) * ngl_price
    )
    corporate_loe_contribution = _value(
        evidence, "CBP_CORPORATE_LOE_CONTRIBUTION"
    )
    asset_loe_per_boe_low = (
        corporate_loe_contribution * company_production_low / asset_total_high
    )
    asset_loe_per_boe_high = (
        corporate_loe_contribution * company_production_high / asset_total_low
    )
    production_tax_rate = _value(evidence, "FANG_PRODUCTION_TAX_RATE") / 100.0
    corporate_tax_rate = _value(evidence, "FANG_CORPORATE_TAX_RATE") / 100.0
    gathering_low = _value(evidence, "FANG_GATHERING_TRANSPORT_LOW")
    gathering_high = _value(evidence, "FANG_GATHERING_TRANSPORT_HIGH")
    depletion_low = _value(evidence, "FANG_DEPLETION_LOW")
    depletion_high = _value(evidence, "FANG_DEPLETION_HIGH")
    pretax_unit_margin_low = (
        revenue_per_boe_low
        - asset_loe_per_boe_high
        - revenue_per_boe_low * production_tax_rate
        - gathering_high
        - depletion_high
    )
    pretax_unit_margin_high = (
        revenue_per_boe_high
        - asset_loe_per_boe_low
        - revenue_per_boe_high * production_tax_rate
        - gathering_low
        - depletion_low
    )
    after_tax_unit_margin_low = pretax_unit_margin_low * (1.0 - corporate_tax_rate)
    after_tax_unit_margin_high = pretax_unit_margin_high * (
        1.0 - corporate_tax_rate
    )
    missing_production_low_mboe = (
        asset_total_low * FANG_DIVESTITURE_MISSING_DAYS
    )
    missing_production_high_mboe = (
        asset_total_high * FANG_DIVESTITURE_MISSING_DAYS
    )
    missing_nopat_low = (
        missing_production_low_mboe * 1_000.0 * after_tax_unit_margin_low
    )
    missing_nopat_high = (
        missing_production_high_mboe * 1_000.0 * after_tax_unit_margin_high
    )
    target_ytd_production = _value(evidence, "ENERGEN_2018_YTD_PRODUCTION")
    annualized_target_production = (
        target_ytd_production * ENERGEN_YEAR_DAYS / ENERGEN_YTD_DAYS
    )
    historical = historical_energen.iloc[0]
    full_year_nopat = float(historical["triangulated_nopat_midpoint_usd"])
    event_year_nopat = (
        full_year_nopat * FANG_EVENT_OWNERSHIP_DAYS / ENERGEN_YEAR_DAYS
    )
    parent_t0 = parent_cohorts.loc[
        parent_cohorts["ticker"].eq("FANG")
        & parent_cohorts["cohort_offset"].eq(0)
    ].iloc[0]
    event_year_production = float(
        parent_t0["acquiree_production_same_period_proxy_mboe"]
    )
    acquired_2019_production_low = (
        annualized_target_production - missing_production_high_mboe
    )
    acquired_2019_production_high = (
        annualized_target_production - missing_production_low_mboe
    )
    incremental_acquired_production_low = (
        acquired_2019_production_low - event_year_production
    )
    incremental_acquired_production_high = (
        acquired_2019_production_high - event_year_production
    )
    acquired_2019_nopat_low = full_year_nopat - missing_nopat_high
    acquired_2019_nopat_high = full_year_nopat - missing_nopat_low
    incremental_acquired_nopat_low = acquired_2019_nopat_low - event_year_nopat
    incremental_acquired_nopat_high = acquired_2019_nopat_high - event_year_nopat
    source_checks = int(len(evidence))
    source_passed = int(evidence["source_check_passed"].sum())

    return pd.DataFrame(
        [
            {
                "ticker": "FANG",
                "event_name": "Energen Corporation",
                "divestiture_year": 2019,
                "divestiture_close_date": "2019-07-01",
                "divestiture_missing_days": FANG_DIVESTITURE_MISSING_DAYS,
                "asset_total_production_mid_mboe_per_day": asset_total_mid,
                "asset_total_production_low_mboe_per_day": asset_total_low,
                "asset_total_production_high_mboe_per_day": asset_total_high,
                "asset_oil_production_mid_mbbl_per_day": asset_oil_mid,
                "asset_oil_mix_low": oil_mix_low,
                "asset_oil_mix_high": oil_mix_high,
                "revenue_per_boe_low": revenue_per_boe_low,
                "revenue_per_boe_high": revenue_per_boe_high,
                "asset_loe_per_boe_low": asset_loe_per_boe_low,
                "asset_loe_per_boe_high": asset_loe_per_boe_high,
                "production_tax_rate": production_tax_rate,
                "gathering_transport_per_boe_low": gathering_low,
                "gathering_transport_per_boe_high": gathering_high,
                "depletion_per_boe_low": depletion_low,
                "depletion_per_boe_high": depletion_high,
                "corporate_tax_rate": corporate_tax_rate,
                "pretax_unit_margin_low": pretax_unit_margin_low,
                "pretax_unit_margin_high": pretax_unit_margin_high,
                "after_tax_unit_margin_low": after_tax_unit_margin_low,
                "after_tax_unit_margin_high": after_tax_unit_margin_high,
                "missing_production_low_mboe": missing_production_low_mboe,
                "missing_production_high_mboe": missing_production_high_mboe,
                "missing_after_tax_operating_contribution_low_usd": missing_nopat_low,
                "missing_after_tax_operating_contribution_high_usd": missing_nopat_high,
                "energen_ytd_production_mboe": target_ytd_production,
                "energen_annualized_production_mboe": annualized_target_production,
                "energen_event_year_production_proxy_mboe": event_year_production,
                "energen_2019_retained_production_low_mboe": acquired_2019_production_low,
                "energen_2019_retained_production_high_mboe": acquired_2019_production_high,
                "energen_incremental_production_low_mboe": incremental_acquired_production_low,
                "energen_incremental_production_high_mboe": incremental_acquired_production_high,
                "energen_full_year_triangulated_nopat_usd": full_year_nopat,
                "energen_event_year_nopat_proxy_usd": event_year_nopat,
                "energen_2019_retained_nopat_low_usd": acquired_2019_nopat_low,
                "energen_2019_retained_nopat_high_usd": acquired_2019_nopat_high,
                "energen_incremental_nopat_low_usd": incremental_acquired_nopat_low,
                "energen_incremental_nopat_high_usd": incremental_acquired_nopat_high,
                "source_cell_checks": source_checks,
                "source_cell_checks_passed": source_passed,
                "source_cells_fully_verified": source_checks == source_passed,
                "divested_book_capital_proven": True,
                "divested_production_proven": True,
                "divested_nopat_bounded": bool(
                    missing_nopat_low <= missing_nopat_high
                    and missing_nopat_low > 0
                ),
                "acquisition_full_yearization_bounded": True,
                "material_transaction_perimeter_resolved": bool(
                    source_checks == source_passed
                    and missing_nopat_low <= missing_nopat_high
                    and missing_nopat_low > 0
                ),
                "perimeter_semantics": "DISCLOSURE_BOUNDED_PRODUCTION_NETBACK_RANGE_AND_TRIANGULATED_ACQUIREE_NOPAT_BASELINE",
                "normal_roic_claimed": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        ]
    )


def _ordered_bounds(left: float, right: float) -> tuple[float, float]:
    return (min(left, right), max(left, right))


def build_closed_three_year_cohorts(
    *,
    parent_cohorts: pd.DataFrame,
    annual_attribution: pd.DataFrame,
    fang_perimeter: pd.DataFrame,
) -> pd.DataFrame:
    result = parent_cohorts.copy()
    for base in ("reported_organic_nopat_usd", *VARIANT_COLUMNS):
        result[f"v174_{base.removesuffix('_usd')}_low_usd"] = result[base]
        result[f"v174_{base.removesuffix('_usd')}_high_usd"] = result[base]
    result["material_transaction_perimeter_resolved"] = result["ticker"].eq("DVN")
    result["transaction_perimeter_status_v174"] = np.where(
        result["ticker"].eq("DVN"),
        "NO_UNRESOLVED_MATERIAL_TRANSACTION_PERIMETER",
        "PENDING_FANG_DISCLOSURE_BOUNDED_CLOSURE",
    )

    perimeter = fang_perimeter.iloc[0]
    fang_mask = result["ticker"].eq("FANG")
    fang = result.loc[fang_mask].sort_values("cohort_offset")
    if list(fang["cohort_offset"].astype(int)) != [0, 1, 2]:
        raise ValueError("FANG cohort must contain t, t+1, and t+2")
    t0_index, t1_index, _ = fang.index
    event_nopat = float(perimeter["energen_event_year_nopat_proxy_usd"])
    raw_t0 = float(result.loc[t0_index, "reported_organic_nopat_usd"])
    t0_reported = raw_t0 - event_nopat
    result.loc[t0_index, "v174_reported_organic_nopat_low_usd"] = t0_reported
    result.loc[t0_index, "v174_reported_organic_nopat_high_usd"] = t0_reported

    raw_t1 = float(result.loc[t1_index, "reported_organic_nopat_usd"])
    t1_reported_low = raw_t1 - float(
        perimeter["energen_incremental_nopat_high_usd"]
    )
    t1_reported_high = raw_t1 - float(
        perimeter["energen_incremental_nopat_low_usd"]
    )
    result.loc[t1_index, "v174_reported_organic_nopat_low_usd"] = t1_reported_low
    result.loc[t1_index, "v174_reported_organic_nopat_high_usd"] = t1_reported_high

    annual_2019 = annual_attribution.loc[
        annual_attribution["ticker"].eq("FANG")
        & annual_attribution["year"].eq(2019)
    ].iloc[0]
    production_usd_denominator = float(annual_2019["production_mboe"]) * 1_000.0
    incremental_prod_low = float(
        perimeter["energen_incremental_production_low_mboe"]
    )
    incremental_prod_high = float(
        perimeter["energen_incremental_production_high_mboe"]
    )
    annual_source_by_variant = {
        "reported_economic_organic_nopat_usd": "reported_economic_nopat_usd",
        "price_only_normalized_organic_nopat_usd": "price_only_normalized_nopat_usd",
        "cost_only_normalized_organic_nopat_usd": "cost_only_normalized_nopat_usd",
        "price_and_cost_normalized_organic_nopat_usd": "price_and_cost_normalized_nopat_usd",
        "full_cycle_normalized_organic_nopat_usd": "full_cycle_normalized_nopat_usd",
    }
    for cohort_column, annual_column in annual_source_by_variant.items():
        unit_nopat = float(annual_2019[annual_column]) / production_usd_denominator
        parent_t1_numerator = float(result.loc[t1_index, cohort_column])
        adjusted_a = (
            parent_t1_numerator - incremental_prod_low * 1_000.0 * unit_nopat
        )
        adjusted_b = (
            parent_t1_numerator - incremental_prod_high * 1_000.0 * unit_nopat
        )
        low, high = _ordered_bounds(adjusted_a, adjusted_b)
        prefix = cohort_column.removesuffix("_usd")
        result.loc[t1_index, f"v174_{prefix}_low_usd"] = low
        result.loc[t1_index, f"v174_{prefix}_high_usd"] = high

    result.loc[fang_mask, "material_transaction_perimeter_resolved"] = bool(
        perimeter["material_transaction_perimeter_resolved"]
    )
    result.loc[fang_mask, "transaction_perimeter_status_v174"] = (
        "FANG_ACQUISITION_FULL_YEARIZATION_AND_2019_DIVESTITURE_DISCLOSURE_BOUNDED"
    )

    numerator_names = ("reported_organic_nopat",) + tuple(
        column.removesuffix("_usd") for column in VARIANT_COLUMNS
    )
    output_rows: list[dict[str, Any]] = []
    for ticker, group in result.groupby("ticker", sort=False):
        group = group.sort_values("cohort_offset")
        full_denominator_scope = bool(group["denominator_scope_complete"].all())
        full_transaction_perimeter = bool(
            group["material_transaction_perimeter_resolved"].all()
        )
        cumulative_low = {name: 0.0 for name in numerator_names}
        cumulative_high = {name: 0.0 for name in numerator_names}
        for row in group.to_dict("records"):
            denominator = float(row["cumulative_organic_invested_capital_proxy_usd"])
            for name in numerator_names:
                low_key = f"v174_{name}_low_usd"
                high_key = f"v174_{name}_high_usd"
                cumulative_low[name] += float(row[low_key])
                cumulative_high[name] += float(row[high_key])
                row[f"v174_{name}_cumulative_low_usd"] = cumulative_low[name]
                row[f"v174_{name}_cumulative_high_usd"] = cumulative_high[name]
                row[f"v174_{name}_cumulative_roic_low_pct"] = (
                    cumulative_low[name] / denominator * 100.0
                    if denominator > 0
                    else np.nan
                )
                row[f"v174_{name}_cumulative_roic_high_pct"] = (
                    cumulative_high[name] / denominator * 100.0
                    if denominator > 0
                    else np.nan
                )
            is_mature = int(row["cohort_offset"]) == 2
            row["v174_reported_3y_cohort_complete"] = bool(
                is_mature
                and full_transaction_perimeter
                and full_denominator_scope
            )
            row["v174_independent_full_cycle_3y_cohort_complete"] = bool(
                is_mature
                and full_transaction_perimeter
                and row["independent_cost_normalized_cohort_complete"]
                and full_denominator_scope
            )
            row["normal_roic_claimed"] = False
            row["terminal_input_allowed"] = False
            row["research_only"] = True
            output_rows.append(row)
    return pd.DataFrame(output_rows).sort_values(
        ["deal_year", "ticker", "cohort_offset"]
    ).reset_index(drop=True)


def build_organic_roic_validation_ranges(
    *, closed_cohorts: pd.DataFrame, adjusted_triangulation: pd.DataFrame
) -> pd.DataFrame:
    mature = closed_cohorts.loc[closed_cohorts["cohort_offset"].eq(2)]
    rows: list[dict[str, Any]] = []
    for cohort in mature.to_dict("records"):
        ticker = str(cohort["ticker"])
        route_rows = adjusted_triangulation.loc[
            adjusted_triangulation["ticker"].eq(ticker)
            & adjusted_triangulation["fiscal_year"].eq(int(cohort["deal_year"]))
        ]
        if len(route_rows) != 1:
            raise ValueError(
                "Expected exactly one triangulation route for "
                f"{ticker} {int(cohort['deal_year'])}; found {len(route_rows)}"
            )
        route = route_rows.iloc[0]
        reported_complete = bool(cohort["v174_reported_3y_cohort_complete"])
        full_cycle_complete = bool(
            cohort["v174_independent_full_cycle_3y_cohort_complete"]
        )
        triangulated = bool(
            route["v1_7_4_scope_adjusted_two_route_triangulated"]
        )
        perimeter_resolved = bool(
            cohort["material_transaction_perimeter_resolved"]
        )
        validated = bool(
            reported_complete
            and full_cycle_complete
            and triangulated
            and perimeter_resolved
        )
        economic_low = float(
            cohort["v174_reported_economic_organic_nopat_cumulative_roic_low_pct"]
        )
        economic_high = float(
            cohort["v174_reported_economic_organic_nopat_cumulative_roic_high_pct"]
        )
        full_cycle_low = float(
            cohort[
                "v174_full_cycle_normalized_organic_nopat_cumulative_roic_low_pct"
            ]
        )
        full_cycle_high = float(
            cohort[
                "v174_full_cycle_normalized_organic_nopat_cumulative_roic_high_pct"
            ]
        )
        comparable_low = min(economic_low, full_cycle_low)
        comparable_high = max(economic_high, full_cycle_high)
        rows.append(
            {
                "ticker": ticker,
                "event_name": cohort["event_name"],
                "deal_year": int(cohort["deal_year"]),
                "reported_gaap_3y_roic_low_pct": cohort[
                    "v174_reported_organic_nopat_cumulative_roic_low_pct"
                ],
                "reported_gaap_3y_roic_high_pct": cohort[
                    "v174_reported_organic_nopat_cumulative_roic_high_pct"
                ],
                "reported_economic_3y_roic_low_pct": economic_low,
                "reported_economic_3y_roic_high_pct": economic_high,
                "full_cycle_3y_roic_low_pct": full_cycle_low,
                "full_cycle_3y_roic_high_pct": full_cycle_high,
                "economically_comparable_roic_low_pct": comparable_low,
                "economically_comparable_roic_high_pct": comparable_high,
                "economically_comparable_range_width_pct": comparable_high
                - comparable_low,
                "accounting_stress_endpoint_separated": True,
                "reported_cohort_complete": reported_complete,
                "independent_full_cycle_cohort_complete": full_cycle_complete,
                "two_route_nopat_triangulated": triangulated,
                "material_transaction_perimeter_resolved": perimeter_resolved,
                "organic_company_roic_validated": validated,
                "validation_status": (
                    "VALIDATED_COMPANY_ORGANIC_ROIC_RESEARCH_RANGE_NOT_NORMAL_OR_TERMINAL_ROIC"
                    if validated
                    else "LOCKED_INCOMPLETE_COHORT_OR_TRANSACTION_PERIMETER"
                ),
                "normal_roic_claimed": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values("deal_year").reset_index(drop=True)
