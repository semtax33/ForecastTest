from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.benchmark import verify_revenue_research_benchmark
from energy_nowcast.valuation.benchmark import MANIFEST, freeze_v1, verify_v1
from energy_nowcast.valuation.financials import (
    ENERGY_TICKERS,
    SUBINDUSTRY,
    build_quarterly_financials,
    build_ttm_financials,
)
from energy_nowcast.valuation.market import load_market_inputs
from energy_nowcast.valuation.valuation import run_valuation


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs" / "energy_valuation_v1.toml"
OUTPUT = ROOT / "output" / "energy_valuation_v1"
ARCANA = ROOT.parent / "Arcana" / "data-lake"
COMPANYFACTS = ARCANA / "bronze" / "sec" / "companyfacts"
PRICE_ROOT = ARCANA / "bronze" / "yfinance" / "price"
BENCHMARK_PRICE = ARCANA / "bronze" / "yfinance" / "benchmark" / "us_sp500.csv"
SHARES = ARCANA / "silver" / "us" / "shares" / "us_normalized_shares.csv"
RISK_FREE = ARCANA / "bronze" / "fred" / "rates" / "us_dgs10.csv"
PRICE_OVERRIDES = ROOT / "configs" / "energy_v1_market_price_overrides.csv"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Energy Valuation Platform V1")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument(
        "--rebuild-candidate",
        action="store_true",
        help="Write a candidate output even when immutable V1 already exists",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def _anchor_growth_inputs(ttm: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "ticker": ticker,
            "subindustry": SUBINDUSTRY[ticker],
            "anchor_growth_pct": np.nan,
            "anchor_growth_source": "HISTORICAL_PIT_DISTRIBUTION",
            "anchor_forecast_quarter": pd.NA,
        }
        for ticker in ENERGY_TICKERS
    ]
    result = pd.DataFrame(rows).set_index("ticker")
    ep_path = ROOT / "output" / "v3_4" / "nowcast.csv"
    if ep_path.exists():
        ep = pd.read_csv(ep_path)
        for row in ep.itertuples(index=False):
            result.at[row.ticker, "anchor_growth_pct"] = (
                np.exp(float(row.predicted_revenue_log_yoy) / 100.0) - 1.0
            ) * 100.0
            result.at[row.ticker, "anchor_growth_source"] = "V3.4_FROZEN_REVENUE_NOWCAST"
            result.at[row.ticker, "anchor_forecast_quarter"] = row.nowcast_quarter
    downstream_path = (
        ROOT / "output" / "phase2_4_company_kpi_research"
        / "latest_research_predictions.csv"
    )
    if downstream_path.exists():
        downstream = pd.read_csv(downstream_path)
        for row in downstream.itertuples(index=False):
            result.at[row.ticker, "anchor_growth_pct"] = (
                np.exp(float(row.candidate_prediction) / 100.0) - 1.0
            ) * 100.0
            result.at[row.ticker, "anchor_growth_source"] = (
                f"PHASE2_4_{str(row.subindustry).upper()}_SELECTED_RESEARCH_ROUTE"
            )
            result.at[row.ticker, "anchor_forecast_quarter"] = row.quarter
    ebitda_path = (
        ROOT / "output" / "phase2_5_target_aligned_research"
        / "midstream_adjusted_ebitda_quarterly.csv"
    )
    if ebitda_path.exists():
        ebitda = pd.read_csv(ebitda_path).sort_values("report_quarter")
        for ticker, group in ebitda.groupby("ticker"):
            latest = group.dropna(subset=["adjusted_ebitda_log_yoy"]).tail(1)
            if len(latest):
                row = latest.iloc[0]
                result.at[ticker, "anchor_growth_pct"] = (
                    np.exp(float(row["adjusted_ebitda_log_yoy"]) / 100.0) - 1.0
                ) * 100.0
                result.at[ticker, "anchor_growth_source"] = (
                    "MIDSTREAM_LATEST_ADJUSTED_EBITDA_YOY_ANCHOR"
                )
                result.at[ticker, "anchor_forecast_quarter"] = row["report_quarter"]
    return result.reset_index()


def _completion_status(
    config: dict[str, object],
    quarterly: pd.DataFrame,
    source_coverage: pd.DataFrame,
    latest: pd.DataFrame,
    market_coverage: pd.DataFrame,
    valuation: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assumptions = valuation["scenario_assumptions"]
    projections = valuation["dcf_projections"]
    forward = valuation["forward_dcf_probability_weighted"]
    reverse = valuation["reverse_dcf_expectations"]
    identity_error = (
        quarterly["nopat_usd"] - quarterly["reinvestment_usd"]
        - quarterly["fcff_usd"]
    ).abs().dropna()
    probability = assumptions.groupby("ticker")["probability"].sum()
    checks = {
        "all_26_tickers_have_latest_ttm_financials": latest["ticker"].nunique() == 26,
        "all_5_subindustries_covered": latest["subindustry"].nunique() == 5,
        "all_tickers_have_standardized_or_conditional_source_history": (
            source_coverage["complete_quarterly_rows"].ge(8).all()
        ),
        "historical_fcff_identity_holds": (
            len(identity_error) > 0 and float(identity_error.max()) < 1e-3
        ),
        "all_market_inputs_complete": market_coverage["market_input_complete"].all(),
        "all_market_prices_within_freshness_limit": market_coverage[
            "price_freshness_status"
        ].eq("CURRENT_WITHIN_LIMIT").all(),
        "three_scenarios_per_ticker": len(assumptions) == 26 * 3,
        "scenario_probabilities_sum_to_one": np.allclose(probability, 1.0),
        "scenario_guardrails_pass": assumptions["assumption_validation"].eq("PASS").all(),
        "minimum_distribution_history_pass": assumptions["minimum_history_pass"].all(),
        "five_year_projection_complete": len(projections) == 26 * 3 * int(config["forecast_horizon_years"]),
        "forward_dcf_complete": (
            len(forward) == 26
            and np.isfinite(forward["probability_weighted_fair_value"]).all()
        ),
        "reverse_dcf_complete": (
            len(reverse) == 26
            and reverse[[
                "market_implied_growth_pct", "market_implied_operating_margin_pct",
                "market_implied_roic_pct",
                "market_implied_competitive_advantage_period_years",
            ]].notna().all().all()
        ),
        "fixed_ratio_reverse_calculation_absent": (
            not bool(config["fixed_ratio_reverse_calculation_allowed"])
            and not assumptions["fixed_ratio_used"].any()
        ),
        "production_live_gate_not_met": int(config["live_matched_observations"]) < int(config["production_live_minimum"]),
    }
    audit = pd.DataFrame(
        [{"requirement": requirement, "passed": bool(passed)} for requirement, passed in checks.items()]
    )
    code_complete = all(checks[key] for key in (
        "historical_fcff_identity_holds", "three_scenarios_per_ticker",
        "five_year_projection_complete", "forward_dcf_complete",
        "reverse_dcf_complete", "fixed_ratio_reverse_calculation_absent",
    ))
    research_complete = bool(code_complete and all(checks.values()))
    statuses = pd.DataFrame([
        {"status_dimension": "V1_CODE", "status": "COMPLETE" if code_complete else "INCOMPLETE", "passed": code_complete},
        {"status_dimension": "V1_RESEARCH", "status": "COMPLETE" if research_complete else "INCOMPLETE", "passed": research_complete},
        {"status_dimension": "V1_PRODUCTION", "status": "NOT_PROMOTED_LIVE_0_OF_20", "passed": False},
    ])
    return audit, statuses


def main() -> None:
    args = _arguments()
    manifest_path = ROOT / MANIFEST
    if manifest_path.exists() and not args.rebuild_candidate:
        verified = verify_v1(ROOT)
        print(json.dumps(verified, indent=2, ensure_ascii=False))
        return
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    revenue_freeze = verify_revenue_research_benchmark(ROOT)

    quarterly, source_coverage = build_quarterly_financials(COMPANYFACTS)
    ttm = build_ttm_financials(quarterly)
    latest = (
        ttm.loc[ttm["ttm_complete"]]
        .sort_values(["ticker", "quarter_ordinal"])
        .groupby("ticker", as_index=False, group_keys=False)
        .tail(1)
        .reset_index(drop=True)
    )
    anchor_growth = _anchor_growth_inputs(ttm)
    market, market_coverage = load_market_inputs(
        price_root=PRICE_ROOT,
        benchmark_path=BENCHMARK_PRICE,
        shares_path=SHARES,
        risk_free_path=RISK_FREE,
        companyfacts_root=COMPANYFACTS,
        latest_financials=latest,
        tickers=ENERGY_TICKERS,
        as_of_date=pd.Timestamp(datetime.now().date()),
        equity_risk_premium_pct=float(config["equity_risk_premium_pct"]),
        fallback_credit_spread_pct=float(config["fallback_credit_spread_pct"]),
        maximum_price_age_days=int(config["market_price_max_age_days"]),
        price_overrides_path=PRICE_OVERRIDES,
    )
    valuation = run_valuation(ttm, market, config, anchor_growth)
    requirement_audit, completion_status = _completion_status(
        config, quarterly, source_coverage, latest, market_coverage, valuation
    )
    if not completion_status.loc[
        completion_status["status_dimension"].eq("V1_RESEARCH"), "passed"
    ].iloc[0]:
        # Persist the minimum failure diagnostics so a coverage miss can be
        # audited without re-reading every Companyfacts payload interactively.
        source_coverage.to_csv(output / "source_coverage.csv", index=False)
        valuation["scenario_assumptions"].to_csv(
            output / "scenario_assumptions.csv", index=False
        )
        requirement_audit.to_csv(output / "v1_requirement_audit.csv", index=False)
        completion_status.to_csv(output / "v1_completion_status.csv", index=False)
        failed = requirement_audit.loc[~requirement_audit["passed"], "requirement"].tolist()
        raise RuntimeError(f"Energy V1 research completion failed: {failed}")

    scenario_values = valuation["forward_dcf_scenario_values"]
    expectations = valuation["expectations_gap"]
    latest_score = latest[[
        "ticker", "subindustry", "quarter", "ttm_revenue",
        "operating_margin_pct", "ttm_fcff_usd", "fcff_margin_pct",
        "roic_pct", "incremental_roic_pct",
    ]].merge(
        expectations[[
            "ticker", "probability_weighted_fair_value",
            "probability_weighted_value_gap_pct",
            "growth_expectations_gap_pct_points",
            "margin_expectations_gap_pct_points",
            "roic_expectations_gap_pct_points", "cap_expectations_gap_years",
        ]],
        on="ticker",
        how="left",
    )
    subindustry_scorecard = (
        latest_score.groupby("subindustry", as_index=False)
        .agg(
            tickers=("ticker", "nunique"),
            median_operating_margin_pct=("operating_margin_pct", "median"),
            median_fcff_margin_pct=("fcff_margin_pct", "median"),
            median_roic_pct=("roic_pct", "median"),
            median_incremental_roic_pct=("incremental_roic_pct", "median"),
            median_probability_weighted_value_gap_pct=("probability_weighted_value_gap_pct", "median"),
            median_growth_expectations_gap_pct_points=("growth_expectations_gap_pct_points", "median"),
            median_margin_expectations_gap_pct_points=("margin_expectations_gap_pct_points", "median"),
            median_roic_expectations_gap_pct_points=("roic_expectations_gap_pct_points", "median"),
        )
    )

    artifacts = {
        "quarterly_financial_bridge.parquet": quarterly,
        "ttm_financial_bridge.parquet": ttm,
        "latest_financial_bridge.csv": latest,
        "source_coverage.csv": source_coverage,
        "anchor_growth_inputs.csv": anchor_growth,
        "market_inputs.csv": market,
        "market_input_coverage.csv": market_coverage,
        "scenario_assumptions.csv": valuation["scenario_assumptions"],
        "dcf_projections.csv": valuation["dcf_projections"],
        "forward_dcf_scenario_values.csv": scenario_values,
        "forward_dcf_probability_weighted.csv": valuation["forward_dcf_probability_weighted"],
        "reverse_dcf_expectations.csv": valuation["reverse_dcf_expectations"],
        "expectations_gap.csv": expectations,
        "latest_valuation_scorecard.csv": latest_score,
        "subindustry_valuation_scorecard.csv": subindustry_scorecard,
        "v1_requirement_audit.csv": requirement_audit,
        "v1_completion_status.csv": completion_status,
    }
    for name, frame in artifacts.items():
        path = output / name
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False)

    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_code_complete": True,
        "v1_research_complete": True,
        "v1_production_promoted": False,
        "live_matched_observations": "0/20",
        "ticker_count": int(latest["ticker"].nunique()),
        "subindustry_count": int(latest["subindustry"].nunique()),
        "scenario_count": int(valuation["scenario_assumptions"]["scenario"].nunique()),
        "fixed_ratio_reverse_calculation_used": False,
        "revenue_freeze_manifest_sha256": revenue_freeze["manifest_sha256"],
        "config_sha256": _sha256(CONFIG),
        "market_price_first_date": str(market["market_date"].min().date()),
        "market_price_last_date": str(market["market_date"].max().date()),
        "source_semantics": {
            "fcff": "CFO + AFTER_TAX_INTEREST - CASH_CAPEX",
            "nopat": "EBIT * (1 - EFFECTIVE_TAX_RATE)",
            "reinvestment": "NOPAT - FCFF",
            "invested_capital": "CURRENT_DEBT + NONCURRENT_DEBT + EQUITY_INCLUDING_NCI - CASH",
            "roic": "TTM_NOPAT / AVERAGE_INVESTED_CAPITAL",
            "incremental_roic": "DELTA_TTM_NOPAT / DELTA_INVESTED_CAPITAL",
        },
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    report = f"""# Energy Valuation Platform V1 — Research Freeze Candidate

## Completion status

{_markdown(completion_status)}

Development and research V1 are complete. Production remains explicitly not promoted because live-forward coverage is 0/20.

## End-to-end architecture

Every Energy subindustry now runs through:

`Economic Anchor → Revenue/EBIT → NOPAT → Reinvestment → FCFF → Invested Capital/ROIC → Forward DCF → Reverse DCF → Expectations Gap`

No fixed-margin reverse calculation is used. Missing source taxonomy is bridged only with prior-only trailing distributions and is separately labelled.

## Requirement audit

{_markdown(requirement_audit)}

## Subindustry valuation results

{_markdown(subindustry_scorecard)}

## Scenario engine

Bear/Base/Bull assumptions separately carry growth, operating margin, reinvestment, ROIC, WACC, terminal growth, probability, and Possible/Plausible/Probable validation. Probabilities sum to one for every ticker.

{_markdown(valuation['scenario_assumptions'].groupby(['subindustry', 'scenario'], as_index=False).agg(
    tickers=('ticker', 'nunique'),
    median_growth_pct=('growth_pct', 'median'),
    median_operating_margin_pct=('operating_margin_pct', 'median'),
    median_reinvestment_rate_pct=('reinvestment_rate_pct', 'median'),
    median_roic_pct=('roic_pct', 'median'),
    median_wacc_pct=('wacc_pct', 'median'),
    median_terminal_growth_pct=('terminal_growth_pct', 'median'),
    probability=('probability', 'first'),
))}

## Interpretation boundary

This is a research-complete valuation engine, not a production investment-decision engine. Fair values and reverse-DCF gaps are scenario outputs, not recommendations. Production promotion remains gated on 20 matched live-forward observations.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    if args.freeze:
        print(json.dumps(freeze_v1(ROOT), indent=2, ensure_ascii=False))
    else:
        print(f"Energy Valuation Platform V1 candidate written to {output}")


if __name__ == "__main__":
    main()
