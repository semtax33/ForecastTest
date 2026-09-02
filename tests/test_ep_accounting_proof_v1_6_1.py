from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.research.ep_v161.benchmark import verify_v161


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_6_1_research"


def test_v1_6_1_frozen_research_manifest_verifies() -> None:
    manifest = verify_v161(ROOT)
    assert manifest["research_frozen"] is True
    assert manifest["accounting_proof_frozen"] is True
    assert manifest["reserve_chain_ready_tickers"] == 9
    assert manifest["core_accounting_pass_tickers"] == 3
    assert manifest["mna_normalization_diagnostic_implemented"] is True
    assert manifest["mna_normalization_validated"] is False
    assert manifest["terminal_anchor_ready"] == 0
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
    assert manifest["verified_files"] == 17
    assert manifest["verified_source_dependencies"] == 4


def test_ar_composite_lifting_cost_proves_transport_tax_scope_without_double_count() -> None:
    proof = pd.read_csv(OUTPUT / "ar_composite_cost_scope_proof.csv")
    assert len(proof) >= 3
    assert proof["transport_tax_already_in_composite_lifting_cost"].all()
    assert (~proof["separate_transport_tax_addition_allowed"]).all()
    assert proof["composite_identity_error_pct"].le(2.0).all()
    assert proof["source_sha256"].str.len().eq(64).all()


def test_cnx_hedge_presentation_is_authoritatively_reconciled() -> None:
    proof = pd.read_csv(OUTPUT / "cnx_hedge_accounting_reconciliation.csv")
    assert len(proof) >= 3
    assert proof["derivative_separate_from_production_revenue"].all()
    assert proof["realized_plus_unrealized_identity_proven"].all()
    assert proof["cash_sales_equals_production_revenue_plus_realized_hedge"].all()
    assert proof["income_statement_derivative_matches_reconciliation"].all()
    assert proof["hedge_accounting_semantics"].str.contains(
        "REALIZED_AND_UNREALIZED_PRESENTED_SEPARATELY"
    ).all()


def test_fang_2025_gap_is_attributed_without_dropping_gaap_impairment() -> None:
    proof = pd.read_csv(OUTPUT / "fang_margin_gap_attribution.csv").set_index("year")
    row = proof.loc[2025]
    assert np.isclose(row["impairment_usd_millions"], 3652.0)
    assert bool(row["tax_and_transport_already_in_composite_lifting_cost"])
    assert abs(row["residual_after_primary_attribution_pct_points"]) <= 5.0
    assert row["margin_gap_classification"] == (
        "EXPLAINED_IMPAIRMENT_PLUS_DUPLICATE_COMPOSITE_COST_SCOPE"
    )
    assert bool(row["derivative_in_operating_income"]) is False


def test_core_accounting_freeze_target_reaches_at_least_two_of_three() -> None:
    summary = pd.read_csv(OUTPUT / "core_accounting_proof_summary.csv").set_index("ticker")
    assert int(summary["accounting_perimeter_pass"].sum()) >= 2
    assert bool(summary.loc["AR", "scope_identity_proven"])
    assert bool(summary.loc["CNX", "hedge_presentation_proven"])
    assert bool(summary.loc["FANG", "special_case_classified"])


def test_mna_normalized_bridge_is_diagnostic_and_not_overclaimed() -> None:
    panel = pd.read_csv(OUTPUT / "annual_mna_normalized_capital_bridge.csv")
    summary = pd.read_csv(OUTPUT / "mna_normalized_roic_summary.csv")
    expected = (
        panel["raw_delta_invested_capital_usd"]
        - panel["acquisition_cash_proxy_usd"]
        + panel["divestiture_cash_proxy_usd"]
    )
    assert np.allclose(
        panel["mna_cash_normalized_delta_invested_capital_usd"], expected, equal_nan=True
    )
    assert summary["diagnostic_implemented"].all()
    assert (~summary["mna_normalization_validated"]).all()
    assert panel["limitations"].str.contains("ACQUIRED_NOPAT_NOT_REMOVED").all()


def test_freeze_gate_and_production_terminal_locks() -> None:
    gate = pd.read_csv(OUTPUT / "v1_6_1_freeze_gate.csv").iloc[0]
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert bool(gate["reserve_coverage_8_of_14"])
    assert bool(gate["all_group_coverage"])
    assert bool(gate["core_accounting_min_2_of_3"])
    assert bool(gate["mna_normalization_diagnostic_implemented"])
    assert bool(gate["v1_6_1_research_freeze_eligible"])
    assert bool(gate["terminal_anchor_replacement_allowed"]) is False
    assert bool(gate["production_promoted"]) is False
    assert gate["live_matched_observations"] == "0/20"
    assert metadata["v15_manifest_sha256"] == verify_v15(ROOT)["manifest_sha256"]
