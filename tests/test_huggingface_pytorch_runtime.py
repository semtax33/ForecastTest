from __future__ import annotations

import os

from equity_platform.text_ie.training.huggingface_fine_tuning import (
    configure_pytorch_only_transformers_environment,
    trainer_checkpoint_policy,
)


def test_pytorch_runtime_disables_tensorflow_before_transformers_import(
    monkeypatch,
) -> None:
    monkeypatch.setenv("USE_TF", "1")
    monkeypatch.delenv("USE_TORCH", raising=False)

    configure_pytorch_only_transformers_environment()

    assert os.environ["USE_TF"] == "0"
    assert os.environ["USE_TORCH"] == "1"


def test_resumable_runtime_disables_redundant_trainer_checkpoints() -> None:
    assert trainer_checkpoint_policy() == {
        "save_strategy": "no",
        "load_best_model_at_end": False,
    }
