from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.cost_scope import build_cost_scope_research
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output" / "energy_valuation_v1_4_research"
ARCANA = ROOT.parent / "Arcana"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run E&P V1.4 standardized cost-scope and basis research"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def _verify_parents() -> dict[str, dict[str, object]]:
    return {
        "v1": verify_v1(ROOT),
        "v11": verify_v11(ROOT),
        "v12": verify_v12(ROOT),
        "v13": verify_v13(ROOT),
    }


def main() -> int:
    args = _arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    parents_before = _verify_parents()
    artifacts = build_cost_scope_research(
        companyfacts_root=COMPANYFACTS,
        production_path=(
            ROOT / "output/v3_5_2_clean_component/production_actuals.csv"
        ),
        price_path=DATA.v33 / "energy_v3_3_price_quarters.csv",
        frozen_v13_cross_path=(
            ROOT / "output/energy_valuation_v1_3_research/unit_economics_cross_check.csv"
        ),
        v11_assumptions_path=(
            ROOT / "output/energy_valuation_v1_1/scenario_assumptions.csv"
        ),
    )
    for name, frame in artifacts.items():
        frame.to_csv(args.output / f"{name}.csv", index=False)

    tag_audit = artifacts["standardized_tag_coverage"]
    tag_summary = (
        tag_audit.assign(
            usable_3y=tag_audit["standardized_tag_years_2021_2025"].ge(3)
        )
        .groupby("concept", as_index=False)
        .agg(
            tickers_with_any_standardized_year=(
                "standardized_tag_years_2021_2025",
                lambda values: int(values.gt(0).sum()),
            ),
            tickers_with_at_least_3_years=("usable_3y", "sum"),
            total_standardized_years=("standardized_tag_years_2021_2025", "sum"),
        )
        .sort_values("concept")
        .reset_index(drop=True)
    )
    tag_summary["tickers_with_at_least_3_years"] = tag_summary[
        "tickers_with_at_least_3_years"
    ].astype(int)
    tag_summary.to_csv(args.output / "standardized_tag_summary.csv", index=False)

    cross = artifacts["expanded_core_cross_check"]
    core = cross.loc[
        cross["v13_unit_economics_status"].eq(
            "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK"
        )
    ].copy()
    gate = artifacts["cost_scope_gate"].iloc[0]
    core_columns = [
        "ticker",
        "v14_cost_scope_status",
        "median_realized_revenue_basis_per_boe",
        "median_transport_cost_per_boe",
        "median_production_tax_per_boe",
        "median_g_and_a_per_boe",
        "median_reported_hedge_gain_loss_per_boe",
        "median_abs_reported_hedge_gain_loss_per_boe",
        "basis_hedge_correlation",
        "hedge_inclusion_diagnostic",
        "basis_iqr_pct_of_adjusted_price",
        "basis_dispersion_status",
        "v13_historical_margin_q50_pct",
        "v13_core_accounting_margin_q50_pct",
        "v14_known_cost_accounting_margin_q50_pct",
        "v14_margin_gap_vs_v13_historical_q50_pct_points",
        "absolute_margin_gap_improvement_vs_v13_core_pct_points",
        "v13_core_roic_proxy_q50_pct",
        "v14_known_cost_roic_proxy_q50_pct",
        "roic_proxy_reduction_vs_v13_pct_points",
        "roic_cross_check_status",
    ]
    report = f"""# E&P V1.4 standardized cost-scope research

V1.4 is a research-only child of the frozen V1.3 benchmark. It verifies V1.0,
V1.1, V1.2, and V1.3 before and after execution and does not recalibrate any
frozen WACC, terminal assumption, scenario, parser, or valuation result.

## Standardized tag coverage

{_markdown(tag_summary)}

The annual panel uses original 10-K annual facts with filing-lag and duration
checks. Transport and production tax require their exact standardized tags.
G&A may use a disclosed consolidated allocation route, and every selected tag
and scope remains in the annual audit panel. Missing cost components stay null;
they are never silently set to zero.

## Expanded core cross-check

{_markdown(core[core_columns])}

`Realized revenue basis` means exact upstream revenue per BOE minus the
production-mix benchmark basket. It is not claimed to be a pure price
differential because upstream revenue can contain mix, timing, and other
presentation effects. Reported hedge gains/losses are quantified separately.
The long-run hedge normalization is zero, but it is not mechanically netted
against revenue without evidence that the selected revenue fact includes it.
The basis/hedge correlation is an association diagnostic only. A 25%-of-price
IQR flag makes unstable basis histories visible but does not fit or alter any
valuation assumption.

Only CNX currently has at least three usable years for transport, production
tax, G&A, and exact-upstream-revenue basis. AR and FANG are explicitly labelled
known-cost upper bounds. A lower ROIC proxy is therefore a diagnostic, not a
validated terminal input.

## Gate

{_markdown(artifacts['cost_scope_gate'])}

- Complete standardized cost scope: {int(gate['standardized_complete_cost_scope_tickers'])}/14.
- Complete V1.3-core cross-check: {int(gate['v14_complete_core_cross_check_tickers'])}/3.
- High basis dispersion among core cross-checks: {int(gate['high_basis_dispersion_core_tickers'])}/3.
- Terminal anchor replacement: locked at 0/14.
- Independent V1.3 WACC range: retained unchanged; no point estimate selected.
- Risk channels: no new duplicate allocation; Hormuz remains a cash-flow overlay.
- Production: locked at 0/20 matched live observations.

These outputs are research diagnostics and not investment recommendations.
"""
    (args.output / "report.md").write_text(report, encoding="utf-8")

    parents_after = _verify_parents()
    for key in parents_before:
        if (
            parents_before[key]["manifest_sha256"]
            != parents_after[key]["manifest_sha256"]
        ):
            raise RuntimeError(f"Frozen {key} manifest changed during V1.4 research")
    metadata = {
        "version": "E&P_STANDARDIZED_COST_SCOPE_V1_4_RESEARCH_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_manifest_sha256": parents_after["v1"]["manifest_sha256"],
        "v1_1_manifest_sha256": parents_after["v11"]["manifest_sha256"],
        "v1_2_manifest_sha256": parents_after["v12"]["manifest_sha256"],
        "v1_3_manifest_sha256": parents_after["v13"]["manifest_sha256"],
        "frozen_parent_mutated": False,
        "ep_ticker_count": int(gate["ep_tickers"]),
        "standardized_complete_cost_scope_tickers": int(
            gate["standardized_complete_cost_scope_tickers"]
        ),
        "v14_complete_core_cross_check_tickers": int(
            gate["v14_complete_core_cross_check_tickers"]
        ),
        "high_basis_dispersion_core_tickers": int(
            gate["high_basis_dispersion_core_tickers"]
        ),
        "terminal_anchor_ready": int(gate["terminal_anchor_ready_tickers"]),
        "terminal_anchor_replacement_allowed": False,
        "single_appropriate_wacc_claim_allowed": False,
        "wacc_range_recalibrated": False,
        "v1_1_mutation_allowed": False,
        "risk_channel_duplicate_count": 0,
        "hormuz_treatment": "CASH_FLOW_REGIME_OVERLAY_NO_WACC_PREMIUM",
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (args.output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(tag_summary.to_string(index=False))
    print(core[core_columns].to_string(index=False))
    print(artifacts["cost_scope_gate"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
