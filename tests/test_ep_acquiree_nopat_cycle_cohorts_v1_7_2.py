from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_2_research"


def _nopat() -> pd.DataFrame:
    return pd.read_csv(
        OUTPUT / "acquiree_net_income_to_nopat_reconciliation.csv"
    ).set_index("ticker")


def test_v172_preserves_parent_snapshots_and_model_locks() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    gate = pd.read_csv(OUTPUT / "v1_7_2_gate.csv").iloc[0]
    assert metadata["v1_6_1_manifest_sha256"] == verify_v161(ROOT)["manifest_sha256"]
    assert metadata["frozen_v1_6_1_mutated"] is False
    assert metadata["v1_7_1_parent_mutated"] is False
    assert len(metadata["v1_7_1_parent_snapshot_sha256"]) == 64
    assert not bool(gate["terminal_anchor_replacement_allowed"])
    assert not bool(gate["wacc_recalibrated"])
    assert not bool(gate["production_promoted"])
    assert gate["live_matched_observations"] == "0/20"


def test_wpx_nopat_bridge_reconciles_interest_tax_and_ownership() -> None:
    row = _nopat().loc["DVN"]
    annualized_interest = 145_000_000.0 * 366.0 / 274.0
    implied_rate = annualized_interest / 3_257_000_000.0
    tax_rate = abs(-194_000_000.0 / -961_000_000.0)
    full_year_after_tax_interest = 3_562_000_000.0 * implied_rate * (1.0 - tax_rate)
    current_after_tax_interest = full_year_after_tax_interest * 359.0 / 365.0
    assert np.isclose(row["predeal_annualized_interest_expense_usd"], annualized_interest)
    assert np.isclose(row["predeal_implied_interest_rate"], implied_rate)
    assert np.isclose(row["predeal_normalized_tax_rate"], tax_rate)
    assert np.isclose(
        row["acquiree_current_period_nopat_bridge_usd"],
        1_382_000_000.0 + current_after_tax_interest,
    )
    assert np.isclose(
        row["acquiree_full_year_normalized_nopat_bridge_usd"],
        row["full_year_normalized_acquiree_net_income_usd"]
        + full_year_after_tax_interest,
    )


def test_concho_nopat_bridge_uses_inferred_pretax_and_retains_nonoperating_evidence() -> None:
    row = _nopat().loc["COP"]
    inferred_pretax = -9_773_000_000.0 + -1_673_000_000.0
    expected_tax_rate = abs(-1_673_000_000.0 / inferred_pretax)
    assert np.isnan(row["predeal_ytd_pretax_income_usd"])
    assert np.isclose(row["predeal_ytd_pretax_income_for_tax_rate_usd"], inferred_pretax)
    assert row["predeal_normalized_tax_rate_source"] == "INFERRED_NET_INCOME_PLUS_TAX"
    assert np.isclose(row["predeal_normalized_tax_rate"], expected_tax_rate)
    assert np.isclose(row["predeal_ytd_nonoperating_income_expense_usd"], -208_000_000.0)
    assert not bool(row["nonoperating_adjustment_applied"])
    assert row["nonoperating_adjustment_status"].startswith("EVIDENCE_CAPTURED_NOT_APPLIED")


def test_two_interest_bridged_nopat_events_improve_asset_return_without_direct_claim() -> None:
    nopat = _nopat()
    assert set(nopat.index[nopat["acquiree_nopat_bridge_ready"]]) == {"COP", "DVN"}
    assert (~nopat["acquiree_nopat_directly_disclosed"]).all()
    assert np.isclose(nopat.loc["DVN", "acquiree_nopat_return_proxy_pct"], 18.198379, atol=1e-5)
    assert np.isclose(nopat.loc["COP", "acquiree_nopat_return_proxy_pct"], 14.905298, atol=1e-5)
    assert nopat.loc["DVN", "acquiree_nopat_return_proxy_pct"] > 16.2439
    assert nopat.loc["COP", "acquiree_nopat_return_proxy_pct"] > 13.8937
    assert nopat.loc["DVN", "source_evidence_bundle_sha256"].__len__() == 64
    assert nopat.loc["COP", "source_evidence_bundle_sha256"].__len__() == 64


def test_private_target_financing_scope_fails_closed() -> None:
    nopat = _nopat()
    for ticker in ("EOG", "FANG"):
        row = nopat.loc[ticker]
        assert not bool(row["acquiree_nopat_bridge_ready"])
        assert np.isnan(row["acquiree_full_year_normalized_nopat_bridge_usd"])
        assert row["acquiree_nopat_bridge_status"] == (
            "LOCKED_PRIVATE_TARGET_FINANCING_AND_NONOPERATING_SCOPE_UNAVAILABLE"
        )


def test_cycle_reference_uses_independent_component_costs_where_proven() -> None:
    reference = pd.read_csv(OUTPUT / "cycle_normalization_reference.csv").set_index(
        "ticker"
    )
    dvn = reference.loc["DVN"]
    fang = reference.loc["FANG"]
    eog = reference.loc["EOG"]
    assert bool(dvn["independent_complete_unit_cost_scope"])
    assert int(dvn["normalized_unit_cost_observations"]) >= 3
    assert dvn["cycle_normalization_route"] == (
        "V13_NORMALIZED_COMMODITY_PRICE_PLUS_SEC_COMPONENT_UNIT_COST"
    )
    assert bool(fang["independent_complete_unit_cost_scope"])
    assert fang["cycle_normalization_route"] == (
        "V14_BASIS_ADJUSTED_PRICE_PLUS_V161_ACCOUNTING_PROVEN_COMPONENT_UNIT_COST"
    )
    assert not bool(eog["independent_complete_unit_cost_scope"])
    for row in (dvn, fang, eog):
        assert np.isclose(
            row["normalized_pre_tax_unit_margin_per_boe"],
            row["normalized_price_per_boe"] - row["normalized_unit_cost_per_boe"],
        )


def test_dvn_2020_production_supplement_is_sec_proven() -> None:
    production = pd.read_csv(OUTPUT / "cycle_production_evidence.csv")
    row = production.loc[
        production["ticker"].eq("DVN") & production["year"].eq(2020)
    ].iloc[0]
    assert np.isclose(row["production_mboe"], 122_000.0)
    assert bool(row["production_evidence_proven"])
    assert row["production_source_semantics"] == (
        "SEC_RESERVE_TABLE_ROUNDED_COMBINED_PRODUCTION"
    )
    assert len(row["source_record_sha256"]) == 64


def test_event_year_cycle_nopat_removes_acquiree_production_proxy() -> None:
    panel = pd.read_csv(OUTPUT / "cycle_normalized_company_year_panel.csv")
    for ticker, year in (("DVN", 2021), ("EOG", 2025), ("FANG", 2024)):
        row = panel.loc[panel["ticker"].eq(ticker) & panel["year"].eq(year)].iloc[0]
        assert np.isclose(
            row["organic_cycle_normalized_delta_nopat_proxy_usd"],
            row["company_cycle_normalized_delta_nopat_usd"]
            - row["acquiree_cycle_normalized_nopat_same_period_proxy_usd"],
        )
        assert row["acquiree_production_proxy_status"].startswith(
            "REVENUE_DIVIDED_BY_BUYER"
        )
    fang = panel.loc[panel["ticker"].eq("FANG") & panel["year"].eq(2024)].iloc[0]
    assert not bool(fang["cycle_normalized_annual_scope_complete"])


def test_reported_event_nopat_bridge_subtracts_after_tax_interest() -> None:
    cohorts = pd.read_csv(OUTPUT / "reported_vs_cycle_normalized_deal_cohorts.csv")
    dvn = cohorts.loc[
        cohorts["ticker"].eq("DVN") & cohorts["cohort_offset"].eq(0)
    ].iloc[0]
    assert np.isclose(
        dvn["reported_organic_nopat_bridge_usd"],
        dvn["v171_net_income_based_organic_numerator_proxy_usd"]
        - dvn["acquiree_after_tax_interest_adjustment_usd"],
    )
    assert bool(dvn["reported_organic_nopat_annual_scope_complete"])


def test_cop_and_fang_contaminated_event_years_keep_explicit_scope_locks() -> None:
    cohorts = pd.read_csv(OUTPUT / "reported_vs_cycle_normalized_deal_cohorts.csv")
    for ticker in ("COP", "FANG"):
        event = cohorts.loc[
            cohorts["ticker"].eq(ticker) & cohorts["cohort_offset"].eq(0)
        ].iloc[0]
        assert not bool(event["parent_annual_scope_complete"])
        assert event["reported_organic_nopat_bridge_status"].startswith(
            "LOCKED_COMPANY_YEAR_MNA_SCOPE"
        )
        assert event["cycle_normalization_status"].startswith(
            "LOCKED_COMPANY_YEAR_MNA_SCOPE"
        ) or event["cycle_normalization_status"] == (
            "LOCKED_MISSING_PRODUCTION_OR_NORMALIZED_ECONOMICS"
        )


def test_dvn_complete_cohort_separates_reported_and_cycle_normalized_roic() -> None:
    cohorts = pd.read_csv(OUTPUT / "reported_vs_cycle_normalized_deal_cohorts.csv")
    mature = cohorts.loc[
        cohorts["ticker"].eq("DVN") & cohorts["cohort_offset"].eq(2)
    ].iloc[0]
    assert bool(mature["reported_nopat_cohort_complete"])
    assert bool(mature["cycle_normalized_cohort_complete"])
    assert np.isclose(
        mature["reported_cumulative_organic_nopat_roic_pct"], 139.394105, atol=1e-5
    )
    assert np.isclose(
        mature["cycle_normalized_cumulative_organic_roic_proxy_pct"],
        -2.175785,
        atol=1e-5,
    )
    assert not bool(mature["organic_company_roic_validated"])


def test_eog_cycle_view_is_available_while_reported_nopat_stays_locked() -> None:
    cohorts = pd.read_csv(OUTPUT / "reported_vs_cycle_normalized_deal_cohorts.csv")
    eog = cohorts.loc[cohorts["ticker"].eq("EOG")].iloc[0]
    assert not bool(eog["reported_organic_nopat_annual_scope_complete"])
    assert np.isnan(eog["reported_organic_nopat_roic_pct"])
    assert bool(eog["cycle_normalized_annual_scope_complete"])
    assert np.isclose(eog["cycle_normalized_organic_roic_proxy_pct"], 14.232028, atol=1e-5)
    assert not bool(eog["cycle_normalized_cohort_complete"])


def test_v172_research_gate_passes_without_false_freeze_or_validation() -> None:
    gate = pd.read_csv(OUTPUT / "v1_7_2_gate.csv").iloc[0]
    assert int(gate["direct_acquiree_nopat_events"]) == 0
    assert int(gate["bridged_acquiree_nopat_events"]) == 2
    assert int(gate["complete_3y_reported_nopat_cohort_tickers"]) == 1
    assert int(gate["cycle_normalized_annual_tickers"]) == 3
    assert int(gate["complete_3y_cycle_normalized_cohort_tickers"]) == 1
    assert int(gate["validated_organic_roic_tickers"]) == 0
    assert bool(gate["v1_7_2_research_gate"])
    assert not bool(gate["v1_7_2_research_freeze_eligible"])
    assert gate["development_status"] == "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
