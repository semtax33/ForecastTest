from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import MANIFEST, verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_1"


def test_v1_1_audit_passes_but_production_remains_fail_closed() -> None:
    status = pd.read_csv(OUTPUT / "v1_1_completion_status.csv").set_index(
        "status_dimension"
    )
    assert status.loc["V1_1_CODE", "status"] == "COMPLETE"
    assert bool(status.loc["V1_1_CODE", "passed"])
    assert status.loc["V1_1_RESEARCH", "status"] == "COMPLETE"
    assert bool(status.loc["V1_1_RESEARCH", "passed"])
    assert status.loc["V1_1_PRODUCTION", "status"] == (
        "NOT_PROMOTED_LIVE_0_OF_20"
    )
    assert not bool(status.loc["V1_1_PRODUCTION", "passed"])
    assert pd.read_csv(OUTPUT / "v1_1_requirement_audit.csv")["passed"].all()

    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["parent_v1_0_manifest_verified"] is True
    assert metadata["freeze_eligible"] is True
    assert metadata["v1_1_production_promoted"] is False
    assert metadata["live_matched_observations"] == "0/20"


def test_boundary_gate_exposes_raw_clipped_bounds_and_improves_parent() -> None:
    detail = pd.read_csv(OUTPUT / "scenario_boundary_detail.csv")
    summary = pd.read_csv(OUTPUT / "scenario_boundary_summary.csv")
    parent = pd.read_csv(OUTPUT / "parent_v1_0_boundary_summary.csv")
    required = {
        "raw_value", "clipped_value", "lower_bound", "upper_bound",
        "hit_lower_bound", "hit_upper_bound", "boundary_hit",
        "same_boundary_all_three_scenarios",
    }
    assert required.issubset(detail.columns)
    assert len(detail) == 26 * 3 * 6
    assert detail[["raw_value", "clipped_value", "lower_bound", "upper_bound"]].notna().all().all()
    assert summary["boundary_hit_pct"].le(25.0).all()
    assert summary["freeze_eligible"].all()
    assert not detail["same_boundary_all_three_scenarios"].any()
    assert parent["boundary_status"].eq("RED_FREEZE_PROHIBITED").any()
    assert parent["all_scenarios_same_boundary_tickers"].gt(0).any()


def test_default_weights_and_roic_semantics_are_not_mislabeled() -> None:
    assumptions = pd.read_csv(OUTPUT / "scenario_assumptions.csv")
    assert assumptions["scenario_weight_source"].eq(
        "DEFAULT_SCENARIO_WEIGHT_NOT_EMPIRICAL_PROBABILITY"
    ).all()
    assert np.allclose(
        assumptions.groupby("ticker")["scenario_weight"].sum().to_numpy(), 1.0
    )
    assert assumptions["story_validation_class"].isin(
        ["POSSIBLE", "PLAUSIBLE", "PROBABLE"]
    ).all()
    assert {
        "historical_incremental_roic_pct", "forecast_normalized_roic_pct"
    }.issubset(assumptions.columns)
    assert (~assumptions["fixed_ratio_used"]).all()


def test_forward_fcff_and_growth_reinvestment_roic_identities_hold() -> None:
    projections = pd.read_csv(OUTPUT / "dcf_projections.csv")
    sanity = pd.read_csv(OUTPUT / "forward_fcff_sanity.csv")
    assert len(projections) == 26 * 3 * 5
    assert np.allclose(
        projections["nopat_usd"] - projections["reinvestment_usd"],
        projections["fcff_usd"],
        rtol=1e-12,
        atol=1e-3,
    )
    assert sanity["fcff_identity_error_usd"].abs().le(1e-3).all()
    assert sanity["growth_reinvestment_roic_gap_pct_points"].abs().le(
        1e-6
    ).all()
    assert sanity["reinvestment_plausibility_status"].notna().all()


def test_reverse_dcf_roundtrip_is_bidirectional_and_fail_closed() -> None:
    roundtrip = pd.read_csv(OUTPUT / "reverse_dcf_roundtrip.csv")
    reverse = pd.read_csv(OUTPUT / "reverse_dcf_expectations.csv")
    test_a = roundtrip.loc[roundtrip["test"].eq("A_FORWARD_BASE_TO_REVERSE")]
    test_b = roundtrip.loc[roundtrip["test"].eq("B_MARKET_REVERSE_TO_FORWARD")]
    solved_b = test_b.loc[test_b["solver_status"].eq("SOLVED")]
    assert len(test_a) == 26 * 3
    assert test_a["solver_status"].eq("SOLVED").all()
    assert test_a["assumption_error"].abs().le(0.01).all()
    assert test_a["forward_roundtrip_error_pct"].abs().le(0.10).all()
    assert len(solved_b) > 0
    assert solved_b["forward_roundtrip_error_pct"].abs().le(0.10).all()
    assert test_b["solver_status"].isin(
        ["SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"]
    ).all()
    for variable in ("growth", "operating_margin", "roic"):
        unbracketed = reverse[f"{variable}_solver_status"].eq(
            "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
        )
        assert reverse.loc[
            unbracketed, f"market_implied_{variable}_pct"
        ].isna().all()


def test_ev_to_common_equity_perimeter_reconciles_without_double_counting() -> None:
    claims = pd.read_csv(OUTPUT / "capital_claims_reconciliation.csv")
    assert claims["market_cap_reconciliation_error_usd"].abs().le(1e-3).all()
    assert claims["ev_equity_reconciliation_error_usd"].abs().le(1e-3).all()
    assert claims["noncontrolling_interest_usd"].gt(0).any()
    assert claims["debt_double_count_adjustment_usd"].abs().gt(0).any()
    assert claims["lease_valuation_treatment"].eq(
        "DISCLOSED_NOT_ADDED_TO_EV_TO_AVOID_LEASE_EXPENSE_DOUBLE_COUNT"
    ).all()
    sm = claims.loc[claims["ticker"].eq("SM")].iloc[0]
    assert sm["adjusted_total_debt_usd"] > 0
    assert sm["debt_semantics_method"] == (
        "PIT_LAST_DISCLOSED_DEBT_CARRY_FORWARD_TAXONOMY_GAP"
    )


def test_unsafe_psx_capex_semantics_are_rejected_and_replaced_prior_only() -> None:
    audit = pd.read_csv(OUTPUT / "capex_semantics_audit.csv")
    psx = audit.loc[audit["ticker"].eq("PSX")]
    assert not psx.empty
    assert psx["v1_0_semantic_status"].eq(
        "REJECTED_NET_PAYMENTS_PROCEEDS_CONCEPT_AS_GROSS_CAPEX"
    ).all()
    resolved = psx.loc[psx["v1_1_cash_capex_imputed"]]
    unresolved = psx.loc[~psx["v1_1_cash_capex_imputed"]]
    assert not resolved.empty
    assert resolved["v1_1_cash_capex_method"].str.startswith(
        "PRIOR_ONLY_REFINING_PEER_MEDIAN_"
    ).all()
    assert resolved["v1_1_semantic_status"].eq(
        "REPLACED_WITH_PRIOR_ONLY_SUBINDUSTRY_DISTRIBUTION"
    ).all()
    assert unresolved["v1_1_cash_capex_usd"].isna().all()
    assert unresolved["v1_1_semantic_status"].eq(
        "UNRESOLVED_EXCLUDED_FROM_COMPLETE_HISTORY"
    ).all()


def test_terminal_dependence_and_expectations_outliers_are_exposed() -> None:
    terminal = pd.read_csv(OUTPUT / "terminal_value_audit.csv")
    skew = pd.read_csv(OUTPUT / "subindustry_expectations_skew.csv")
    outliers = pd.read_csv(OUTPUT / "expectations_gap_outliers.csv")
    assert terminal["terminal_dependence_status"].isin([
        "NORMAL", "TERMINAL_DEPENDENCE_WARNING", "HIGH_TERMINAL_DEPENDENCE",
        "UNSTABLE_OR_NONPOSITIVE_ENTERPRISE_VALUE",
    ]).all()
    assert terminal["terminal_dependence_status"].eq(
        "HIGH_TERMINAL_DEPENDENCE"
    ).any()
    ep = skew.loc[skew["subindustry"].eq("ep")].iloc[0]
    assert bool(ep["systematic_sector_skew_flag"])
    assert ep["median_probability_weighted_value_gap_pct"] > 50.0
    assert outliers.loc[outliers["subindustry"].eq("ep"), "expectations_gap_outlier"].any()


def test_historical_fcff_sanity_keeps_capex_nonnegative_and_visible() -> None:
    historical = pd.read_csv(OUTPUT / "historical_fcff_sanity.csv")
    summary = pd.read_csv(OUTPUT / "historical_fcff_subindustry_summary.csv")
    assert len(historical) == 26
    assert historical["cash_capex_sign_status"].eq("PASS_NONNEGATIVE").all()
    assert historical["ttm_cash_capex_usd"].ge(0).all()
    assert summary["subindustry"].nunique() == 5
    assert summary["median_cash_conversion_adjustment_usd"].notna().all()


@pytest.mark.skipif(not (ROOT / MANIFEST).exists(), reason="freeze not created yet")
def test_energy_v1_1_and_immutable_parent_manifests_verify() -> None:
    parent = verify_v1(ROOT)
    manifest = verify_v11(ROOT)
    assert parent["immutable"] is True
    assert manifest["immutable"] is True
    assert manifest["sanity_audit_passed"] is True
    assert manifest["research_frozen"] is True
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
