from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd


BUYER_CIK = {
    "DVN": "0001090012",
    "FANG": "0001539838",
}
DVN_COMPONENT_TAGS = (
    "ResultsOfOperationsProductionOrLiftingCosts",
    "ResultsOfOperationsExplorationExpense",
    "ResultsOfOperationsDepreciationDepletionAmortizationAndAccretion",
    "GeneralAndAdministrativeExpense",
)
UPSTREAM_REVENUE_TAGS = (
    "ResultsOfOperationsRevenueFromOilAndGasProducingActivities",
    "OilAndGasRevenue",
    "OilAndGasSalesRevenue",
)
ATTRIBUTION_VARIANTS = (
    "reported_economic_nopat_usd",
    "price_only_normalized_nopat_usd",
    "cost_only_normalized_nopat_usd",
    "price_and_cost_normalized_nopat_usd",
    "full_cycle_normalized_nopat_usd",
)


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _annual_fact(
    companyfacts_root: Path,
    ticker: str,
    year: int,
    tags: tuple[str, ...],
) -> tuple[float, str, str, str, float]:
    cik = BUYER_CIK[ticker]
    facts = json.loads(
        (companyfacts_root / f"CIK{cik}.json").read_text(encoding="utf-8")
    )
    candidates: list[tuple[int, str, dict[str, Any], str]] = []
    all_values: list[float] = []
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
                record.get("form") == "10-K"
                and record.get("start") == f"{year}-01-01"
                and record.get("end") == f"{year}-12-31"
            ):
                candidates.append((priority, str(record.get("filed", "")), record, tag))
                all_values.append(float(record["val"]))
    if not candidates:
        return np.nan, "", "", "", np.nan
    best_priority = min(item[0] for item in candidates)
    same_route = [item for item in candidates if item[0] == best_priority]
    same_route.sort(key=lambda item: item[1])
    _, filed, selected, tag = same_route[0]
    selected_values = [
        float(item[2]["val"]) for item in same_route if item[3] == tag
    ]
    restatement_span_pct = (
        (max(selected_values) - min(selected_values))
        / max(abs(float(selected["val"])), 1.0)
        * 100.0
    )
    return (
        float(selected["val"]),
        tag,
        _record_hash({**selected, "tag": tag}),
        filed,
        restatement_span_pct,
    )


def _number(value: object) -> float:
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text.lower() == "nan" or text in {"—", "–", "-"}:
        return np.nan
    negative = text.startswith("(") or text.endswith(")")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return np.nan
    number = float(match.group())
    return -abs(number) if negative else number


def _labeled_value_present(
    tables: list[pd.DataFrame], aliases: tuple[str, ...], expected: float
) -> bool:
    for table in tables:
        for _, row in table.iterrows():
            cells = [str(value) for value in row.tolist()]
            row_text = " ".join(cells).casefold()
            if not any(alias.casefold() in row_text for alias in aliases):
                continue
            values = [_number(value) for value in cells]
            if any(
                np.isfinite(value)
                and np.isclose(
                    abs(value),
                    abs(expected),
                    rtol=0.0,
                    atol=max(0.01, abs(expected) * 1e-7),
                )
                for value in values
            ):
                return True
    return False


def _build_fang_historical_cost_evidence(
    *,
    registry_path: Path,
    ir_root: Path,
    companyfacts_root: Path,
) -> pd.DataFrame:
    registry = pd.read_csv(registry_path)
    table_cache: dict[Path, list[pd.DataFrame]] = {}
    rows: list[dict[str, Any]] = []
    labels = {
        "production_mboe": ("oil equivalents", "production"),
        "lease_operating_usd": ("lease operating expense",),
        "production_tax_usd": ("production and ad valorem taxes",),
        "transport_usd": ("gathering and transportation",),
        "dda_usd": ("depreciation, depletion and amortization",),
        "g_and_a_usd": ("general and administrative expenses",),
    }
    for item in registry.to_dict("records"):
        source = ir_root / str(item["ticker"]) / str(item["release_file"])
        table_cache.setdefault(source, pd.read_html(source, flavor="lxml"))
        tables = table_cache[source]
        scale = float(item["source_display_scale_usd"])
        checks: dict[str, bool] = {}
        for name, aliases in labels.items():
            expected = float(item[name])
            if name != "production_mboe":
                expected /= scale
            checks[name] = _labeled_value_present(tables, aliases, expected)
        year = int(item["year"])
        revenue, revenue_tag, revenue_hash, revenue_filed, revenue_span = _annual_fact(
            companyfacts_root, "FANG", year, UPSTREAM_REVENUE_TAGS
        )
        components = [
            float(item[column])
            for column in (
                "lease_operating_usd",
                "production_tax_usd",
                "transport_usd",
                "dda_usd",
                "g_and_a_usd",
            )
        ]
        production = float(item["production_mboe"])
        rows.append(
            {
                "ticker": "FANG",
                "year": year,
                "production_mboe": production,
                "actual_upstream_revenue_usd": revenue,
                "actual_price_per_boe": revenue / (production * 1_000.0),
                "actual_all_in_component_cost_usd": sum(components),
                "actual_unit_cost_per_boe": sum(components) / (production * 1_000.0),
                "lease_operating_usd": components[0],
                "production_tax_usd": components[1],
                "transport_usd": components[2],
                "dda_usd": components[3],
                "g_and_a_usd": components[4],
                "component_count": len(components),
                "source_cell_checks": len(checks),
                "source_cell_checks_passed": sum(checks.values()),
                "source_cells_fully_verified": bool(all(checks.values())),
                "production_source_semantics": "IR_SELECTED_OPERATING_DATA_ANNUAL_COMPONENT_IDENTITY",
                "cost_source_semantics": "IR_LIFTING_TAX_TRANSPORT_DDA_GA_COMPLETE_COMPONENT_SCOPE",
                "revenue_source_semantics": "SEC_RESULTS_OF_OPERATIONS_UPSTREAM_REVENUE",
                "revenue_source_tag": revenue_tag,
                "revenue_record_sha256": revenue_hash,
                "revenue_available_at": revenue_filed,
                "revenue_restatement_span_pct": revenue_span,
                "source_path": str(source),
                "source_file_sha256": _file_hash(source),
                "source_availability_date": source.name[:10],
                "source_selection_policy": "CONTEMPORANEOUS_IR_RELEASE_PLUS_EARLIEST_10K_VINTAGE",
                "normalization_confidence_grade": "A",
                "normalization_confidence_weight": 1.0,
                "independent_complete_cost_scope": True,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values(["ticker", "year"]).reset_index(drop=True)


def _build_dvn_cost_evidence(
    *,
    production: pd.DataFrame,
    companyfacts_root: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    panel = production.loc[
        production["ticker"].eq("DVN") & production["year"].between(2020, 2023)
    ]
    for prod in panel.to_dict("records"):
        year = int(prod["year"])
        component_values: list[float] = []
        hashes: list[str] = []
        filed_dates: list[str] = []
        spans: list[float] = []
        for tag in DVN_COMPONENT_TAGS:
            value, _, record_hash, filed, span = _annual_fact(
                companyfacts_root, "DVN", year, (tag,)
            )
            component_values.append(value)
            hashes.append(record_hash)
            filed_dates.append(filed)
            spans.append(span)
        revenue, revenue_tag, revenue_hash, revenue_filed, revenue_span = _annual_fact(
            companyfacts_root, "DVN", year, UPSTREAM_REVENUE_TAGS
        )
        production_mboe = float(prod["production_mboe"])
        complete = bool(
            prod["production_evidence_proven"]
            and all(pd.notna(value) for value in component_values)
            and pd.notna(revenue)
        )
        component_total = sum(component_values) if complete else np.nan
        rows.append(
            {
                "ticker": "DVN",
                "year": year,
                "production_mboe": production_mboe,
                "actual_upstream_revenue_usd": revenue,
                "actual_price_per_boe": (
                    revenue / (production_mboe * 1_000.0) if complete else np.nan
                ),
                "actual_all_in_component_cost_usd": component_total,
                "actual_unit_cost_per_boe": (
                    component_total / (production_mboe * 1_000.0)
                    if complete
                    else np.nan
                ),
                "lease_operating_usd": component_values[0],
                "exploration_usd": component_values[1],
                "dda_usd": component_values[2],
                "g_and_a_usd": component_values[3],
                "component_count": len(component_values),
                "source_cell_checks": len(component_values) + 2,
                "source_cell_checks_passed": (
                    len(component_values) + 2 if complete else 0
                ),
                "source_cells_fully_verified": complete,
                "production_source_semantics": prod["production_source_semantics"],
                "cost_source_semantics": "SEC_LIFTING_EXPLORATION_DDA_PLUS_COMPANY_GA_COMPLETE_COMPONENT_SCOPE",
                "revenue_source_semantics": "SEC_RESULTS_OF_OPERATIONS_UPSTREAM_REVENUE",
                "revenue_source_tag": revenue_tag,
                "revenue_record_sha256": revenue_hash,
                "revenue_available_at": revenue_filed,
                "revenue_restatement_span_pct": revenue_span,
                "source_path": prod["source_file"],
                "source_file_sha256": hashlib.sha256(
                    "|".join(sorted(hashes + [revenue_hash])).encode("ascii")
                ).hexdigest(),
                "source_availability_date": max(filed_dates + [revenue_filed]),
                "source_selection_policy": "EARLIEST_10K_VINTAGE_FOR_POINT_IN_TIME",
                "component_restatement_span_max_pct": float(np.nanmax(spans)),
                "normalization_confidence_grade": "A" if complete else "C",
                "normalization_confidence_weight": 1.0 if complete else 0.0,
                "independent_complete_cost_scope": complete,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values(["ticker", "year"]).reset_index(drop=True)


def _confidence_tables(reference: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = pd.DataFrame(
        [
            {
                "normalization_confidence_grade": "A",
                "definition": "INDEPENDENT_COMPLETE_COST_AND_PRODUCTION_EVIDENCE",
                "sector_inference_weight": 1.0,
                "sector_inference_eligible": True,
            },
            {
                "normalization_confidence_grade": "B",
                "definition": "ACCOUNTING_PROVEN_PARTIAL_COST_SCOPE",
                "sector_inference_weight": 0.5,
                "sector_inference_eligible": True,
            },
            {
                "normalization_confidence_grade": "C",
                "definition": "HIERARCHICAL_MARGIN_IMPLIED_NOT_INDEPENDENT",
                "sector_inference_weight": 0.0,
                "sector_inference_eligible": False,
            },
        ]
    )
    by_ticker = reference[
        [
            "ticker",
            "unit_cost_scope",
            "normalized_unit_cost_observations",
            "independent_complete_unit_cost_scope",
        ]
    ].copy()
    by_ticker["normalization_confidence_grade"] = np.select(
        [
            by_ticker["independent_complete_unit_cost_scope"],
            by_ticker["unit_cost_scope"].str.contains(
                "ACCOUNTING_PROVEN|SEC_UPSTREAM", regex=True
            ),
        ],
        ["A", "B"],
        default="C",
    )
    weights = policy.set_index("normalization_confidence_grade")[
        "sector_inference_weight"
    ]
    by_ticker["sector_inference_weight"] = by_ticker[
        "normalization_confidence_grade"
    ].map(weights)
    by_ticker["terminal_input_allowed"] = False
    by_ticker["research_only"] = True
    return policy, by_ticker


def _build_annual_attribution(
    *,
    evidence: pd.DataFrame,
    reference: pd.DataFrame,
    ttm_financial: pd.DataFrame,
) -> pd.DataFrame:
    financial = ttm_financial.loc[
        ttm_financial["quarter"].astype(str).str.endswith("Q4"),
        ["ticker", "quarter", "ttm_nopat_usd", "effective_tax_rate"],
    ].copy()
    financial["year"] = financial["quarter"].astype(str).str[:4].astype(int)
    merged = evidence.merge(
        reference[
            [
                "ticker",
                "normalized_price_per_boe",
                "normalized_unit_cost_per_boe",
                "normalized_tax_rate",
            ]
        ],
        on="ticker",
        how="left",
        validate="many_to_one",
    ).merge(
        financial.drop(columns="quarter"),
        on=["ticker", "year"],
        how="left",
        validate="one_to_one",
    )
    merged["actual_tax_rate"] = merged["effective_tax_rate"].clip(0.0, 0.35)
    volume = merged["production_mboe"] * 1_000.0
    actual_pre_tax_margin = (
        merged["actual_price_per_boe"] - merged["actual_unit_cost_per_boe"]
    )
    merged["reported_gaap_nopat_usd"] = merged["ttm_nopat_usd"]
    merged["reported_economic_nopat_usd"] = (
        actual_pre_tax_margin * volume * (1.0 - merged["actual_tax_rate"])
    )
    merged["price_only_normalized_nopat_usd"] = (
        (merged["normalized_price_per_boe"] - merged["actual_unit_cost_per_boe"])
        * volume
        * (1.0 - merged["actual_tax_rate"])
    )
    merged["cost_only_normalized_nopat_usd"] = (
        (merged["actual_price_per_boe"] - merged["normalized_unit_cost_per_boe"])
        * volume
        * (1.0 - merged["actual_tax_rate"])
    )
    merged["price_and_cost_normalized_nopat_usd"] = (
        (
            merged["normalized_price_per_boe"]
            - merged["normalized_unit_cost_per_boe"]
        )
        * volume
        * (1.0 - merged["actual_tax_rate"])
    )
    merged["full_cycle_normalized_nopat_usd"] = (
        (
            merged["normalized_price_per_boe"]
            - merged["normalized_unit_cost_per_boe"]
        )
        * volume
        * (1.0 - merged["normalized_tax_rate"])
    )
    merged["accounting_scope_residual_usd"] = (
        merged["reported_gaap_nopat_usd"]
        - merged["reported_economic_nopat_usd"]
    )
    merged["price_normalization_effect_usd"] = (
        merged["price_only_normalized_nopat_usd"]
        - merged["reported_economic_nopat_usd"]
    )
    merged["cost_normalization_effect_usd"] = (
        merged["cost_only_normalized_nopat_usd"]
        - merged["reported_economic_nopat_usd"]
    )
    merged["tax_normalization_effect_usd"] = (
        merged["full_cycle_normalized_nopat_usd"]
        - merged["price_and_cost_normalized_nopat_usd"]
    )
    reconstructed = (
        merged["reported_gaap_nopat_usd"]
        - merged["accounting_scope_residual_usd"]
        + merged["price_normalization_effect_usd"]
        + merged["cost_normalization_effect_usd"]
        + merged["tax_normalization_effect_usd"]
    )
    merged["normalization_attribution_identity_error_usd"] = (
        merged["full_cycle_normalized_nopat_usd"] - reconstructed
    )
    merged["normalization_attribution_identity_passed"] = merged[
        "normalization_attribution_identity_error_usd"
    ].abs().le(1.0)
    merged["normalization_attribution_annual_complete"] = (
        merged["source_cells_fully_verified"]
        & merged["independent_complete_cost_scope"]
        & merged[list(ATTRIBUTION_VARIANTS)].notna().all(axis=1)
        & merged["normalization_attribution_identity_passed"]
    )
    merged["terminal_input_allowed"] = False
    merged["research_only"] = True
    return merged.sort_values(["ticker", "year"]).reset_index(drop=True)


def _fang_divestiture_book_evidence(
    companyfacts_root: Path,
) -> dict[str, Any]:
    proceeds, proceeds_tag, proceeds_hash, proceeds_filed, _ = _annual_fact(
        companyfacts_root,
        "FANG",
        2019,
        ("ProceedsFromSaleOfPropertyPlantAndEquipment",),
    )
    gain, gain_tag, gain_hash, gain_filed, _ = _annual_fact(
        companyfacts_root,
        "FANG",
        2019,
        ("GainLossOnSaleOfPropertyPlantEquipment",),
    )
    book_value = proceeds - gain if pd.notna(proceeds) and pd.notna(gain) else np.nan
    return {
        "proceeds_usd": proceeds,
        "gain_usd": gain,
        "book_value_usd": book_value,
        "source_tags": f"{proceeds_tag};{gain_tag}",
        "source_bundle_sha256": hashlib.sha256(
            "|".join(sorted([proceeds_hash, gain_hash])).encode("ascii")
        ).hexdigest(),
        "available_at": max(proceeds_filed, gain_filed),
        "book_value_proven": bool(pd.notna(book_value) and book_value >= 0),
    }


def _build_cohort_attribution(
    *,
    annual: pd.DataFrame,
    v172_cohorts: pd.DataFrame,
    v172_cycle_company_year: pd.DataFrame,
    historical_evidence: pd.DataFrame,
    annual_organic: pd.DataFrame,
    companyfacts_root: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    events = [("DVN", "WPX Energy", 2021), ("FANG", "Energen Corporation", 2018)]
    fang_event = historical_evidence.iloc[0]
    fang_divestiture = _fang_divestiture_book_evidence(companyfacts_root)
    for ticker, event_name, deal_year in events:
        history = annual.loc[
            annual["ticker"].eq(ticker)
            & annual["year"].between(deal_year - 1, deal_year + 2)
        ].set_index("year")
        if len(history) != 4:
            continue
        cumulative_denominator = 0.0
        cumulative: dict[str, float] = {
            "reported_gaap": 0.0,
            **{variant: 0.0 for variant in ATTRIBUTION_VARIANTS},
        }
        all_scope: dict[str, bool] = {
            "reported_gaap": True,
            **{variant: True for variant in ATTRIBUTION_VARIANTS},
        }
        opening_row = annual_organic.loc[
            annual_organic["ticker"].eq(ticker)
            & annual_organic["year"].eq(deal_year)
        ].iloc[0]
        threshold = abs(float(opening_row["opening_invested_capital_usd"])) * 0.02
        for offset in range(3):
            year = deal_year + offset
            current = history.loc[year]
            prior = history.loc[year - 1]
            annual_row = annual_organic.loc[
                annual_organic["ticker"].eq(ticker)
                & annual_organic["year"].eq(year)
            ].iloc[0]
            acquired_production_mboe = 0.0
            if ticker == "DVN":
                parent = v172_cohorts.loc[
                    v172_cohorts["ticker"].eq(ticker)
                    & v172_cohorts["cohort_offset"].eq(offset)
                ].iloc[0]
                denominator = float(parent["organic_invested_capital_proxy_usd"])
                denominator_scope = bool(parent["parent_annual_scope_complete"])
                reported_numerator = float(parent["reported_organic_nopat_bridge_usd"])
                reported_scope = bool(
                    parent["reported_organic_nopat_annual_scope_complete"]
                )
                if offset == 0:
                    cycle_row = v172_cycle_company_year.loc[
                        v172_cycle_company_year["ticker"].eq(ticker)
                        & v172_cycle_company_year["deal_year"].eq(deal_year)
                        & v172_cycle_company_year["year"].eq(year)
                    ].iloc[0]
                    acquired_production_mboe = float(
                        cycle_row["acquiree_production_since_close_proxy_mboe"]
                    )
                perimeter_status = parent["parent_cohort_status"]
            else:
                raw_denominator = float(annual_row["raw_delta_invested_capital_usd"])
                if offset == 0:
                    denominator = raw_denominator - float(
                        fang_event["acquired_invested_capital_usd"]
                    )
                    gross_perimeter = abs(
                        float(annual_row["opening_invested_capital_usd"])
                    ) + float(fang_event["acquired_invested_capital_usd"])
                    divestiture_ratio = (
                        float(annual_row["divestiture_cash_proxy_usd"])
                        / gross_perimeter
                    )
                    denominator_scope = bool(
                        fang_event["acquired_capital_proxy_ready"]
                        and divestiture_ratio <= 0.01
                    )
                    acquired_production_mboe = (
                        float(fang_event["acquiree_revenue_since_close_usd"])
                        / float(current["actual_price_per_boe"])
                        / 1_000.0
                    )
                    perimeter_status = "EVENT_ACQUISITION_BRIDGED_IMMATERIAL_DIVESTITURE_GROSS_PERIMETER"
                elif offset == 1:
                    denominator = raw_denominator + float(
                        fang_divestiture["book_value_usd"]
                    )
                    denominator_scope = bool(fang_divestiture["book_value_proven"])
                    perimeter_status = "DIVESTITURE_BOOK_CAPITAL_PROVEN_OPERATING_CONTRIBUTION_MISSING"
                else:
                    denominator = raw_denominator
                    denominator_scope = bool(annual_row["denominator_scope_complete"])
                    perimeter_status = annual_row["organic_bridge_status"]
                reported_numerator = float(annual_row["raw_delta_nopat_usd"])
                reported_scope = bool(offset == 2 and annual_row["numerator_scope_complete"])

            variant_numerators: dict[str, float] = {}
            annual_evidence_complete = bool(
                current["normalization_attribution_annual_complete"]
                and prior["normalization_attribution_annual_complete"]
            )
            for variant in ATTRIBUTION_VARIANTS:
                numerator = float(current[variant] - prior[variant])
                if offset == 0:
                    per_boe = float(current[variant]) / (
                        float(current["production_mboe"]) * 1_000.0
                    )
                    numerator -= acquired_production_mboe * 1_000.0 * per_boe
                variant_numerators[variant] = numerator
            if ticker == "DVN":
                economic_scope = bool(denominator_scope and annual_evidence_complete)
            else:
                economic_scope = bool(
                    denominator_scope
                    and annual_evidence_complete
                    and offset != 1
                )

            cumulative_denominator += denominator
            all_scope["reported_gaap"] = (
                all_scope["reported_gaap"] and denominator_scope and reported_scope
            )
            if all_scope["reported_gaap"]:
                cumulative["reported_gaap"] += reported_numerator
            for variant, numerator in variant_numerators.items():
                all_scope[variant] = all_scope[variant] and economic_scope
                if all_scope[variant]:
                    cumulative[variant] += numerator

            output: dict[str, Any] = {
                "ticker": ticker,
                "event_name": event_name,
                "deal_year": deal_year,
                "cohort_offset": offset,
                "observation_year": year,
                "year_label": "t" if offset == 0 else f"t+{offset}",
                "organic_invested_capital_proxy_usd": denominator,
                "denominator_scope_complete": denominator_scope,
                "perimeter_status": perimeter_status,
                "acquiree_production_same_period_proxy_mboe": acquired_production_mboe,
                "reported_organic_nopat_usd": reported_numerator,
                "reported_organic_nopat_scope_complete": reported_scope,
                "economic_variant_scope_complete": economic_scope,
                "reported_organic_roic_pct": (
                    reported_numerator / denominator * 100.0
                    if reported_scope and denominator > threshold
                    else np.nan
                ),
                "cumulative_organic_invested_capital_proxy_usd": cumulative_denominator,
                "reported_cumulative_organic_roic_pct": (
                    cumulative["reported_gaap"] / cumulative_denominator * 100.0
                    if all_scope["reported_gaap"]
                    and cumulative_denominator > threshold
                    else np.nan
                ),
                "reported_cohort_complete": bool(
                    offset == 2 and all_scope["reported_gaap"]
                ),
                "methodology_attribution_complete": bool(
                    len(history) == 4
                    and history["normalization_attribution_annual_complete"].all()
                ),
                "independent_cost_normalized_cohort_complete": bool(
                    offset == 2
                    and len(history) == 4
                    and history["normalization_attribution_annual_complete"].all()
                    and history["normalization_confidence_grade"].eq("A").all()
                ),
                "organic_company_roic_validated": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
            for variant, numerator in variant_numerators.items():
                prefix = variant.removesuffix("_nopat_usd")
                output[f"{prefix}_organic_nopat_usd"] = numerator
                output[f"{prefix}_organic_roic_pct"] = (
                    numerator / denominator * 100.0
                    if economic_scope and denominator > threshold
                    else np.nan
                )
                output[f"{prefix}_cumulative_organic_roic_pct"] = (
                    cumulative[variant] / cumulative_denominator * 100.0
                    if all_scope[variant]
                    and cumulative_denominator > threshold
                    else np.nan
                )
                output[f"{prefix}_cohort_complete"] = bool(
                    offset == 2 and all_scope[variant]
                )
            rows.append(output)
    return pd.DataFrame(rows).sort_values(
        ["deal_year", "ticker", "cohort_offset"]
    ).reset_index(drop=True)


def _build_organic_validation(
    *, triangulation: pd.DataFrame, cohorts: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    mature = cohorts.loc[cohorts["cohort_offset"].eq(2)].set_index(
        ["ticker", "deal_year"]
    )
    for event in triangulation.to_dict("records"):
        key = (event["ticker"], int(event["fiscal_year"]))
        cohort = mature.loc[key] if key in mature.index else None
        reported_complete = bool(
            cohort is not None and cohort["reported_cohort_complete"]
        )
        full_cycle_complete = bool(
            cohort is not None
            and cohort["full_cycle_normalized_cohort_complete"]
        )
        method_complete = bool(
            cohort is not None
            and cohort["methodology_attribution_complete"]
        )
        independent_complete = bool(
            cohort is not None
            and cohort["independent_cost_normalized_cohort_complete"]
        )
        triangulated = bool(event["two_route_nopat_triangulated"])
        acquisition_return = event["evidence_backed_acquisition_return_proxy_pct"]
        blockers: list[str] = []
        if not triangulated:
            blockers.append("NOPAT_TWO_ROUTE_NOT_TRIANGULATED")
        if not reported_complete:
            blockers.append("REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE")
        if not full_cycle_complete:
            blockers.append("CYCLE_NORMALIZED_ORGANIC_3Y_COHORT_INCOMPLETE")
        if not independent_complete:
            blockers.append("INDEPENDENT_COST_COHORT_INCOMPLETE")
        if pd.isna(acquisition_return):
            blockers.append("ACQUISITION_RETURN_UNAVAILABLE")
        validated = bool(
            triangulated
            and reported_complete
            and full_cycle_complete
            and method_complete
            and independent_complete
            and pd.notna(acquisition_return)
        )
        rows.append(
            {
                "ticker": event["ticker"],
                "fiscal_year": int(event["fiscal_year"]),
                "event_name": event["event_name"],
                "reported_3y_roic_pct": (
                    cohort["reported_cumulative_organic_roic_pct"]
                    if cohort is not None
                    else np.nan
                ),
                "cycle_normalized_3y_roic_pct": (
                    cohort["full_cycle_normalized_cumulative_organic_roic_pct"]
                    if cohort is not None
                    else np.nan
                ),
                "acquisition_return_proxy_pct": acquisition_return,
                "two_route_nopat_triangulated": triangulated,
                "reported_cohort_complete": reported_complete,
                "cycle_normalized_cohort_complete": full_cycle_complete,
                "methodology_attribution_complete": method_complete,
                "independent_cost_cohort_complete": independent_complete,
                "organic_company_roic_validated": validated,
                "validation_status": (
                    "VALIDATED_ORGANIC_ROIC_RESEARCH_RANGE"
                    if validated
                    else "LOCKED__" + "__".join(blockers)
                ),
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(
        drop=True
    )


def build_normalization_attribution(
    *,
    fang_registry_path: Path,
    ir_root: Path,
    companyfacts_root: Path,
    v172_reference: pd.DataFrame,
    v172_production: pd.DataFrame,
    v172_cohorts: pd.DataFrame,
    v172_cycle_company_year: pd.DataFrame,
    historical_evidence: pd.DataFrame,
    triangulation: pd.DataFrame,
    annual_organic: pd.DataFrame,
    ttm_financial_path: Path,
) -> dict[str, pd.DataFrame]:
    fang = _build_fang_historical_cost_evidence(
        registry_path=fang_registry_path,
        ir_root=ir_root,
        companyfacts_root=companyfacts_root,
    )
    dvn = _build_dvn_cost_evidence(
        production=v172_production,
        companyfacts_root=companyfacts_root,
    )
    evidence = pd.concat([fang, dvn], ignore_index=True, sort=False).sort_values(
        ["ticker", "year"]
    )
    ttm = pd.read_parquet(ttm_financial_path)
    annual = _build_annual_attribution(
        evidence=evidence,
        reference=v172_reference,
        ttm_financial=ttm,
    )
    policy, by_ticker = _confidence_tables(v172_reference)
    cohorts = _build_cohort_attribution(
        annual=annual,
        v172_cohorts=v172_cohorts,
        v172_cycle_company_year=v172_cycle_company_year,
        historical_evidence=historical_evidence,
        annual_organic=annual_organic,
        companyfacts_root=companyfacts_root,
    )
    validation = _build_organic_validation(
        triangulation=triangulation,
        cohorts=cohorts,
    )
    return {
        "normalization_confidence_policy": policy,
        "normalization_confidence_by_ticker": by_ticker,
        "independent_cost_annual_evidence": evidence.reset_index(drop=True),
        "normalization_attribution_annual": annual,
        "normalization_attribution_cohorts": cohorts,
        "organic_roic_validation": validation,
    }
