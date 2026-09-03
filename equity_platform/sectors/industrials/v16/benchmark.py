from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import freeze_manifest, verify_manifest


MANIFEST = Path("benchmarks/industrials_cat_revenue_champion_v1/manifest.json")


def _files() -> list[str]:
    return [
        "configs/industrials_v1_5.toml",
        "configs/industrials_v1_6.toml",
        "equity_platform/sectors/industrials/v14/economics.py",
        "equity_platform/sectors/industrials/v15/routes.py",
        "equity_platform/sectors/industrials/v16/benchmark.py",
        "equity_platform/sectors/industrials/v16/revenue.py",
        "scripts/industrials/freeze_revenue_champion_v1.py",
        "tests/test_industrials_revenue_champion_v1_freeze.py",
        "output/industrials_valuation_v1_5_research/ir_segment_quarterly_history.csv",
        "output/industrials_valuation_v1_5_research/ir_segment_pq_bridge.csv",
        "output/industrials_valuation_v1_5_research/segment_route_panel.csv",
        "output/industrials_valuation_v1_5_research/segment_route_inner_validation.csv",
        "output/industrials_valuation_v1_5_research/segment_route_walk_forward.csv",
        "output/industrials_valuation_v1_6_research/revenue_champion_validation.csv",
    ]


def _assertions(root: Path) -> dict[str, object]:
    summary = pd.read_csv(root / "output/industrials_valuation_v1_6_research/revenue_champion_validation.csv")
    validation = pd.read_csv(root / "output/industrials_valuation_v1_5_research/segment_route_walk_forward.csv")
    return {
        "benchmark_scope": "CAT_SEGMENT_REVENUE_FORECAST_ONLY",
        "segments": int(summary["segment"].nunique()),
        "oos_observations_per_segment": int(summary["validation_observations"].min()),
        "historical_pit_coverage_pct": float(validation["historical_pit_input"].astype(bool).mean() * 100.0),
        "champion_segments": int(summary["revenue_champion_eligible"].astype(bool).sum()),
        "maximum_revenue_mase": float(summary["revenue_level_mase"].max()),
        "all_wape_below_naive": bool((summary["revenue_wape_pct"] < summary["naive_revenue_wape_pct"]).all()),
        "minimum_direction_accuracy_pct": float(summary["revenue_direction_accuracy_pct"].min()),
        "all_no_material_regression": bool(summary["no_material_regression"].astype(bool).all()),
        "margin_model_in_scope": False,
        "reinvestment_model_in_scope": False,
        "roic_model_in_scope": False,
        "terminal_input_allowed": False,
        "production_promoted": False,
    }


def freeze_revenue_champion_v1(root: Path) -> dict[str, object]:
    parent = verify_manifest(root=root, manifest_path=Path("benchmarks/industrials_v1_5_pit_data/manifest.json"))
    return freeze_manifest(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_CAT_REVENUE_CHAMPION_V1",
        version="1.0",
        relative_paths=_files(),
        assertions=_assertions(root),
        parents={"industrials_v1_5_pit_data": parent["manifest_sha256"]},
    )


def verify_revenue_champion_v1(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
