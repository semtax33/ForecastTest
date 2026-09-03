from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.core.platform import structural_gate
from energy_nowcast.core.steo import select_point_in_time_features
from energy_nowcast.core.taxonomy import (
    SUBINDUSTRY_TICKERS,
    all_phase_tickers,
    subindustry_for_ticker,
)
from equity_platform.sectors.energy.forecasting.integrated import predict_integrated
from equity_platform.sectors.energy.forecasting.midstream import predict_midstream
from energy_nowcast.operations.champion import verify_champion
from equity_platform.sectors.energy.forecasting.refining import predict_refiner
from energy_nowcast.research.v36.benchmark import verify_research_champion
from equity_platform.sectors.energy.forecasting.services import predict_services


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "phase2_4_structural_research"


def test_fixed_taxonomy_routes_each_phase_company_once() -> None:
    tickers = all_phase_tickers()
    assert len(tickers) == len(set(tickers)) == 12
    assert subindustry_for_ticker("XOM") == "integrated"
    assert subindustry_for_ticker("VLO") == "refining"
    assert subindustry_for_ticker("KMI") == "midstream"
    assert subindustry_for_ticker("SLB") == "services"


def test_steo_selector_uses_latest_vintage_before_cutoff() -> None:
    quarterly = pd.DataFrame([
        {
            "target_quarter": "2025Q4",
            "available_at": pd.Timestamp("2025-11-13"),
            "issue": "nov25",
            "wti": 60.0,
        },
        {
            "target_quarter": "2025Q4",
            "available_at": pd.Timestamp("2025-12-02"),
            "issue": "dec25",
            "wti": 70.0,
        },
    ])
    selected = select_point_in_time_features(quarterly, ["2025Q4"])
    assert selected.loc[0, "issue"] == "nov25"
    assert selected.loc[0, "wti"] == 60.0
    assert pd.Timestamp(selected.loc[0, "available_at"]) <= pd.Timestamp(
        selected.loc[0, "forecast_cutoff_date"]
    )


def test_integrated_is_explicit_segment_sum_of_parts() -> None:
    row = pd.Series({
        "ticker": "XOM",
        "wti_log_yoy": 10.0,
        "henry_log_yoy": 2.0,
        "us_crude_production_log_yoy": 4.0,
        "us_dry_gas_production_log_yoy": 2.0,
        "product_price_basket_log_yoy": 8.0,
        "refinery_crude_input_log_yoy": 1.0,
        "refiner_crude_cost_log_yoy": 5.0,
        "lag_revenue_log_yoy": 3.0,
    })
    result = predict_integrated(row)
    contributions = sum(
        float(result[column])
        for column in (
            "upstream_contribution_log_points",
            "downstream_contribution_log_points",
            "chemicals_contribution_log_points",
            "other_contribution_log_points",
        )
    )
    assert np.isclose(float(result["candidate_prediction"]), contributions)


def test_refiner_revenue_does_not_treat_crack_as_revenue() -> None:
    row = pd.Series({
        "product_price_basket_log_yoy": 10.0,
        "refinery_crude_input_log_yoy": 2.0,
        "refinery_crude_input": 16.0,
        "crack_321_per_bbl": 25.0,
    })
    first = predict_refiner(row)
    row["crack_321_per_bbl"] = 50.0
    second = predict_refiner(row)
    assert first["candidate_prediction"] == second["candidate_prediction"] == 12.0
    assert first["forecast_crack_321_per_bbl"] != second["forecast_crack_321_per_bbl"]
    assert bool(first["margin_signal_only"])


def test_midstream_fee_share_limits_direct_commodity_sensitivity() -> None:
    base = pd.Series({
        "ticker": "WMB",
        "us_dry_gas_production_log_yoy": 3.0,
        "us_crude_production_log_yoy": 3.0,
        "henry_log_yoy": 0.0,
        "wti_log_yoy": 0.0,
    })
    shocked = base.copy()
    shocked["henry_log_yoy"] = 50.0
    change = (
        float(predict_midstream(shocked)["candidate_prediction"])
        - float(predict_midstream(base)["candidate_prediction"])
    )
    assert np.isclose(change, 4.5)


def test_services_capex_price_signal_is_clipped() -> None:
    row = pd.Series({
        "ticker": "HAL",
        "total_rigs_log_yoy": 0.0,
        "us_crude_production_log_yoy": 0.0,
        "world_liquids_production_log_yoy": 0.0,
        "wti_log_yoy": 1000.0,
        "henry_log_yoy": 1000.0,
    })
    result = predict_services(row)
    assert result["capex_pricing_contribution_log_points"] == 8.0


def _passing_refiner_score() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": list(SUBINDUSTRY_TICKERS["refining"]),
        "observations": [8, 8, 8],
        "mase": [0.6, 0.7, 0.75],
        "improvement_log_points": [1.0, 0.5, 0.1],
    })


def test_structural_gate_keeps_pi80_bounds_exact() -> None:
    summary = pd.Series({
        "median_ticker_mase": 0.7,
        "mean_ticker_mase": 0.6833,
        "mean_pi_80_coverage": 0.85,
        "mean_directional_hit_rate": 0.70,
    })
    assert bool(structural_gate(
        _passing_refiner_score(), summary, "refining"
    ).loc[0, "research_gate"])
    summary["mean_pi_80_coverage"] = 0.850001
    assert not bool(structural_gate(
        _passing_refiner_score(), summary, "refining"
    ).loc[0, "research_gate"])


def test_generated_artifacts_are_point_in_time_and_use_no_paid_market_data() -> None:
    steo = pd.read_csv(OUTPUT / "steo_point_in_time_quarterly.csv")
    assert pd.to_datetime(steo["available_at"]).le(
        pd.to_datetime(steo["forecast_cutoff_date"])
    ).all()
    rigs = pd.read_csv(OUTPUT / "rig_point_in_time_quarterly.csv")
    for column in [name for name in rigs if name.endswith("_available_at")]:
        assert pd.to_datetime(rigs[column]).le(
            pd.to_datetime(rigs["rig_cutoff_date"])
        ).all()
    sources = pd.read_csv(OUTPUT / "free_source_manifest.csv")
    assert sources["source_url"].str.contains("eia.gov", case=False).all()
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["paid_market_data_used"] is False
    assert metadata["cme_used"] is False
    assert metadata["cma_used"] is False


def test_consensus_snapshots_are_cutoff_audited_and_never_leak() -> None:
    audit = pd.read_csv(OUTPUT / "consensus_cutoff_audit.csv")
    audit["snapshot_date"] = pd.to_datetime(audit["snapshot_date"], errors="coerce")
    audit["forecast_cutoff_date"] = pd.to_datetime(audit["forecast_cutoff_date"])
    eligible = audit["point_in_time_eligible"].astype(bool)
    assert audit.loc[eligible, "snapshot_date"].le(
        audit.loc[eligible, "forecast_cutoff_date"]
    ).all()
    post_cutoff = audit["status"].eq("POST_CUTOFF_DIAGNOSTIC_ONLY")
    assert audit.loc[post_cutoff, "snapshot_date"].gt(
        audit.loc[post_cutoff, "forecast_cutoff_date"]
    ).all()

    formal = pd.read_csv(OUTPUT / "model_vs_consensus_point_in_time.csv")
    assert formal["consensus_revenue"].isna().all()
    assert formal["comparison_status"].eq(
        "NO_PRE_CUTOFF_REVENUE_CONSENSUS"
    ).all()

    diagnostic = pd.read_csv(
        OUTPUT / "model_vs_consensus_post_cutoff_diagnostic.csv"
    )
    matched = diagnostic["consensus_revenue"].notna()
    assert diagnostic.loc[matched, "snapshot_after_cutoff"].astype(bool).all()
    assert diagnostic.loc[matched, "comparison_status"].eq(
        "POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION"
    ).all()
    providers = set(
        diagnostic.loc[matched, "providers"].str.split(",").explode().dropna()
    )
    assert providers.issubset({"ALPHA_VANTAGE", "FMP"})

    finnworlds = pd.read_csv(OUTPUT / "finnworlds_consensus_coverage.csv")
    assert finnworlds["provider"].eq("FINNWORLDS").all()
    assert finnworlds["revenue_consensus_available"].eq(False).all()  # noqa: E712
    performance = pd.read_csv(OUTPUT / "model_vs_consensus_performance.csv")
    assert performance.loc[0, "status"] == "NO_MATCHED_OBSERVATIONS"
    assert performance.loc[0, "observations"] == 0


def test_operating_proxy_and_macro_overlay_boundaries_are_explicit() -> None:
    coverage = pd.read_csv(OUTPUT / "operational_kpi_coverage.csv")
    assert set(coverage["ticker"]) == set(all_phase_tickers())
    refiners = coverage["subindustry"].eq("refining")
    assert coverage.loc[refiners, "active_proxy"].eq(
        "EIA_STEO_US_REFINERY_CRUDE_INPUT"
    ).all()
    assert coverage.loc[refiners, "proxy_scope"].eq(
        "US_GROUP_PROXY_NOT_COMPANY_GUIDANCE"
    ).all()
    overlay = pd.read_csv(OUTPUT / "macro_overlay_status.csv")
    assert overlay["macro_residual_overlay_enabled"].eq(False).all()  # noqa: E712
    assert overlay["promotion_effect"].eq("NONE_RESEARCH_ONLY").all()


def test_every_company_has_eight_time_and_loco_forecasts() -> None:
    for filename in ("time_predictions.csv", "loco_predictions.csv"):
        predictions = pd.read_csv(OUTPUT / filename)
        counts = predictions.groupby("ticker").size()
        assert set(counts.index) == set(all_phase_tickers())
        assert counts.eq(8).all()


def test_failed_gates_retain_baseline_and_champions_verify() -> None:
    predictions = pd.read_csv(OUTPUT / "latest_unobserved_predictions.csv")
    failed = predictions["research_gate"].eq(False)  # noqa: E712
    assert predictions.loc[failed, "selected_model"].eq("LAG_REVENUE_BASELINE").all()
    assert np.allclose(
        predictions.loc[failed, "selected_prediction"],
        predictions.loc[failed, "legacy_prediction"],
    )
    assert verify_champion(ROOT, "3.4")["version"] == "3.4"
    assert verify_research_champion(ROOT, "3.5.3")["version"] == "3.5.3"
