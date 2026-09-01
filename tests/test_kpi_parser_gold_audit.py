from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.core.kpi_parser_audit import (
    load_gold_labels,
    verify_pre_audit_benchmark,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "output" / "kpi_parser_gold_audit"
COMPANY_OUTPUT = ROOT / "output" / "phase2_4_company_kpi_research"
GOLD = ROOT / "configs" / "phase2_4_kpi_parser_gold_labels.csv"


def test_pre_audit_parser_benchmark_is_frozen_and_verifiable() -> None:
    result = verify_pre_audit_benchmark(ROOT)
    assert result["version"] == "PHASE2_4_KPI_PARSER_PRE_AUDIT_V1"
    assert result["files"] == 5


def test_manual_gold_sample_is_unique_and_stratified() -> None:
    gold = load_gold_labels(GOLD)
    assert len(gold) == 75
    assert not gold.duplicated(["ticker", "report_quarter", "metric_id"]).any()
    assert gold.groupby("subindustry").size().to_dict() == {
        "integrated": 18,
        "midstream": 27,
        "refining": 15,
        "services": 15,
    }
    assert set(gold["sample_era"]) == {"EARLY", "MID", "RECENT"}
    assert set(gold["source_quality_stratum"]) == {"HIGH", "LOW"}
    assert set(gold["manual_period"]) == {"THREE_MONTHS"}
    assert gold[["manual_value", "manual_unit", "manual_semantics"]].notna().all().all()


def test_gold_audit_exposes_old_failures_and_new_parser_passes_all_gates() -> None:
    overall = pd.read_csv(AUDIT / "parser_gold_audit_summary.csv").iloc[0]
    assert int(overall["gold_rows"]) == 75
    assert np.isclose(overall["pre_numeric_accuracy"], 65 / 75)
    assert np.isclose(overall["pre_all_dimension_accuracy"], 62 / 75)
    for dimension in ("numeric", "unit", "period", "semantic"):
        assert overall[f"post_{dimension}_accuracy"] == 1.0
    assert bool(overall["parser_quality_gate"])

    gates = pd.read_csv(AUDIT / "parser_quality_gate.csv")
    assert set(gates["subindustry"]) == {
        "integrated",
        "midstream",
        "refining",
        "services",
    }
    assert gates["parser_quality_gate"].all()
    assert gates["post_numeric_accuracy"].ge(0.95).all()
    assert gates["post_unit_accuracy"].eq(1.0).all()
    assert gates["post_period_accuracy"].eq(1.0).all()
    assert gates["post_semantic_accuracy"].ge(0.95).all()


def test_known_period_aggregation_component_and_unit_corrections_are_locked() -> None:
    changes = pd.read_csv(AUDIT / "parser_change_log.csv").set_index(
        ["ticker", "report_quarter", "metric_id"]
    )
    expected_values = {
        ("BKR", "2024Q4", "orders_activity"): (28240.0, 7496.0),
        ("HAL", "2024Q2", "completion_production_activity"): (6774.0, 3401.0),
        ("MPC", "2024Q2", "company_throughput"): (9065.0, 3065.0),
        ("SLB", "2023Q4", "international_activity"): (26188.0, 7293.0),
        ("ET", "2023Q3", "liquids_transport_volume"): (2161.0, 7801.0),
    }
    for key, (pre, post) in expected_values.items():
        row = changes.loc[key]
        assert row["metric_value_pre"] == pre
        assert row["metric_value_post"] == post

    epd = changes.loc[("EPD", "2024Q1", "equivalent_pipeline_volume")]
    assert epd["metric_unit_pre"] == "million_bpd"
    assert epd["metric_unit_post"] == "mbpd"


def test_parser_correction_attribution_and_candidate_decision_are_reproducible() -> None:
    performance = pd.read_csv(AUDIT / "pre_gold_post_model_performance.csv").set_index(
        "subindustry"
    )
    assert performance.loc["services", "post_parser_median_mase"] < performance.loc[
        "services", "pre_parser_median_mase"
    ]
    assert performance.loc[
        "services", "gold_sample_replacement_median_mase"
    ] < performance.loc["services", "pre_parser_median_mase"]
    assert performance.loc["refining", "post_parser_wape_pct"] < performance.loc[
        "refining", "pre_parser_wape_pct"
    ]

    selection = pd.read_csv(COMPANY_OUTPUT / "research_model_selection.csv").set_index(
        "subindustry"
    )
    assert selection.index[selection["company_kpi_candidate_accepted"]].tolist() == [
        "refining"
    ]
    assert selection["parser_quality_gate"].all()


def test_quality_provenance_and_point_in_time_boundaries_are_emitted() -> None:
    predictions = pd.read_csv(COMPANY_OUTPUT / "company_kpi_time_predictions.csv")
    required = {
        "kpi_used",
        "fallback_used",
        "company_kpi_age_days",
        "company_kpi_quality_score",
        "company_kpi_rule_confidence",
    }
    assert required.issubset(predictions.columns)
    assert predictions["kpi_used"].astype(bool).any()
    assert predictions["fallback_used"].astype(bool).any()
    assert predictions["kpi_used"].astype(bool).eq(
        ~predictions["fallback_used"].astype(bool)
    ).all()

    features = pd.read_csv(COMPANY_OUTPUT / "company_kpi_point_in_time_features.csv")
    used = features["company_kpi_status"].eq("AVAILABLE")
    assert pd.to_datetime(features.loc[used, "company_kpi_available_at"]).le(
        pd.to_datetime(features.loc[used, "forecast_cutoff_date"])
    ).all()

    buckets = pd.read_csv(AUDIT / "kpi_quality_vs_forecast_error.csv")
    assert "FALLBACK" in set(buckets["quality_bucket"])
    assert buckets["mean_absolute_forecast_error_log_points"].notna().all()

    metadata = json.loads((AUDIT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["all_subindustry_parser_gates_pass"] is True
    assert metadata["paid_market_data_used"] is False
