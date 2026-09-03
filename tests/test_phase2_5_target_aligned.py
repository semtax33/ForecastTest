from __future__ import annotations

import json
from pathlib import Path
import shutil

import pandas as pd

from equity_platform.data_catalog import DATA
from energy_nowcast.core.company_kpi import select_company_kpis_for_targets
from energy_nowcast.research.phase25.benchmark import (
    verify_refining_kpi_benchmark,
)
from energy_nowcast.research.v36.macro_data import (
    build_macro_feature_panel,
    load_macro_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "phase2_5_target_aligned_research"


def test_p21_refining_benchmark_is_frozen_and_complete() -> None:
    status = verify_refining_kpi_benchmark(ROOT)

    assert status["version"] == "P2.1_REFINING_COMPANY_KPI_RESEARCH_CHAMPION_V1"
    assert status["files"] == 10


def test_p21_refining_benchmark_fails_closed_on_byte_change(tmp_path: Path) -> None:
    source = ROOT / "benchmarks" / "phase2_1_refining_kpi"
    target = tmp_path / "benchmarks" / "phase2_1_refining_kpi"
    shutil.copytree(source, target)
    frozen = target / "metadata.json"
    frozen.write_bytes(frozen.read_bytes() + b"\n")

    try:
        verify_refining_kpi_benchmark(tmp_path)
    except ValueError as error:
        assert "Frozen P2.1 benchmark changed" in str(error)
    else:
        raise AssertionError("A modified frozen benchmark must fail closed")


def test_target_aligned_macro_snapshot_is_point_in_time() -> None:
    macro = load_macro_snapshot(DATA.macro_snapshot)
    required = {
        "EIA_TOTAL_GASOLINE_INVENTORY",
        "EIA_DISTILLATE_INVENTORY",
        "EIA_REFINERY_UTILIZATION_PCT",
    }
    assert required.issubset(set(macro["series"]))

    features = build_macro_feature_panel(["2024Q3", "2025Q4", "2026Q2"], macro)
    for name in (
        "gasoline_inventory_z",
        "distillate_inventory_z",
        "refinery_utilization_z",
        "ovx_regime_z",
        "oil_rig_z",
    ):
        assert features[name].notna().all()
        available = pd.to_datetime(features[f"{name}_availability_date"])
        cutoff = pd.to_datetime(features["forecast_cutoff_date"])
        assert available.le(cutoff).all()


def test_company_kpi_selector_enforces_explicit_report_lag() -> None:
    metrics = pd.DataFrame(
        {
            "ticker": ["BKR", "BKR"],
            "report_quarter": ["2025Q4", "2025Q3"],
            "metric_id": ["orders_activity", "orders_activity"],
            "metric_log_yoy": [12.0, 5.0],
            "available_at": pd.to_datetime(["2026-01-25", "2025-10-25"]),
            "quality_score": [1.0, 1.0],
            "parser_rule_confidence": [1.0, 1.0],
            "source_url": ["one", "two"],
        }
    )
    targets = pd.DataFrame({"ticker": ["BKR"], "quarter": ["2026Q1"]})

    lag_one = select_company_kpis_for_targets(
        metrics, targets, report_lag_quarters=1
    ).iloc[0]
    lag_two = select_company_kpis_for_targets(
        metrics, targets, report_lag_quarters=2
    ).iloc[0]

    assert lag_one["company_kpi_report_quarter"] == "2025Q4"
    assert lag_one["orders_activity_log_yoy"] == 12.0
    assert lag_two["company_kpi_report_quarter"] == "2025Q3"
    assert lag_two["orders_activity_log_yoy"] == 5.0


def test_macro_promotion_order_and_research_decisions_are_fail_closed() -> None:
    gates = pd.read_csv(OUTPUT / "macro_time_gates.csv")
    decisions = pd.read_csv(OUTPUT / "macro_research_decisions.csv")

    assert len(gates) == 10
    assert set(gates["research_stage"]) == {"SINGLE"}
    assert not gates["candidate_gate"].astype(bool).any()
    assert set(decisions["selected_macro"]) == {"NONE"}
    assert set(decisions["decision"]) == {"RETAIN_FROZEN_BENCHMARK"}

    refining = decisions.set_index("subindustry").loc["refining"]
    services = decisions.set_index("subindustry").loc["services"]
    assert refining["research_route_model"] == "P2.1_REFINING_COMPANY_KPI"
    assert services["research_route_model"] == "STRUCTURAL_PROXY_RECALIBRATED"


def test_services_orders_are_diagnostic_only_and_integrated_stays_locked() -> None:
    orders = pd.read_csv(OUTPUT / "services_orders_lag_gates.csv")
    integrated = pd.read_csv(OUTPUT / "integrated_forward_signal_coverage.csv")

    assert set(orders["orders_report_lag_quarters"]) == {1, 2}
    assert set(orders["industry_ticker_coverage"]) == {"1/3"}
    assert not orders["candidate_gate"].astype(bool).any()
    assert not orders["loco_cold_start_gate"].astype(bool).any()
    assert set(integrated["ticker"]) == {"XOM", "CVX"}
    assert integrated["numeric_candidate_quarters"].ge(8).all()
    assert integrated["manual_gold_verified_quarters"].eq(0).all()
    assert not integrated["forward_candidate_unlocked"].astype(bool).any()


def test_midstream_ebitda_is_a_separate_gold_gated_target() -> None:
    audit = pd.read_csv(OUTPUT / "midstream_adjusted_ebitda_gold_audit_summary.csv")
    quarterly = pd.read_csv(OUTPUT / "midstream_adjusted_ebitda_quarterly.csv")
    gate = pd.read_csv(OUTPUT / "midstream_adjusted_ebitda_gate.csv")

    assert int(audit.loc[0, "gold_rows"]) == 20
    for column in (
        "numeric_accuracy",
        "unit_accuracy",
        "period_accuracy",
        "semantic_accuracy",
        "all_dimension_accuracy",
    ):
        assert float(audit.loc[0, column]) == 1.0
    assert bool(audit.loc[0, "parser_quality_gate"])
    assert set(quarterly["ticker"]) == {"KMI", "WMB", "ET", "EPD"}
    assert quarterly.groupby("ticker").size().ge(32).all()
    assert not bool(gate.loc[0, "target_research_gate"])
    assert not bool(gate.loc[0, "production_eligible"])


def test_phase5_router_preserves_taxonomy_and_does_not_train_meta_model() -> None:
    schema = pd.read_csv(OUTPUT / "phase5_common_forecast_schema_time.csv")
    routes = pd.read_csv(OUTPUT / "phase5_routing_table.csv")
    registry = pd.read_csv(OUTPUT / "phase5_target_registry.csv")
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))

    required = {
        "ticker",
        "quarter",
        "phase",
        "subindustry",
        "forecast_target",
        "actual_value",
        "predicted_value",
        "prediction_log_yoy",
        "lower_80_log_yoy",
        "upper_80_log_yoy",
        "research_route_model",
        "production_model",
        "validation",
        "router_role",
    }
    assert required.issubset(schema.columns)
    assert set(schema["router_role"]) == {"STATIC_DISPATCH_ONLY_NO_META_MODEL"}
    expected_phases = {
        "integrated": 2,
        "refining": 2,
        "midstream": 3,
        "services": 4,
    }
    downstream = schema.loc[~schema["subindustry"].str.startswith("ep_")]
    for subindustry, phase in expected_phases.items():
        assert set(downstream.loc[downstream["subindustry"].eq(subindustry), "phase"]) == {
            phase
        }
    assert set(routes["taxonomy"]) == {
        "E&P",
        "Integrated",
        "Refining",
        "Midstream",
        "Services",
    }
    assert set(registry["forecast_target"]) == {
        "CAPEX",
        "OPERATING_MARGIN",
        "SEGMENT_OPERATING_EARNINGS_MARGIN",
        "REFINING_MARGIN_OR_EBITDA",
        "ADJUSTED_EBITDA_NON_GAAP",
        "ORDERS_OR_BACKLOG",
    }
    assert not registry["status"].str.startswith("PROMOTED").any()
    assert metadata["phase5_router_meta_model_trained"] is False
    assert metadata["production_champion_changed"] is False
    assert metadata["live_matched_observations"] == "0/20"
