from __future__ import annotations

from importlib import import_module
from typing import Callable

from ..llm.encoder_registry import EncoderSourceSlice
from ..llm.transformer_backend import (
    TransformerDevicePolicy,
    TransformerUnavailableError,
    resolve_transformer_device,
)
from ..model import TextBlock
from .model import LearnedSpanProposal, LearnedSpanUnavailableError


PipelineFactory = Callable[..., object]


class HfTokenSpanBackend:
    """Lazy Hugging Face token classifier used only to propose metric spans.

    The default runtime is intentionally offline-only and CUDA-required.  This
    prevents an extraction run from silently downloading a large checkpoint or
    falling back to CPU.  Callers may inject a factory for tests or a managed
    model store.
    """

    name = "HF_TOKEN_SPAN_CHALLENGER"
    SEC_SOURCE_SLICES = frozenset({
        EncoderSourceSlice.SEC_10K,
        EncoderSourceSlice.SEC_10Q,
    })

    def __init__(
        self,
        *,
        model_id: str = "AAU-NLP/BERT-SL1000",
        model_revision: str = "main",
        minimum_confidence: float = 0.50,
        local_files_only: bool = True,
        device_policy: TransformerDevicePolicy = TransformerDevicePolicy.CUDA_REQUIRED,
        pipeline_factory: PipelineFactory | None = None,
        torch_module=None,
        transformers_module=None,
    ) -> None:
        if not model_id.strip() or not model_revision.strip():
            raise ValueError("span checkpoint identity cannot be blank")
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum span confidence must be within [0, 1]")
        self.model_id = model_id
        self.model_revision = model_revision
        self.minimum_confidence = minimum_confidence
        self.local_files_only = local_files_only
        self.device_policy = device_policy
        self._pipeline_factory = pipeline_factory
        self._torch_module = torch_module
        self._transformers_module = transformers_module
        self._pipeline = None
        self.device = (
            "cuda:pending"
            if device_policy is TransformerDevicePolicy.CUDA_REQUIRED
            else "cpu:pending"
        )

    def _build_pipeline(self):
        try:
            selected = resolve_transformer_device(
                torch_module=self._torch_module,
                policy=self.device_policy,
            )
            self.device = selected.device
            if self._pipeline_factory is not None:
                return self._pipeline_factory(
                    task="token-classification",
                    model_id=self.model_id,
                    revision=self.model_revision,
                    device=selected.device,
                    local_files_only=self.local_files_only,
                    aggregation_strategy="none",
                )
            transformers = self._transformers_module
            if transformers is None:
                transformers = import_module("transformers")
            load_kwargs = {
                "revision": self.model_revision,
                "local_files_only": self.local_files_only,
            }
            tokenizer = transformers.AutoTokenizer.from_pretrained(
                self.model_id,
                **load_kwargs,
            )
            model = transformers.AutoModelForTokenClassification.from_pretrained(
                self.model_id,
                **load_kwargs,
            )
            model.to(selected.device)
            model.eval()
            return transformers.pipeline(
                "token-classification",
                model=model,
                tokenizer=tokenizer,
                device=0 if selected.device == "cuda" else -1,
                aggregation_strategy="none",
            )
        except LearnedSpanUnavailableError:
            raise
        except (
            ModuleNotFoundError,
            OSError,
            TransformerUnavailableError,
            ValueError,
        ) as exc:
            raise LearnedSpanUnavailableError(str(exc)) from exc

    def propose(
        self,
        block: TextBlock,
        source_slice: EncoderSourceSlice,
    ) -> tuple[LearnedSpanProposal, ...]:
        if source_slice not in self.SEC_SOURCE_SLICES:
            raise LearnedSpanUnavailableError(
                "BERT-SL1000 is restricted to SEC_10K/SEC_10Q source slices"
            )
        if self._pipeline is None:
            self._pipeline = self._build_pipeline()
        try:
            rows = self._pipeline(block.text)
        except (ModuleNotFoundError, OSError, RuntimeError) as exc:
            raise LearnedSpanUnavailableError(str(exc)) from exc
        token_spans = []
        try:
            for row in rows:
                label = str(
                    row.get("entity_group") or row.get("entity") or ""
                ).strip()
                if not label or label.upper() == "O":
                    continue
                confidence = float(row.get("score", 0.0))
                if confidence < self.minimum_confidence:
                    continue
                start = int(row["start"])
                end = int(row["end"])
                if not 0 <= start < end <= len(block.text):
                    continue
                token_spans.append((start, end, label, confidence))
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise LearnedSpanUnavailableError(
                f"malformed token-classification output: {exc}"
            ) from exc

        # BERT-SL1000 exposes taxonomy labels without BIO prefixes.  Group
        # adjacent same-label wordpieces ourselves so the model remains a span
        # proposer instead of producing one candidate per token.
        grouped = []
        for start, end, label, confidence in sorted(token_spans):
            if grouped:
                prior_start, prior_end, prior_label, prior_confidence = grouped[-1]
                gap = block.text[prior_end:start]
                if prior_label == label and (not gap or gap.isspace()):
                    grouped[-1] = (
                        prior_start,
                        end,
                        label,
                        min(prior_confidence, confidence),
                    )
                    continue
            grouped.append((start, end, label, confidence))

        proposals = []
        for start, end, label, confidence in grouped:
            # Tokenizer renderings may contain wordpiece markers; the source is
            # always authoritative for the literal.
            raw_text = block.text[start:end]
            proposals.append(LearnedSpanProposal(
                source_sha256=block.source.sha256,
                block_char_start=block.char_start,
                block_char_end=block.char_end,
                char_start=start,
                char_end=end,
                raw_text=raw_text,
                raw_label=label,
                confidence=confidence,
                model_id=self.model_id,
                model_revision=self.model_revision,
                canonical_concept=None,
            ))
        return tuple(proposals)


__all__ = ["HfTokenSpanBackend"]
