from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from energy_nowcast.operations.champion import sha256_file, verify_champion
from equity_platform.sectors.energy.research.revenue.v35.adapters import StandardizedKPIBundle
from equity_platform.sectors.energy.research.revenue.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import E_AND_P_GROUPS
from equity_platform.sectors.energy.research.revenue.v35.validation import run_loco, run_time_holdout
from energy_nowcast.research.v353.gas_prices import (
    extract_strict_gas_prices,
    merge_strict_gas_prices,
)
from energy_nowcast.research.v353.gas_validation import gas_research_gate
from energy_nowcast.validation.cross_section_metrics import ticker_scorecard, universe_summary


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA_ROOT = ROOT.parent / "Arcana"
V352_OUTPUT = ROOT / "output" / "v3_5_2_clean_component"
DEFAULT_OUTPUT = ROOT / "output" / "v3_5_3_gas_research"
GAS_TICKERS = E_AND_P_GROUPS["gas_heavy"]


def _load_inputs() -> tuple[StandardizedKPIBundle, pd.DataFrame, pd.DataFrame]:
    bundle = StandardizedKPIBundle(
        production_actuals=pd.read_parquet(V352_OUTPUT / "production_actuals.parquet"),
        production_guidance=pd.read_parquet(V352_OUTPUT / "production_guidance.parquet"),
        realized_prices=pd.read_parquet(V352_OUTPUT / "realized_prices.parquet"),
        coverage=pd.read_csv(V352_OUTPUT / "source_coverage.csv"),
    )
    panel = pd.read_parquet(V352_OUTPUT / "audited_revenue_panel.parquet")
    prices = pd.read_csv(DATA.v33 / "energy_v3_3_price_quarters.csv")
    return bundle, panel, prices


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows_"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in columns]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def main() -> int:
    output = DEFAULT_OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "v3_5_3_gas_research.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    before = verify_champion(ROOT, "3.4")
    bundle, panel, prices = _load_inputs()
    strict = extract_strict_gas_prices(
        ARCANA_ROOT / "data-lake" / "bronze" / "sec" / "fillings" / "ir",
        preference=str(config["realized_gas_price_preference"]),
    )
    merged_prices = merge_strict_gas_prices(bundle.realized_prices, strict)
    research_bundle = StandardizedKPIBundle(
        bundle.production_actuals,
        bundle.production_guidance,
        merged_prices,
        bundle.coverage,
    )
    strategy = KPIHierarchicalStrategy(
        research_bundle,
        panel,
        prices,
        V35StrategyConfig(
            cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
            use_company_basis=False,
            gas_heavy_price_mode=str(config["gas_heavy_price_mode"]),
            gas_basis_history_quarters=int(config["gas_basis_history_quarters"]),
            gas_basis_partial_pooling_k=float(config["gas_basis_partial_pooling_k"]),
        ),
    )
    all_time, history = run_time_holdout(strategy, panel, holdout_quarters=8)
    all_loco = run_loco(strategy, panel, history, holdout_quarters=8)
    time = all_time.loc[all_time["ticker"].isin(GAS_TICKERS)].copy()
    loco = all_loco.loc[all_loco["ticker"].isin(GAS_TICKERS)].copy()

    # Parser-only ablation: useful for attribution, but not promotion-eligible
    # because the legacy ratio formulation mixes $/Mcf with BOE component mix.
    ratio_strategy = KPIHierarchicalStrategy(
        research_bundle,
        panel,
        prices,
        V35StrategyConfig(
            cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
            use_company_basis=False,
            gas_heavy_price_mode="BENCHMARK_RATIO",
        ),
    )
    ratio_all_time, _ = run_time_holdout(ratio_strategy, panel, holdout_quarters=8)
    ratio_time = ratio_all_time.loc[ratio_all_time["ticker"].isin(GAS_TICKERS)].copy()
    ratio_score = ticker_scorecard(ratio_time, minimum_observations=8)
    baseline_time = pd.read_csv(V352_OUTPUT / "time_holdout_predictions.csv")
    baseline_loco = pd.read_csv(V352_OUTPUT / "loco_predictions.csv")
    baseline_time = baseline_time.loc[baseline_time["ticker"].isin(GAS_TICKERS)]
    baseline_loco = baseline_loco.loc[baseline_loco["ticker"].isin(GAS_TICKERS)]
    for candidate, baseline, name in (
        (time, baseline_time, "TIME"),
        (loco, baseline_loco, "LOCO"),
    ):
        candidate_keys = set(map(tuple, candidate[["ticker", "quarter"]].to_numpy()))
        baseline_keys = set(map(tuple, baseline[["ticker", "quarter"]].to_numpy()))
        if candidate_keys != baseline_keys:
            raise AssertionError(f"{name} gas research split differs from V3.5.2")
        available = candidate["candidate_status"].eq("AVAILABLE")
        if not candidate.loc[available, "basis_adjustment_log_points"].eq(0.0).all():
            raise AssertionError("Company revenue basis was enabled in gas research")

    time_score = ticker_scorecard(time, minimum_observations=8)
    loco_score = ticker_scorecard(loco, minimum_observations=8)
    summaries = pd.concat([
        universe_summary(time_score, time, "GAS_TIME_HOLDOUT_8Q_PRIMARY"),
        universe_summary(loco_score, loco, "GAS_LOCO_TIME_SAFE_8Q_COLD_START"),
    ], ignore_index=True)
    gate = gas_research_gate(time_score, strict)
    baseline_score = pd.read_csv(V352_OUTPUT / "ticker_scorecard_time.csv")
    baseline_score = baseline_score.loc[baseline_score["ticker"].isin(GAS_TICKERS)]
    comparison = baseline_score[[
        "ticker", "mase", "candidate_mae_log_points", "improvement_log_points"
    ]].merge(
        time_score[["ticker", "mase", "candidate_mae_log_points", "improvement_log_points"]],
        on="ticker",
        suffixes=("_v352_clean", "_gas_basis_research"),
    )
    comparison["candidate_mae_change"] = (
        comparison["candidate_mae_log_points_gas_basis_research"]
        - comparison["candidate_mae_log_points_v352_clean"]
    )
    comparison = comparison.merge(
        ratio_score[["ticker", "mase", "candidate_mae_log_points", "improvement_log_points"]],
        on="ticker",
        how="left",
    ).rename(columns={
        "mase": "mase_strict_parser_ratio_diagnostic",
        "candidate_mae_log_points": "candidate_mae_log_points_strict_parser_ratio_diagnostic",
        "improvement_log_points": "improvement_log_points_strict_parser_ratio_diagnostic",
    })
    baseline_predictions = baseline_time.copy()
    baseline_gas_score = ticker_scorecard(baseline_predictions, minimum_observations=8)
    variant_summary = pd.concat([
        universe_summary(
            baseline_gas_score,
            baseline_predictions,
            "V352_LOOSE_PARSER_BENCHMARK_RATIO_BASELINE",
        ),
        universe_summary(
            ratio_score,
            ratio_time,
            "STRICT_PARSER_BENCHMARK_RATIO_DIAGNOSTIC_ONLY",
        ),
        universe_summary(
            time_score,
            time,
            "STRICT_REALIZED_ADDITIVE_BASIS_PROMOTION_CANDIDATE",
        ),
    ], ignore_index=True)
    coverage = strict.groupby("ticker", as_index=False).agg(
        strict_price_quarters=("quarter", "size"),
        first_quarter=("quarter", "min"),
        last_quarter=("quarter", "max"),
        hedge_adjusted_quarters=("hedge_included", "sum"),
    )
    for filename, frame in {
        "strict_realized_gas_prices.csv": strict,
        "gas_price_coverage.csv": coverage,
        "merged_realized_prices.csv": merged_prices,
        "time_holdout_predictions.csv": time,
        "loco_predictions.csv": loco,
        "ticker_scorecard_time.csv": time_score,
        "ticker_scorecard_loco.csv": loco_score,
        "gas_summary.csv": summaries,
        "gas_research_gate.csv": gate,
        "v352_gas_research_comparison.csv": comparison,
        "gas_variant_summary.csv": variant_summary,
    }.items():
        frame.to_csv(output / filename, index=False)

    active_model = str(gate["active_group_model"].iloc[0])
    lines = [
        "# V3.5.3 gas-basis research report",
        "",
        "This isolated experiment replaces loose IR gas-price parsing with strict absolute-price labels,",
        "normalizes $/Mcf to $/BOE, and forecasts a point-in-time additive company/regional gas basis.",
        "The V3.5.3 grouped branch continues to use legacy unless this experiment passes every gate.",
        "",
        "## Strict price coverage",
        "",
        _markdown_table(coverage),
        "",
        "## TIME and LOCO results",
        "",
        _markdown_table(summaries.round(4)),
        "",
        "## Gas-price variant attribution",
        "",
        _markdown_table(variant_summary.round(4)),
        "",
        "The strict-parser ratio variant is diagnostic only because its old component equation",
        "does not normalize $/Mcf into the BOE mix. It cannot be selected even if it looks better.",
        "",
        "## Ticker comparison versus V3.5.2 clean component",
        "",
        _markdown_table(comparison.round(4)),
        "",
        "## Gas research gate",
        "",
        _markdown_table(gate),
        "",
        "## Decision",
        "",
        f"- Gas-heavy active grouped model: **{active_model}**",
        f"- Gas macro research: **{'UNLOCKED' if bool(gate['gas_macro_research_unlocked'].iloc[0]) else 'BLOCKED'}**",
        "- No macro overlay was applied to these results.",
        "- V3.4 production champion remains frozen.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")

    after = verify_champion(ROOT, "3.4")
    if before["manifest_sha256"] != after["manifest_sha256"]:
        raise RuntimeError("V3.4 changed during V3.5.3 gas research")
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gas_research_gate": bool(gate["gas_research_gate"].iloc[0]),
        "active_group_model": active_model,
        "strict_price_rows": len(strict),
        "known_parser_issue_removed": "CNX_TOC_PAGE_8_NOT_A_PRICE",
        "gas_price_unit_normalization": config["gas_price_unit_normalization"],
        "macro_applied_to_results": False,
        "production_champion": "V3.4_FROZEN",
        "v3_4_unchanged": True,
        "v3_4_manifest_sha256": after["manifest_sha256"],
        "config_sha256": sha256_file(config_path),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(coverage.to_string(index=False))
    print("\n", summaries.round(4).to_string(index=False))
    print("\n", comparison.round(4).to_string(index=False))
    print("\n", gate.to_string(index=False))
    print(f"\nV3.4 unchanged: {after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
