from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_6_research"


def test_v1_6_preserves_all_frozen_parents() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    expected = {
        "v1": verify_v1(ROOT),
        "v11": verify_v11(ROOT),
        "v12": verify_v12(ROOT),
        "v13": verify_v13(ROOT),
        "v14": verify_v14(ROOT),
        "v15": verify_v15(ROOT),
    }
    for key, manifest in expected.items():
        assert metadata[f"{key}_manifest_sha256"] == manifest["manifest_sha256"]
    assert metadata["frozen_parent_mutated"] is False
    assert metadata["v1_1_mutation_allowed"] is False


def test_reserve_coverage_meets_sector_and_group_gates_without_semantic_blending() -> None:
    gate = pd.read_csv(OUTPUT / "v16_coverage_completion_gate.csv").iloc[0]
    groups = pd.read_csv(OUTPUT / "v16_reserve_group_gate.csv").set_index("group")
    summary = pd.read_csv(OUTPUT / "v16_reserve_coverage_summary.csv").set_index("ticker")
    panel = pd.read_csv(OUTPUT / "supplemental_ir_reserve_panel.csv")
    assert int(gate["reserve_chain_ready_tickers"]) >= 8
    assert bool(gate["coverage_completion_gate"])
    assert groups.loc["oil_heavy", "ready_tickers"] >= 3
    assert groups.loc["gas_heavy", "ready_tickers"] >= 3
    assert groups.loc["mixed", "ready_tickers"] >= 2
    for ticker in ("EOG", "RRC", "DVN", "SM", "MTDR"):
        assert bool(summary.loc[ticker, "v16_reserve_chain_ready"])
    mtdr = panel.loc[panel["ticker"].eq("MTDR")]
    assert mtdr["reserve_semantics"].eq(
        "TOTAL_REPLACEMENT_INCLUDING_ACQUISITIONS_NOT_ORGANIC"
    ).all()
    assert (~summary.loc[["MTDR"], "organic_replacement_claim_allowed"]).all()


def test_supplemental_event_chains_have_independent_production_and_identity_proof() -> None:
    panel = pd.read_csv(OUTPUT / "supplemental_ir_reserve_panel.csv")
    events = panel.loc[panel["reserve_route"].eq("IR_TOTAL_PROVED_EVENT_ROLLFORWARD")]
    assert set(events["ticker"]) >= {"EOG", "RRC", "DVN", "SM"}
    accepted = events.loc[
        events["production_independently_verified"]
        & events["reserve_identity_error_ratio"].le(0.02)
    ]
    assert accepted.groupby("ticker")["year"].nunique().ge(3).all()
    assert accepted["production_verification_ratio"].between(0.95, 1.05).all()
    assert events["source_file_sha256"].str.len().eq(64).all()
    assert events["availability_date"].str.match(r"\d{4}-\d{2}-\d{2}").all()


def test_fang_actual_mix_and_transport_are_source_proven() -> None:
    actual = pd.read_csv(OUTPUT / "fang_actual_cost_mix_panel.csv")
    proof = pd.read_csv(OUTPUT / "v16_accounting_proof_summary.csv").set_index("ticker")
    assert len(actual) >= 3
    assert actual["component_identity_ratio"].between(0.99, 1.01).all()
    assert actual["transport_cost_per_boe"].gt(0).all()
    assert actual["production_tax_per_boe"].gt(0).all()
    assert bool(proof.loc["FANG", "complete_standardized_cost_scope"])
    assert bool(proof.loc["FANG", "actual_three_component_mix_ready"])
    assert proof.loc["AR", "primary_accounting_blocker"] == (
        "TRANSPORT_AND_PRODUCTION_TAX_SCOPE_NOT_PROVEN"
    )
    assert proof.loc["CNX", "primary_accounting_blocker"] == (
        "HEDGE_PRESENTATION_NOT_PROVEN"
    )


def test_three_level_roic_is_separated_and_company_level_stays_diagnostic() -> None:
    summary = pd.read_csv(OUTPUT / "three_level_roic_summary.csv")
    annual = pd.read_csv(OUTPUT / "annual_company_incremental_roic_panel.csv")
    assert summary["three_level_roic_separated"].all()
    assert (~summary["company_incremental_roic_validated"]).all()
    eligible = annual.loc[annual["company_incremental_roic_eligible"]]
    expected = eligible["delta_nopat_usd"] / eligible["delta_invested_capital_usd"] * 100.0
    assert np.allclose(eligible["company_incremental_roic_pct"], expected)
    assert eligible["delta_invested_capital_usd"].gt(0).all()
    assert eligible["delta_capital_to_prior_ratio"].gt(0.02).all()


def test_terminal_and_production_gates_remain_locked() -> None:
    terminal = pd.read_csv(OUTPUT / "terminal_candidate_gate.csv")
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert int(terminal["terminal_candidate_ready"].sum()) == 0
    assert (~terminal["terminal_anchor_replacement_allowed"]).all()
    assert metadata["terminal_anchor_replacement_allowed"] is False
    assert metadata["wacc_range_recalibrated"] is False
    assert metadata["production_promoted"] is False
    assert metadata["live_matched_observations"] == "0/20"
