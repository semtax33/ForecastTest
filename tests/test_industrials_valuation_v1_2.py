from pathlib import Path

import pandas as pd
import pytest

from equity_platform.industry_data.registry import build_registry_coverage, load_industry_sensor_registry
from equity_platform.sectors.industrials.v11_benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/industrials_valuation_v1_2_research"


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_common_industry_sensor_registry_covers_all_gics_sectors_and_roles() -> None:
    registry = load_industry_sensor_registry(ROOT / "configs/industry_sensor_registry.csv")
    coverage = build_registry_coverage(registry)
    assert len(registry) == 59
    assert registry["sector"].nunique() == 11
    assert {"P", "Q", "C", "I"}.issubset(set(registry["pqci_dimension"]))
    assert {"FORECAST", "NOWCAST", "CALIBRATION_ONLY"}.issubset(set(registry["forecast_use"]))
    machinery = coverage.loc[coverage["subindustry"].eq("machinery")].iloc[0]
    assert machinery["sensor_count"] == 6
    assert machinery["forecast_ready"]


def test_cat_industry_bridge_uses_public_pqci_but_fails_closed_on_vintages() -> None:
    signals = read("industry_sensor_signals")
    gate = read("industry_data_gate").iloc[0]
    assert len(signals) == 6
    assert set(signals["pqci_dimension"]) == {"P", "Q", "C", "I"}
    assert signals["vintage_status"].eq("LATEST_REVISED_SNAPSHOT_NO_HISTORICAL_RELEASE_DATE").all()
    assert not signals["historical_pit_backtest_eligible"].any()
    assert gate["current_research_nowcast_allowed"]
    assert not gate["historical_pit_backtest_allowed"]
    assert not gate["terminal_replacement_allowed"]


def test_revenue_margin_reinvestment_roic_bridge_reconciles() -> None:
    bridge = read("industry_financial_bridge").iloc[0]
    assert bridge["forecast_revenue_growth_pct"] == pytest.approx(17.0278191306)
    assert bridge["forecast_operating_margin_pct"] == pytest.approx(26.2938833298)
    assert bridge["forecast_roic_pct"] == pytest.approx(75.0964163551)
    assert bridge["incremental_roic_pct"] > 100.0
    assert abs(bridge["growth_identity_error_pct_points"]) < 1e-9
    assert not bridge["reinvestment_bridge_validated"]
    assert bridge["economics_scope_flag"] == "REQUIRES_COST_SCOPE_AND_COMPANY_CAPTURE_VALIDATION"
    assert not bridge["terminal_input_allowed"]


def test_v12_dcf_uses_year_one_industry_anchor_and_frozen_terminal() -> None:
    bridge = read("industry_financial_bridge").iloc[0]
    projection = read("v1_2_mpe_dcf_projection")
    assert projection.iloc[0]["revenue_usd"] == pytest.approx(bridge["forecast_revenue_usd"])
    assert projection.iloc[0]["reinvestment_usd"] == pytest.approx(bridge["required_reinvestment_usd"])
    assert projection["fcff_identity_error_usd"].abs().max() < 1e-3
    assert projection.iloc[-1]["terminal_margin_pct"] == pytest.approx(17.0115661144)
    assert projection.iloc[-1]["terminal_roic_pct"] == pytest.approx(49.3718922356)
    value = read("v1_2_sotp_valuation").iloc[0]
    assert value["terminal_value_share_pct"] == pytest.approx(69.1624352324)


def test_expectations_surfaces_are_monotonic_and_preserve_non_identification() -> None:
    margin_wacc = read("expectations_surface_margin_wacc")
    growth_margin = read("expectations_surface_growth_margin")
    growth_roic = read("expectations_surface_growth_roic")
    iso = read("expectations_iso_value_curve")
    summary = read("expectations_surface_summary").iloc[0]
    assert len(margin_wacc) == len(growth_margin) == len(growth_roic) == 25
    for _, group in margin_wacc.groupby("wacc_pct"):
        assert group.sort_values("margin_pct")["mpe_enterprise_value_usd"].is_monotonic_increasing
    for _, group in margin_wacc.groupby("margin_pct"):
        assert group.sort_values("wacc_pct")["mpe_enterprise_value_usd"].is_monotonic_decreasing
    assert summary["surface_points"] == 75
    assert summary["iso_unbracketed_conditions"] == 2
    assert iso.loc[iso["status"].ne("SOLVED"), "solution_pct"].isna().all()
    assert summary["non_identification_preserved"]
    assert not summary["appropriate_parameter_claim_allowed"]


def test_mpe_roic_audit_keeps_historical_incremental_and_terminal_separate() -> None:
    summary = read("mpe_roic_measure_summary").iloc[0]
    assert summary["historical_roic_median_pct"] == pytest.approx(49.3718922356)
    assert summary["annual_incremental_roic_median_pct"] == pytest.approx(-8.7821669234)
    assert summary["endpoint_incremental_roic_pct"] == pytest.approx(74.5446658363)
    assert not summary["historical_equals_incremental"]
    assert not summary["incremental_equals_terminal"]
    assert not summary["terminal_roic_identified"]


def test_cfsc_exact_economics_reconcile_to_broader_financial_products_perimeter() -> None:
    history = read("cfsc_standalone_economics_history")
    audit = read("financial_products_perimeter_audit").iloc[0]
    latest = history.iloc[-1]
    assert len(history) == 5
    assert latest["total_revenue_usd"] == pytest.approx(3.634e9)
    assert latest["standalone_profit_usd"] == pytest.approx(540e6)
    assert latest["net_finance_spread_pct"] == pytest.approx(3.8141295083)
    assert latest["credit_loss_rate_pct"] == pytest.approx(0.3431586785)
    assert latest["payout_ratio_pct"] == pytest.approx(92.5925925926)
    assert audit["broader_fp_reconciling_profit_usd"] == pytest.approx(194e6)
    assert not audit["reconciling_profit_attribution_identified"]
    assert audit["exact_cfsc_economics_available"]
    assert not audit["whole_fp_exact_economics_available"]


def test_parser_gold_and_cross_filing_gate_are_exact() -> None:
    cross = read("parser_cross_filing_audit")
    gold = read("parser_gold_cell_audit")
    summary = read("parser_quality_summary").iloc[0]
    assert len(cross) == 196
    assert cross["within_tolerance"].all()
    assert gold["gold_match"].all()
    assert summary["cross_filing_mismatches"] == 0
    assert summary["parser_quality_gate_pass"]


def test_v12_keeps_backlog_and_parent_frozen_and_never_promotes_production() -> None:
    manifest = verify_v11(ROOT)
    gate = read("industrials_v1_2_gate").iloc[0]
    value = read("v1_2_sotp_valuation").iloc[0]
    assert manifest["verified_files"] == 35
    assert not gate["backlog_model_changed"]
    assert gate["backlog_oos_observations"] == 2
    assert value["sotp_value_per_share"] == pytest.approx(363.8863803840)
    assert value["component_identity_error_usd"] == pytest.approx(0.0)
    assert not value["financial_products_funding_debt_double_counted"]
    assert not gate["terminal_input_allowed"]
    assert not gate["production_promoted"]
    assert gate["live_matched_observations"] == "0/20"
