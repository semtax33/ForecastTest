from __future__ import annotations

from pathlib import Path

import pandas as pd


V5_OUTPUT = Path("output/industrials_v5_hii_third_company_research")


def _classify_company_route(route: str) -> tuple[str, bool, str]:
    if route == "PREDECLARED_EQUAL_BLEND":
        return "CLEAN_PROSPECTIVE_BENCHMARK", True, "PREDECLARED_BEFORE_FIXED_OOS"
    if route == "PRIOR_YEAR_NAIVE":
        return "PREDECLARED_BASELINE", True, "SCALING_BASELINE_ONLY"
    if route == "PIT_INDUSTRY_BRIDGE":
        return "BEST_TESTED_DIAGNOSTIC", False, "MINIMUM_SELECTED_FROM_SIX_ROUTES_ON_SAME_OOS"
    return "ALTERNATE_TESTED_DIAGNOSTIC", False, "TESTED_ON_SAME_FIXED_OOS"


def _route_registry(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = pd.read_csv(root / V5_OUTPUT / "hii_company_route_metrics.csv")
    rows: list[dict[str, object]] = []
    for row in metrics.itertuples(index=False):
        classification, predeclared, reason = _classify_company_route(str(row.route))
        rows.append(
            {
                **row._asdict(),
                "selection_class": classification,
                "predeclared_before_oos": predeclared,
                "clean_prospective_claim_allowed": bool(
                    row.route == "PREDECLARED_EQUAL_BLEND" and row.mase < 1.0
                ),
                "selection_reason": reason,
                "registry_status": "IMMUTABLE_FAILED_AND_ALTERNATE_ROUTE_RECORD",
            }
        )
    registry = pd.DataFrame(rows).sort_values(["mase", "route"]).reset_index(drop=True)
    best = registry.iloc[0]
    clean = registry.loc[registry["route"].eq("PREDECLARED_EQUAL_BLEND")].iloc[0]
    audit = pd.DataFrame(
        [
            {
                "company": "HII",
                "fixed_oos_window": "2025Q1-2026Q2",
                "routes_tested_on_same_oos": len(registry),
                "same_oos_minimum_was_reported_as_champion_in_v5": True,
                "v5_reported_route": best["route"],
                "v5_reported_mase": best["mase"],
                "corrected_v51_class": "BEST_TESTED_DIAGNOSTIC",
                "clean_predeclared_route": clean["route"],
                "clean_predeclared_mase": clean["mase"],
                "clean_predeclared_beats_naive": bool(clean["beats_prior_year_naive"]),
                "route_selection_leakage_present": True,
                "prospective_champion_claim_allowed": bool(clean["mase"] < 1.0),
                "forecast_reestimated_or_retuned": False,
            }
        ]
    )
    return registry, audit


def _segment_registry(root: Path) -> pd.DataFrame:
    outputs: list[pd.DataFrame] = []
    for target, filename in (
        ("SEGMENT_REVENUE", "hii_segment_revenue_route_metrics.csv"),
        ("SEGMENT_MARGIN", "hii_segment_margin_route_metrics.csv"),
    ):
        frame = pd.read_csv(root / V5_OUTPUT / filename)
        frame["target"] = target
        frame["predeclared_before_oos"] = frame["route"].isin(
            ["PREDECLARED_BLEND", "PRIOR_YEAR_NAIVE"]
        )
        frame["selection_class"] = "ALTERNATE_TESTED_DIAGNOSTIC"
        frame.loc[frame["route"].eq("PRIOR_YEAR_NAIVE"), "selection_class"] = (
            "PREDECLARED_BASELINE"
        )
        frame.loc[frame["route"].eq("PREDECLARED_BLEND"), "selection_class"] = (
            "CLEAN_PROSPECTIVE_BENCHMARK"
        )
        best_index = frame.groupby("segment")["mase"].idxmin().tolist()
        ex_post = [
            index
            for index in best_index
            if frame.at[index, "route"] != "PREDECLARED_BLEND"
        ]
        frame.loc[ex_post, "selection_class"] = "BEST_TESTED_DIAGNOSTIC"
        frame["clean_prospective_claim_allowed"] = (
            frame["route"].eq("PREDECLARED_BLEND") & frame["mase"].lt(1.0)
        )
        frame["registry_status"] = "IMMUTABLE_FAILED_AND_ALTERNATE_ROUTE_RECORD"
        outputs.append(frame)
    return pd.concat(outputs, ignore_index=True).sort_values(
        ["target", "segment", "mase", "route"]
    ).reset_index(drop=True)


def _authority_namespaces() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "authority_namespace": "AGGREGATE_REVENUE_POINT_AUTHORITY",
                "status": "RESEARCH_PROSPECTIVE_BENCHMARK",
                "allowed_input": "PREDECLARED_EQUAL_BLEND",
                "prohibited_claim": "PIT_INDUSTRY_BRIDGE_IS_CLEAN_CHAMPION",
            },
            {
                "authority_namespace": "SEGMENT_REVENUE_POINT_AUTHORITY",
                "status": "RESEARCH_PROSPECTIVE_BENCHMARK",
                "allowed_input": "PREDECLARED_BLEND_BY_SEGMENT",
                "prohibited_claim": "EX_POST_BEST_ROUTE_IS_PROSPECTIVE_CHAMPION",
            },
            {
                "authority_namespace": "SEGMENT_REVENUE_CAUSAL_ATTRIBUTION_AUTHORITY",
                "status": "DENIED",
                "allowed_input": "DIAGNOSTIC_ONLY",
                "prohibited_claim": "BACKLOG_OR_PPI_CAUSES_POINT_FORECAST_ACCURACY",
            },
            {
                "authority_namespace": "SEGMENT_MARGIN_POINT_AUTHORITY",
                "status": "RESEARCH_PROSPECTIVE_BENCHMARK",
                "allowed_input": "PREDECLARED_BLEND_BY_SEGMENT",
                "prohibited_claim": "COMPONENT_CAUSAL_AUTHORITY",
            },
            {
                "authority_namespace": "MARGIN_COMPONENT_CAUSAL_AUTHORITY",
                "status": "DENIED",
                "allowed_input": "BLS_COST_SIGNAL_AS_DIAGNOSTIC",
                "prohibited_claim": "PPI_SPREAD_IDENTIFIES_PROGRAM_MARGIN_CAUSE",
            },
            {
                "authority_namespace": "ROIC_ATTRIBUTION_AUTHORITY",
                "status": "DENIED_HISTORICAL_DIAGNOSTIC_ONLY",
                "allowed_input": "CONSOLIDATED_REPORTED_AND_PENSION_ADJUSTED_HISTORY",
                "prohibited_claim": "SEGMENT_OR_PROGRAM_ROIC_CAUSAL_ATTRIBUTION",
            },
            {
                "authority_namespace": "TERMINAL_AUTHORITY",
                "status": "DENIED_CONDITIONAL_SURFACE_ONLY",
                "allowed_input": "SCENARIO_SENSITIVITY",
                "prohibited_claim": "APPROPRIATE_TERMINAL_MARGIN_OR_ROIC",
            },
        ]
    )


def _replication(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    company = pd.read_csv(
        root / V5_OUTPUT / "aerospace_defense_three_company_company_level.csv"
    ).copy()
    company = company.rename(columns={"revenue_mase": "best_tested_revenue_mase"})
    company["fixed_oos_window"] = "2025Q1-2026Q2"
    company["cross_company_replication"] = True
    company["cross_regime_replication"] = False
    company["terminal_input_allowed"] = False
    company["production_promoted"] = False
    company.loc[company["company"].eq("HII"), "route"] = "PIT_INDUSTRY_BRIDGE_BEST_TESTED_DIAGNOSTIC"
    company["selection_caveat"] = "SEE_COMPANY_ROUTE_SELECTION_AUDIT"
    company.loc[company["company"].isin(["LMT", "NOC"]), "selection_caveat"] = (
        "PARENT_RESEARCH_ROUTE_AS_FROZEN"
    )

    segment = pd.read_csv(
        root / V5_OUTPUT / "aerospace_defense_three_company_segment_level.csv"
    ).copy()
    segment["fixed_oos_window"] = "2025Q1-2026Q2"
    segment["segment_result_use"] = "TIMING_HETEROGENEITY_DIAGNOSTIC"

    summary = pd.DataFrame(
        [
            {
                "benchmark": "AEROSPACE_DEFENSE_AGGREGATE_REVENUE_REPLICATION_V1",
                "companies": int(company["company"].nunique()),
                "aggregate_pass": int(company["revenue_champion_eligible"].sum()),
                "aggregate_total": len(company),
                "segment_pass": int(segment["revenue_champion_eligible"].sum()),
                "segment_total": len(segment),
                "fixed_oos_window": "2025Q1-2026Q2",
                "cross_company_replication": True,
                "cross_regime_replication": False,
                "status": "REPLICATED_RESEARCH_HYPOTHESIS_NOT_INDUSTRY_LAW",
                "terminal_input_allowed": False,
                "production_promoted": False,
                "research_freeze_eligible": True,
            }
        ]
    )
    return company, segment, summary


def build_hii_v51_governance(root: Path) -> dict[str, pd.DataFrame]:
    routes, leakage = _route_registry(root)
    company, segments, replication = _replication(root)
    return {
        "hii_company_route_registry": routes,
        "hii_route_selection_leakage_audit": leakage,
        "hii_segment_route_registry": _segment_registry(root),
        "hii_authority_namespaces": _authority_namespaces(),
        "ad_aggregate_replication_company": company,
        "ad_aggregate_replication_segment": segments,
        "ad_aggregate_replication_summary": replication,
    }
