from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from types import MappingProxyType
from typing import Mapping

from ..semantic_challenger import (
    SemanticChallengerUnavailableError,
    SemanticPairRequest,
    SemanticScore,
    SemanticTask,
)


class TransformerUnavailableError(SemanticChallengerUnavailableError):
    pass


class TransformerDevicePolicy(StrEnum):
    CUDA_REQUIRED = "CUDA_REQUIRED"
    CPU_TEST_ONLY = "CPU_TEST_ONLY"


@dataclass(frozen=True)
class TransformerDevice:
    device: str
    device_name: str
    policy: TransformerDevicePolicy


class TransformerSemanticBackend:
    """Lazy learned challenger backed by one fine-tuned head per semantic task.

    Construction is deliberately dependency- and device-free.  CUDA and the
    optional ML packages are resolved only when ``score`` is invoked, allowing
    the deterministic extraction pipeline to run without a learned backend.
    """

    name = "TRANSFORMER_SEMANTIC_CHALLENGER"

    def __init__(
        self,
        *,
        checkpoints: Mapping[SemanticTask, str],
        device_policy: TransformerDevicePolicy = TransformerDevicePolicy.CUDA_REQUIRED,
        batch_size: int = 4,
        max_length: int = 512,
        torch_module=None,
        transformers_module=None,
    ) -> None:
        required = set(SemanticTask)
        supplied = set(checkpoints)
        missing = required - supplied
        if missing:
            required_labels = ", ".join(task.value for task in SemanticTask)
            labels = ", ".join(task.value for task in SemanticTask if task in missing)
            raise ValueError(
                "fine-tuned checkpoints are required for every head "
                f"({required_labels}); missing: {labels}"
            )
        unexpected = supplied - required
        if unexpected:
            raise ValueError(f"unsupported semantic checkpoint tasks: {unexpected}")
        if any(not str(checkpoints[task]).strip() for task in SemanticTask):
            raise ValueError("semantic checkpoint identifiers must not be empty")
        if batch_size < 1 or max_length < 32:
            raise ValueError("batch_size and max_length must be positive and usable")
        self.checkpoints = MappingProxyType(
            {task: str(checkpoints[task]) for task in SemanticTask}
        )
        self.device_policy = device_policy
        self.batch_size = batch_size
        self.max_length = max_length
        self._torch_module = torch_module
        self._transformers_module = transformers_module
        self.device = "cuda:pending" if device_policy is TransformerDevicePolicy.CUDA_REQUIRED else "cpu:pending"

    def score(
        self,
        requests: tuple[SemanticPairRequest, ...],
    ) -> tuple[SemanticScore, ...]:
        if not requests:
            return ()
        selected = resolve_transformer_device(
            torch_module=self._torch_module,
            policy=self.device_policy,
        )
        torch = self._torch_module
        if torch is None:
            torch = import_module("torch")
        transformers = self._transformers_module
        if transformers is None:
            try:
                transformers = import_module("transformers")
            except ModuleNotFoundError as exc:
                raise TransformerUnavailableError(
                    "the transformers package is required for semantic scoring"
                ) from exc
        self.device = selected.device
        scores: list[SemanticScore] = []
        for task in SemanticTask:
            active_requests = requests
            if task is SemanticTask.ROLE:
                bound_ids = {
                    score.request_id
                    for score in scores
                    if score.task is SemanticTask.BINDING
                    and score.label == "BELONGS_TO"
                }
                active_requests = tuple(
                    request for request in requests if request.request_id in bound_ids
                )
                if not active_requests:
                    continue
            checkpoint = self.checkpoints[task]
            tokenizer = transformers.AutoTokenizer.from_pretrained(checkpoint)
            model = transformers.AutoModelForSequenceClassification.from_pretrained(
                checkpoint
            )
            model.to(selected.device)
            model.eval()
            try:
                for offset in range(0, len(active_requests), self.batch_size):
                    batch = active_requests[offset : offset + self.batch_size]
                    encoded = tokenizer(
                        [
                            request.metric_marked_context
                            if task is SemanticTask.CONCEPT
                            else request.marked_context
                            for request in batch
                        ],
                        padding=True,
                        truncation=True,
                        max_length=self.max_length,
                        return_tensors="pt",
                    )
                    encoded = {
                        key: value.to(selected.device)
                        for key, value in encoded.items()
                    }
                    with torch.inference_mode():
                        if selected.device == "cuda":
                            with torch.autocast(
                                device_type="cuda",
                                dtype=torch.float16,
                            ):
                                logits = model(**encoded).logits
                        else:
                            logits = model(**encoded).logits
                    probabilities = torch.softmax(logits, dim=-1).detach().cpu().tolist()
                    id2label = model.config.id2label
                    for request, row in zip(batch, probabilities, strict=True):
                        label_id, confidence = max(
                            enumerate(row), key=lambda item: item[1]
                        )
                        label = id2label.get(label_id, id2label.get(str(label_id)))
                        if label is None:
                            raise TransformerUnavailableError(
                                f"checkpoint {checkpoint} has no label for id {label_id}"
                            )
                        scores.append(SemanticScore(
                            request_id=request.request_id,
                            task=task,
                            label=str(label),
                            confidence=float(confidence),
                            source_sha256=request.source_sha256,
                            metric_char_start=request.metric_char_start,
                            metric_char_end=request.metric_char_end,
                            quantity_char_start=request.quantity_char_start,
                            quantity_char_end=request.quantity_char_end,
                            model_id=checkpoint,
                            device=selected.device,
                        ))
            finally:
                model.to("cpu")
                del model
                del tokenizer
                if selected.device == "cuda":
                    torch.cuda.empty_cache()
        return tuple(scores)


def resolve_transformer_device(
    *,
    torch_module=None,
    policy: TransformerDevicePolicy = TransformerDevicePolicy.CUDA_REQUIRED,
) -> TransformerDevice:
    """Resolve the learned challenger device without an implicit CPU fallback."""

    torch = torch_module
    if torch is None:
        try:
            torch = import_module("torch")
        except ModuleNotFoundError as exc:
            raise TransformerUnavailableError(
                "PyTorch with CUDA support is required for transformer execution"
            ) from exc
    if policy is TransformerDevicePolicy.CPU_TEST_ONLY:
        return TransformerDevice("cpu", "CPU_TEST_ONLY", policy)
    if not torch.cuda.is_available():
        raise TransformerUnavailableError(
            "CUDA is required for transformer execution; CPU fallback is disabled"
        )
    return TransformerDevice("cuda", str(torch.cuda.get_device_name(0)), policy)


__all__ = [
    "TransformerDevice",
    "TransformerDevicePolicy",
    "TransformerSemanticBackend",
    "TransformerUnavailableError",
    "resolve_transformer_device",
]
