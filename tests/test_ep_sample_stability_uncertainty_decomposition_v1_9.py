from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v174.benchmark import verify_v174
from energy_nowcast.research.ep_v19.parent import v18_parent_snapshot


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_9_research"
V18_OUTPUT = ROOT / "output" / "energy_valuation_v1_8_research"
def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_v19_preserves_v18_snapshot_and_frozen_v174() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    snapshot = v18_parent_snapshot(ROOT)
    assert snapshot["snapshot_sha256"] == metadata["v1_8_parent_snapshot_sha256"]
    assert snapshot["verified_files"] == 19
    assert metadata["v1_8_parent_mutated"] is False
    v174 = verify_v174(ROOT)
    assert len(v174["manifest_sha256"]) == 64
    assert metadata["v1_7_4_manifest_sha256"] == v174["manifest_sha256"]
    assert metadata["v1_7_4_parent_mutated"] is False


def test_rrc_selection_policy_retains_v18_thresholds_and_is_outcome_blind() -> None:
    policy = pd.read_csv(ROOT / "configs" / "ep_v19_selection_policy.csv").set_index(
        "policy_name"
    )
    assert policy.loc["research_cutoff", "value"] == "2025-03-01"
    assert float(policy.loc["capital_materiality_ratio", "value"]) == 0.01
    assert float(policy.loc["reserve_event_materiality_ratio", "value"]) == 0.02
    assert float(policy.loc["eligible_denominator_ratio", "value"]) == 0.02
    assert int(policy.loc["freeze_min_strong_or_usable", "value"]) == 2
    assert float(policy.loc["loco_max_p50_shift", "value"]) == 10.0
    assert policy.loc["selection_order", "value"] == "LATEST_ELIGIBLE_WINDOW"
    assert policy.loc["outcome_values_used_for_selection", "value"] == "false"


def test_rrc_gold_registry_has_five_predeclared_sec_filings() -> None:
    registry = pd.read_csv(
        ROOT / "configs" / "ep_v19_rrc_sources.csv", dtype={"adsh": str}
    )
    assert list(registry["year"]) == [2020, 2021, 2022, 2023, 2024]
    assert registry["adsh"].str.len().eq(20).all()
    assert registry["segment_phrase_verified"].all()
    assert registry["reserve_values_verified_from_local_fnsd"].all()
    assert set(registry["expected_reserve_dimh"]) == {
        "0xcec9f14bc7eff4887675c675fd5e6584"
    }
    assert set(registry["required_segment_phrase"]) == {
        "only one operating segment"
    }


def test_rrc_live_companyfacts_and_gold_registry_evidence_close_identities() -> None:
    evidence = _csv("rrc_annual_source_evidence")
    assert list(evidence["year"]) == [2020, 2021, 2022, 2023, 2024]
    assert evidence["source_cells_fully_verified"].all()
    assert int(evidence["source_cell_checks"].sum()) == 50
    assert int(evidence["source_cell_checks_passed"].sum()) == 50
    assert evidence["source_evidence_bundle_sha256"].str.len().eq(64).all()
    assert evidence["source_registry_record_sha256"].str.len().eq(64).all()
    assert evidence["local_fnsd_source_files_present"].all()
    assert set(evidence["source_verification_route"]) == {
        "LIVE_SEC_COMPANYFACTS_PLUS_CURATED_LOCAL_FNSD_GOLD_REGISTRY"
    }
    income_identity = (
        evidence["revenue_usd"]
        - evidence["cost_and_expense_usd"]
        - evidence["income_before_tax_usd"]
    )
    assert np.allclose(income_identity, 0.0, atol=1.0)
    assert evidence["income_identity_passed"].all()


def test_rrc_reserve_rollforward_proves_immaterial_transaction_perimeter() -> None:
    evidence = _csv("rrc_annual_source_evidence").set_index("year")
    assert evidence["reserve_rollforward_identity_passed"].all()
    assert evidence.loc[2021:2023, "net_reserve_transaction_balancing_mmcfe"].eq(0).all()
    assert np.isclose(
        evidence.loc[2024, "net_reserve_transaction_balancing_mmcfe"], -10_542
    )
    assert np.isclose(evidence.loc[2024, "sales_identity_mmcfe"], 10_542)
    assert np.isclose(
        evidence.loc[2024, "reserve_event_ratio"], 0.0005820089023843208
    )
    assert evidence.loc[2021:, "reserve_event_ratio"].max() < 0.02
    assert set(evidence["reserve_event_zero_semantics"]) == {
        "NET_TRANSACTION_BALANCING_ITEM_FROM_STANDARDIZED_ROLLFORWARD_NOT_CLAIMED_AS_DIRECT_DISCLOSURE"
    }


def test_latest_eligible_rrc_window_is_selected_without_roic_outcomes() -> None:
    audit = _csv("rrc_clean_window_candidate_audit")
    assert list(audit["window_start_year"]) == [2021, 2022, 2023]
    assert audit.loc[
        audit["window_start_year"].isin([2021, 2022]), "window_eligible"
    ].all()
    assert not bool(
        audit.loc[audit["window_start_year"].eq(2023), "window_eligible"].iloc[0]
    )
    selected = audit.loc[audit["selected_for_v19"]]
    assert len(selected) == 1
    row = selected.iloc[0]
    assert int(row["window_start_year"]) == 2022
    assert int(row["window_end_year"]) == 2024
    assert np.isclose(row["reserve_event_max_ratio"], 0.0005820089023843208)
    assert np.isclose(row["capital_materiality_threshold"], 0.01)
    assert np.isclose(row["cumulative_organic_invested_capital_usd"], 534_725_000)
    assert np.isclose(row["denominator_threshold_usd"], 95_940_560)
    assert not audit["outcome_values_used_for_selection"].any()


def test_rrc_selected_normalization_has_complete_signed_attribution() -> None:
    evidence = _csv("rrc_selected_normalization_evidence")
    assert list(evidence["year"]) == [2021, 2022, 2023, 2024]
    assert np.isclose(
        evidence["normalized_price_per_boe"].iloc[0], 22.526549805194804
    )
    assert np.isclose(
        evidence["normalized_complete_company_unit_cost_per_boe"].iloc[0],
        18.49477703161832,
    )
    assert evidence["normalization_attribution_complete"].all()
    assert (
        evidence["normalization_attribution_identity_error_usd"].abs().le(1.0).all()
    )
    assert set(evidence["normalization_confidence_grade"]) == {"A"}
    assert not evidence["terminal_input_allowed"].any()


def test_rrc_clean_cohort_is_validated_only_on_mature_row() -> None:
    cohort = _csv("rrc_clean_organic_cohort")
    assert len(cohort) == 3
    mature = cohort.loc[cohort["cohort_offset"].eq(2)].iloc[0]
    assert np.isclose(
        mature["cumulative_organic_invested_capital_proxy_usd"], 534_725_000
    )
    assert np.isclose(
        mature["reported_economic_nopat_cumulative_roic_pct"],
        -22.37219131329188,
    )
    assert np.isclose(
        mature["full_cycle_normalized_nopat_cumulative_roic_pct"],
        1.8708471136783238,
    )
    assert bool(mature["reported_3y_cohort_complete"])
    assert bool(mature["independent_full_cycle_3y_cohort_complete"])
    assert bool(mature["organic_company_roic_validated"])
    immature = cohort.loc[cohort["cohort_offset"].lt(2)]
    assert not immature["organic_company_roic_validated"].any()


def test_expanded_ranges_preserve_all_v18_rows_and_add_usable_rrc() -> None:
    parent = pd.read_csv(V18_OUTPUT / "company_organic_roic_ranges.csv").sort_values(
        "ticker"
    )
    expanded = _csv("expanded_company_organic_roic_ranges").sort_values("ticker")
    pd.testing.assert_frame_equal(
        expanded.loc[
            expanded["ticker"].isin(parent["ticker"]), parent.columns
        ].reset_index(drop=True),
        parent.reset_index(drop=True),
        check_dtype=False,
    )
    rrc = expanded.loc[expanded["ticker"].eq("RRC")].iloc[0]
    assert np.isclose(rrc["roic_range_width_pct"], 24.243038426970205)
    assert rrc["range_width_category"] == "USABLE_RESEARCH"
    assert np.isclose(rrc["company_confidence_weight"], 0.75)
    assert bool(rrc["range_width_gate_pass"])
    assert not expanded["normal_roic_claimed"].any()
    assert not expanded["terminal_input_allowed"].any()


def test_dvn_fang_width_attribution_exactly_reconstructs_observed_ranges() -> None:
    wide = _csv("dvn_fang_range_width_attribution").set_index("ticker")
    assert set(wide.index) == {"DVN", "FANG"}
    assert wide["range_width_attribution_complete"].all()
    assert wide["range_width_attribution_identity_error_pct"].abs().le(1e-9).all()
    assert np.allclose(wide["denominator_signed_width_contribution_pct"], 0.0)
    assert np.isclose(
        wide.loc["DVN", "price_normalization_signed_width_contribution_pct"],
        54.812840461355044,
    )
    assert np.isclose(
        wide.loc["FANG", "price_normalization_signed_width_contribution_pct"],
        170.0670459521587,
    )
    assert np.isclose(
        wide.loc["DVN", "cost_normalization_signed_width_contribution_pct"],
        -9.800531434549926,
    )
    assert np.isclose(
        wide.loc["FANG", "cost_normalization_signed_width_contribution_pct"],
        -43.36429583311286,
    )
    assert set(wide["dominant_width_expansion_driver"]) == {"PRICE_NORMALIZATION"}


def test_component_attribution_has_all_five_channels_and_signed_offsets() -> None:
    components = _csv("range_width_component_attribution")
    assert len(components) == 10
    assert set(components["component"]) == {
        "DENOMINATOR",
        "PRICE_NORMALIZATION",
        "COST_NORMALIZATION",
        "TAX_NORMALIZATION",
        "ACCOUNTING_PERIMETER",
    }
    for _, frame in components.groupby("ticker"):
        assert np.isclose(
            frame["signed_width_contribution_pct"].sum(),
            frame["observed_range_width_pct"].iloc[0],
        )
    offsets = components.loc[
        components["component"].isin(["COST_NORMALIZATION", "TAX_NORMALIZATION"]),
        "contribution_role",
    ]
    assert set(offsets) == {"WIDTH_OFFSET"}
    assert not components["terminal_input_allowed"].any()


def test_four_cohort_distribution_improves_effective_sample_without_normal_claim() -> None:
    row = _csv("expanded_through_cycle_roic_distribution").iloc[0]
    assert int(row["cohort_count"]) == 4
    assert int(row["group_count"]) == 3
    assert np.isclose(row["effective_weighted_cohort_count"], 3.0)
    assert np.isclose(row["midpoint_p25_pct"], -8.679067518664434)
    assert np.isclose(row["midpoint_p50_pct"], -3.964254210871169)
    assert np.isclose(row["midpoint_p75_pct"], 0.2783011065027865)
    assert int(row["strong_cohorts"]) == 1
    assert int(row["usable_research_cohorts"]) == 1
    assert int(row["strong_or_usable_cohorts"]) == 2
    assert not bool(row["normal_roic_claimed"])
    assert not bool(row["terminal_input_allowed"])


def test_expanded_loco_passes_unchanged_ten_point_gate() -> None:
    loco = _csv("expanded_leave_one_cohort_out_robustness").set_index(
        "held_out_ticker"
    )
    assert set(loco.index) == {"AR", "DVN", "FANG", "RRC"}
    assert loco["loco_p50_stable"].all()
    assert loco["all_loco_p50_stable"].all()
    assert np.isclose(
        loco["abs_p50_shift_pct_points"].max(), 2.8733471630511427
    )
    assert np.isclose(
        loco.loc["RRC", "p50_shift_pct_points"], 2.8733471630511427
    )
    assert loco["predeclared_max_abs_p50_shift_pct_points"].eq(10.0).all()


def test_sample_stability_comparison_proves_both_original_gates_now_pass() -> None:
    row = _csv("sample_stability_comparison").iloc[0]
    assert int(row["v1_8_strong_or_usable_cohorts"]) == 1
    assert int(row["v1_9_strong_or_usable_cohorts"]) == 2
    assert np.isclose(
        row["v1_8_max_abs_loco_p50_shift_pct_points"], 11.19608849740327
    )
    assert np.isclose(
        row["v1_9_max_abs_loco_p50_shift_pct_points"], 2.8733471630511427
    )
    assert np.isclose(
        row["max_abs_loco_improvement_pct_points"], 8.322741334352127
    )
    assert bool(row["sample_stability_gate_resolved"])


def test_v19_is_freeze_eligible_but_not_frozen_or_terminal_ready() -> None:
    gate = _csv("v1_9_gate").iloc[0]
    assert bool(gate["v1_8_parent_snapshot_verified"])
    assert bool(gate["outcome_blind_fourth_cohort_selection"])
    assert bool(gate["independent_fourth_cohort_validated"])
    assert bool(gate["dvn_fang_range_width_attribution_complete"])
    assert bool(gate["minimum_two_strong_or_usable_ranges"])
    assert bool(gate["loco_p50_max_shift_10pp"])
    assert bool(gate["sample_stability_issue_resolved"])
    assert bool(gate["uncertainty_decomposition_issue_resolved"])
    assert bool(gate["v1_9_research_freeze_eligible"])
    assert not bool(gate["v1_9_research_frozen"])
    assert gate["development_status"] == (
        "RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE_AWAITING_APPROVAL"
    )
    assert not bool(gate["normal_roic_claimed"])
    assert not bool(gate["sector_distribution_terminal_ready"])
    assert not bool(gate["terminal_anchor_replacement_allowed"])
    assert not bool(gate["wacc_recalibrated"])
    assert not bool(gate["production_promoted"])
    assert gate["live_matched_observations"] == "0/20"


def test_v19_writes_all_declared_research_artifacts() -> None:
    expected = {
        "rrc_clean_window_candidate_audit.csv",
        "rrc_annual_source_evidence.csv",
        "rrc_selected_normalization_evidence.csv",
        "rrc_clean_organic_cohort.csv",
        "dvn_fang_range_width_attribution.csv",
        "range_width_component_attribution.csv",
        "expanded_company_organic_roic_ranges.csv",
        "expanded_through_cycle_roic_distribution.csv",
        "expanded_leave_one_cohort_out_robustness.csv",
        "sample_stability_comparison.csv",
        "v1_9_gate.csv",
        "metadata.json",
        "report.md",
    }
    assert expected == {path.name for path in OUTPUT.iterdir() if path.is_file()}
