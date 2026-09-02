from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.unit_economics import build_unit_economics_research
from energy_nowcast.research.ep_v13.wacc_research import build_wacc_research
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "energy_valuation_v1_3_research"
ARCANA = ROOT.parent / "Arcana"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"
PRICE_ROOT = ARCANA / "data-lake" / "bronze" / "yfinance" / "price"
BENCHMARK = ARCANA / "data-lake" / "bronze" / "yfinance" / "benchmark" / "us_sp500.csv"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run E&P V1.3 normalized unit-economics research"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    args = _arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    parents_before = {
        "v1": verify_v1(ROOT),
        "v11": verify_v11(ROOT),
        "v12": verify_v12(ROOT),
    }
    unit = build_unit_economics_research(
        companyfacts_root=COMPANYFACTS,
        production_path=ROOT / "output/v3_5_2_clean_component/production_actuals.csv",
        price_path=ROOT / "data-lake/energy_v3_3_price_quarters.csv",
        strict_realized_gas_coverage_path=ROOT / "output/v3_5_3_gas_research/gas_price_coverage.csv",
        v12_economics_path=ROOT / "output/energy_valuation_v1_2_research/through_cycle_economics.csv",
        v11_assumptions_path=ROOT / "output/energy_valuation_v1_1/scenario_assumptions.csv",
    )
    wacc = build_wacc_research(
        price_root=PRICE_ROOT,
        benchmark_path=BENCHMARK,
        market_inputs_path=ROOT / "output/energy_valuation_v1_1/adjusted_market_inputs.csv",
        assumptions_path=ROOT / "output/energy_valuation_v1_1/scenario_assumptions.csv",
    )
    artifacts = {**unit, **wacc}
    for name, frame in artifacts.items():
        frame.to_csv(args.output / f"{name}.csv", index=False)

    cross = unit["unit_economics_cross_check"]
    full = cross.loc[
        cross["unit_economics_status"].eq(
            "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK"
        )
    ]
    partial = cross.loc[
        cross["unit_economics_status"].eq(
            "PARTIAL_PRICE_VOLUME_ONLY_RESERVE_REPLACEMENT_LOCKED"
        )
    ]
    coverage = unit["data_coverage"]
    wacc_summary = wacc["wacc_reference_summary"]
    gate = wacc["double_count_gate"].iloc[0]
    unit_summary = pd.DataFrame(
        [{
            "ep_tickers": len(cross),
            "price_volume_proxy_ready": int(
                cross["production_mix_status"].eq("PRICE_VOLUME_PROXY_READY").sum()
            ),
            "core_reserve_replacement_cross_check": len(full),
            "partial_price_volume_only": len(partial),
            "fully_locked": int(
                cross["unit_economics_status"].eq("LOCKED_NO_AUDITED_PRODUCTION_INPUT").sum()
            ),
            "strict_realized_gas_tickers": int(
                coverage["strict_realized_gas_price_quarters"].gt(0).sum()
            ),
            "common_cross_commodity_realized_basis_ready": 0,
            "terminal_anchor_ready": 0,
            "directionally_consistent_margin_cross_checks": int(
                cross["margin_cross_check_status"].eq(
                    "DIRECTIONALLY_CONSISTENT_WITH_V12_WITHIN_10PPT"
                ).sum()
            ),
            "roic_proxy_above_100pct_flags": int(
                cross["roic_cross_check_status"].eq(
                    "PLAUSIBILITY_REVIEW_REQUIRED_ABOVE_100PCT"
                ).sum()
            ),
            "production_eligible": False,
        }]
    )
    unit_summary.to_csv(args.output / "unit_economics_summary.csv", index=False)

    full_columns = [
        "ticker", "reserve_life_median_years",
        "stock_flow_organic_replacement_rate_median_pct",
        "normalized_lifting_cost_per_boe", "normalized_dda_per_boe",
        "normalized_development_cost_per_added_boe",
        "normalized_gross_price_q50_per_boe",
        "commodity_normalized_accounting_margin_q50_pct",
        "reserve_replacement_cash_margin_q50_pct",
        "reserve_replacement_roic_proxy_q50_pct",
        "v12_historical_margin_q50_pct",
        "accounting_margin_q50_gap_vs_v12_pct_points",
        "margin_cross_check_status", "roic_cross_check_status",
    ]
    v12_wacc = pd.read_csv(
        ROOT / "output/energy_valuation_v1_2_research/through_cycle_margin_wacc_summary.csv"
    ).set_index("through_cycle_margin_reference")
    wacc_comparison = pd.DataFrame(
        [{
            "v1_1_base_wacc_median_pct": float(
                wacc_summary.iloc[0]["v1_1_base_wacc_median_pct"]
            ),
            "v1_2_q50_conditional_market_equivalent_wacc_median_pct": float(
                v12_wacc.loc["Q50", "conditional_wacc_median_pct"]
            ),
            "v1_3_independent_symmetric_return_wacc_median_pct": float(
                wacc_summary.iloc[0]["symmetric_return_wacc_median_pct"]
            ),
            "v1_3_independent_downside_return_wacc_median_pct": float(
                wacc_summary.iloc[0]["downside_return_wacc_median_pct"]
            ),
            "v1_3_symmetric_minus_v1_2_conditional_pct_points": float(
                wacc_summary.iloc[0]["symmetric_return_wacc_median_pct"]
                - v12_wacc.loc["Q50", "conditional_wacc_median_pct"]
            ),
            "interpretation": (
                "V1_2_IS_CONDITIONAL_PRICE_EXPLANATION_V1_3_IS_INDEPENDENT_RETURN_RANGE"
            ),
        }]
    )
    wacc_comparison.to_csv(args.output / "wacc_cross_comparison.csv", index=False)
    report = f"""# E&P V1.3 normalized unit-economics research

This branch was created after freezing the V1.2 expectations surface. V1.0,
V1.1, and V1.2 manifests are verified before and after execution. No frozen
valuation assumption is recalibrated and production remains locked at 0/20.

## Coverage gate

{_markdown(unit_summary)}

Standardized reserve roll-forwards are used only where SEC quantity facts can
be reconciled to the separately audited production KPI within 25%. Filing unit
power-of-ten adjustments are detected from that reconciliation and retained in
the annual audit panel. Missing reserve event facts may be zero only inside the
stock-flow identity and are separately disclosed; they are never silently
presented as reported observations.

## Core reserve-replacement cross-checks

{_markdown(full[full_columns] if len(full) else full)}

The commodity price reference is the empirical 2015Q1-2024Q4 WTI, Henry Hub,
and propane distribution. It deliberately excludes 2025-2026 from the long-run
anchor. The accounting-margin proxy subtracts normalized lifting cost and
DD&A. The replacement-cash-margin proxy substitutes development cost per added
BOE for DD&A. Both omit unstandardized transport, production tax, hedging,
corporate cost, and realized-basis effects, so they are cross-checks rather than
terminal assumptions.

## Independent return-based WACC range

{_markdown(wacc_summary)}

The range uses local adjusted-total-return beta against the S&P 500, current
risk-free/debt/capital-structure inputs, and the frozen 4.5% ERP. Symmetric and
downside 10-year beta endpoints are reported separately. Market prices and the
V1.2 expectations surface are not used to fit this range; therefore no row is
labelled an appropriate WACC point estimate.

{_markdown(wacc_comparison)}

## Risk-channel separation

{_markdown(wacc["risk_allocation_policy"])}

The proposed V1.3 policy has `{int(gate['proposed_policy_duplicate_risk_channels'])}`
duplicated risk allocations and its double-count gate is
`{bool(gate['proposed_v1_3_double_count_gate'])}`. Frozen V1.1 has
`{int(gate['inherited_v1_1_coupled_nonbase_rows'])}` non-base rows where cash-flow
and WACC both move. That coupling is not proof of double counting, but the risk
source is not separately attributed, so it remains an explicit monitoring item
rather than being retroactively changed.

## Research decision

- Commodity-normalized price/volume economics: research-ready for 13/14.
- Core reserve-replacement cross-check: research-ready for {len(full)}/14.
- Terminal anchor replacement: locked for 14/14 until transport, production
  tax, and cross-commodity realized basis are standardized.
- Common realized-price/basis anchor: locked; strict coverage is gas-only for
  four tickers and is not cross-commodity complete.
- Hormuz overlay: deferred to cash-flow regime scenarios, with no WACC premium.
- Production: locked at 0/20. These outputs are not investment recommendations.
"""
    (args.output / "report.md").write_text(report, encoding="utf-8")

    parents_after = {
        "v1": verify_v1(ROOT),
        "v11": verify_v11(ROOT),
        "v12": verify_v12(ROOT),
    }
    for key in parents_before:
        if parents_before[key]["manifest_sha256"] != parents_after[key]["manifest_sha256"]:
            raise RuntimeError(f"Frozen {key} manifest changed during V1.3 research")
    metadata = {
        "version": "E&P_NORMALIZED_UNIT_ECONOMICS_V1_3_RESEARCH_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_manifest_sha256": parents_after["v1"]["manifest_sha256"],
        "v1_1_manifest_sha256": parents_after["v11"]["manifest_sha256"],
        "v1_2_manifest_sha256": parents_after["v12"]["manifest_sha256"],
        "frozen_parent_mutated": False,
        "ep_ticker_count": len(cross),
        "price_volume_proxy_ready": int(
            cross["production_mix_status"].eq("PRICE_VOLUME_PROXY_READY").sum()
        ),
        "core_reserve_replacement_cross_check": len(full),
        "terminal_anchor_ready": 0,
        "directionally_consistent_margin_cross_checks": int(
            cross["margin_cross_check_status"].eq(
                "DIRECTIONALLY_CONSISTENT_WITH_V12_WITHIN_10PPT"
            ).sum()
        ),
        "common_cross_commodity_realized_basis_ready": 0,
        "single_appropriate_wacc_claim_allowed": False,
        "market_price_calibration_used": False,
        "hormuz_treatment": "DEFERRED_CASH_FLOW_REGIME_SCENARIO_NO_WACC_PREMIUM",
        "double_count_gate": bool(gate["proposed_v1_3_double_count_gate"]),
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (args.output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(unit_summary.to_string(index=False))
    print(full[full_columns].to_string(index=False))
    print(wacc_summary.to_string(index=False))
    print(wacc["double_count_gate"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
