from __future__ import annotations

from contextlib import redirect_stdout
from importlib import import_module
from io import StringIO
from typing import Callable, Mapping

from ..llm.encoder_registry import EncoderSourceSlice
from ..llm.transformer_backend import (
    TransformerDevicePolicy,
    TransformerUnavailableError,
    resolve_transformer_device,
)
from ..model import TextBlock
from .model import LearnedSpanProposal, LearnedSpanUnavailableError


ExtractorFactory = Callable[..., object]


DEFAULT_IR_ENTITY_SCHEMA: Mapping[str, str] = {
    "financial_kpi": (
        "A named financial or operating performance metric; exclude standalone "
        "numbers, dates, currencies, and generic company names."
    ),
    "product_kpi": (
        "A product-specific volume, price, mix, utilization, capacity, backlog, "
        "or demand metric."
    ),
    "segment_kpi": (
        "A business-segment-specific revenue, margin, volume, price, or demand metric."
    ),
}


class GLiNER2SpanBackend:
    """Schema-guided IR metric-span challenger backed by GLiNER2."""

    name = "GLINER2_IR_SPAN_CHALLENGER"
    IR_SOURCE_SLICES = frozenset({
        EncoderSourceSlice.IR_PREPARED_REMARKS,
        EncoderSourceSlice.IR_QA,
    })

    def __init__(
        self,
        *,
        checkpoint: str = "fastino/gliner2-base-v1",
        model_id: str = "fastino/gliner2-base-v1",
        model_revision: str = "main",
        entity_schema: Mapping[str, str] = DEFAULT_IR_ENTITY_SCHEMA,
        minimum_confidence: float = 0.50,
        local_files_only: bool = True,
        device_policy: TransformerDevicePolicy = TransformerDevicePolicy.CUDA_REQUIRED,
        extractor_factory: ExtractorFactory | None = None,
        torch_module=None,
    ) -> None:
        if not checkpoint.strip() or not model_id.strip() or not model_revision.strip():
            raise ValueError("GLiNER2 checkpoint identity cannot be blank")
        if not entity_schema or any(
            not str(label).strip() or not str(description).strip()
            for label, description in entity_schema.items()
        ):
            raise ValueError("GLiNER2 requires a non-empty entity schema")
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum span confidence must be within [0, 1]")
        self.checkpoint = checkpoint
        self.model_id = model_id
        self.model_revision = model_revision
        self.entity_schema = dict(entity_schema)
        self.minimum_confidence = minimum_confidence
        self.local_files_only = local_files_only
        self.device_policy = device_policy
        self._extractor_factory = extractor_factory
        self._torch_module = torch_module
        self._extractor = None
        self.device = (
            "cuda:pending"
            if device_policy is TransformerDevicePolicy.CUDA_REQUIRED
            else "cpu:pending"
        )

    def _build_extractor(self):
        try:
            selected = resolve_transformer_device(
                torch_module=self._torch_module,
                policy=self.device_policy,
            )
            self.device = selected.device
            if self._extractor_factory is not None:
                return self._extractor_factory(
                    checkpoint=self.checkpoint,
                    revision=self.model_revision,
                    device=selected.device,
                    local_files_only=self.local_files_only,
                )
            gliner2 = import_module("gliner2")
            # GLiNER2 prints a Unicode configuration banner while loading.
            # Windows terminals commonly default to cp949, which cannot encode
            # that banner and used to abort model construction before inference.
            # The banner is informational only, so isolate it in a Unicode-safe
            # in-memory stream without mutating the process-wide console codec.
            with redirect_stdout(StringIO()):
                extractor = gliner2.AutoExtractor.from_pretrained(
                    self.checkpoint,
                    revision=self.model_revision,
                    local_files_only=self.local_files_only,
                )
            extractor.to(selected.device)
            extractor.eval()
            return extractor
        except (
            ImportError,
            ModuleNotFoundError,
            OSError,
            RuntimeError,
            TransformerUnavailableError,
            ValueError,
        ) as exc:
            raise LearnedSpanUnavailableError(str(exc)) from exc

    def propose(
        self,
        block: TextBlock,
        source_slice: EncoderSourceSlice,
    ) -> tuple[LearnedSpanProposal, ...]:
        if source_slice not in self.IR_SOURCE_SLICES:
            raise LearnedSpanUnavailableError(
                "GLiNER2 is restricted to IR_PREPARED_REMARKS/IR_QA source slices"
            )
        if self._extractor is None:
            self._extractor = self._build_extractor()
        try:
            result = self._extractor.extract_entities(
                block.text,
                self.entity_schema,
                threshold=self.minimum_confidence,
                format_results=True,
                include_confidence=True,
                include_spans=True,
            )
            entities = result.get("entities")
            if not isinstance(entities, dict):
                raise TypeError("GLiNER2 response has no entity mapping")
            proposals = {}
            for label, mentions in entities.items():
                if mentions is None:
                    continue
                if not isinstance(mentions, list):
                    mentions = [mentions]
                for mention in mentions:
                    if not isinstance(mention, dict):
                        raise TypeError("GLiNER2 entity mention is not structured")
                    if "start" not in mention or "end" not in mention:
                        raise ValueError("GLiNER2 entity mention lacks exact offsets")
                    start = int(mention["start"])
                    end = int(mention["end"])
                    confidence = float(mention["confidence"])
                    if confidence < self.minimum_confidence:
                        continue
                    if not 0 <= start < end <= len(block.text):
                        raise ValueError("GLiNER2 entity offsets are outside the source")
                    literal = block.text[start:end]
                    if str(mention.get("text", "")) != literal:
                        raise ValueError("GLiNER2 entity literal does not match exact offsets")
                    proposal = LearnedSpanProposal(
                        source_sha256=block.source.sha256,
                        block_char_start=block.char_start,
                        block_char_end=block.char_end,
                        char_start=start,
                        char_end=end,
                        raw_text=literal,
                        raw_label=str(label),
                        confidence=confidence,
                        model_id=self.model_id,
                        model_revision=self.model_revision,
                        canonical_concept=None,
                    )
                    key = (start, end, str(label))
                    prior = proposals.get(key)
                    if prior is None or proposal.confidence > prior.confidence:
                        proposals[key] = proposal
            return tuple(proposals[key] for key in sorted(proposals))
        except LearnedSpanUnavailableError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise LearnedSpanUnavailableError(
                f"malformed GLiNER2 output: {exc}"
            ) from exc


__all__ = ["DEFAULT_IR_ENTITY_SCHEMA", "GLiNER2SpanBackend"]
