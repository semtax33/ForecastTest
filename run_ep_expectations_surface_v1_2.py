from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.expectations_surface import (
    build_conditional_margin_wacc_tradeoffs,
    build_expectations_surfaces,
    build_iso_value_curves,
    build_through_cycle_economics,
    evaluate_weighted_value,
)
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parent
V1_OUTPUT = ROOT / "output" / "energy_valuation_v1"
V11_OUTPUT = ROOT / "output" / "energy_valuation_v1_1"
OUTPUT = ROOT / "output" / "energy_valuation_v1_2_research"


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def _iso_summary(curves: pd.DataFrame) -> pd.DataFrame:
    solved = curves.loc[curves["solver_status"].eq("SOLVED")]
    return (
        curves.groupby("surface", as_index=False)
        .agg(
            curve_points=("ticker", "size"),
            solved_points=("solver_status", lambda values: values.eq("SOLVED").sum()),
            unbracketed_points=(
                "solver_status",
                lambda values: values.eq("UNBRACKETED_NO_SOLUTION_IN_DOMAIN").sum(),
            ),
            tickers=("ticker", "nunique"),
        )
        .merge(
            solved.groupby("surface", as_index=False).agg(
                solved_value_q25_pct=("solved_value_pct", lambda values: values.quantile(0.25)),
                solved_value_median_pct=("solved_value_pct", "median"),
                solved_value_q75_pct=("solved_value_pct", lambda values: values.quantile(0.75)),
            ),
            on="surface",
            how="left",
        )
    )


def _conditional_summary(tradeoffs: pd.DataFrame) -> pd.DataFrame:
    solved = tradeoffs.loc[tradeoffs["solver_status"].eq("SOLVED")]
    return (
        tradeoffs.groupby("through_cycle_margin_reference", as_index=False)
        .agg(
            tickers=("ticker", "nunique"),
            solved_tickers=("solver_status", lambda values: values.eq("SOLVED").sum()),
            unbracketed_tickers=(
                "solver_status",
                lambda values: values.eq("UNBRACKETED_NO_SOLUTION_IN_DOMAIN").sum(),
            ),
        )
        .merge(
            solved.groupby("through_cycle_margin_reference", as_index=False).agg(
                terminal_margin_median_pct=("terminal_margin_pct", "median"),
                conditional_wacc_q25_pct=(
                    "market_equivalent_wacc_pct", lambda values: values.quantile(0.25)
                ),
                conditional_wacc_median_pct=("market_equivalent_wacc_pct", "median"),
                conditional_wacc_q75_pct=(
                    "market_equivalent_wacc_pct", lambda values: values.quantile(0.75)
                ),
            ),
            on="through_cycle_margin_reference",
            how="left",
        )
    )


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_before = verify_v1(ROOT)
    benchmark_before = verify_v11(ROOT)

    assumptions = pd.read_csv(V11_OUTPUT / "scenario_assumptions.csv")
    assumptions = assumptions.loc[assumptions["subindustry"].eq("ep")].copy()
    market = pd.read_csv(V11_OUTPUT / "adjusted_market_inputs.csv")
    market = market.loc[market["subindustry"].eq("ep")].copy()
    ttm = pd.read_parquet(V1_OUTPUT / "ttm_financial_bridge.parquet")
    economics = build_through_cycle_economics(ttm)
    detail, sector = build_expectations_surfaces(assumptions, market)
    curves = build_iso_value_curves(assumptions, market)
    tradeoffs = build_conditional_margin_wacc_tradeoffs(
        assumptions, market, economics
    )
    iso_summary = _iso_summary(curves)
    conditional_summary = _conditional_summary(tradeoffs)

    market_lookup = market.set_index("ticker")
    reproduced_rows = []
    for ticker, ticker_assumptions in assumptions.groupby("ticker", sort=True):
        reproduced_rows.append({
            "ticker": ticker,
            **evaluate_weighted_value(ticker_assumptions, market_lookup.loc[ticker]),
        })
    reproduced = pd.DataFrame(reproduced_rows).set_index("ticker")
    frozen = pd.read_csv(V11_OUTPUT / "forward_dcf_probability_weighted.csv")
    frozen = frozen.loc[frozen["subindustry"].eq("ep")].set_index("ticker")
    reproduced["frozen_fair_value"] = frozen["probability_weighted_fair_value"]
    reproduced["reproduction_error_per_share"] = (
        reproduced["fair_value"] - reproduced["frozen_fair_value"]
    )
    maximum_error = float(reproduced["reproduction_error_per_share"].abs().max())
    if maximum_error > 1e-6:
        raise RuntimeError(f"V1.2 research failed frozen reproduction: {maximum_error}")

    terminal_surface = sector.loc[
        sector["surface"].eq("TERMINAL_MARGIN_X_WACC")
    ]
    gap_matrix = terminal_surface.pivot(
        index="x_value_pct", columns="y_value_pct", values="median_value_gap_pct"
    )
    gap_matrix.index.name = "terminal_margin_pct"
    gap_matrix.columns = [f"wacc_{value:.1f}_pct" for value in gap_matrix.columns]
    count_matrix = terminal_surface.pivot(
        index="x_value_pct", columns="y_value_pct", values="tickers_above_market"
    )
    count_matrix.index.name = "terminal_margin_pct"
    count_matrix.columns = [
        f"wacc_{value:.1f}_pct" for value in count_matrix.columns
    ]

    economics.to_csv(OUTPUT / "through_cycle_economics.csv", index=False)
    detail.to_csv(OUTPUT / "expectations_surface_ticker_detail.csv", index=False)
    sector.to_csv(OUTPUT / "expectations_surface_sector_summary.csv", index=False)
    gap_matrix.to_csv(OUTPUT / "terminal_margin_wacc_gap_matrix.csv")
    count_matrix.to_csv(OUTPUT / "terminal_margin_wacc_above_market_count_matrix.csv")
    curves.to_csv(OUTPUT / "iso_value_curves.csv", index=False)
    iso_summary.to_csv(OUTPUT / "iso_value_curve_summary.csv", index=False)
    tradeoffs.to_csv(OUTPUT / "through_cycle_margin_wacc_tradeoffs.csv", index=False)
    conditional_summary.to_csv(
        OUTPUT / "through_cycle_margin_wacc_summary.csv", index=False
    )
    reproduced.reset_index().to_csv(
        OUTPUT / "frozen_v1_1_reproduction.csv", index=False
    )

    confidence = (
        economics.groupby("normalization_confidence", as_index=False)
        .agg(tickers=("ticker", "nunique"))
    )
    q50 = conditional_summary.loc[
        conditional_summary["through_cycle_margin_reference"].eq("Q50")
    ].iloc[0]
    report = f"""# E&P V1.2 expectations-surface research

This research layer does not alter frozen V1.1. The immutable V1.0 and V1.1
manifests were verified before and after execution. Maximum V1.1 fair-value
reproduction error was `{maximum_error:.3e}` per share.

## Research boundary

- No single market-implied margin, growth, ROIC, or WACC is reported.
- Every solved row is one point on a non-unique iso-value curve.
- Unbracketed combinations remain explicit; no domain edge is presented as a solution.
- Through-cycle distributions use company history with an eight-observation peer prior.
- Hormuz/AIS is deferred to a later regime overlay and is not a long-run anchor.
- All outputs are `V1.2_RESEARCH_ONLY`; production remains V1.1 live 0/20 locked.

## Through-cycle evidence quality

{_markdown(confidence)}

## Terminal margin × WACC sector median gap matrix

{_markdown(gap_matrix.reset_index())}

## Iso-value curve coverage

{_markdown(iso_summary)}

## Conditional market-equivalent WACC

{_markdown(conditional_summary)}

At the hierarchical Q50 through-cycle terminal-margin reference, the median
conditional market-equivalent WACC among solved tickers is
`{float(q50['conditional_wacc_median_pct']):.2f}%`. This is a conditional
combination, not an independently estimated appropriate discount rate.

## Interpretation

The surface makes non-identification visible: lower terminal margins can pair
with lower WACC, while higher margins require higher WACC to explain the same
price. Growth/margin and growth/ROIC curves preserve the same many-solutions
property. These results are evidence for designing independent through-cycle
margin, ROIC, and risk-premium research; they are not instructions to calibrate
V1.1 to current market prices and are not investment recommendations.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    parent_after = verify_v1(ROOT)
    benchmark_after = verify_v11(ROOT)
    if parent_after["manifest_sha256"] != parent_before["manifest_sha256"]:
        raise RuntimeError("Immutable V1.0 changed during V1.2 research")
    if benchmark_after["manifest_sha256"] != benchmark_before["manifest_sha256"]:
        raise RuntimeError("Frozen V1.1 changed during V1.2 research")
    metadata = {
        "version": "E&P_EXPECTATIONS_SURFACE_V1_2_RESEARCH_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_0_manifest_sha256": parent_after["manifest_sha256"],
        "v1_1_manifest_sha256": benchmark_after["manifest_sha256"],
        "frozen_v1_1_mutated": False,
        "maximum_frozen_reproduction_error_per_share": maximum_error,
        "ticker_count": 14,
        "surface_dimensions": [
            "TERMINAL_MARGIN_X_WACC",
            "GROWTH_X_OPERATING_MARGIN",
            "GROWTH_X_NORMALIZED_ROIC",
        ],
        "single_point_market_implied_claim_allowed": False,
        "hormuz_treatment": "DEFERRED_REGIME_SCENARIO_OVERLAY",
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(gap_matrix.to_string())
    print(conditional_summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
