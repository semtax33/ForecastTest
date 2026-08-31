from datetime import date

import numpy as np
import pandas as pd
import pytest

from energy_nowcast.config import ModelConfig
from energy_nowcast.data.cutoff import filter_available_as_of, quarter_cutoff_date
from energy_nowcast.validation.intervals import pooled_residual_quantiles
from energy_nowcast.validation.metrics import enrich_revenue_level_errors, mase
from energy_nowcast.validation.walk_forward import shrink_weight, walk_forward_validation


def test_feedback_shrinkage_example_is_exact():
    assert shrink_weight(1.0, 6, prior_weight=0.75, k=6) == pytest.approx(0.875)


def test_mase_uses_naive_error_scale():
    actual = pd.Series([10.0, -10.0])
    predicted = pd.Series([5.0, -5.0])
    naive = pd.Series([0.0, 0.0])
    assert mase(actual, predicted, naive) == pytest.approx(0.5)


def test_revenue_level_ape_is_not_yoy_percentage_point_error():
    validation = pd.DataFrame(
        {
            "ticker": ["EOG"],
            "quarter": ["2025Q1"],
            "prediction_log_yoy": [100.0 * np.log(1.3067)],
        }
    )
    panel = pd.DataFrame(
        {
            "ticker": ["EOG", "EOG"],
            "quarter": ["2024Q1", "2025Q1"],
            "revenue": [100.0, 120.0],
        }
    )
    result = enrich_revenue_level_errors(validation, panel)
    assert result.loc[0, "predicted_revenue"] == pytest.approx(130.67)
    assert result.loc[0, "revenue_level_ape_pct"] == pytest.approx(8.8916667)


def test_release_date_cutoff_is_inclusive_and_quarter_bounded():
    assert quarter_cutoff_date("2026Q3", 61) == pd.Timestamp("2026-08-31")
    frame = pd.DataFrame(
        {"release_date": ["2026-08-31", "2026-09-01", None], "value": [1, 2, 3]}
    )
    result = filter_available_as_of(frame, "2026-08-31", "release_date")
    assert result["value"].tolist() == [1]


def test_untouched_rows_never_train_on_other_untouched_actuals():
    frame = pd.DataFrame(
        {
            "ticker": ["EOG"] * 6,
            "quarter": [f"202{i}Q1" for i in range(1, 7)],
            "actual_log_yoy": [1, 2, 3, 4, 1000, -1000],
            "v21_log_yoy": [0, 0, 0, 0, 0, 0],
            "structural_log_yoy": [1, 2, 3, 4, 5, 6],
            "source_quality_score": [1.0] * 6,
            "production_yoy_source": ["GUIDANCE_VS_ACTUAL"] * 6,
        }
    )
    config = ModelConfig(
        version="test", as_of_date=date(2026, 8, 31), untouched_test_quarters=2
    )
    result = walk_forward_validation(frame, config)
    test_rows = result.loc[result["evaluation_split"].eq("untouched_test")]
    assert test_rows["weight_history_observations"].tolist() == [4, 4]
    assert test_rows["raw_structural_weight"].nunique() == 1


def test_interval_quantiles_mix_ticker_and_sector_residuals():
    residuals = pd.DataFrame(
        {
            "ticker": ["EOG", "EOG", "COP", "COP"],
            "residual_log_points": [-2.0, 2.0, -10.0, 10.0],
        }
    )
    lower, upper, ticker_n, pooled_n = pooled_residual_quantiles(
        residuals, "EOG", 0.1, 0.9, ticker_weight=0.5
    )
    assert ticker_n == 2
    assert pooled_n == 4
    assert lower < -2.0
    assert upper > 2.0
