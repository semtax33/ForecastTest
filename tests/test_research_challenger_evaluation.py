from __future__ import annotations

from equity_platform.text_ie.training.research_evaluation import (
    build_research_diagnostics,
    evaluate_research_predictions,
)


def _prediction(
    example_id: str,
    source: str,
    gold: str,
    predicted: str,
    confidence: float,
) -> dict[str, object]:
    return {
        "example_id": example_id,
        "source_slice": source,
        "gold_label": gold,
        "predicted_label": predicted,
        "confidence": confidence,
    }


def test_research_metrics_are_unthresholded_and_source_sliced() -> None:
    rows = (
        _prediction("1", "SEC_10K", "A", "A", 0.9),
        _prediction("2", "SEC_10K", "A", "B", 0.8),
        _prediction("3", "IR_QA", "B", "B", 0.7),
        _prediction("4", "IR_QA", "B", "B", 0.6),
    )

    result = evaluate_research_predictions(rows)

    assert result["count"] == 4
    assert result["accuracy"] == 0.75
    assert result["macro_f1"] == 0.7333333333333334
    assert result["naive_majority_accuracy"] == 0.5
    assert result["mean_confidence"] == 0.75
    assert result["mean_error_confidence"] == 0.8
    assert result["by_source_slice"]["SEC_10K"]["accuracy"] == 0.5
    assert result["by_source_slice"]["IR_QA"]["accuracy"] == 1.0


def test_research_metrics_reject_empty_and_count_reused_context_ids() -> None:
    try:
        evaluate_research_predictions(())
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("empty predictions must be rejected")

    repeated_context = (
        _prediction("same", "SEC_10K", "A", "A", 0.9),
        _prediction("same", "IR_QA", "B", "B", 0.8),
    )
    result = evaluate_research_predictions(repeated_context)

    assert result["count"] == 2
    assert result["unique_example_count"] == 1


def test_diagnostics_require_complete_matrix_without_selecting_champion() -> None:
    receipt = {
        "model_id": "model-a",
        "task": "CONCEPT",
        "checkpoint": "checkpoint-a",
        "device": "cuda",
        "evaluation_loss": 0.25,
        "predictions": [
            _prediction("1", "SEC_10K", "A", "A", 0.9),
        ],
    }

    report = build_research_diagnostics(
        (receipt,), expected_matrix=(("model-a", "CONCEPT"),)
    )

    assert report["status"] == "RESEARCH_DIAGNOSTICS_ONLY_CALIBRATION_LOCKED"
    assert report["champion_model_id"] is None
    assert report["certification_opened"] is False
    assert report["cells"][0]["metrics"]["accuracy"] == 1.0

    try:
        build_research_diagnostics(
            (receipt,),
            expected_matrix=(("model-a", "CONCEPT"), ("model-a", "ROLE")),
        )
    except ValueError as exc:
        assert "matrix" in str(exc)
    else:
        raise AssertionError("incomplete diagnostic matrix must be rejected")
