from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.platform import (
    DcfAssumptions,
    INDUSTRIALS_SUBINDUSTRIES,
    build_industrials_bls_sensor_map,
    enterprise_value,
    solve_parameter,
)
from equity_platform.sectors.industrials.platform.domain import DriverRole


OUTPUT = PROJECT_ROOT / "output/industrials_v8_subindustry_platform_research"
SILVER = PROJECT_ROOT / "data-lake/silver/industrials/v8/subindustries"
GOLD = PROJECT_ROOT / "data-lake/gold/industrials/v8/subindustries"


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_all_registered_subindustries_have_pqci_sources_and_locked_authority() -> None:
    assert len(INDUSTRIALS_SUBINDUSTRIES) == 26
    assert len({profile.code for profile in INDUSTRIALS_SUBINDUSTRIES}) == 26
    for profile in INDUSTRIALS_SUBINDUSTRIES:
        roles = {role for source in profile.sources for role in source.roles}
        assert roles == set(DriverRole)


def test_bls_sensor_registry_covers_every_subindustry() -> None:
    sensors = build_industrials_bls_sensor_map()
    assert set(sensors["segment"]) == {
        profile.code for profile in INDUSTRIALS_SUBINDUSTRIES
    }
    assert sensors["series_id"].nunique() == 30
    assert sensors.groupby("segment")["role"].apply(
        lambda values: "output_price" in set(values)
    ).all()


def test_sec_ir_and_bls_lineage_gates() -> None:
    gate = _read("industrials_v8_gate").iloc[0]
    assert gate["domestic_sec_companies_ready"] == 24
    assert gate["sec_10k_10q_filings"] == 539
    assert gate["arcana_ir_companies_ready"] == 24
    assert gate["arcana_ir_documents_audited"] == 1143
    assert gate["ir_hash_mismatches"] == 0
    assert gate["bls_pit_series"] == 30
    assert gate["bls_pit_vintage_rows"] == 8037
    assert bool(gate["bls_pit_gate_pass"])
    selections = pd.read_csv(
        SILVER / "subindustry_pit_vintage_selection_audit.csv"
    )
    assert selections["cutoff_respected"].all()
    ir = pd.read_csv(SILVER / "subindustry_ir_document_evidence.csv")
    assert ir["metadata_sha256_matches"].all()
    assert not ir["numerical_model_input_allowed"].any()
    assert not ir["pdf_parsing_used"].any()


def test_forecast_authority_is_outcome_consistent_and_proxy_downgraded() -> None:
    performance = _read("subindustry_forecast_performance")
    assert (performance["oos_observations"] >= 4).sum() == 20
    assert (performance["forecast_authority"] == "STRONG").sum() == 4
    assert not (
        performance["profit_target_definition"].eq("PROFIT_PROXY_PRETAX")
        & performance["forecast_authority"].eq("STRONG")
    ).any()
    strong = performance.loc[performance["forecast_authority"].eq("STRONG")]
    assert strong["revenue_mase"].lt(1.0).all()
    assert strong["profit_margin_mase"].lt(1.0).all()
    not_tested = performance.loc[performance["oos_observations"].lt(4)]
    assert not_tested["forecast_authority"].eq("NOT_TESTED").all()
    routes = _read("subindustry_forecast_routes")
    assert routes["route_selected_before_oos"].all()
    assert not routes["post_hoc_route_reselection_allowed"].any()


def test_point_and_uncertainty_authority_are_separate() -> None:
    performance = _read("subindustry_forecast_performance")
    assert "uncertainty_authority" in performance
    assert set(performance["uncertainty_authority"]).issubset(
        {"PRELIMINARY_90_INTERVAL_COVERAGE_PASS", "NOT_CALIBRATED"}
    )
    forecasts = _read("subindustry_fixed_oos_forecasts")
    assert forecasts["margin_shrinkage_weight"].between(0.0, 0.5).all()
    assert forecasts["leakage_check_pass"].all()


def test_reinvestment_scope_is_applicability_aware_and_rd_fails_closed() -> None:
    annual = pd.read_csv(
        SILVER / "subindustry_annual_roic_reinvestment_history.csv"
    )
    identified = annual.loc[annual["core_reinvestment_claim_allowed"]]
    assert len(identified) == 58
    assert identified["operating_nwc_minimum_scope_pass"].all()
    assert identified["operating_nwc_scope"].ne("NOT_IDENTIFIED").all()
    innovation = annual.loc[
        annual["innovation_adjusted_reinvestment_claim_allowed"]
    ]
    assert innovation["research_development_usd"].notna().all()
    missing_rd = annual["research_development_usd"].isna()
    assert not annual.loc[
        missing_rd, "innovation_adjusted_reinvestment_claim_allowed"
    ].any()


def test_generic_dcf_round_trip_and_accounting_identities() -> None:
    assumptions = DcfAssumptions(
        ticker="TEST",
        scenario="base",
        base_revenue_usd=10_000.0,
        near_term_growth_pct=6.0,
        terminal_growth_pct=2.5,
        initial_margin_pct=12.0,
        terminal_margin_pct=14.0,
        tax_rate_pct=21.0,
        initial_roic_pct=18.0,
        terminal_roic_pct=15.0,
        wacc_pct=9.0,
    )
    flow, summary = enterprise_value(assumptions)
    identity = (
        flow["reinvestment_rate_pct"]
        - flow["revenue_growth_pct"] / flow["roic_pct"] * 100.0
    ).abs()
    assert identity.max() < 1e-12
    solved = solve_parameter(
        replace(assumptions, wacc_pct=8.0),
        target_ev_usd=summary["enterprise_value_usd"],
        field="wacc_pct",
        lower=3.0,
        upper=20.0,
        tolerance_usd=1e-8,
    )
    assert solved["status"] == "SOLVED"
    assert solved["value"] == pytest.approx(9.0, abs=1e-8)
    unbracketed = solve_parameter(
        assumptions,
        target_ev_usd=summary["enterprise_value_usd"] * 100.0,
        field="wacc_pct",
        lower=3.0,
        upper=20.0,
    )
    assert unbracketed["status"] == "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
    assert np.isnan(unbracketed["value"])


def test_research_dcf_never_claims_fair_value_or_terminal_readiness() -> None:
    gate = _read("industrials_v8_gate").iloc[0]
    assert gate["conditional_dcf_companies"] == 13
    assert gate["dcf_identity_max_error"] == 0.0
    assert gate["ev_equity_identity_max_error_usd"] == 0.0
    assert not bool(gate["terminal_evidence_eligible"])
    assert not bool(gate["fair_value_claim_allowed"])
    assert not bool(gate["production_promotable"])
    assert gate["live_matched_observations"] == "0/20"
    valuation = _read("subindustry_conditional_dcf_summary")
    assert not valuation["fair_value_authority"].any()
    assert valuation["growth_reinvestment_roic_identity_max_error_pct_points"].max() == 0.0
    assert valuation["ev_to_common_equity_identity_error_usd"].max() == 0.0
    assert valuation["common_equity_value_usd"].ge(0.0).all()
    reverse = _read("subindustry_reverse_dcf_diagnostics")
    assert reverse["non_identification_preserved"].all()
    assert not reverse["appropriate_wacc_claim_allowed"].any()


def test_medallion_outputs_and_foreign_adapter_fail_closed() -> None:
    assert SILVER.is_dir()
    assert GOLD.is_dir()
    coverage = _read("subindustry_coverage_matrix")
    foreign = coverage.loc[coverage["ticker"].isin(["PAC", "FER"])]
    assert len(foreign) == 2
    pac = foreign.loc[foreign["ticker"].eq("PAC")].iloc[0]
    fer = foreign.loc[foreign["ticker"].eq("FER")].iloc[0]
    assert pac["sec_status"] == "IFRS_ANNUAL_AND_COMPANY_Q_ANCHOR_READY"
    assert pac["quantity_status"] == "COMPANY_DISCLOSED_MONTHLY_QUANTITY_DSL_READY"
    assert fer["sec_status"] == "IFRS_ANNUAL_SHORT_HISTORY"
    assert not foreign["conditional_dcf_run"].eq(True).any()


def test_ifrs_dsl_pac_quantity_and_ifric12_bridge() -> None:
    gate = _read("industrials_v8_gate").iloc[0]
    assert gate["ifrs_companies_ready"] == 2
    assert gate["ifrs_20f_6k_filings"] == 325
    assert gate["compiled_parser_rules"] == 2
    assert gate["parser_emitted_facts"] == 68
    assert gate["parser_failures"] == 0

    monthly = pd.read_csv(SILVER / "pac_monthly_passenger_traffic.csv")
    assert len(monthly) == 63
    assert monthly["period"].min() == "2021-05"
    assert monthly["period"].max() == "2026-07"
    assert monthly["terminal_passengers_thousands"].between(0, 10_000).all()
    assert monthly["historical_pit_input"].all()
    assert monthly["rule_id"].eq("airport.monthly_terminal_passengers").all()

    annual = pd.read_csv(SILVER / "ifrs_annual_financial_history.csv")
    pac_2024 = annual.loc[
        annual["ticker"].eq("PAC") & annual["fiscal_year"].eq(2024)
    ].iloc[0]
    assert pac_2024["capex_local"] == pytest.approx(6_832_541_000.0)
    assert pac_2024["gaap_operating_margin_pct"] == pytest.approx(44.774429, abs=1e-6)
    assert pac_2024["economic_operating_margin_pct"] == pytest.approx(56.197214, abs=1e-6)
    assert pd.isna(pac_2024["research_development_local"])
    assert not bool(pac_2024["innovation_reinvestment_claim_allowed"])
    assert not bool(pac_2024["terminal_input_allowed"])
