from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .sources import (
    build_cost_recovery_evidence,
    build_program_event_timeline,
    parse_bls_labor_snapshot,
    parse_guidance_vintages,
    parse_workforce_history,
    sha256_file,
)
from .valuation import build_operational_margin_valuation_crosscheck


def _annual_segment_actuals(segment_history: pd.DataFrame) -> pd.DataFrame:
    frame = segment_history.copy()
    frame["year"] = frame["period"].astype(str).str[:4].astype(int)
    coverage = frame.groupby(["year", "segment"])["period"].nunique().rename("quarters")
    annual = (
        frame.groupby(["year", "segment"], as_index=False)
        .agg(
            revenue_usd=("sales_usd", "sum"),
            operating_income_usd=("operating_profit_usd", "sum"),
        )
        .merge(coverage.reset_index(), on=["year", "segment"], validate="one_to_one")
    )
    annual = annual.loc[annual["quarters"].eq(4)].copy()
    annual["operating_margin_pct"] = (
        annual["operating_income_usd"] / annual["revenue_usd"] * 100.0
    )
    ship = (
        annual.loc[annual["segment"].ne("mission_technologies")]
        .groupby("year", as_index=False)
        .agg(
            revenue_usd=("revenue_usd", "sum"),
            operating_income_usd=("operating_income_usd", "sum"),
        )
    )
    ship["operating_margin_pct"] = ship["operating_income_usd"] / ship["revenue_usd"] * 100.0
    ship["business"] = "shipbuilding"
    mission = annual.loc[annual["segment"].eq("mission_technologies")].copy()
    mission["business"] = "mission_technologies"
    return pd.concat(
        [
            ship[["year", "business", "revenue_usd", "operating_income_usd", "operating_margin_pct"]],
            mission[["year", "business", "revenue_usd", "operating_income_usd", "operating_margin_pct"]],
        ],
        ignore_index=True,
    ).sort_values(["year", "business"])


def _build_guidance_analysis(
    vintages: pd.DataFrame, segment_history: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    revisions = vintages.sort_values(["forecast_year", "filing_date"]).copy()
    for metric in (
        "shipbuilding_margin_midpoint_pct",
        "mission_margin_midpoint_pct",
        "free_cash_flow_midpoint_usd",
        "shipbuilding_revenue_midpoint_usd",
        "mission_revenue_midpoint_usd",
    ):
        revisions[f"revision_{metric}"] = revisions.groupby("forecast_year")[metric].diff()
    revisions["both_segment_margins_improved_same_vintage"] = (
        revisions["revision_shipbuilding_margin_midpoint_pct"].gt(0)
        & revisions["revision_mission_margin_midpoint_pct"].gt(0)
    )
    revisions["material_shipbuilding_margin_revision"] = revisions[
        "revision_shipbuilding_margin_midpoint_pct"
    ].abs().ge(0.5)
    revisions["guidance_is_point_in_time_at_origin"] = True
    revisions["terminal_margin_point_input_allowed"] = False

    actuals = _annual_segment_actuals(segment_history)
    realization_rows: list[dict[str, object]] = []
    for year, group in revisions.groupby("forecast_year"):
        group = group.sort_values("filing_date")
        first, last = group.iloc[0], group.iloc[-1]
        actual_ship = actuals.loc[
            actuals["year"].eq(year) & actuals["business"].eq("shipbuilding")
        ]
        actual_mission = actuals.loc[
            actuals["year"].eq(year) & actuals["business"].eq("mission_technologies")
        ]
        realized = len(actual_ship) == 1 and len(actual_mission) == 1
        ship_actual = float(actual_ship.iloc[0]["operating_margin_pct"]) if realized else np.nan
        mission_actual = (
            float(actual_mission.iloc[0]["operating_margin_pct"]) if realized else np.nan
        )
        realization_rows.append(
            {
                "forecast_year": year,
                "first_origin_period": first["forecast_origin_period"],
                "last_origin_period": last["forecast_origin_period"],
                "guidance_vintages": len(group),
                "first_shipbuilding_margin_midpoint_pct": first[
                    "shipbuilding_margin_midpoint_pct"
                ],
                "last_shipbuilding_margin_midpoint_pct": last[
                    "shipbuilding_margin_midpoint_pct"
                ],
                "realized_shipbuilding_margin_pct": ship_actual,
                "first_shipbuilding_error_pp": (
                    float(first["shipbuilding_margin_midpoint_pct"]) - ship_actual
                    if realized
                    else np.nan
                ),
                "last_shipbuilding_error_pp": (
                    float(last["shipbuilding_margin_midpoint_pct"]) - ship_actual
                    if realized
                    else np.nan
                ),
                "realized_shipbuilding_inside_last_range": (
                    bool(
                        float(last["shipbuilding_margin_low_pct"])
                        <= ship_actual
                        <= float(last["shipbuilding_margin_high_pct"])
                    )
                    if realized
                    else pd.NA
                ),
                "first_mission_margin_midpoint_pct": first["mission_margin_midpoint_pct"],
                "last_mission_margin_midpoint_pct": last["mission_margin_midpoint_pct"],
                "realized_mission_margin_pct": mission_actual,
                "first_mission_error_pp": (
                    float(first["mission_margin_midpoint_pct"]) - mission_actual
                    if realized
                    else np.nan
                ),
                "last_mission_error_pp": (
                    float(last["mission_margin_midpoint_pct"]) - mission_actual
                    if realized
                    else np.nan
                ),
                "realized_mission_inside_last_range": (
                    bool(
                        float(last["mission_margin_low_pct"])
                        <= mission_actual
                        <= float(last["mission_margin_high_pct"])
                    )
                    if realized
                    else pd.NA
                ),
                "realized": realized,
                "authority": "GUIDANCE_RELIABILITY_RESEARCH_NOT_TERMINAL_INPUT",
            }
        )
    realization = pd.DataFrame(realization_rows)
    shocks = revisions.loc[
        revisions["material_shipbuilding_margin_revision"]
        | revisions["revision_free_cash_flow_midpoint_usd"].abs().ge(200_000_000.0)
    ].copy()
    shocks["execution_loss_signal"] = (
        shocks["revision_shipbuilding_margin_midpoint_pct"].lt(0)
        | shocks["revision_free_cash_flow_midpoint_usd"].lt(0)
    )
    shocks["structural_margin_upgrade_evidence"] = False
    return revisions.reset_index(drop=True), realization, shocks.reset_index(drop=True)


def _build_workforce_productivity(
    workforce: pd.DataFrame,
    company_history: pd.DataFrame,
    annual_catchup: pd.DataFrame,
) -> pd.DataFrame:
    company = company_history.copy()
    company["year"] = company["period"].astype(str).str[:4].astype(int)
    annual = company.groupby("year", as_index=False).agg(
        quarters=("period", "nunique"),
        revenue_usd=("revenue_usd", "sum"),
        operating_income_usd=("operating_income_usd", "sum"),
    )
    annual = annual.loc[annual["quarters"].eq(4)]
    catchup = annual_catchup.copy()
    catchup["year"] = catchup["period"].astype(int)
    result = workforce.merge(annual, on="year", how="left").merge(
        catchup[["year", "net_cumulative_catchup_adjustment_usd"]],
        on="year",
        how="left",
    )
    result["revenue_per_approximate_employee_usd"] = (
        result["revenue_usd"] / result["approximate_employees"]
    )
    result["catchup_neutral_operating_income_usd"] = (
        result["operating_income_usd"] - result["net_cumulative_catchup_adjustment_usd"]
    )
    result["catchup_neutral_operating_income_per_employee_usd"] = (
        result["catchup_neutral_operating_income_usd"] / result["approximate_employees"]
    )
    result["revenue_per_employee_yoy_pct"] = result[
        "revenue_per_approximate_employee_usd"
    ].pct_change(fill_method=None) * 100.0
    result["labor_hour_productivity_claim_allowed"] = False
    result["reason"] = (
        "Approximate total headcount spans all businesses; direct labor hours and segment headcount are not disclosed."
    )
    return result


def _build_contract_behavior(
    segment_history: pd.DataFrame,
    contract_mix: pd.DataFrame,
    annual_segment_catchup: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = segment_history.copy()
    detail["year"] = detail["period"].astype(str).str[:4].astype(int)
    segment_annual = (
        detail.groupby(["year", "segment"], as_index=False)
        .agg(
            quarters=("period", "nunique"),
            revenue_usd=("sales_usd", "sum"),
            operating_income_usd=("operating_profit_usd", "sum"),
        )
    )
    segment_annual = segment_annual.loc[segment_annual["quarters"].eq(4)]
    segment_annual["period"] = segment_annual["year"].astype(str)
    mix = contract_mix.loc[
        contract_mix["source_type"].eq("SEC_10K")
        & contract_mix["segment"].ne("consolidated")
    ]
    fixed = (
        mix.loc[mix["fixed_price_risk_channel"]]
        .groupby(["period", "segment"], as_index=False)["contract_mix_pct"]
        .sum()
        .rename(columns={"contract_mix_pct": "fixed_price_risk_share_pct"})
    )
    catchup = annual_segment_catchup.copy()
    fixed["period"] = fixed["period"].astype(str)
    catchup["period"] = catchup["period"].astype(str)
    behavior = (
        segment_annual.merge(fixed, on=["period", "segment"], how="inner")
        .merge(
            catchup[["period", "segment", "net_cumulative_catchup_adjustment_usd"]],
            on=["period", "segment"],
            how="inner",
        )
        .sort_values(["period", "segment"])
    )
    behavior["reported_margin_pct"] = (
        behavior["operating_income_usd"] / behavior["revenue_usd"] * 100.0
    )
    behavior["catchup_effect_pct_of_segment_revenue"] = (
        behavior["net_cumulative_catchup_adjustment_usd"]
        / behavior["revenue_usd"]
        * 100.0
    )
    behavior["catchup_neutral_margin_pct"] = (
        behavior["operating_income_usd"]
        - behavior["net_cumulative_catchup_adjustment_usd"]
    ) / behavior["revenue_usd"] * 100.0
    behavior["contract_mix_is_ex_post_annual"] = True
    behavior["contract_vintage_margin_identified"] = False
    behavior["causal_claim_allowed"] = False

    correlation = float(
        behavior["fixed_price_risk_share_pct"].corr(
            behavior["catchup_effect_pct_of_segment_revenue"].abs()
        )
    )
    summary = pd.DataFrame(
        [
            {
                "observations": len(behavior),
                "segments": behavior["segment"].nunique(),
                "years": behavior["period"].nunique(),
                "fixed_share_vs_absolute_catchup_pearson": correlation,
                "contract_vintage_margin_identified": False,
                "causal_claim_allowed": False,
                "status": "SMALL_EX_POST_PANEL_DIAGNOSTIC_ONLY",
            }
        ]
    )
    return behavior.reset_index(drop=True), summary


def _build_contract_vintage_coverage(
    contract_mix: pd.DataFrame,
    quarterly_segment_catchup: pd.DataFrame,
    program_events: pd.DataFrame,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"field": "CONTRACT_TYPE_REVENUE", "coverage": f"{contract_mix['period'].nunique()} PERIODS", "identified": True, "limitation": "Type mix, not contract vintage margin."},
            {"field": "SEGMENT_CATCHUP", "coverage": f"{quarterly_segment_catchup['period'].nunique()} QUARTERS", "identified": True, "limitation": "Segment total; program attribution is partial."},
            {"field": "AWARD_AND_MODIFICATION_YEAR", "coverage": f"{len(program_events)} PROGRAM EVENTS", "identified": True, "limitation": "Selected major programs only."},
            {"field": "CONTRACT_VINTAGE_MARGIN", "coverage": "0", "identified": False, "limitation": "No margin disclosure by individual award vintage."},
            {"field": "COST_SHARE_LIMIT_BY_CONTRACT", "coverage": "0", "identified": False, "limitation": "FPI mechanics disclosed, thresholds are not."},
            {"field": "PRICE_RESET_AMOUNT", "coverage": "0", "identified": False, "limitation": "Modification does not prove economic price reset."},
            {"field": "DIRECT_LABOR_HOURS_AND_VARIANCE", "coverage": "0", "identified": False, "limitation": "No company labor-hour series disclosed."},
            {"field": "MATERIAL_AND_SCHEDULE_VARIANCE", "coverage": "PARTIAL_NARRATIVE", "identified": False, "limitation": "Large catch-ups named selectively, not a complete variance ledger."},
        ]
    ).assign(
        terminal_margin_point_input_allowed=False,
        status="PARTIAL_MECHANISM_DIAGNOSTIC_NOT_CONTRACT_VINTAGE_MARGIN_MODEL",
    )


def _build_nonsegment_normalization(
    company_history: pd.DataFrame,
    fas_cas: pd.DataFrame,
    company_ttm: pd.DataFrame,
    guidance: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    company = company_history.copy()
    company["year"] = company["period"].astype(str).str[:4].astype(int)
    annual_revenue = company.groupby("year", as_index=False).agg(
        quarters=("period", "nunique"), revenue_usd=("revenue_usd", "sum")
    )
    annual_revenue = annual_revenue.loc[annual_revenue["quarters"].eq(4)]
    annual = fas_cas.loc[fas_cas["source_type"].eq("SEC_10K")].copy()
    annual["year"] = annual["period"].astype(int)
    annual = annual.merge(annual_revenue, on="year", how="left")
    annual["fas_cas_effect_pct_of_revenue"] = (
        annual["operating_fas_cas_effect_on_operating_income_usd"]
        / annual["revenue_usd"]
        * 100.0
    )
    annual["other_nonsegment_effect_pct_of_revenue"] = (
        annual["other_nonsegment_effect_on_operating_income_usd"]
        / annual["revenue_usd"]
        * 100.0
    )
    annual["total_nonsegment_effect_pct_of_revenue"] = (
        annual["operating_income_usd"] - annual["segment_operating_income_usd"]
    ) / annual["revenue_usd"] * 100.0
    annual["terminal_persistence_assumed"] = False

    latest_ttm = company_ttm.sort_values("period").iloc[-1]
    latest_guidance = guidance.sort_values("filing_date").iloc[-1]
    company_revenue_mid = (
        float(latest_guidance["shipbuilding_revenue_midpoint_usd"])
        + float(latest_guidance["mission_revenue_midpoint_usd"])
        - 150_000_000.0
    )
    guided_nonsegment = (
        float(latest_guidance["operating_fas_cas_midpoint_usd"])
        + float(latest_guidance["noncurrent_state_tax_midpoint_usd"])
    ) / company_revenue_mid * 100.0
    summary = pd.DataFrame(
        [
            {
                "reference": "TTM_CURRENT",
                "nonsegment_contribution_pct": float(
                    latest_ttm["nonsegment_ttm_contribution_pct"]
                ),
                "evidence": latest_ttm["period"],
            },
            {
                "reference": "TTM_HISTORICAL_MEDIAN",
                "nonsegment_contribution_pct": float(
                    company_ttm["nonsegment_ttm_contribution_pct"].median()
                ),
                "evidence": f"{len(company_ttm)} TTM windows",
            },
            {
                "reference": "FY26_GUIDANCE",
                "nonsegment_contribution_pct": guided_nonsegment,
                "evidence": latest_guidance["forecast_origin_period"],
            },
        ]
    )
    summary["terminal_input_allowed"] = False
    summary["authority"] = "NONSEGMENT_NORMALIZATION_DIAGNOSTIC"
    return annual, summary


def _build_contemporaneous_panel(
    segment_history: pd.DataFrame,
    quarterly_segment_catchup: pd.DataFrame,
    company_ttm: pd.DataFrame,
    guidance: pd.DataFrame,
) -> pd.DataFrame:
    frame = segment_history.merge(
        quarterly_segment_catchup[
            ["period", "segment", "net_cumulative_catchup_adjustment_usd"]
        ],
        on=["period", "segment"],
        how="inner",
        validate="one_to_one",
    ).sort_values(["segment", "period"])
    frame["catchup_neutral_operating_income_usd"] = (
        frame["operating_profit_usd"] - frame["net_cumulative_catchup_adjustment_usd"]
    )
    rows: list[pd.DataFrame] = []
    for segment, group in frame.groupby("segment"):
        group = group.sort_values("period").copy()
        group["ttm_revenue_usd"] = group["sales_usd"].rolling(4).sum()
        group["ttm_catchup_neutral_operating_income_usd"] = group[
            "catchup_neutral_operating_income_usd"
        ].rolling(4).sum()
        group["catchup_neutral_ttm_margin_pct"] = (
            group["ttm_catchup_neutral_operating_income_usd"]
            / group["ttm_revenue_usd"]
            * 100.0
        )
        rows.append(
            group[
                [
                    "period",
                    "segment",
                    "ttm_revenue_usd",
                    "ttm_catchup_neutral_operating_income_usd",
                    "catchup_neutral_ttm_margin_pct",
                ]
            ]
        )
    segment_ttm = pd.concat(rows, ignore_index=True).dropna()
    ship = (
        segment_ttm.loc[segment_ttm["segment"].ne("mission_technologies")]
        .groupby("period", as_index=False)
        .agg(
            shipbuilding_ttm_revenue_usd=("ttm_revenue_usd", "sum"),
            shipbuilding_ttm_neutral_operating_income_usd=(
                "ttm_catchup_neutral_operating_income_usd",
                "sum",
            ),
        )
    )
    ship["shipbuilding_catchup_neutral_ttm_margin_pct"] = (
        ship["shipbuilding_ttm_neutral_operating_income_usd"]
        / ship["shipbuilding_ttm_revenue_usd"]
        * 100.0
    )
    mission = segment_ttm.loc[
        segment_ttm["segment"].eq("mission_technologies"),
        ["period", "catchup_neutral_ttm_margin_pct"],
    ].rename(
        columns={
            "catchup_neutral_ttm_margin_pct": "mission_catchup_neutral_ttm_margin_pct"
        }
    )
    company = company_ttm[
        [
            "period",
            "catchup_neutral_ttm_margin_pct",
            "nonsegment_ttm_contribution_pct",
        ]
    ].rename(
        columns={
            "catchup_neutral_ttm_margin_pct": "reported_mix_catchup_neutral_consolidated_margin_pct"
        }
    )
    panel = ship.merge(mission, on="period", validate="one_to_one").merge(
        company, on="period", validate="one_to_one"
    )
    latest_guidance = guidance.sort_values("filing_date").iloc[-1]
    ship_revenue = float(latest_guidance["shipbuilding_revenue_midpoint_usd"])
    mission_revenue = float(latest_guidance["mission_revenue_midpoint_usd"])
    company_revenue = ship_revenue + mission_revenue - 150_000_000.0
    panel["fy26_mix_reweighted_consolidated_margin_pct"] = (
        ship_revenue
        * panel["shipbuilding_catchup_neutral_ttm_margin_pct"]
        / 100.0
        + mission_revenue
        * panel["mission_catchup_neutral_ttm_margin_pct"]
        / 100.0
        + company_revenue * panel["nonsegment_ttm_contribution_pct"] / 100.0
    ) / company_revenue * 100.0
    panel["all_components_are_same_ttm_window"] = True
    panel["terminal_input_allowed"] = False
    return panel.sort_values("period").reset_index(drop=True)


def _build_mission_ceiling(
    distributions: pd.DataFrame, guidance: pd.DataFrame
) -> pd.DataFrame:
    normalized = distributions.loc[
        distributions["entity"].eq("mission_technologies")
        & distributions["basis"].eq("CATCHUP_NEUTRAL_TTM")
    ].iloc[0]
    latest = guidance.sort_values("filing_date").iloc[-1]
    guided_margin = float(latest["mission_margin_midpoint_pct"])
    guided_ebitda = float(latest["mission_ebitda_margin_midpoint_pct"])
    return pd.DataFrame(
        [
            {
                "catchup_neutral_observations": int(normalized["observations"]),
                "historical_median_operating_margin_pct": float(normalized["median_pct"]),
                "historical_q90_operating_margin_pct": float(normalized["q90_pct"]),
                "historical_max_operating_margin_pct": float(normalized["maximum_pct"]),
                "fy26_guided_operating_margin_pct": guided_margin,
                "fy26_guided_ebitda_margin_pct": guided_ebitda,
                "ebitda_less_operating_margin_spread_pp": guided_ebitda - guided_margin,
                "guided_margin_gap_vs_normalized_max_pp": guided_margin
                - float(normalized["maximum_pct"]),
                "sustainable_operating_margin_ceiling_identified": False,
                "status": "FY26_5PCT_GUIDANCE_ABOVE_NORMALIZED_MAX_NOT_YET_REALIZED",
                "terminal_input_allowed": False,
            }
        ]
    )


def _build_industry_pressure_summary(
    ppi: pd.DataFrame, bls: pd.DataFrame
) -> pd.DataFrame:
    bls_index = bls.set_index("series_id")
    ship_ppi = ppi.loc[ppi["segment"].eq("ingalls_shipbuilding")].iloc[0]
    mission_ppi = ppi.loc[ppi["segment"].eq("mission_technologies")].iloc[0]
    labor_composite = float(bls["composite_labor_input_cost_proxy_yoy_pct"].iloc[0])
    rows = [
        {
            "pressure_channel": "SHIPBUILDING_MATERIAL_PRICE_RECOVERY_PROXY",
            "scope": "INGALLS_AND_NEWPORT",
            "primary_metric_pct": float(ship_ppi["price_less_cost_proxy_yoy_pp"]),
            "secondary_metric_pct": float(ship_ppi["dedicated_cost_yoy_pct"]),
            "interpretation": "Input-cost PPI proxy is outrunning output-price proxy.",
            "pit_status": "PIT_AS_RELEASED_PROXY",
        },
        {
            "pressure_channel": "MISSION_MATERIAL_PRICE_RECOVERY_PROXY",
            "scope": "MISSION_TECHNOLOGIES",
            "primary_metric_pct": float(mission_ppi["price_less_cost_proxy_yoy_pp"]),
            "secondary_metric_pct": float(mission_ppi["dedicated_cost_yoy_pct"]),
            "interpretation": "Input-cost PPI proxy is outrunning output-price proxy.",
            "pit_status": "PIT_AS_RELEASED_PROXY",
        },
        {
            "pressure_channel": "SHIPBUILDING_LABOR_INPUT_PROXY",
            "scope": "SHIPBUILDING_EMPLOYMENT_PLUS_TRANSPORT_EQUIPMENT_HOURS_WAGES",
            "primary_metric_pct": labor_composite,
            "secondary_metric_pct": float(
                bls_index.loc["CES3133600003", "year_over_year_pct"]
            ),
            "interpretation": "Composite employment-hours-wage input proxy remains positive; wage data is broader than shipbuilding.",
            "pit_status": "CURRENT_REVISED_NOT_PIT_MODEL_INPUT",
        },
    ]
    result = pd.DataFrame(rows)
    result["supports_structural_margin_expansion"] = False
    result["terminal_input_allowed"] = False
    return result


def _verify_lineage_sources(frames: list[pd.DataFrame]) -> pd.DataFrame:
    inventory = pd.concat(
        [
            frame[["source_path", "source_sha256"]]
            for frame in frames
            if {"source_path", "source_sha256"}.issubset(frame.columns)
        ],
        ignore_index=True,
    ).drop_duplicates()
    rows: list[dict[str, object]] = []
    for record in inventory.itertuples():
        path = Path(str(record.source_path))
        exists = path.is_file()
        actual = sha256_file(path) if exists else ""
        rows.append(
            {
                "source_path": str(path),
                "expected_sha256": record.source_sha256,
                "actual_sha256": actual,
                "source_exists": exists,
                "hash_match": exists and actual == str(record.source_sha256),
            }
        )
    return pd.DataFrame(rows)


def _build_operational_requirements(
    panel: pd.DataFrame,
    mission_ceiling: pd.DataFrame,
    nonsegment: pd.DataFrame,
    guidance: pd.DataFrame,
    targets: list[float],
) -> pd.DataFrame:
    latest = guidance.sort_values("filing_date").iloc[-1]
    ship_revenue = float(latest["shipbuilding_revenue_midpoint_usd"])
    mission_revenue = float(latest["mission_revenue_midpoint_usd"])
    company_revenue = ship_revenue + mission_revenue - 150_000_000.0
    mission_margin = float(mission_ceiling.iloc[0]["fy26_guided_operating_margin_pct"])
    guided_nonsegment_pct = float(
        nonsegment.loc[nonsegment["reference"].eq("FY26_GUIDANCE"), "nonsegment_contribution_pct"].iloc[0]
    )
    ship_q90 = float(panel["shipbuilding_catchup_neutral_ttm_margin_pct"].quantile(0.90))
    ship_max = float(panel["shipbuilding_catchup_neutral_ttm_margin_pct"].max())
    mission_q90 = float(panel["mission_catchup_neutral_ttm_margin_pct"].quantile(0.90))
    contemporaneous_max = float(panel["fy26_mix_reweighted_consolidated_margin_pct"].max())
    rows: list[dict[str, object]] = []
    for target in targets:
        required_ship = (
            target / 100.0 * company_revenue
            - mission_revenue * mission_margin / 100.0
            - company_revenue * guided_nonsegment_pct / 100.0
        ) / ship_revenue * 100.0
        required_mission = (
            target / 100.0 * company_revenue
            - ship_revenue * ship_q90 / 100.0
            - company_revenue * guided_nonsegment_pct / 100.0
        ) / mission_revenue * 100.0
        rows.append(
            {
                "target_consolidated_margin_pct": target,
                "fy26_shipbuilding_revenue_midpoint_usd": ship_revenue,
                "fy26_mission_revenue_midpoint_usd": mission_revenue,
                "fy26_company_revenue_midpoint_usd": company_revenue,
                "mission_margin_assumption_pct": mission_margin,
                "nonsegment_contribution_assumption_pct": guided_nonsegment_pct,
                "required_shipbuilding_margin_pct": required_ship,
                "shipbuilding_normalized_q90_pct": ship_q90,
                "shipbuilding_normalized_max_pct": ship_max,
                "required_shipbuilding_gap_vs_normalized_max_pp": required_ship - ship_max,
                "required_mission_margin_if_shipbuilding_at_q90_pct": required_mission,
                "mission_normalized_q90_pct": mission_q90,
                "observed_contemporaneous_max_pct": contemporaneous_max,
                "observed_contemporaneous_periods_at_or_above_target": int(
                    panel["fy26_mix_reweighted_consolidated_margin_pct"].ge(target).sum()
                ),
                "operational_mechanism_proven": False,
                "terminal_input_allowed": False,
            }
        )
    return pd.DataFrame(rows)


def _build_mechanism_scorecard(
    guidance_shocks: pd.DataFrame,
    bls_summary: pd.DataFrame,
    panel: pd.DataFrame,
    mission: pd.DataFrame,
    nonsegment: pd.DataFrame,
) -> pd.DataFrame:
    bls = bls_summary.set_index("series_id")
    latest_nonsegment = float(
        nonsegment.loc[nonsegment["reference"].eq("FY26_GUIDANCE"), "nonsegment_contribution_pct"].iloc[0]
    )
    rows = [
        {"mechanism": "CONTRACT_VINTAGE_MARGIN", "evidence_status": "NOT_IDENTIFIED", "key_metric": "0 contract-vintage margin observations", "supports_8_to_10_pct": False},
        {"mechanism": "FPI_COST_RECOVERY", "evidence_status": "PARTIAL_RISK_EVIDENCE", "key_metric": "Cost-share limit and escalation basis risk disclosed; clause-level thresholds absent", "supports_8_to_10_pct": False},
        {"mechanism": "LABOR_AND_PRODUCTIVITY", "evidence_status": "PRESSURE_NOT_DIRECT_PRODUCTIVITY", "key_metric": f"Shipbuilding employment YoY {bls.loc['CES3133661101','year_over_year_pct']:.2f}%; transport-equipment hours {bls.loc['CES3133600002','year_over_year_pct']:.2f}%; wage {bls.loc['CES3133600003','year_over_year_pct']:.2f}%", "supports_8_to_10_pct": False},
        {"mechanism": "GUIDANCE_AND_SCHEDULE_EXECUTION", "evidence_status": "NEGATIVE_TAIL_OBSERVED", "key_metric": f"{len(guidance_shocks)} material guidance revision rows", "supports_8_to_10_pct": False},
        {"mechanism": "AWARD_MODIFICATION_PRICE_RESET_LAG", "evidence_status": "NOT_IDENTIFIED", "key_metric": "Award/modification years exist; economic price reset amount and effective lag do not", "supports_8_to_10_pct": False},
        {"mechanism": "FAS_CAS_AND_NONSEGMENT", "evidence_status": "NORMALIZED_DRAG_IDENTIFIED", "key_metric": f"FY26 guided contribution {latest_nonsegment:.2f}%p", "supports_8_to_10_pct": False},
        {"mechanism": "MISSION_TECHNOLOGIES_MARGIN", "evidence_status": "FIVE_PERCENT_FORWARD_STRETCH", "key_metric": f"FY26 guide {mission.iloc[0]['fy26_guided_operating_margin_pct']:.2f}% vs neutral max {mission.iloc[0]['historical_max_operating_margin_pct']:.2f}%", "supports_8_to_10_pct": False},
        {"mechanism": "CONTEMPORANEOUS_COMPONENT_UPSIDE", "evidence_status": "NOT_OBSERVED", "key_metric": f"FY26-mix reweighted same-window max {panel['fy26_mix_reweighted_consolidated_margin_pct'].max():.2f}%", "supports_8_to_10_pct": False},
    ]
    result = pd.DataFrame(rows)
    result["valuation_upgrade_allowed"] = False
    result["terminal_input_allowed"] = False
    result["authority"] = "OPERATIONAL_MECHANISM_RESEARCH_ONLY"
    return result


def build_hii_v54_margin_mechanism_research(
    *, root: Path, config: dict[str, Any]
) -> dict[str, pd.DataFrame]:
    v53 = root / Path(config["v53_output"])
    segment_history = pd.read_csv(root / Path(config["segment_history"]))
    company_history = pd.read_csv(root / Path(config["company_history"]))
    contract_mix = pd.read_csv(v53 / "hii_contract_type_mix_history.csv")
    annual_catchup = pd.read_csv(v53 / "hii_annual_cumulative_catchup_history.csv")
    annual_segment_catchup = pd.read_csv(v53 / "hii_annual_segment_catchup_history.csv")
    quarterly_segment_catchup = pd.read_csv(v53 / "hii_quarterly_segment_catchup_history.csv")
    fas_cas = pd.read_csv(v53 / "hii_fas_cas_reconciliation_history.csv")
    company_ttm = pd.read_csv(v53 / "hii_company_ttm_margin_history.csv")
    distributions = pd.read_csv(v53 / "hii_margin_distribution.csv")

    ten_k_paths = sorted((root / Path(config["sec_10k_directory"])).glob("*.htm"))
    ten_q_paths = sorted((root / Path(config["sec_10q_directory"])).glob("*.htm"))
    guidance = parse_guidance_vintages(
        root=root,
        inventory_path=Path(config["ir_inventory"]),
        start_period=str(config["guidance_start_period"]),
    )
    revisions, realization, shocks = _build_guidance_analysis(guidance, segment_history)
    workforce = parse_workforce_history(ten_k_paths)
    workforce_productivity = _build_workforce_productivity(
        workforce, company_history, annual_catchup
    )
    bls_history, bls_summary = parse_bls_labor_snapshot(
        root / Path(config["bls_labor_snapshot"]),
        max_reference_period=str(config["bls_max_reference_period"]),
    )
    latest_ten_k = ten_k_paths[-1]
    recovery = build_cost_recovery_evidence(latest_ten_k)
    program_events = build_program_event_timeline(latest_ten_k)
    contract_behavior, contract_summary = _build_contract_behavior(
        segment_history, contract_mix, annual_segment_catchup
    )
    vintage_coverage = _build_contract_vintage_coverage(
        contract_mix, quarterly_segment_catchup, program_events
    )
    nonsegment_annual, nonsegment_summary = _build_nonsegment_normalization(
        company_history, fas_cas, company_ttm, guidance
    )
    panel = _build_contemporaneous_panel(
        segment_history, quarterly_segment_catchup, company_ttm, guidance
    )
    mission = _build_mission_ceiling(distributions, guidance)
    ppi = pd.read_csv(v53 / "hii_industry_cost_recovery_diagnostic.csv")
    industry_pressure = _build_industry_pressure_summary(ppi, bls_summary)
    requirements = _build_operational_requirements(
        panel,
        mission,
        nonsegment_summary,
        guidance,
        [float(value) for value in config["terminal_margin_hypotheses_pct"]],
    )
    margin_cases = pd.DataFrame(
        [
            {
                "margin_case": "FY26_GUIDED_CONSOLIDATED_MIDPOINT",
                "terminal_margin_pct": 5.5452830188679245,
                "operational_evidence_class": "NEAR_TERM_GUIDANCE_NOT_TERMINAL",
            },
            {
                "margin_case": "RECENT_CONTEMPORANEOUS_NORMALIZED_MAX",
                "terminal_margin_pct": float(
                    panel["fy26_mix_reweighted_consolidated_margin_pct"].max()
                ),
                "operational_evidence_class": "RECENT_SAME_WINDOW_MAX_NOT_TERMINAL",
            },
            *[
                {
                    "margin_case": f"HYPOTHESIS_{target:g}_PCT",
                    "terminal_margin_pct": target,
                    "operational_evidence_class": "UNPROVEN_STRUCTURAL_HYPOTHESIS",
                }
                for target in config["terminal_margin_hypotheses_pct"]
            ],
        ]
    )
    valuation = build_operational_margin_valuation_crosscheck(
        root=root, config=config, margin_cases=margin_cases
    )
    scorecard = _build_mechanism_scorecard(
        shocks,
        bls_summary,
        panel,
        mission,
        nonsegment_summary,
    )
    scorecard.loc[
        scorecard["mechanism"].eq("FPI_COST_RECOVERY"), "key_metric"
    ] = (
        "Cost-share limit plus escalation basis risk; shipbuilding PIT price-cost gap "
        f"{float(ppi.loc[ppi['segment'].eq('ingalls_shipbuilding'), 'price_less_cost_proxy_yoy_pp'].iloc[0]):.2f}%p"
    )
    lineage = _verify_lineage_sources(
        [
            guidance,
            segment_history,
            bls_history,
            workforce,
            recovery,
            program_events,
            contract_mix,
            annual_catchup,
            annual_segment_catchup,
            quarterly_segment_catchup,
            fas_cas,
        ]
    )
    if not lineage["hash_match"].all():
        raise ValueError("V5.4 source-lineage hash verification failed")
    latest_contract = contract_mix.loc[contract_mix["period"].eq("2026Q2")]
    fixed_share = float(
        latest_contract.loc[
            latest_contract["segment"].eq("consolidated")
            & latest_contract["fixed_price_risk_channel"],
            "contract_mix_pct",
        ].sum()
    )
    source_coverage = pd.DataFrame(
        [
            {"layer": "SEC_10K_HTML", "source_count": len(ten_k_paths), "use": "WORKFORCE_COST_RECOVERY_PROGRAM_EVENTS_FAS_CAS"},
            {"layer": "SEC_10Q_HTML", "source_count": len(ten_q_paths), "use": "PARENT_V53_CATCHUP_AND_CONTRACT_EVIDENCE"},
            {"layer": "ARCANA_IR_HTML", "source_count": guidance["source_sha256"].nunique(), "use": "18_PIT_GUIDANCE_VINTAGES_AND_REALIZATION"},
            {"layer": "ARCANA_IR_HTML_ACTUALS", "source_count": segment_history["source_sha256"].nunique(), "use": "27_QUARTER_SEGMENT_MARGIN_HISTORY"},
            {"layer": "BLS_CES_CURRENT_REVISED", "source_count": bls_history["series_id"].nunique(), "use": "SHIPBUILDING_EMPLOYMENT_AND_LABOR_COST_CONTEXT_THROUGH_2026M06"},
            {"layer": "BLS_PPI_AS_RELEASED", "source_count": ppi["segment"].nunique(), "use": "PIT_OUTPUT_PRICE_VERSUS_INPUT_COST_PROXY"},
            {"layer": "FROZEN_V5_3", "source_count": 1, "use": "CATCHUP_NEUTRAL_MARGIN_CONTRACT_AND_NONSEGMENT_BASE"},
            {"layer": "FROZEN_V5_2", "source_count": 1, "use": "DCF_AND_REVERSE_DCF_EXPECTATIONS_CROSSCHECK"},
        ]
    )
    source_coverage["all_lineage_hashes_verified"] = bool(lineage["hash_match"].all())
    source_coverage["pdf_parsing_used"] = False
    source_coverage["terminal_point_input_allowed"] = False

    summary = pd.DataFrame(
        [
            {
                "as_of_date": config["as_of_date"],
                "guidance_vintages": len(guidance),
                "realized_guidance_years": int(realization["realized"].sum()),
                "material_guidance_revision_rows": len(shocks),
                "latest_fixed_price_risk_share_pct": fixed_share,
                "recent_contemporaneous_ttm_windows": len(panel),
                "recent_contemporaneous_normalized_max_pct": float(
                    panel["fy26_mix_reweighted_consolidated_margin_pct"].max()
                ),
                "mission_fy26_guided_margin_pct": float(
                    mission.iloc[0]["fy26_guided_operating_margin_pct"]
                ),
                "mission_normalized_max_pct": float(
                    mission.iloc[0]["historical_max_operating_margin_pct"]
                ),
                "operational_mechanisms_supporting_8_to_10_pct": int(
                    scorecard["supports_8_to_10_pct"].sum()
                ),
                "shipbuilding_pit_price_cost_gap_pp": float(
                    ppi.loc[
                        ppi["segment"].eq("ingalls_shipbuilding"),
                        "price_less_cost_proxy_yoy_pp",
                    ].iloc[0]
                ),
                "bls_labor_input_proxy_yoy_pct": float(
                    bls_summary["composite_labor_input_cost_proxy_yoy_pct"].iloc[0]
                ),
                "valuation_upgrade_allowed": False,
                "fair_value_claim_allowed": False,
                "terminal_authority": False,
                "production_promoted": False,
                "live_forward_matched_observations": "0/20",
                "status": "MARGIN_MECHANISM_RESEARCH_COMPLETE_NO_STRUCTURAL_8_TO_10PCT_PROOF",
            }
        ]
    )
    all_10k_available = len(ten_k_paths) == 7
    all_10q_available = len(ten_q_paths) == 20
    all_ir_hashes_verified = bool(guidance["source_sha256"].notna().all())
    guidance_vintage_coverage_complete = len(guidance) == 18
    bls_series_complete = bls_history["series_id"].nunique() == 4
    bls_cutoff_enforced = bool(
        bls_history["reference_period"].le(
            str(config["bls_max_reference_period"])
        ).all()
    )
    all_lineage_hashes_verified = bool(lineage["hash_match"].all())
    dcf_reverse_crosscheck_run = len(valuation) == 5
    research_freeze_eligible = all(
        (
            all_10k_available,
            all_10q_available,
            all_ir_hashes_verified,
            guidance_vintage_coverage_complete,
            bls_series_complete,
            bls_cutoff_enforced,
            all_lineage_hashes_verified,
            dcf_reverse_crosscheck_run,
        )
    )
    gate = pd.DataFrame(
        [
            {
                "all_10k_available": all_10k_available,
                "all_10q_available": all_10q_available,
                "all_ir_hashes_verified": all_ir_hashes_verified,
                "guidance_vintage_coverage_complete": guidance_vintage_coverage_complete,
                "bls_series_complete": bls_series_complete,
                "bls_cutoff_enforced": bls_cutoff_enforced,
                "all_lineage_hashes_verified": all_lineage_hashes_verified,
                "contract_vintage_margin_identified": False,
                "direct_labor_hours_identified": False,
                "price_reset_lag_identified": False,
                "contemporaneous_eight_pct_observed": bool(
                    panel["fy26_mix_reweighted_consolidated_margin_pct"].ge(8.0).any()
                ),
                "operational_mechanism_for_structural_eight_to_ten_proven": False,
                "dcf_reverse_crosscheck_run": dcf_reverse_crosscheck_run,
                "valuation_upgrade_allowed": False,
                "fair_value_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_promoted": False,
                "research_freeze_eligible": research_freeze_eligible,
                "status": "RESEARCH_FREEZE_READY_WITH_FAIL_CLOSED_AUTHORITY",
            }
        ]
    )
    return {
        "hii_v54_source_coverage": source_coverage,
        "hii_guidance_vintage_history": guidance,
        "hii_guidance_revision_history": revisions,
        "hii_guidance_realization_audit": realization,
        "hii_material_guidance_shocks": shocks,
        "hii_workforce_history": workforce,
        "hii_workforce_productivity_proxy": workforce_productivity,
        "hii_bls_labor_history": bls_history,
        "hii_bls_labor_summary": bls_summary,
        "hii_industry_labor_material_pressure_summary": industry_pressure,
        "hii_source_lineage_hash_audit": lineage,
        "hii_cost_recovery_mechanism_evidence": recovery,
        "hii_program_award_modification_timeline": program_events,
        "hii_contract_catchup_behavior": contract_behavior,
        "hii_contract_catchup_behavior_summary": contract_summary,
        "hii_contract_vintage_identifiability": vintage_coverage,
        "hii_nonsegment_annual_bridge": nonsegment_annual,
        "hii_nonsegment_normalization_summary": nonsegment_summary,
        "hii_contemporaneous_margin_panel": panel,
        "hii_mission_margin_ceiling": mission,
        "hii_operational_margin_requirements": requirements,
        "hii_operational_margin_valuation_crosscheck": valuation,
        "hii_margin_mechanism_scorecard": scorecard,
        "hii_v54_research_summary": summary,
        "hii_v54_gate": gate,
    }
