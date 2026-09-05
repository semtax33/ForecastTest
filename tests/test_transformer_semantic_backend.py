from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from equity_platform.text_ie.llm import (
    TransformerSemanticBackend,
    TransformerDevicePolicy,
    TransformerUnavailableError,
    resolve_transformer_device,
)
from equity_platform.text_ie.semantic_challenger import SemanticPairRequest, SemanticTask


class _Cuda:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def get_device_name(self, index: int) -> str:
        assert index == 0
        return "TEST GPU"


class _Torch:
    def __init__(self, cuda_available: bool) -> None:
        self.cuda = _Cuda(cuda_available)


class _Tensor:
    def __init__(self, values) -> None:
        self.values = values

    def to(self, device: str):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.values


class _RuntimeCuda(_Cuda):
    def __init__(self, events: list[str]) -> None:
        super().__init__(True)
        self._events = events

    def empty_cache(self) -> None:
        self._events.append("empty_cache")


class _RuntimeTorch:
    float16 = "float16"

    def __init__(self, events: list[str]) -> None:
        self.cuda = _RuntimeCuda(events)

    @staticmethod
    def inference_mode():
        return nullcontext()

    @staticmethod
    def autocast(**kwargs):
        return nullcontext()

    @staticmethod
    def softmax(logits: _Tensor, dim: int) -> _Tensor:
        assert dim == -1
        return logits


class _Tokenizer:
    def __call__(self, contexts, **kwargs):
        assert kwargs["return_tensors"] == "pt"
        return {"input_ids": _Tensor([[1]] * len(contexts))}


class _Model:
    def __init__(self, checkpoint: str, label: str, events: list[str]) -> None:
        self._checkpoint = checkpoint
        self._events = events
        self.config = SimpleNamespace(id2label={0: "OTHER", 1: label})

    def to(self, device: str):
        self._events.append(f"{self._checkpoint}:to:{device}")
        return self

    def eval(self) -> None:
        self._events.append(f"{self._checkpoint}:eval")

    def __call__(self, *, input_ids: _Tensor):
        return SimpleNamespace(logits=_Tensor([[0.01, 0.99]] * len(input_ids.values)))


class _Factory:
    def __init__(self, loader) -> None:
        self.from_pretrained = loader


class _Transformers:
    def __init__(self, events: list[str], *, binding_label: str = "BELONGS_TO") -> None:
        labels = {
            "models/concept": "REVENUE",
            "models/binding": binding_label,
            "models/role": "VALUE_CURRENT",
        }
        self.AutoTokenizer = _Factory(
            lambda checkpoint: events.append(f"{checkpoint}:tokenizer") or _Tokenizer()
        )
        self.AutoModelForSequenceClassification = _Factory(
            lambda checkpoint: events.append(f"{checkpoint}:model")
            or _Model(checkpoint, labels[checkpoint], events)
        )


def test_transformer_device_is_cuda_required_by_default() -> None:
    selected = resolve_transformer_device(torch_module=_Torch(True))

    assert selected.device == "cuda"
    assert selected.device_name == "TEST GPU"
    assert selected.policy is TransformerDevicePolicy.CUDA_REQUIRED


def test_transformer_device_never_silently_falls_back_to_cpu() -> None:
    with pytest.raises(TransformerUnavailableError, match="CUDA"):
        resolve_transformer_device(torch_module=_Torch(False))


def test_transformer_backend_requires_fine_tuned_checkpoint_for_every_head() -> None:
    with pytest.raises(ValueError, match="CONCEPT, BINDING, ROLE"):
        TransformerSemanticBackend(
            checkpoints={SemanticTask.CONCEPT: "models/concept"},
        )

    backend = TransformerSemanticBackend(
        checkpoints={
            SemanticTask.CONCEPT: "models/concept",
            SemanticTask.BINDING: "models/binding",
            SemanticTask.ROLE: "models/role",
        },
    )
    assert backend.device == "cuda:pending"


def test_transformer_backend_scores_and_evicts_each_head_sequentially() -> None:
    events: list[str] = []
    backend = TransformerSemanticBackend(
        checkpoints={
            SemanticTask.CONCEPT: "models/concept",
            SemanticTask.BINDING: "models/binding",
            SemanticTask.ROLE: "models/role",
        },
        torch_module=_RuntimeTorch(events),
        transformers_module=_Transformers(events),
        batch_size=2,
    )
    text = "Revenue was $10 million."
    request = SemanticPairRequest(
        request_id="req-1",
        source_sha256="a" * 64,
        context=text,
        metric_char_start=0,
        metric_char_end=7,
        quantity_char_start=12,
        quantity_char_end=23,
    )

    scores = backend.score((request,))

    assert [(score.task, score.label, score.confidence) for score in scores] == [
        (SemanticTask.CONCEPT, "REVENUE", 0.99),
        (SemanticTask.BINDING, "BELONGS_TO", 0.99),
        (SemanticTask.ROLE, "VALUE_CURRENT", 0.99),
    ]
    assert all(score.device == "cuda" for score in scores)
    assert events == [
        "models/concept:tokenizer",
        "models/concept:model",
        "models/concept:to:cuda",
        "models/concept:eval",
        "models/concept:to:cpu",
        "empty_cache",
        "models/binding:tokenizer",
        "models/binding:model",
        "models/binding:to:cuda",
        "models/binding:eval",
        "models/binding:to:cpu",
        "empty_cache",
        "models/role:tokenizer",
        "models/role:model",
        "models/role:to:cuda",
        "models/role:eval",
        "models/role:to:cpu",
        "empty_cache",
    ]


def test_transformer_backend_does_not_run_role_head_for_unbound_pairs() -> None:
    events: list[str] = []
    backend = TransformerSemanticBackend(
        checkpoints={
            SemanticTask.CONCEPT: "models/concept",
            SemanticTask.BINDING: "models/binding",
            SemanticTask.ROLE: "models/role",
        },
        torch_module=_RuntimeTorch(events),
        transformers_module=_Transformers(events, binding_label="NOT_RELATED"),
    )
    text = "Revenue was $10 million."
    request = SemanticPairRequest(
        request_id="req-1",
        source_sha256="a" * 64,
        context=text,
        metric_char_start=0,
        metric_char_end=7,
        quantity_char_start=12,
        quantity_char_end=23,
    )

    scores = backend.score((request,))

    assert [score.task for score in scores] == [
        SemanticTask.CONCEPT,
        SemanticTask.BINDING,
    ]
    assert not any(event.startswith("models/role") for event in events)
