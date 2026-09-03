from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.v15.benchmark import verify_v15_pit_data
from equity_platform.sectors.industrials.v16 import (
    build_cost_perimeter,
    build_cost_timing_validation,
    build_v16_research,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v1_6.toml"
OUTPUT = ROOT / "output/industrials_valuation_v1_6_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent = verify_v15_pit_data(ROOT)
    parent_output = ROOT / config["parent_v1_5_output"]
    route_panel = pd.read_csv(parent_output / "segment_route_panel.csv")
    base_validation = pd.read_csv(parent_output / "segment_route_walk_forward.csv")
    reinvestment_summary = pd.read_csv(parent_output / "reinvestment_pit_full_chain_summary.csv")

    perimeter = build_cost_perimeter(
        route_panel=route_panel,
        validation_start_period=config["validation_start_period"],
        material_recast_threshold_pct=float(config["material_recast_threshold_pct"]),
    )
    timing = build_cost_timing_validation(
        cost_perimeter=perimeter["segment_cost_perimeter"],
        base_validation=base_validation,
        validation_start_period=config["validation_start_period"],
        expected_oos_quarters_per_segment=int(config["expected_oos_quarters_per_segment"]),
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        minimum_inner_validation_quarters=int(config["minimum_inner_validation_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
        cost_recognition_lags=[int(value) for value in config["cost_recognition_lags"]],
    )
    research = build_v16_research(
        base_validation=base_validation,
        timing_validation=timing["cost_timing_walk_forward"],
        perimeter_audit=perimeter["cost_perimeter_audit"],
        pit_benchmark_verified=True,
        reinvestment_summary=reinvestment_summary,
        expected_oos_quarters_per_segment=int(config["expected_oos_quarters_per_segment"]),
        maximum_revenue_mase=float(config["maximum_revenue_mase"]),
        minimum_revenue_direction_accuracy_pct=float(config["minimum_revenue_direction_accuracy_pct"]),
        minimum_segments_margin_validated=int(config["minimum_segments_margin_validated"]),
        maximum_margin_mase=float(config["maximum_margin_mase"]),
        cancellation_ratio_threshold=float(config["component_cancellation_ratio_threshold"]),
        component_gross_mae_threshold_pct=float(config["component_gross_mae_threshold_pct"]),
        minimum_backlog_oos_observations=int(config["minimum_backlog_oos_observations"]),
        production_minimum_live_observations=int(config["production_minimum_live_observations"]),
    )
    write_csv_artifacts(OUTPUT, {**perimeter, **timing, **research})

    parent_after = verify_v15_pit_data(ROOT)
    parent_inputs = [
        "output/industrials_valuation_v1_5_research/segment_route_panel.csv",
        "output/industrials_valuation_v1_5_research/segment_route_walk_forward.csv",
        "output/industrials_valuation_v1_5_research/reinvestment_pit_full_chain_summary.csv",
    ]
    source_paths = [
        "configs/industrials_v1_6.toml",
        "equity_platform/sectors/industrials/v16/__init__.py",
        "equity_platform/sectors/industrials/v16/perimeter.py",
        "equity_platform/sectors/industrials/v16/revenue.py",
        "equity_platform/sectors/industrials/v16/timing.py",
        "equity_platform/sectors/industrials/v16/research.py",
        "scripts/industrials/valuation_v1_6.py",
    ]
    gate = research["industrials_v1_6_gate"].iloc[0]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "branch_status": gate["status"],
        "research_scope": "SEGMENT_COST_PERIMETER_AND_TIMING_CLOSURE",
        "v1_5_pit_data_manifest_sha256": parent["manifest_sha256"],
        "v1_5_pit_data_verified_after": parent_after["manifest_sha256"] == parent["manifest_sha256"],
        "v1_5_pit_data_verified_files": parent["verified_files"],
        "v1_5_forecast_model_frozen": False,
        "fixed_validation_window": "2025Q1-2026Q2",
        "pdf_parsing_deferred": True,
        "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "terminal_evidence_eligible": bool(gate["terminal_evidence_eligible"]),
        "production_promotable": bool(gate["production_promotable"]),
        "valuation_update_allowed": False,
        "v1_3_lite_reference_value_per_share_usd": 399.1175,
        "parent_forecast_input_hashes": hash_files(ROOT, parent_inputs),
        "source_hashes": hash_files(ROOT, source_paths),
        "parent_pit_manifest_path": config["parent_pit_manifest"],
        "parent_pit_manifest_file_sha256": sha256_file(ROOT / config["parent_pit_manifest"]),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Industrials V1.6 — Segment cost perimeter and timing closure

## Three independent gates

{markdown_table(research['v1_6_gate_layers'])}

Research freeze, terminal evidence, and production promotion are intentionally
separate. Production 0/20 and backlog 2/3 do not directly fail the research
freeze gate. The forecast branch nevertheless remains `HOLD_RESEARCH_UNFROZEN`
on its own margin evidence.

## V1.5 PIT data benchmark

The V1.5 PIT data infrastructure is immutable and independently verified across
{parent['verified_files']} files. The V1.5 forecast model is not frozen.

## Cost perimeter identity

{markdown_table(perimeter['segment_cost_perimeter_summary'])}

Reported segment cost is separated exactly into prior-scope recast and
comparable economic cost movement. Unexpected recasts are flagged and are never
forecast as though they were ordinary operating inflation.

## Recognition-lag validation

{markdown_table(timing['cost_timing_validation_summary'])}

Only lags 0-3 and one Construction load/mix route were compared. Each route was
selected using training-only inner validation on the unchanged six-quarter OOS
window.

## Revenue champion evidence

{markdown_table(research['revenue_champion_validation'])}

Revenue is evaluated independently with level MASE, WAPE, direction accuracy,
and no-regression checks.

## Margin route evidence

{markdown_table(research['margin_route_validation'])}

A statistically passing margin remains blocked when component cancellation or
unforecasted segment-scope recasts are present.

## Valuation authority

{markdown_table(research['v1_6_valuation_authority'])}

Reinvestment remains a frozen pending evidence gate at one PIT OOS year and
backlog remains 2/3. No DCF, Reverse DCF, ROIC, or terminal update was run.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(perimeter["segment_cost_perimeter_summary"].to_string(index=False))
    print(timing["cost_timing_validation_summary"].to_string(index=False))
    print(research["revenue_champion_validation"].to_string(index=False))
    print(research["margin_route_validation"].to_string(index=False))
    print(research["v1_6_gate_layers"].to_string(index=False))
    return 0 if bool(gate["research_complete"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
