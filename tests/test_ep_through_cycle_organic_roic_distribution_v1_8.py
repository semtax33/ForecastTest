from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v174.benchmark import verify_v174
from energy_nowcast.research.ep_v18.distribution import _classify_width
from energy_nowcast.research.ep_v18.gate import build_v18_gate


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_8_research"
PARENT_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_4_research"
def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_v18_preserves_frozen_v174_and_all_model_locks() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    parent = verify_v174(ROOT)
    assert len(parent["manifest_sha256"]) == 64
    assert metadata["v1_7_4_parent_manifest_sha256"] == parent["manifest_sha256"]
    assert metadata["v1_7_4_parent_mutated"] is False
    assert metadata["normal_roic_claimed"] is False
    assert metadata["terminal_anchor_replacement_allowed"] is False
    assert metadata["wacc_recalibrated"] is False
    assert metadata["production_promoted"] is False
    assert metadata["live_matched_observations"] == "0/20"


def test_range_width_policy_has_exact_predeclared_boundaries() -> None:
    policy = pd.read_csv(ROOT / "configs" / "ep_v18_distribution_policy.csv")
    assert list(policy["range_category"]) == [
        "STRONG",
        "USABLE_RESEARCH",
        "TOO_UNCERTAIN_FOR_TERMINAL",
    ]
    assert _classify_width(14.999, policy)["range_category"] == "STRONG"
    assert _classify_width(15.0, policy)["range_category"] == "USABLE_RESEARCH"
    assert _classify_width(29.999, policy)["range_category"] == "USABLE_RESEARCH"
    assert (
        _classify_width(30.0, policy)["range_category"]
        == "TOO_UNCERTAIN_FOR_TERMINAL"
    )
    assert np.allclose(policy["research_weight"], [1.0, 0.75, 0.25])
    assert not policy["terminal_input_allowed"].any()


def test_gas_cohort_selection_is_deterministic_and_outcome_blind() -> None:
    audit = _csv("gas_heavy_candidate_audit")
    selected = audit.loc[audit["selected_for_v18"]]
    assert len(selected) == 1
    row = selected.iloc[0]
    assert row["ticker"] == "AR"
    assert int(row["window_start_year"]) == 2022
    assert int(row["window_end_year"]) == 2024
    assert bool(row["four_year_direct_unit_evidence"])
    assert bool(row["capital_transaction_perimeter_clean"])
    assert bool(row["reserve_transaction_perimeter_clean"])
    assert bool(row["reported_nopat_complete"])
    assert bool(row["window_eligible"])
    assert np.isclose(row["cumulative_organic_invested_capital_usd"], 526_920_000)
    assert np.isclose(row["denominator_threshold_usd"], 163_830_720)
    assert not audit["outcome_values_used_for_selection"].any()


def test_more_recent_ar_window_fails_closed_on_reserve_event() -> None:
    audit = _csv("gas_heavy_candidate_audit")
    row = audit.loc[
        audit["ticker"].eq("AR")
        & audit["window_start_year"].eq(2023)
        & audit["window_end_year"].eq(2025)
    ].iloc[0]
    assert row["reserve_event_max_ratio"] > row[
        "reserve_event_materiality_threshold"
    ]
    assert not bool(row["reserve_transaction_perimeter_clean"])
    assert not bool(row["window_eligible"])
    assert "MATERIAL_RESERVE_PURCHASE_OR_SALE" in row["selection_status"]


def test_ar_direct_segment_sources_are_fully_verified() -> None:
    evidence = _csv("ar_segment_annual_evidence")
    assert list(evidence["year"]) == [2021, 2022, 2023, 2024]
    assert set(evidence["source_form"]) == {"10-K"}
    assert evidence["source_cells_fully_verified"].all()
    assert evidence["segment_label_phrase_proven"].all()
    assert int(evidence["source_cell_checks"].sum()) == 28
    assert int(evidence["source_cell_checks_passed"].sum()) == 28
    assert evidence["source_evidence_bundle_sha256"].str.len().eq(64).all()
    assert set(evidence["selected_ep_segment_dimh"]) == {
        "0xbfcc26f79e52fb34d485be40058529a5"
    }


def test_ar_segment_and_normalization_attribution_identities_close() -> None:
    evidence = _csv("ar_segment_annual_evidence")
    recomputed = (
        evidence["segment_revenue_usd"]
        - evidence["segment_cost_and_expense_usd"]
        - evidence["segment_operating_income_usd"]
    )
    assert np.allclose(recomputed, 0.0, atol=1.0)
    assert evidence["segment_accounting_identity_error_usd"].abs().le(1.0).all()
    assert (
        evidence["normalization_attribution_identity_error_usd"]
        .abs()
        .le(1.0)
        .all()
    )
    assert evidence["normalization_attribution_complete"].all()
    assert set(evidence["normalization_confidence_grade"]) == {"A"}
    assert not evidence["terminal_input_allowed"].any()


def test_ar_clean_cohort_produces_a_validated_strong_research_range() -> None:
    cohort = _csv("ar_clean_organic_cohort")
    assert len(cohort) == 3
    mature = cohort.loc[cohort["cohort_offset"].eq(2)].iloc[0]
    assert np.isclose(
        mature["cumulative_organic_invested_capital_proxy_usd"], 526_920_000
    )
    assert np.isclose(
        mature["reported_gaap_nopat_cumulative_roic_pct"],
        -1.6776318516690223,
    )
    assert np.isclose(
        mature["reported_economic_nopat_cumulative_roic_pct"],
        -7.420999766925554,
    )
    assert np.isclose(
        mature["full_cycle_normalized_nopat_cumulative_roic_pct"],
        1.5879639264246663,
    )
    assert bool(mature["reported_3y_cohort_complete"])
    assert bool(mature["independent_full_cycle_3y_cohort_complete"])
    assert bool(mature["organic_company_roic_validated"])
    assert not cohort.loc[cohort["cohort_offset"].lt(2), "organic_company_roic_validated"].any()


def test_oil_mixed_gas_ranges_preserve_v174_parents_and_apply_confidence() -> None:
    ranges = _csv("company_organic_roic_ranges").set_index("ticker")
    parent = pd.read_csv(
        PARENT_OUTPUT / "organic_roic_validation_ranges.csv"
    ).set_index("ticker")
    assert set(ranges.index) == {"AR", "DVN", "FANG"}
    assert set(ranges["group"]) == {"gas_heavy", "mixed", "oil_heavy"}
    for ticker in ("DVN", "FANG"):
        assert np.isclose(
            ranges.loc[ticker, "organic_roic_research_low_pct"],
            parent.loc[ticker, "economically_comparable_roic_low_pct"],
        )
        assert np.isclose(
            ranges.loc[ticker, "organic_roic_research_high_pct"],
            parent.loc[ticker, "economically_comparable_roic_high_pct"],
        )
    assert np.isclose(ranges.loc["AR", "roic_range_width_pct"], 9.008963693350221)
    assert ranges.loc["AR", "range_width_category"] == "STRONG"
    assert ranges.loc["DVN", "range_width_category"] == "TOO_UNCERTAIN_FOR_TERMINAL"
    assert ranges.loc["FANG", "range_width_category"] == "TOO_UNCERTAIN_FOR_TERMINAL"
    assert np.allclose(
        ranges.loc[["AR", "DVN", "FANG"], "company_confidence_weight"],
        [1.0, 0.25, 0.25],
    )
    assert not ranges["normal_roic_claimed"].any()
    assert not ranges["terminal_input_allowed"].any()


def test_project_reserve_acquisition_company_comparison_keeps_semantics_separate() -> None:
    comparison = _csv("three_level_roic_comparison").set_index("ticker")
    assert np.isclose(comparison.loc["AR", "project_development_roic_pct"], 30.213649009639354)
    assert np.isclose(comparison.loc["AR", "reserve_replacement_roic_pct"], 26.31864158365348)
    assert np.isnan(comparison.loc["AR", "acquisition_return_proxy_pct"])
    assert np.isclose(comparison.loc["DVN", "acquisition_return_proxy_pct"], 18.19837859105508)
    assert np.isclose(comparison.loc["FANG", "acquisition_return_proxy_pct"], 3.016280697174831)
    assert comparison.loc["AR", "acquisition_semantics"].startswith("NOT_APPLICABLE")
    assert comparison.loc["DVN", "acquisition_semantics"].startswith("PREDEAL_TARGET")
    assert not comparison["normal_roic_claimed"].any()
    assert not comparison["terminal_input_allowed"].any()


def test_distribution_is_descriptive_low_confidence_not_normal_roic() -> None:
    row = _csv("through_cycle_roic_distribution").iloc[0]
    assert int(row["cohort_count"]) == 3
    assert int(row["group_count"]) == 3
    assert np.isclose(row["effective_weighted_cohort_count"], 2.0)
    assert np.isclose(row["midpoint_p25_pct"], -2.916517920250444)
    assert np.isclose(row["midpoint_p50_pct"], -1.0909070478200262)
    assert np.isclose(row["midpoint_p75_pct"], 1.6475092608256006)
    assert int(row["strong_cohorts"]) == 1
    assert int(row["usable_research_cohorts"]) == 0
    assert int(row["too_uncertain_cohorts"]) == 2
    assert "NOT_POSTERIOR_OR_NORMAL_ROIC" in row["distribution_semantics"]
    assert row["distribution_confidence"].startswith("LOW_")
    assert not bool(row["normal_roic_claimed"])
    assert not bool(row["terminal_input_allowed"])


def test_leave_one_cohort_out_detects_ar_dependence() -> None:
    loco = _csv("leave_one_cohort_out_robustness").set_index("held_out_ticker")
    assert set(loco.index) == {"AR", "DVN", "FANG"}
    assert np.isclose(
        loco.loc["AR", "abs_p50_shift_pct_points"], 11.19608849740327
    )
    assert not bool(loco.loc["AR", "loco_p50_stable"])
    assert np.isclose(
        loco["max_abs_p50_shift_pct_points"].unique(), [11.19608849740327]
    ).all()
    assert not loco["all_loco_p50_stable"].any()
    assert not loco["terminal_input_allowed"].any()


def test_v18_research_gate_passes_but_freeze_and_terminal_stay_locked() -> None:
    gate = _csv("v1_8_gate").iloc[0]
    assert bool(gate["v1_7_4_frozen_parent_verified"])
    assert bool(gate["oil_mixed_gas_group_coverage"])
    assert bool(gate["gas_heavy_clean_cohort_validated"])
    assert bool(gate["v1_8_research_gate"])
    assert bool(gate["sector_pooling_descriptive_ready"])
    assert int(gate["strong_or_usable_range_count"]) == 1
    assert not bool(gate["minimum_two_strong_or_usable_ranges_for_freeze"])
    assert not bool(gate["loco_p50_max_shift_10pp"])
    assert not bool(gate["v1_8_research_freeze_eligible"])
    assert not bool(gate["terminal_evidence_thresholds_met"])
    assert not bool(gate["sector_distribution_terminal_ready"])
    assert gate["development_status"] == (
        "RESEARCH_GATE_PASSED_FREEZE_DEFERRED_DISTRIBUTION_UNSTABLE"
    )
    assert bool(gate["terminal_replacement_remains_locked"])
    assert not bool(gate["terminal_anchor_replacement_allowed"])
    assert not bool(gate["wacc_recalibrated"])
    assert not bool(gate["production_promoted"])
    assert gate["live_matched_observations"] == "0/20"


def test_terminal_lock_is_unconditional_even_if_evidence_thresholds_are_met() -> None:
    companies = pd.DataFrame(
        {
            "ticker": ["OIL", "MIX", "GAS"],
            "group": ["oil_heavy", "mixed", "gas_heavy"],
            "accounting_perimeter_validated": [True, True, True],
            "range_width_category": ["STRONG", "STRONG", "STRONG"],
            "range_width_gate_pass": [True, True, True],
        }
    )
    gas = pd.DataFrame(
        {"cohort_offset": [2], "organic_company_roic_validated": [True]}
    )
    loco = pd.DataFrame(
        {
            "all_loco_p50_stable": [True, True, True],
            "abs_p50_shift_pct_points": [0.0, 0.0, 0.0],
        }
    )
    gate = build_v18_gate(
        parent_v174_verified=True,
        company_ranges=companies,
        gas_cohort=gas,
        distribution=pd.DataFrame([{}]),
        loco=loco,
        three_level_comparison=pd.DataFrame({"ticker": ["OIL", "MIX", "GAS"]}),
    ).iloc[0]
    assert bool(gate["terminal_evidence_thresholds_met"])
    assert bool(gate["v1_8_research_freeze_eligible"])
    assert not bool(gate["sector_distribution_terminal_ready"])
    assert not bool(gate["terminal_anchor_replacement_allowed"])


def test_v18_writes_all_declared_research_artifacts() -> None:
    expected = {
        "gas_heavy_candidate_audit.csv",
        "ar_segment_annual_evidence.csv",
        "ar_clean_organic_cohort.csv",
        "company_organic_roic_ranges.csv",
        "three_level_roic_comparison.csv",
        "through_cycle_roic_distribution.csv",
        "leave_one_cohort_out_robustness.csv",
        "roic_range_width_gate.csv",
        "v1_8_gate.csv",
        "metadata.json",
        "report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT.iterdir()})
