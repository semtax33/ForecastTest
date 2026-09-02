from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_1_ep_attribution"


def test_attribution_reproduces_frozen_v1_1_without_mutation() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    parent = verify_v1(ROOT)
    benchmark = verify_v11(ROOT)
    assert metadata["v1_0_manifest_sha256"] == parent["manifest_sha256"]
    assert metadata["v1_1_manifest_sha256"] == benchmark["manifest_sha256"]
    assert metadata["frozen_v1_1_mutated"] is False
    assert metadata["maximum_frozen_reproduction_error_per_share"] < 1e-6


def test_hormuz_is_not_falsely_claimed_as_directly_identified() -> None:
    audit = pd.read_csv(OUTPUT / "hormuz_identifiability_audit.csv").set_index(
        "candidate_driver"
    )
    for driver in (
        "COMMODITY_SPOT_OR_QTD_PRICE", "HORMUZ_GEOPOLITICAL_PREMIUM",
        "AIS_VISIBLE_OR_DARK_TRANSIT",
    ):
        assert not bool(audit.loc[driver, "direct_v1_1_input"])
    assert audit.loc["HORMUZ_GEOPOLITICAL_PREMIUM", "analysis_treatment"] == (
        "MARGIN_PERSISTENCE_PROXY_ONLY"
    )
    assert audit.loc[
        "FROZEN_REVENUE_NOWCAST_GROWTH_ANCHOR", "coverage"
    ] == "4/14"


def test_original_gap_and_anchor_channel_are_reproduced() -> None:
    summary = pd.read_csv(OUTPUT / "counterfactual_summary.csv").set_index(
        "experiment"
    )
    assert np.isclose(
        summary.loc["ORIGINAL_V1_1", "median_value_gap_pct"],
        90.66707198700433,
    )
    assert np.isclose(
        summary.loc["NO_NEAR_TERM_REVENUE_ANCHOR", "median_value_gap_pct"],
        summary.loc["ORIGINAL_V1_1", "median_value_gap_pct"],
    )
    exposure = pd.read_csv(OUTPUT / "ticker_driver_exposure.csv")
    anchored = exposure.loc[exposure["anchor_used"]]
    assert set(anchored["ticker"]) == {"COP", "DVN", "EOG", "FANG"}
    assert anchored["no_anchor_gap_reduction_pct_points"].max() < 15.0


def test_risk_and_terminal_sensitivities_are_monotonic_and_nonadditive() -> None:
    summary = pd.read_csv(OUTPUT / "counterfactual_summary.csv").set_index(
        "experiment"
    )
    gaps = summary.loc[[
        "ORIGINAL_V1_1", "WACC_PLUS_100BP", "WACC_PLUS_200BP",
        "WACC_PLUS_300BP",
    ], "median_value_gap_pct"].to_numpy()
    assert np.all(np.diff(gaps) < 0)
    fade = summary.loc[[
        "MARGIN_PREMIUM_PROXY_1Y_FADE",
        "MARGIN_PREMIUM_PROXY_2Y_FADE",
        "MARGIN_PREMIUM_PROXY_4Y_FADE",
    ], "median_value_gap_pct"]
    assert fade.max() - fade.min() < 1.0
    assert summary.loc[
        "COMBINED_LONG_RUN_NORMALIZATION", "median_value_gap_pct"
    ] < 0


def test_ev_to_equity_is_an_amplifier_and_fcff_anomaly_is_not_mechanical() -> None:
    diagnostics = pd.read_csv(OUTPUT / "diagnostic_summary.csv").set_index(
        "metric"
    )
    equity_gap = diagnostics.loc["equity_value_gap_median_pct", "value"]
    ev_gap = diagnostics.loc["enterprise_value_gap_median_pct", "value"]
    assert equity_gap > ev_gap > 0
    assert diagnostics.loc[
        "ev_to_equity_individual_gap_amplification_median_pct_points", "value"
    ] > 0
    assert np.isclose(
        diagnostics.loc["historical_fcff_margin_gap_rank_correlation", "value"],
        0.5384615384615385,
    )
