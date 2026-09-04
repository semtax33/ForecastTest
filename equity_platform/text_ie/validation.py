from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from .model import KPIFrame, QuantityKind, SemanticFrame, VerificationStatus
from .ontology import definition_for


class FrameValidationError(ValueError):
    pass


def _base_concept(concept: str) -> str:
    base = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_NOT_EXPECTED", "_GUIDANCE", "_CHANGE"):
        base = base.removesuffix(suffix)
    return base


def _quantity_kind(frame: KPIFrame) -> QuantityKind | None:
    if frame.value is None:
        return None
    if frame.unit == "USD":
        return QuantityKind.MONEY
    if str(frame.unit).startswith("USD_PER_"):
        return QuantityKind.PRICE
    if frame.unit == "PERCENT":
        return QuantityKind.PERCENT
    if frame.unit == "BASIS_POINTS":
        return QuantityKind.BASIS_POINTS
    if frame.unit == "X":
        return QuantityKind.RATE
    return QuantityKind.COUNT


def validate_kpi_frame(frame: KPIFrame, document: CanonicalDocument) -> KPIFrame:
    """Promote a proposed frame only after deterministic source/ontology checks."""

    if frame.source.sha256 != document.source.sha256:
        raise FrameValidationError("Frame source does not match its canonical document")
    start, end = frame.source_span.char_start, frame.source_span.char_end
    if end > len(document.text) or document.text[start:end] != frame.source_span.literal:
        raise FrameValidationError("Frame source span is not an exact document substring")
    try:
        definition = definition_for(_base_concept(frame.concept))
    except KeyError as exc:
        raise FrameValidationError(str(exc)) from exc
    kind = _quantity_kind(frame)
    if kind is not None and definition.quantity_kinds and kind not in definition.quantity_kinds:
        raise FrameValidationError(
            f"{frame.concept} does not accept quantity kind {kind.value}"
        )
    if (frame.lower_value is None) != (frame.upper_value is None):
        raise FrameValidationError("Range frames require both endpoints")
    if frame.lower_value is not None:
        assert frame.upper_value is not None
        if frame.value is None or not frame.lower_value <= frame.value <= frame.upper_value:
            raise FrameValidationError("Range midpoint must lie within its endpoints")
    if frame.frame is SemanticFrame.NOT_EXPECTED and frame.polarity.positive:
        raise FrameValidationError("NOT_EXPECTED frames require an explicit negation cue")
    if frame.period == "UNRESOLVED":
        raise FrameValidationError("Frame period is unresolved")
    return replace(
        frame,
        verification_status=VerificationStatus.VERIFIED,
        verified_by="DETERMINISTIC_KPI_FRAME_VALIDATOR",
    )
