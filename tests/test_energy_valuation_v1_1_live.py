from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from energy_nowcast.operations.store import (
    connect_store,
    insert_valuation_settlement,
    insert_valuation_snapshot,
    read_table,
)
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11
from energy_nowcast.valuation_monitoring.scorecard import (
    build_valuation_live_scorecard,
)
from energy_nowcast.valuation_monitoring.snapshot import (
    build_valuation_snapshots,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_1_live"


def test_live_monitoring_preserves_both_frozen_benchmarks() -> None:
    parent = verify_v1(ROOT)
    benchmark = verify_v11(ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert parent["immutable"] is True
    assert benchmark["immutable"] is True
    assert benchmark["sanity_audit_passed"] is True
    assert metadata["benchmark_manifest_sha256"] == benchmark["manifest_sha256"]
    assert metadata["parent_manifest_sha256"] == parent["manifest_sha256"]
    assert metadata["benchmark_verified_before_and_after"] is True
    assert metadata["frozen_benchmark_mutated"] is False


def test_live_snapshot_is_complete_and_production_remains_locked() -> None:
    snapshots = pd.read_csv(OUTPUT / "valuation_snapshots.csv")
    score = pd.read_csv(OUTPUT / "live_scorecard_summary.csv").iloc[0]
    vintage_coverage = snapshots.groupby("as_of_date")["ticker"].agg(
        rows="size", unique_tickers="nunique"
    )
    assert vintage_coverage["rows"].eq(26).all()
    assert vintage_coverage["unique_tickers"].eq(26).all()
    assert snapshots["model_version"].eq("ENERGY_VALUATION_V1_1").all()
    assert snapshots["production_eligible"].eq(0).all()
    assert snapshots[[
        "fair_value", "market_price", "value_gap_pct", "base_year1_nopat_usd",
        "base_year1_reinvestment_usd", "base_year1_fcff_usd",
        "base_terminal_value_share_pct",
    ]].notna().all().all()
    assert int(score["matched_observations"]) == 0
    assert score["model_change_lock"] == "LOCKED"
    assert int(score["observations_needed"]) == 20
    assert score["production_status"] == (
        "NOT_PROMOTED_REQUIRES_SEPARATE_REVIEW"
    )


def test_frozen_ep_skew_is_a_monitor_not_a_retuning_input() -> None:
    monitors = pd.read_csv(OUTPUT / "hypothesis_monitors.csv")
    ep = monitors.loc[monitors["hypothesis"].eq("E&P_SYSTEMATIC_SKEW")].iloc[0]
    assert ep["status"] == "MONITOR_DO_NOT_RETUNE"
    assert np.isclose(ep["value"], 90.66707198700433)
    assert ep["secondary_value"] == "8/14"
    snapshots = pd.read_csv(OUTPUT / "valuation_snapshots.csv")
    assert snapshots.loc[
        snapshots["subindustry"].eq("ep"), "expectations_monitor_status"
    ].eq("E&P_SYSTEMATIC_SKEW_MONITOR").all()


def test_terminal_dependence_hypothesis_keeps_frozen_base_medians() -> None:
    monitors = pd.read_csv(OUTPUT / "hypothesis_monitors.csv")
    terminal = monitors.loc[
        monitors["hypothesis"].eq("HIGH_TERMINAL_DEPENDENCE")
    ].set_index("scope")
    expected = {
        "ep": 84.07115139983048,
        "integrated": 81.21100707336696,
        "midstream": 87.37623625315487,
        "refining": 79.78206273458146,
        "services": 80.77438909401172,
    }
    assert set(terminal.index) == set(expected)
    for subindustry, value in expected.items():
        assert np.isclose(terminal.loc[subindustry, "value"], value)
        assert terminal.loc[subindustry, "status"] == (
            "MONITOR_LONG_RUN_ECONOMICS"
        )


def test_fcff_attribution_separates_components_and_reconciles() -> None:
    attribution = pd.read_csv(OUTPUT / "fcff_attributions.csv")
    required = {
        "nopat_usd", "depreciation_amortization_usd",
        "delta_operating_nwc_usd", "other_cash_conversion_usd",
        "cash_capex_usd", "reported_fcff_usd", "reconstructed_fcff_usd",
        "combined_cash_conversion_adjustment_usd",
        "combined_reconstructed_fcff_usd", "combined_identity_error_usd",
        "capex_monitor_status", "attribution_status",
    }
    assert required.issubset(attribution.columns)
    vintage_coverage = attribution.groupby("as_of_date")["ticker"].agg(
        rows="size", unique_tickers="nunique"
    )
    assert vintage_coverage["rows"].eq(26).all()
    assert vintage_coverage["unique_tickers"].eq(26).all()
    assert attribution["diagnostic_only"].all()
    assert attribution["combined_identity_error_usd"].abs().le(1e-3).all()
    complete = attribution.loc[attribution["attribution_status"].eq(
        "COMPLETE_D_AND_A_NWC_OTHER_SEPARATED"
    )]
    assert complete.groupby("as_of_date").size().eq(21).all()
    assert complete["detailed_identity_error_usd"].abs().le(1e-3).all()
    imputed = attribution.loc[attribution["capex_imputed"].eq(1)]
    assert not imputed.empty
    assert imputed["capex_monitor_status"].eq(
        "IMPUTED_CAPEX_REQUIRES_ATTRIBUTION_REVIEW"
    ).all()
    ep_monitor = pd.read_csv(OUTPUT / "hypothesis_monitors.csv").loc[
        lambda frame: frame["hypothesis"].eq(
            "E&P_FCFF_MARGIN_ABOVE_OPERATING_MARGIN"
        )
    ].iloc[0]
    assert np.isclose(ep_monitor["value"], 9.513911910202376)
    assert ep_monitor["secondary_value"] == "8/14"


def test_model_change_policy_routes_changes_outside_frozen_v1_1() -> None:
    policy = pd.read_csv(OUTPUT / "model_change_policy.csv").set_index("change")
    for change in (
        "NEW_MARKET_PRICE", "ACTUAL_RELEASE", "CONSENSUS_VINTAGE",
        "LIVE_FORECAST_SNAPSHOT", "SETTLEMENT", "FCFF_ATTRIBUTION",
        "MONITORING_REPORT",
    ):
        assert policy.loc[change, "policy"] == "ALLOWED_APPEND_ONLY_OBSERVATION"
    for change in (
        "WACC_FORMULA", "SCENARIO_BOUNDS", "TERMINAL_GROWTH",
        "FINANCIAL_BRIDGE", "PARSER_SEMANTICS", "E&P_MANUAL_OVERRIDE",
        "SCENARIO_WEIGHT_RETUNING",
    ):
        assert policy.loc[change, "policy"] == "PROHIBITED_IN_FROZEN_V1_1"
        assert policy.loc[change, "required_version_route"] == (
            "V1.1.1_BUGFIX_IF_PROVEN_BUG_ELSE_V1.2_RESEARCH"
        )


def test_arcana_consensus_sources_are_retained_with_finnworlds_ratings_only() -> None:
    vintages = pd.read_csv(OUTPUT / "consensus_vintages.csv")
    coverage = pd.read_csv(OUTPUT / "consensus_source_coverage.csv")
    assert {"ALPHA_VANTAGE", "FMP"}.issubset(set(vintages["provider"]))
    assert coverage["provider"].eq("FINNWORLDS").all()
    assert coverage["revenue_consensus_available"].eq(0).all()
    assert coverage["status"].eq(
        "RATINGS_ONLY_NOT_USED_AS_REVENUE_CONSENSUS"
    ).all()


def test_append_only_store_is_idempotent_and_rejects_rewrites(tmp_path: Path) -> None:
    source = pd.read_csv(OUTPUT / "valuation_snapshots.csv").iloc[0].to_dict()
    with connect_store(tmp_path / "store.sqlite") as connection:
        assert insert_valuation_snapshot(connection, source) == "INSERTED"
        assert insert_valuation_snapshot(connection, source) == "UNCHANGED"
        changed = {**source, "fair_value": float(source["fair_value"]) + 1.0}
        with pytest.raises(RuntimeError, match="Immutable valuation_snapshots"):
            insert_valuation_snapshot(connection, changed)
        assert len(read_table(connection, "valuation_snapshots")) == 1


def test_settlement_stays_locked_before_twenty_matches(tmp_path: Path) -> None:
    source = pd.read_csv(OUTPUT / "valuation_snapshots.csv").iloc[0].to_dict()
    with connect_store(tmp_path / "store.sqlite") as connection:
        insert_valuation_snapshot(connection, source)
        status = insert_valuation_settlement(connection, {
            "snapshot_as_of_date": source["as_of_date"],
            "ticker": source["ticker"],
            "target_quarter": source["target_quarter"],
            "model_version": source["model_version"],
            "actual_ttm_fcff_usd": source["base_year1_fcff_usd"] * 0.9,
            "settlement_market_price": source["market_price"] * 1.1,
            "release_date": "2027-06-30",
            "source_path": str(tmp_path / "manual.csv"),
        })
        assert status == "INSERTED"
        details, summary = build_valuation_live_scorecard(connection)
    assert len(details) == 1
    assert int(summary.iloc[0]["matched_observations"]) == 1
    assert summary.iloc[0]["model_change_lock"] == "LOCKED"
    assert int(summary.iloc[0]["observations_needed"]) == 19
    assert summary.iloc[0]["production_status"] == (
        "NOT_PROMOTED_REQUIRES_SEPARATE_REVIEW"
    )


def test_market_override_changes_observation_only_and_rejects_future_data(
    tmp_path: Path,
) -> None:
    manifest = verify_v11(ROOT)
    baseline = (
        pd.read_csv(OUTPUT / "valuation_snapshots.csv")
        .loc[lambda frame: frame["as_of_date"].eq("2026-09-02")]
        .set_index("ticker")
    )
    override_path = tmp_path / "market.csv"
    pd.DataFrame([{
        "ticker": "EOG", "market_date": "2026-09-01", "market_price": 200.0,
    }]).to_csv(override_path, index=False)
    updated = build_valuation_snapshots(
        ROOT, date(2026, 9, 2), manifest["manifest_sha256"], override_path
    ).set_index("ticker")
    assert updated.loc["EOG", "market_price"] == 200.0
    assert updated.loc["EOG", "fair_value"] == baseline.loc["EOG", "fair_value"]
    assert np.isclose(
        updated.loc["EOG", "base_year1_fcff_usd"],
        baseline.loc["EOG", "base_year1_fcff_usd"],
        rtol=0.0,
        atol=1e-6,
    )
    pd.DataFrame([{
        "ticker": "EOG", "market_date": "2026-09-03", "market_price": 200.0,
    }]).to_csv(override_path, index=False)
    with pytest.raises(ValueError, match="after as-of"):
        build_valuation_snapshots(
            ROOT, date(2026, 9, 2), manifest["manifest_sha256"], override_path
        )
