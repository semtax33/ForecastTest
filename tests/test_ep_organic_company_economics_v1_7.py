from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_research"


def test_v1_7_preserves_frozen_v1_6_1_and_all_model_locks() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    gate = pd.read_csv(OUTPUT / "v1_7_gate.csv").iloc[0]
    assert metadata["v1_6_1_manifest_sha256"] == verify_v161(ROOT)["manifest_sha256"]
    assert metadata["frozen_parent_mutated"] is False
    assert bool(gate["terminal_anchor_replacement_allowed"]) is False
    assert bool(gate["wacc_recalibrated"]) is False
    assert bool(gate["production_promoted"]) is False
    assert gate["live_matched_observations"] == "0/20"


def test_core_event_classification_is_proven_from_sec_notes() -> None:
    events = pd.read_csv(
        OUTPUT / "mna_event_capital_and_numerator_evidence.csv"
    ).set_index("ticker")
    assert set(events.index) == {"FANG", "EOG", "CNX"}
    assert events["classification_phrase_proven"].all()
    assert events["source_form"].eq("10-K").all()
    assert events["source_evidence_bundle_sha256"].str.len().eq(64).all()
    assert events["point_in_time_proven"].all()
    assert events.loc["CNX", "event_type"] == "asset_acquisition"


def test_fang_endeavor_numerator_and_noncash_consideration_are_explicit() -> None:
    events = pd.read_csv(
        OUTPUT / "mna_event_capital_and_numerator_evidence.csv"
    ).set_index("ticker")
    fang = events.loc["FANG"]
    assert np.isclose(fang["acquiree_revenue_since_close_usd"], 1_800_000_000.0)
    assert np.isclose(fang["acquiree_net_income_since_close_usd"], 459_000_000.0)
    assert np.isclose(fang["recognized_net_assets_usd"], 27_420_000_000.0)
    assert np.isclose(fang["noncash_equity_consideration_usd"], 20_110_000_000.0)
    assert fang["acquired_numerator_semantics"].endswith("NOT_NOPAT")
    assert bool(fang["acquired_nopat_directly_disclosed"]) is False


def test_eog_encino_has_full_ppa_capital_proxy_and_reconciles_formula() -> None:
    events = pd.read_csv(
        OUTPUT / "mna_event_capital_and_numerator_evidence.csv"
    ).set_index("ticker")
    eog = events.loc["EOG"]
    expected_capital = 4_471_000_000.0 + 1_266_000_000.0 - 20_000_000.0
    assert np.isclose(eog["acquired_invested_capital_proxy_usd"], expected_capital)
    assert eog["acquired_capital_proxy_semantics"] == (
        "PPA_NET_ASSETS_PLUS_ASSUMED_DEBT_MINUS_ACQUIRED_CASH"
    )
    annual = pd.read_csv(OUTPUT / "annual_organic_company_economics.csv")
    row = annual.loc[annual["ticker"].eq("EOG") & annual["year"].eq(2025)].iloc[0]
    expected_denominator = (
        row["raw_delta_invested_capital_usd"]
        - row["acquired_capital_adjustment_usd"]
        + row["divested_capital_adjustment_usd"]
    )
    expected_numerator = (
        row["raw_delta_nopat_usd"]
        - row["acquired_after_tax_contribution_adjustment_usd"]
        + row["transaction_cost_after_tax_addback_usd"]
    )
    assert np.isclose(row["organic_delta_invested_capital_proxy_usd"], expected_denominator)
    assert np.isclose(row["organic_delta_nopat_after_tax_proxy_usd"], expected_numerator)
    assert bool(row["material_mna_year_proxy_ready"])


def test_material_divestiture_and_asset_acquisition_fail_closed() -> None:
    annual = pd.read_csv(OUTPUT / "annual_organic_company_economics.csv")
    fang = annual.loc[annual["ticker"].eq("FANG") & annual["year"].eq(2024)].iloc[0]
    cnx = annual.loc[annual["ticker"].eq("CNX") & annual["year"].eq(2025)].iloc[0]
    assert bool(fang["material_divestiture"])
    assert fang["organic_bridge_status"] == (
        "LOCKED_MATERIAL_DIVESTITURE_BOOK_CAPITAL_AND_NOPAT_MISSING"
    )
    assert np.isnan(fang["organic_incremental_roic_after_tax_proxy_pct"])
    assert cnx["organic_bridge_status"] == (
        "LOCKED_ASSET_ACQUISITION_CONTRIBUTION_AND_MATERIAL_DIVESTITURE_SCOPE_MISSING"
    )
    assert np.isnan(cnx["organic_incremental_roic_after_tax_proxy_pct"])


def test_purchase_accounting_step_up_and_terminal_use_remain_locked() -> None:
    events = pd.read_csv(OUTPUT / "mna_event_capital_and_numerator_evidence.csv")
    assert events["purchase_accounting_step_up_usd"].isna().all()
    assert events["purchase_accounting_step_up_status"].eq(
        "LOCKED_ACQUIREE_PREDEAL_BOOK_BASIS_NOT_IDENTIFIED"
    ).all()
    assert (~events["organic_company_roic_validated"]).all()
    assert (~events["terminal_input_allowed"]).all()


def test_v1_7_research_gate_passes_without_false_freeze_claim() -> None:
    gate = pd.read_csv(OUTPUT / "v1_7_gate.csv").iloc[0]
    assert bool(gate["v1_7_research_gate"])
    assert int(gate["classification_proven_events"]) == 3
    assert int(gate["after_tax_contribution_proxy_events"]) == 2
    assert int(gate["acquired_capital_proxy_events"]) == 3
    assert int(gate["material_mna_proxy_ready_company_years"]) >= 1
    assert int(gate["organic_company_roic_validated_tickers"]) == 0
    assert int(gate["purchase_accounting_step_up_identified_events"]) == 0
    assert bool(gate["v1_7_research_freeze_eligible"]) is False
