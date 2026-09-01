from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from energy_nowcast.research.v36.benchmark import verify_research_champion
from energy_nowcast.research.v36.macro_data import build_macro_feature_panel
from energy_nowcast.research.v36.validation import (
    _fit_overlay,
    apply_macro_overlay,
    macro_candidate_gate,
    passing_pairwise_combinations,
)


ROOT = Path(__file__).resolve().parents[1]


def _series(
    name: str,
    dates: pd.DatetimeIndex,
    lag_days: int,
    values: np.ndarray | None = None,
) -> pd.DataFrame:
    if values is None:
        values = np.linspace(1.0, 2.0, len(dates))
    return pd.DataFrame({
        "series": name,
        "date": dates,
        "availability_date": dates + pd.Timedelta(days=lag_days),
        "value": values,
        "source_url": "test",
    })


def test_macro_panel_honors_release_cutoff() -> None:
    historical = pd.date_range("2022-01-03", periods=520, freq="B")
    macro = _series("OVXCLS", historical, 1)
    future = pd.DataFrame([{
        "series": "OVXCLS",
        "date": pd.Timestamp("2024-05-31"),
        "availability_date": pd.Timestamp("2024-06-02"),
        "value": 999.0,
        "source_url": "test",
    }])
    panel = build_macro_feature_panel(["2024Q2"], pd.concat([macro, future]))
    row = panel.iloc[0]
    assert pd.Timestamp(row["forecast_cutoff_date"]) == pd.Timestamp("2024-06-01")
    assert pd.Timestamp(row["ovx_regime_z_availability_date"]) <= pd.Timestamp(
        row["forecast_cutoff_date"]
    )
    assert pd.Timestamp(row["ovx_regime_z_observation_date"]) != pd.Timestamp(
        "2024-05-31"
    )


def test_stale_wti_curve_fails_closed() -> None:
    dates = pd.date_range("2024-03-25", periods=5, freq="B")
    macro = pd.concat([
        _series("EIA_WTI_FUTURES_1", dates, 7, np.full(5, 80.0)),
        _series("EIA_WTI_FUTURES_2", dates, 7, np.full(5, 79.0)),
    ])
    panel = build_macro_feature_panel(["2024Q3"], macro)
    assert np.isnan(panel.loc[0, "wti_curve_slope_pct"])
    assert pd.Timestamp(panel.loc[0, "wti_curve_slope_pct_observation_date"]) == dates[-1]


def test_overlay_cold_start_shrinks_to_frozen_baseline() -> None:
    history = pd.DataFrame({
        "quarter_ordinal": [1, 2, 3],
        "feature": [0.1, 0.2, 0.3],
        "residual": [1.0, -1.0, 0.5],
    })
    target = pd.Series({"quarter_ordinal": 4, "feature": 0.4})
    overlay, n, coefficients, status = _fit_overlay(
        history, target, ("feature",), 8.0, 20, 8.0
    )
    assert overlay == 0.0
    assert n == 3
    assert coefficients == {}
    assert status == "NEUTRAL_COLD_START_SHRINKAGE"
    missing = target.copy()
    missing["feature"] = np.nan
    overlay, _, _, status = _fit_overlay(
        history, missing, ("feature",), 8.0, 20, 8.0
    )
    assert np.isnan(overlay)
    assert status == "MACRO_FEATURE_UNAVAILABLE_AT_CUTOFF"


def _scorecard(tickers: list[str], candidate: bool = False) -> pd.DataFrame:
    rows = []
    for index, ticker in enumerate(tickers):
        rows.append({
            "ticker": ticker,
            "observations": 8,
            "mase": 0.55 if candidate else 0.60,
            "candidate_mae_log_points": (
                6.1 if candidate and index == len(tickers) - 1 else
                5.0 if candidate else 6.0
            ),
            "directional_hit_rate": 0.80,
            "pi_80_coverage": 0.80,
        })
    return pd.DataFrame(rows)


def test_candidate_gate_keeps_exact_80pct_and_severe_thresholds() -> None:
    tickers = ["EOG", "FANG", "MGY", "MTDR", "PR"]
    baseline = _scorecard(tickers)
    candidate = _scorecard(tickers, candidate=True)
    passed = macro_candidate_gate(
        baseline, candidate, "oil_heavy", ("ovx_regime_z",), "TIME"
    ).iloc[0]
    assert passed["baseline_no_regression_share"] == 0.8
    assert bool(passed["candidate_gate"])

    candidate.loc[candidate.index[-2:], "candidate_mae_log_points"] = 6.1
    failed_share = macro_candidate_gate(
        baseline, candidate, "oil_heavy", ("ovx_regime_z",), "TIME"
    ).iloc[0]
    assert failed_share["baseline_no_regression_share"] == 0.6
    assert not bool(failed_share["candidate_gate"])

    candidate = _scorecard(tickers, candidate=True)
    candidate.loc[candidate.index[-1], "candidate_mae_log_points"] = 8.01
    failed_severe = macro_candidate_gate(
        baseline, candidate, "oil_heavy", ("ovx_regime_z",), "TIME"
    ).iloc[0]
    assert int(failed_severe["severe_regression_count"]) == 1
    assert not bool(failed_severe["candidate_gate"])


def test_combinations_require_each_single_to_pass() -> None:
    gates = pd.DataFrame([
        {"group": "oil_heavy", "features": "ovx_regime_z", "candidate_gate": True},
        {"group": "oil_heavy", "features": "dxy_regime_z", "candidate_gate": True},
        {"group": "oil_heavy", "features": "oil_rig_z", "candidate_gate": False},
        {"group": "mixed", "features": "ovx_regime_z", "candidate_gate": True},
    ])
    assert passing_pairwise_combinations(gates, "oil_heavy") == [
        ("dxy_regime_z", "ovx_regime_z")
    ]


def test_gas_macro_is_prohibited() -> None:
    with pytest.raises(ValueError, match="Gas macro research is prohibited"):
        apply_macro_overlay(
            pd.DataFrame({"group": ["gas_heavy"]}),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            "gas_heavy",
            ("ovx_regime_z",),
            "TIME",
        )


def test_frozen_v353_research_manifest_verifies() -> None:
    manifest = verify_research_champion(ROOT, "3.5.3")
    assert manifest["version"] == "3.5.3"
    assert manifest["active_group_models"]["gas_heavy"] == "LEGACY"
