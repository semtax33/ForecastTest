from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11
from energy_nowcast.research.ep_v12.benchmark import verify_v12


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_2_research"


def test_v1_2_frozen_research_manifest_verifies() -> None:
    manifest = verify_v12(ROOT)
    assert manifest["research_frozen"] is True
    assert manifest["expectations_surface_frozen"] is True
    assert manifest["non_identification_policy_frozen"] is True
    assert manifest["single_point_market_implied_claim_allowed"] is False
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
    assert manifest["verified_files"] == 18


def test_v1_2_surface_is_research_only_and_preserves_frozen_manifests() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    parent = verify_v1(ROOT)
    benchmark = verify_v11(ROOT)
    assert metadata["v1_0_manifest_sha256"] == parent["manifest_sha256"]
    assert metadata["v1_1_manifest_sha256"] == benchmark["manifest_sha256"]
    assert metadata["frozen_v1_1_mutated"] is False
    assert metadata["maximum_frozen_reproduction_error_per_share"] < 1e-6
    assert metadata["single_point_market_implied_claim_allowed"] is False
    assert metadata["production_promoted"] is False
    assert metadata["live_matched_observations"] == "0/20"
    assert metadata["hormuz_treatment"] == "DEFERRED_REGIME_SCENARIO_OVERLAY"


def test_through_cycle_economics_are_hierarchical_and_uncertainty_labeled() -> None:
    economics = pd.read_csv(OUTPUT / "through_cycle_economics.csv")
    assert len(economics) == economics["ticker"].nunique() == 14
    assert economics["research_only"].all()
    for prefix in ("margin", "roic"):
        assert economics[f"normalized_{prefix}_q25_pct"].le(
            economics[f"normalized_{prefix}_q50_pct"]
        ).all()
        assert economics[f"normalized_{prefix}_q50_pct"].le(
            economics[f"normalized_{prefix}_q75_pct"]
        ).all()
        assert economics[f"{prefix}_company_weight"].between(0, 1).all()
    assert set(economics["normalization_confidence"]).issubset({
        "HIGH_PRE_RECENT_WINDOW", "MEDIUM_HIERARCHICAL_FULL_HISTORY",
        "LOW_LIMITED_COMPANY_HISTORY",
    })
    assert economics["normalization_confidence"].ne(
        "HIGH_PRE_RECENT_WINDOW"
    ).any()


def test_three_expectations_surfaces_have_complete_grids() -> None:
    detail = pd.read_csv(OUTPUT / "expectations_surface_ticker_detail.csv")
    sector = pd.read_csv(OUTPUT / "expectations_surface_sector_summary.csv")
    assert len(detail) == 14 * (6 * 5 + 5 * 6 + 5 * 6)
    assert len(sector) == 6 * 5 + 5 * 6 + 5 * 6
    assert detail["ticker"].nunique() == 14
    assert set(detail["surface"]) == {
        "TERMINAL_MARGIN_X_WACC", "GROWTH_X_OPERATING_MARGIN",
        "GROWTH_X_NORMALIZED_ROIC",
    }
    assert (~detail["production_eligible"]).all()
    assert detail[["fair_value", "market_price", "value_gap_pct"]].notna().all().all()


def test_terminal_margin_wacc_matrix_has_expected_monotonic_tradeoff() -> None:
    matrix = pd.read_csv(
        OUTPUT / "terminal_margin_wacc_gap_matrix.csv"
    ).set_index("terminal_margin_pct")
    values = matrix.to_numpy(dtype=float)
    assert np.all(np.diff(values, axis=1) < 0)
    assert np.all(np.diff(values, axis=0) > 0)
    assert np.isclose(matrix.loc[22.0, "wacc_6.5_pct"], 28.513623, atol=1e-5)
    assert np.isclose(matrix.loc[22.0, "wacc_7.5_pct"], -1.239451, atol=1e-5)


def test_iso_value_curves_preserve_non_uniqueness_and_fail_closed() -> None:
    curves = pd.read_csv(OUTPUT / "iso_value_curves.csv")
    assert set(curves["solver_status"]).issubset({
        "SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
        "NONFINITE_DOMAIN_ENDPOINT",
    })
    solved = curves.loc[curves["solver_status"].eq("SOLVED")]
    unbracketed = curves.loc[curves["solver_status"].eq(
        "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
    )]
    assert solved["solved_value_pct"].notna().all()
    assert solved["residual_value_gap_pct"].abs().le(1e-6).all()
    assert unbracketed["solved_value_pct"].isna().all()
    margin_wacc = solved.loc[
        solved["surface"].eq("TERMINAL_MARGIN_X_WACC")
    ]
    assert margin_wacc.groupby("ticker").size().eq(15).all()
    assert margin_wacc.groupby("ticker")["solved_value_pct"].nunique().gt(1).all()
    assert curves["interpretation"].eq(
        "ONE_POINT_ON_NON_UNIQUE_ISO_VALUE_CURVE"
    ).all()


def test_through_cycle_margin_implies_a_range_not_one_wacc_answer() -> None:
    summary = pd.read_csv(
        OUTPUT / "through_cycle_margin_wacc_summary.csv"
    ).set_index("through_cycle_margin_reference")
    assert int(summary.loc["Q50", "solved_tickers"]) == 13
    assert int(summary.loc["Q50", "unbracketed_tickers"]) == 1
    assert np.isclose(
        summary.loc["Q50", "conditional_wacc_median_pct"],
        7.917222074320307,
    )
    assert summary.loc["Q25", "conditional_wacc_median_pct"] < (
        summary.loc["Q50", "conditional_wacc_median_pct"]
    ) < summary.loc["Q75", "conditional_wacc_median_pct"]
    tradeoffs = pd.read_csv(OUTPUT / "through_cycle_margin_wacc_tradeoffs.csv")
    assert tradeoffs["interpretation"].eq(
        "CONDITIONAL_COMBINATION_NOT_UNIQUE_MARKET_EXPECTATION"
    ).all()
