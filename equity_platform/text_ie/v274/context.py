from __future__ import annotations

from dataclasses import dataclass

from ..model import TextBlock
from ..spacy_backend import SpacySemanticBackend


@dataclass(frozen=True)
class BoundedSemanticContext:
    """Hierarchy labels only; numeric evidence never leaves the local block."""

    heading: str
    section: str
    previous: str
    guidance: bool
    table_family: bool


_GUIDANCE_CUES = (
    "guidance",
    "financial outlook",
    "business outlook",
    "financial targets",
)
_TABLE_CUES = (
    "supplemental information",
    "reconciliation",
    "financial schedules",
    "balance sheet highlights",
)


def bounded_context(
    block: TextBlock,
    backend: SpacySemanticBackend,
) -> BoundedSemanticContext:
    heading = block.nearest_heading or ""
    section = block.section or ""
    previous = block.previous_sentence or ""
    parent_text = " ".join(part for part in (heading, section) if part)
    # Previous text is intentionally accepted only when it is itself a short
    # heading-like cue.  Its quantities are never passed to extraction.
    prior_heading = previous if sum(token.is_alpha for token in backend.parse(previous)) <= 8 else ""
    guidance = bool(backend.phrase_mentions(parent_text + " " + prior_heading, _GUIDANCE_CUES))
    table_family = bool(backend.phrase_mentions(parent_text, _TABLE_CUES))
    return BoundedSemanticContext(
        heading=heading,
        section=section,
        previous=prior_heading,
        guidance=guidance,
        table_family=table_family,
    )


def has_guidance_context(
    block: TextBlock,
    backend: SpacySemanticBackend,
) -> bool:
    """Accept a local guidance label or a bounded structural parent.

    The local text is used only as a categorical gate.  Numeric mentions still
    have to satisfy the rule inside the current clause.
    """

    return bounded_context(block, backend).guidance or bool(
        backend.phrase_mentions(block.text, _GUIDANCE_CUES)
    )
