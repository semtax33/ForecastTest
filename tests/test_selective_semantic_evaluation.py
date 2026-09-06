from __future__ import annotations

from equity_platform.text_ie.training import (
    SelectivePrediction,
    evaluate_selective_predictions,
)


def test_coverage_adjusted_precision_keeps_abstention_visible() -> None:
    predictions = tuple(
        SelectivePrediction(
            example_id=f"example-{index}",
            source_slice="IR_QA",
            gold_label="BELONGS_TO",
            predicted_label=(
                "BELONGS_TO"
                if index < 58
                else "NOT_RELATED"
                if index < 60
                else None
            ),
            abstention_reason="LOW_CONFIDENCE" if index >= 60 else None,
        )
        for index in range(100)
    )

    metrics = evaluate_selective_predictions(predictions)

    assert metrics.total_gold == 100
    assert metrics.predicted == 60
    assert metrics.correct == 58
    assert metrics.precision == 58 / 60
    assert metrics.recall == 0.58
    assert metrics.coverage == 0.60
    assert metrics.abstention_rate == 0.40
    assert metrics.coverage_adjusted_precision == 0.58
    assert metrics.silent_miss == 0


def test_missing_score_without_abstention_is_a_silent_miss() -> None:
    metrics = evaluate_selective_predictions((
        SelectivePrediction(
            example_id="missing-1",
            source_slice="SEC_10K",
            gold_label="REVENUE",
            predicted_label=None,
            abstention_reason=None,
        ),
    ))

    assert metrics.coverage == 0.0
    assert metrics.abstention_rate == 0.0
    assert metrics.silent_miss == 1
