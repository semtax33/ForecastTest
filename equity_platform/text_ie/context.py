from __future__ import annotations

from dataclasses import dataclass
import re

from .model import (
    ConceptMention,
    PeriodSemantics,
    Polarity,
    Qualifier,
    SemanticFrame,
    TextBlock,
)
from .ontology import resolve_scope
from .quantities import extract_years


NEGATION = re.compile(
    r"\b(?:not|no longer|did not|does not|do not|excluding|except)\b",
    re.IGNORECASE,
)
ANTECEDENT = re.compile(
    r"\b(?:this amount|that amount|of this|of which|thereof)\b",
    re.IGNORECASE,
)


@dataclass
class ContextStack:
    concept: str | None = None
    scope: str = "CONSOLIDATED"
    period: str | None = None
    sentence_index: int = -10

    def resolve_concepts(
        self,
        block: TextBlock,
        mentions: tuple[ConceptMention, ...],
    ) -> tuple[ConceptMention, ...]:
        if mentions:
            return mentions
        if (
            self.concept
            and block.sentence_index - self.sentence_index <= 2
            and ANTECEDENT.search(block.text)
        ):
            match = ANTECEDENT.search(block.text)
            assert match is not None
            return (
                ConceptMention(
                    concept=self.concept,
                    alias=match.group(0),
                    char_start=match.start(),
                    char_end=match.end(),
                ),
            )
        return ()

    def resolve_scope(self, block: TextBlock) -> str:
        scope = resolve_scope(block.text, block.nearest_heading)
        if scope == "CONSOLIDATED" and self.scope != "CONSOLIDATED":
            if block.sentence_index - self.sentence_index <= 2 and ANTECEDENT.search(block.text):
                return self.scope
        return scope

    def update(self, block: TextBlock, concept: str, scope: str, period: str) -> None:
        self.concept = concept
        self.scope = scope
        self.period = period
        self.sentence_index = block.sentence_index


def polarity(text: str) -> Polarity:
    match = NEGATION.search(text)
    return Polarity(
        positive=match is None,
        cue=match.group(0) if match else None,
        cue_start=match.start() if match else None,
        cue_end=match.end() if match else None,
    )


def qualifier(text: str) -> Qualifier:
    folded = text.casefold()
    cues = tuple(
        cue
        for cue in (
            "approximately",
            "substantially",
            "primarily",
            "materially",
            "expected",
            "expects",
            "roughly",
            "at least",
            "more than",
            "up to",
        )
        if cue in folded
    )
    return Qualifier(
        approximation=any(cue in folded for cue in ("approximately", "roughly")),
        forward_looking=any(cue in folded for cue in ("expected", "expects", "guidance")),
        lower_bound=any(cue in folded for cue in ("at least", "more than")),
        upper_bound="up to" in folded,
        materiality="materially" in folded,
        cues=cues,
    )


def resolve_period(
    block: TextBlock,
    frame: SemanticFrame,
) -> tuple[str, PeriodSemantics]:
    years = extract_years(block.text)
    if frame in {SemanticFrame.NOT_EXPECTED, SemanticFrame.RANGE_GUIDANCE}:
        if years:
            return str(years[-1][0]), PeriodSemantics.FORECAST
        return str(block.document_period or "UNRESOLVED"), PeriodSemantics.FORECAST
    if "year-end" in block.text.casefold() or "at december 31" in block.text.casefold():
        if years:
            return str(years[0][0]), PeriodSemantics.END_OF_PERIOD
        return str(block.document_period or "UNRESOLVED"), PeriodSemantics.END_OF_PERIOD
    if years:
        return str(years[0][0]), PeriodSemantics.DURATION
    return str(block.document_period or "UNRESOLVED"), PeriodSemantics.DOCUMENT_PERIOD
