from __future__ import annotations

from equity_platform.text_ie.training import (
    SemanticTrainingAuthority,
    assess_semantic_training_authority,
)


def test_training_minimums_open_research_training_but_not_calibration() -> None:
    authority = assess_semantic_training_authority(
        training_ready=True,
        all_benchmark_slices_ready=False,
    )

    assert authority is SemanticTrainingAuthority.RESEARCH_ONLY
    assert authority.training_allowed
    assert not authority.calibration_champion_allowed


def test_complete_source_corpus_opens_calibration_champion_selection() -> None:
    authority = assess_semantic_training_authority(
        training_ready=True,
        all_benchmark_slices_ready=True,
    )

    assert authority is SemanticTrainingAuthority.CALIBRATION_ALLOWED
    assert authority.training_allowed
    assert authority.calibration_champion_allowed


def test_failed_training_minimums_keep_every_model_action_locked() -> None:
    authority = assess_semantic_training_authority(
        training_ready=False,
        all_benchmark_slices_ready=True,
    )

    assert authority is SemanticTrainingAuthority.BLOCKED
    assert not authority.training_allowed
    assert not authority.calibration_champion_allowed

