from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.data_catalog import DATA
from energy_nowcast.core.proxy_benchmark import verify_proxy_benchmark
from energy_nowcast.core.taxonomy import all_phase_tickers
from energy_nowcast.operations.champion import verify_champion
from energy_nowcast.research.v36.benchmark import verify_research_champion


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "phase2_4_company_kpi_research"
PROXY_OUTPUT = ROOT / "output" / "phase2_4_structural_research"
SNAPSHOT = DATA.company_kpi_snapshot


def test_proxy_benchmark_is_frozen_and_verifiable() -> None:
    result = verify_proxy_benchmark(ROOT)
    assert result["version"] == "PHASE2_4_STRUCTURAL_PROXY_V1"
    assert result["files"] == 13


def test_company_kpi_snapshot_is_official_sec_and_unit_audited() -> None:
    source = pd.read_csv(SNAPSHOT / "source_manifest.csv")
    assert len(source) >= 400
    assert source["source_url"].str.contains("sec.gov", case=False).all()
    assert source["sha256"].str.fullmatch(r"[0-9a-f]{64}").all()

    metrics = pd.read_csv(SNAPSHOT / "company_kpi_quarterly.csv")
    assert set(metrics["ticker"]) == set(all_phase_tickers())
    assert metrics["availability_source"].eq("SEC_ACCEPTANCE_DATETIME").all()
    accepted = pd.to_datetime(metrics["acceptance_datetime_utc"])
    available = pd.to_datetime(metrics["available_at"])
    assert accepted.notna().all()
    assert available.eq(accepted.dt.tz_convert(None)).all()
    assert available.le(
        pd.to_datetime(metrics["filing_date"]) + pd.Timedelta(days=1)
    ).all()
    epd_processing = metrics.loc[
        metrics["ticker"].eq("EPD")
        & metrics["metric_id"].eq("fee_gas_processing_volume")
    ]
    assert epd_processing["metric_value"].between(1.0, 20.0).all()


def test_requested_kpi_coverage_discloses_parsed_and_missing_fields() -> None:
    coverage = pd.read_csv(OUTPUT / "requested_kpi_coverage.csv")
    assert set(coverage["ticker"]) == set(all_phase_tickers())
    assert set(coverage["status"]) == {
        "PARSED_SEC_8K_EARNINGS_EXHIBIT",
        "NOT_YET_STANDARDIZED",
    }
    integrated = coverage["subindustry"].eq("integrated")
    assert coverage.loc[
        integrated & coverage["requested_metric"].eq("upstream_total_boe"),
        "status",
    ].eq("PARSED_SEC_8K_EARNINGS_EXHIBIT").all()
    assert coverage.loc[
        integrated & coverage["requested_metric"].eq("realized_oil_price"),
        "status",
    ].eq("NOT_YET_STANDARDIZED").all()


def test_company_kpi_features_are_previous_quarter_and_point_in_time() -> None:
    features = pd.read_csv(OUTPUT / "company_kpi_point_in_time_features.csv")
    available = features["company_kpi_status"].eq("AVAILABLE")
    assert pd.to_datetime(features.loc[available, "company_kpi_available_at"]).le(
        pd.to_datetime(features.loc[available, "forecast_cutoff_date"])
    ).all()
    target = features.loc[available, "quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 1)
    )
    assert features.loc[available, "company_kpi_report_quarter"].eq(target).all()


def test_pi_recalibration_does_not_change_proxy_point_forecasts() -> None:
    frozen = pd.read_csv(PROXY_OUTPUT / "time_predictions.csv")
    recalibrated = pd.read_csv(OUTPUT / "proxy_recalibrated_time_predictions.csv")
    comparison = recalibrated[["ticker", "quarter", "candidate_prediction"]].merge(
        frozen[["ticker", "quarter", "candidate_prediction"]],
        on=["ticker", "quarter"],
        suffixes=("_new", "_frozen"),
    )
    assert len(comparison) == len(frozen)
    assert np.allclose(
        comparison["candidate_prediction_new"],
        comparison["candidate_prediction_frozen"],
    )


def test_refining_kpi_improves_point_metrics_and_passes_split_gates() -> None:
    comparison = pd.read_csv(OUTPUT / "benchmark_vs_company_kpi_summary.csv").set_index(
        "subindustry"
    )
    refining = comparison.loc["refining"]
    assert refining["company_kpi_median_mase"] < refining["proxy_median_mase"]
    assert refining["company_kpi_mean_mase"] < refining["proxy_mean_mase"]
    assert refining["company_kpi_wape_pct"] < refining["proxy_wape_pct"]
    assert refining["benchmark_no_regression_share"] == 1.0

    gates = pd.read_csv(OUTPUT / "split_gates.csv")
    gate = gates.loc[
        gates["experiment"].eq("COMPANY_KPI")
        & gates["subindustry"].eq("refining")
    ].iloc[0]
    assert bool(gate["point_model_gate"])
    assert bool(gate["uncertainty_gate"])
    assert bool(gate["combined_research_gate"])
    assert not bool(gate["production_promotion_eligible"])


def test_point_and_uncertainty_gates_are_independent() -> None:
    gates = pd.read_csv(OUTPUT / "split_gates.csv")
    services = gates.loc[
        gates["experiment"].eq("PROXY_RECALIBRATED")
        & gates["subindustry"].eq("services")
    ].iloc[0]
    assert bool(services["point_model_gate"])
    assert not bool(services["uncertainty_gate"])
    assert bool(services["macro_research_unlocked"])
    pi = pd.read_csv(OUTPUT / "pi_calibration_comparison.csv").set_index("subindustry")
    for subindustry in ("refining", "services"):
        assert (
            pi.loc[subindustry, "recalibrated_interval_80_score"]
            < pi.loc[subindustry, "original_interval_80_score"]
        )
        assert (
            pi.loc[subindustry, "recalibrated_interval_80_width"]
            < pi.loc[subindustry, "original_interval_80_width"]
        )


def test_research_selection_accepts_only_refining_company_kpi() -> None:
    selection = pd.read_csv(OUTPUT / "research_model_selection.csv").set_index(
        "subindustry"
    )
    accepted = selection.index[selection["company_kpi_candidate_accepted"]].tolist()
    assert accepted == ["refining"]
    assert selection["parser_quality_gate"].all()
    assert selection["parser_numeric_accuracy"].ge(0.95).all()
    assert selection["parser_unit_accuracy"].eq(1.0).all()
    assert selection["parser_period_accuracy"].eq(1.0).all()
    assert selection["parser_semantic_accuracy"].ge(0.95).all()
    assert selection.loc["services", "macro_research_unlocked"]
    assert not selection["production_promotion_eligible"].any()


def test_latest_research_predictions_keep_production_baseline() -> None:
    latest = pd.read_csv(OUTPUT / "latest_research_predictions.csv")
    assert set(latest["ticker"]) == set(all_phase_tickers())
    assert latest["selected_model"].eq("LAG_REVENUE_BASELINE").all()
    assert np.allclose(latest["selected_prediction"], latest["legacy_prediction"])
    refining = latest["subindustry"].eq("refining")
    assert np.allclose(
        latest.loc[refining, "candidate_prediction"],
        latest.loc[refining, "company_kpi_candidate_prediction"],
    )
    assert np.allclose(
        latest.loc[~refining, "candidate_prediction"],
        latest.loc[~refining, "proxy_candidate_prediction"],
    )


def test_every_ticker_retains_eight_time_and_loco_observations() -> None:
    for filename in (
        "research_selected_time_predictions.csv",
        "research_selected_loco_predictions.csv",
    ):
        frame = pd.read_csv(OUTPUT / filename)
        counts = frame.groupby("ticker").size()
        assert set(counts.index) == set(all_phase_tickers())
        assert counts.eq(8).all()


def test_consensus_paid_data_and_champion_boundaries_remain_closed() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["paid_market_data_used"] is False
    assert metadata["cme_used"] is False
    assert metadata["cma_used"] is False
    assert metadata["post_cutoff_consensus_used_for_backtest_or_promotion"] is False
    assert metadata["parser_quality_gate_required_for_company_kpi_selection"] is True
    assert metadata["parser_audit_status"] == "CURRENT"
    assert metadata["company_kpi_accepted_subindustries"] == ["refining"]
    formal = pd.read_csv(OUTPUT / "model_vs_consensus_point_in_time.csv")
    assert formal["consensus_revenue"].isna().all()
    diagnostic = pd.read_csv(
        OUTPUT / "model_vs_consensus_post_cutoff_diagnostic.csv"
    )
    matched = diagnostic["consensus_revenue"].notna()
    assert diagnostic.loc[matched, "snapshot_after_cutoff"].astype(bool).all()
    assert verify_champion(ROOT, "3.4")["version"] == "3.4"
    assert verify_research_champion(ROOT, "3.5.3")["version"] == "3.5.3"
