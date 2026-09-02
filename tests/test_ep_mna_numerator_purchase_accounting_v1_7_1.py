from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_1_research"


def _acquisitions() -> pd.DataFrame:
    return pd.read_csv(
        OUTPUT / "acquisition_numerator_and_purchase_accounting_proof.csv"
    ).set_index("ticker")


def test_v171_preserves_parents_and_all_model_locks() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    gate = pd.read_csv(OUTPUT / "v1_7_1_gate.csv").iloc[0]
    assert metadata["v1_6_1_manifest_sha256"] == verify_v161(ROOT)["manifest_sha256"]
    assert metadata["frozen_v1_6_1_mutated"] is False
    assert metadata["v1_7_parent_mutated"] is False
    assert len(metadata["v1_7_parent_snapshot_sha256"]) == 64
    assert not bool(gate["terminal_anchor_replacement_allowed"])
    assert not bool(gate["wacc_recalibrated"])
    assert not bool(gate["production_promoted"])
    assert gate["live_matched_observations"] == "0/20"


def test_public_target_predeal_book_capital_and_step_up_are_proven() -> None:
    acquisitions = _acquisitions()
    dvn = acquisitions.loc["DVN"]
    cop = acquisitions.loc["COP"]
    dvn_book = 4_536_000_000.0 + 3_257_000_000.0 - 195_000_000.0
    cop_book = 7_787_000_000.0 + 3_856_000_000.0 - 402_000_000.0
    assert np.isclose(dvn["predeal_book_invested_capital_usd"], dvn_book)
    assert np.isclose(cop["predeal_book_invested_capital_usd"], cop_book)
    assert np.isclose(dvn["purchase_accounting_step_up_usd"], 8_650_000_000.0 - dvn_book)
    assert np.isclose(cop["purchase_accounting_step_up_usd"], 17_439_000_000.0 - cop_book)
    assert bool(dvn["predeal_filed_before_close"])
    assert bool(cop["predeal_filed_before_close"])
    assert bool(dvn["purchase_accounting_step_up_proven"])
    assert bool(cop["purchase_accounting_step_up_proven"])
    assert len(dvn["predeal_evidence_bundle_sha256"]) == 64
    assert len(cop["predeal_evidence_bundle_sha256"]) == 64


def test_private_target_step_up_fails_closed() -> None:
    acquisitions = _acquisitions()
    for ticker in ("FANG", "EOG"):
        row = acquisitions.loc[ticker]
        assert np.isnan(row["predeal_book_invested_capital_usd"])
        assert np.isnan(row["purchase_accounting_step_up_usd"])
        assert not bool(row["purchase_accounting_step_up_proven"])
        assert row["purchase_accounting_step_up_status"] == (
            "LOCKED_PRIVATE_TARGET_PREDEAL_BOOK_BASIS_UNAVAILABLE"
        )


def test_ownership_period_normalization_uses_exact_calendar_days() -> None:
    acquisitions = _acquisitions()
    expected = {
        "DVN": (359, 365, 1_382_000_000.0),
        "COP": (351, 365, 2_330_000_000.0),
        "FANG": (113, 366, 459_000_000.0),
        "EOG": (153, 365, 246_000_000.0),
    }
    for ticker, (days, year_days, reported) in expected.items():
        row = acquisitions.loc[ticker]
        assert int(row["ownership_days_in_fiscal_year"]) == days
        assert int(row["fiscal_year_days"]) == year_days
        assert np.isclose(row["ownership_fraction"], days / year_days)
        assert np.isclose(
            row["full_year_normalized_acquiree_net_income_usd"],
            reported / (days / year_days),
        )
        assert row["ownership_normalization_status"].endswith("NOT_NOPAT")


def test_same_period_bridge_does_not_subtract_full_year_normalized_income() -> None:
    bridge = pd.read_csv(
        OUTPUT / "company_year_mna_normalized_bridge_v1_7_1.csv"
    ).set_index("ticker")
    eog = bridge.loc["EOG"]
    expected = (
        eog["raw_delta_nopat_usd"]
        - eog["acquiree_net_income_since_close_usd"]
        + eog["deal_cost_after_tax_addback_usd"]
    )
    wrong_full_year_mix = (
        eog["raw_delta_nopat_usd"]
        - eog["full_year_normalized_acquiree_net_income_usd"]
        + eog["deal_cost_after_tax_addback_usd"]
    )
    assert np.isclose(eog["organic_delta_nopat_same_period_proxy_usd"], expected)
    assert not np.isclose(
        eog["organic_delta_nopat_same_period_proxy_usd"], wrong_full_year_mix
    )
    assert np.isclose(
        eog["organic_delta_invested_capital_v171_proxy_usd"],
        7_362_000_000.0 - 5_717_000_000.0,
    )
    assert bool(eog["same_period_vs_full_year_numerator_separated"])


def test_two_material_company_years_are_fully_bridged_without_validation_claim() -> None:
    bridge = pd.read_csv(
        OUTPUT / "company_year_mna_normalized_bridge_v1_7_1.csv"
    ).set_index("ticker")
    assert set(bridge.index[bridge["company_year_mna_scope_fully_bridged"]]) == {
        "DVN",
        "EOG",
    }
    assert bridge.loc["DVN", "company_year_bridge_status"] == (
        "FULL_MNA_SCOPE_BRIDGE_NONPOSITIVE_OR_SMALL_ORGANIC_DENOMINATOR"
    )
    assert bridge.loc["EOG", "company_year_bridge_status"] == (
        "DIAGNOSTIC_FULL_MNA_SCOPE_AFTER_TAX_PROXY_NOT_NOPAT"
    )
    assert (~bridge["organic_company_roic_validated"]).all()
    assert (~bridge["terminal_input_allowed"]).all()


def test_cop_indonesia_divestiture_capital_and_earnings_are_reconciled() -> None:
    proof = pd.read_csv(
        OUTPUT / "divestiture_capital_and_earnings_proof.csv"
    ).iloc[0]
    assert proof["ticker"] == "COP"
    assert proof["event_close_period"] == "2022-03"
    assert np.isclose(proof["net_proceeds_usd"], 731_000_000.0)
    assert np.isclose(proof["divested_book_invested_capital_usd"], 200_000_000.0)
    assert np.isclose(proof["pre_tax_operating_contribution_usd"], 138_000_000.0)
    assert np.isclose(
        proof["divested_after_tax_operating_contribution_proxy_usd"], 89_700_000.0
    )
    assert bool(proof["classification_phrase_proven"])
    assert bool(proof["numeric_values_reconciled_to_disclosure"])
    assert not bool(proof["divested_nopat_directly_disclosed"])
    assert len(proof["source_disclosure_record_sha256"]) == 64


def test_dvn_has_one_complete_but_unvalidated_three_year_cohort() -> None:
    cohorts = pd.read_csv(OUTPUT / "deal_year_t_plus_2_roic_cohorts.csv")
    dvn = cohorts.loc[cohorts["ticker"].eq("DVN")].sort_values("cohort_offset")
    mature = dvn.loc[dvn["cohort_offset"].eq(2)].iloc[0]
    assert len(dvn) == 3
    assert bool(mature["cohort_window_complete"])
    assert not bool(mature["cohort_validated"])
    numerator = dvn["annual_organic_delta_nopat_after_tax_proxy_usd"].sum()
    denominator = dvn["annual_organic_delta_invested_capital_proxy_usd"].sum()
    assert np.isclose(
        mature["cumulative_organic_incremental_roic_proxy_pct"],
        numerator / denominator * 100.0,
    )
    assert cohorts.loc[
        cohorts["cohort_window_complete"], "ticker"
    ].nunique() == 1


def test_v171_research_gate_passes_but_freeze_remains_deferred() -> None:
    gate = pd.read_csv(OUTPUT / "v1_7_1_gate.csv").iloc[0]
    assert int(gate["acquiree_numerator_normalized_events"]) == 4
    assert int(gate["purchase_accounting_step_up_proven_events"]) == 2
    assert int(gate["divestiture_capital_and_earnings_proxy_proven_events"]) == 1
    assert int(gate["material_mna_fully_bridged_company_years"]) == 2
    assert int(gate["validated_organic_roic_tickers"]) == 0
    assert int(gate["complete_multi_year_roic_cohort_tickers"]) == 1
    assert bool(gate["v1_7_1_research_gate"])
    assert not bool(gate["v1_7_1_research_freeze_eligible"])
    assert gate["development_status"] == "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
