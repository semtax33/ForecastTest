from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.core.champion_gate import assess_against_naive
from equity_platform.sectors.industrials.platform.validation import (
    build_aggregate_error_decomposition,
)


def _lmt(root: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    output = root / "output/industrials_v3_lmt_aerospace_research"
    segment = pd.read_csv(output / "lmt_portability_walk_forward.csv")
    return segment, None


def _noc_or_gd(root: Path, company: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if company == "NOC":
        output = root / "output/industrials_v4_noc_cross_company_research"
        prefix = "noc"
    else:
        output = root / "output/industrials_v6_gd_fourth_company_research"
        prefix = "gd"
    segment = pd.read_csv(output / f"{prefix}_portability_walk_forward.csv").rename(
        columns={"funded_backlog_predicted_sales_usd": "predicted_sales_usd"}
    )
    direct = pd.read_csv(output / f"{prefix}_company_walk_forward.csv").rename(
        columns={"funded_backlog_predicted_sales_usd": "predicted_sales_usd"}
    )
    return segment, direct


def _hii(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = root / "output/industrials_v5_hii_third_company_research"
    segment = pd.read_csv(output / "hii_segment_walk_forward.csv")
    routes = pd.read_csv(output / "hii_segment_revenue_champions.csv")
    route_columns = {
        "PIT_INDUSTRY_BRIDGE": "industry_bridge_sales_usd",
        "PREDECLARED_BLEND": "predeclared_blend_sales_usd",
        "HISTORICAL_GROWTH": "historical_growth_sales_usd",
    }
    route_by_segment = routes.set_index("segment")["route"].to_dict()
    segment["frozen_route"] = segment["segment"].map(route_by_segment)
    segment["predicted_sales_usd"] = [
        row[route_columns[row["frozen_route"]]] for _, row in segment.iterrows()
    ]
    segment = segment.rename(columns={"naive_sales_usd": "naive_prior_year_sales_usd"})
    direct = pd.read_csv(output / "hii_company_walk_forward.csv").rename(
        columns={
            "actual_revenue_usd": "actual_sales_usd",
            "naive_revenue_usd": "naive_prior_year_sales_usd",
            "industry_bridge_revenue_usd": "predicted_sales_usd",
        }
    )
    return segment, direct


def _aggregate_model_comparison(
    company: str, segment: pd.DataFrame, direct: pd.DataFrame | None
) -> dict[str, object]:
    summed = segment.groupby("period", as_index=False).agg(
        actual_sales_usd=("actual_sales_usd", "sum"),
        predicted_sales_usd=("predicted_sales_usd", "sum"),
        naive_prior_year_sales_usd=("naive_prior_year_sales_usd", "sum"),
    )
    segment_sum_metric = assess_against_naive(
        actual=summed["actual_sales_usd"],
        prediction=summed["predicted_sales_usd"],
        naive=summed["naive_prior_year_sales_usd"],
    )
    result: dict[str, object] = {
        "company": company,
        "segment_sum_validation_periods": len(summed),
        "segment_sum_revenue_mase": segment_sum_metric.mase,
        "segment_sum_revenue_champion": segment_sum_metric.eligible,
        "direct_company_model_available": direct is not None,
        "direct_company_validation_periods": np.nan,
        "direct_company_revenue_mase": np.nan,
        "direct_company_revenue_champion": False,
        "direct_minus_segment_sum_mase": np.nan,
    }
    if direct is not None:
        direct = direct.loc[direct["period"].isin(summed["period"])].copy()
        metric = assess_against_naive(
            actual=direct["actual_sales_usd"],
            prediction=direct["predicted_sales_usd"],
            naive=direct["naive_prior_year_sales_usd"],
        )
        result.update(
            {
                "direct_company_validation_periods": len(direct),
                "direct_company_revenue_mase": metric.mase,
                "direct_company_revenue_champion": metric.eligible,
                "direct_minus_segment_sum_mase": metric.mase
                - segment_sum_metric.mase,
            }
        )
    return result


def _anchor_matrix(root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    lmt = pd.read_csv(
        root / "output/industrials_v3_lmt_aerospace_research/lmt_portability_summary.csv"
    )
    for row in lmt.itertuples():
        rows.append(
            {
                "company": "LMT",
                "segment": row.segment,
                "business_archetype": "PLATFORM_MISSILES_ROTARY_MISSION",
                "primary_anchor": row.revenue_route,
                "primary_revenue_mase": row.revenue_mase,
                "primary_revenue_champion": row.revenue_champion_eligible,
                "comparison_anchor": "NONE_PREDECLARED",
                "comparison_revenue_mase": np.nan,
                "anchor_selection_outcome_blind": True,
            }
        )
    for company, folder, prefix in (
        ("NOC", "industrials_v4_noc_cross_company_research", "noc"),
        ("GD", "industrials_v6_gd_fourth_company_research", "gd"),
    ):
        summary = pd.read_csv(root / "output" / folder / f"{prefix}_portability_summary.csv")
        for row in summary.itertuples():
            rows.append(
                {
                    "company": company,
                    "segment": row.segment,
                    "business_archetype": "FUNDED_CONTRACT_PORTFOLIO",
                    "primary_anchor": "FUNDED_BACKLOG_PRICE",
                    "primary_revenue_mase": row.funded_backlog_revenue_mase,
                    "primary_revenue_champion": row.funded_backlog_revenue_champion_eligible,
                    "comparison_anchor": "TOTAL_BACKLOG_PRICE",
                    "comparison_revenue_mase": row.total_backlog_revenue_mase,
                    "anchor_selection_outcome_blind": True,
                }
            )
    hii = pd.read_csv(
        root / "output/industrials_v5_hii_third_company_research/hii_segment_revenue_champions.csv"
    )
    for row in hii.itertuples():
        rows.append(
            {
                "company": "HII",
                "segment": row.segment,
                "business_archetype": "SHIPBUILDING_OR_MISSION_SERVICES",
                "primary_anchor": row.route,
                "primary_revenue_mase": row.mase,
                "primary_revenue_champion": row.beats_prior_year_naive,
                "comparison_anchor": "FUNDING_SPLIT_NOT_DISCLOSED",
                "comparison_revenue_mase": np.nan,
                "anchor_selection_outcome_blind": True,
            }
        )
    return pd.DataFrame(rows)


def build_defense_cross_company_error_audit(root: Path) -> dict[str, pd.DataFrame]:
    company_inputs = {
        "LMT": _lmt(root),
        "NOC": _noc_or_gd(root, "NOC"),
        "HII": _hii(root),
        "GD": _noc_or_gd(root, "GD"),
    }
    period_frames: list[pd.DataFrame] = []
    correlation_frames: list[pd.DataFrame] = []
    summary_frames: list[pd.DataFrame] = []
    aggregate_rows: list[dict[str, object]] = []
    normalized_walks: list[pd.DataFrame] = []
    for company, (segment, direct) in company_inputs.items():
        selected = segment[
            [
                "period",
                "segment",
                "actual_sales_usd",
                "predicted_sales_usd",
                "naive_prior_year_sales_usd",
            ]
        ].copy()
        selected.insert(0, "company", company)
        normalized_walks.append(selected)
        audit = build_aggregate_error_decomposition(segment, company=company)
        period_frames.append(audit["period_error_decomposition"])
        correlation_frames.append(
            audit["scaled_segment_error_correlation"].assign(company=company)
        )
        summary_frames.append(audit["error_decomposition_summary"])
        aggregate_rows.append(_aggregate_model_comparison(company, segment, direct))
    summary = pd.concat(summary_frames, ignore_index=True)
    summary["four_company_universal_law_claim_allowed"] = False
    summary["classification"] = np.where(
        summary["aggregate_outperformance_depends_on_cancellation"],
        "AGGREGATE_SKILL_DEPENDS_ON_ERROR_CANCELLATION",
        np.where(
            summary["aggregate_signal_positive_before_cancellation"],
            "POSITIVE_SIGNAL_BEFORE_CANCELLATION",
            "NO_AGGREGATE_OUTPERFORMANCE",
        ),
    )
    return {
        "defense_normalized_segment_walk_forward": pd.concat(normalized_walks, ignore_index=True),
        "defense_period_error_decomposition": pd.concat(period_frames, ignore_index=True),
        "defense_scaled_segment_error_correlation": pd.concat(correlation_frames, ignore_index=True),
        "defense_error_decomposition_summary": summary,
        "defense_direct_vs_segment_sum_model": pd.DataFrame(aggregate_rows),
        "defense_anchor_portability_matrix": _anchor_matrix(root),
    }
