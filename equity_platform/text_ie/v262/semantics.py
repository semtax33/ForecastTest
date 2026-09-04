from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import re

from equity_platform.documents import CanonicalDocument

from ..model import KPIFrame, QuantityKind, QuantityMention, SemanticFrame, TextBlock
from ..quantities import extract_quantities
from ..validation import FrameValidationError, validate_kpi_frame
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v261.semantics import _Anchor, _frame


_ADJUSTED_EBIT_MARGIN = re.compile(r"\badjusted\s+EBIT\s+margin\b", re.I)
_REVENUE_GROWTH_RANGE = re.compile(
    r"\brevenues?\b.{0,80}?\bgrowth\s+of\s+"
    r"(?P<low>-?\d+(?:\.\d+)?)\s*%\s+to\s+"
    r"(?P<high>-?\d+(?:\.\d+)?)\s*%",
    re.I,
)
_MARGIN_RANGE = re.compile(
    r"\badjusted\s+EBIT\s+margin\s+expansion\s+of\s+"
    r"(?P<low>-?\d+(?:\.\d+)?)\s+to\s+"
    r"(?P<high>-?\d+(?:\.\d+)?)\s+basis\s+points?",
    re.I,
)
_REVENUE_LEVEL_RANGE = re.compile(
    r"\brevenues?\s+in\s+the\s+range\s+of\s+"
    r"(?P<low>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)"
    r"\s+to\s+"
    r"(?P<high>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)",
    re.I,
)
_MARGIN_CHANGE = re.compile(
    r"\b(?P<label>gross\s+margin|operating\s+margin)\b.{0,24}?"
    r"(?P<delta>-?\d+(?:\.\d+)?)\s*(?:basis\s+points?|bps?)",
    re.I,
)
_EBIT_MARGIN_CHANGE_TO = re.compile(
    r"\badjusted\s+EBIT\s+margin\s+increased\s+"
    r"(?P<delta>\d+(?:\.\d+)?)\s*(?:basis\s+points?|bps?)\s+to\s+"
    r"(?P<level>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_REVENUE_TOTAL_CHANGE = re.compile(
    r"\brevenues?\s+totaled\s+"
    r"(?P<level>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)"
    r".{0,100}?\bor\s+(?P<delta>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_ORGANIC_SECOND_DELTA = re.compile(
    r"\band\s+(?P<delta>\d+(?:\.\d+)?)\s*%\s+on\s+an?\s+organic",
    re.I,
)
_REVENUE_TARGET = re.compile(
    r"\brevenues?\s+growing\s+to\s+"
    r"(?P<level>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)",
    re.I,
)
_REVENUE_ABSOLUTE = re.compile(
    r"\brevenues?\s*(?::|(?:of|were)\s+|(?:totaled|reported)\s+)?"
    r"(?P<level>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)",
    re.I,
)
_CAPEX_AFTER = re.compile(
    r"\bcapital\s+investments?\s+of\s+"
    r"(?P<level>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)",
    re.I,
)
_CAPEX_BEFORE = re.compile(
    r"\binvested\s+(?P<level>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)"
    r"\s+in\s+capital\s+expenditures?",
    re.I,
)
_CASH_REDUCTION = re.compile(
    r"(?P<level>\$\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|mm|b|m)?)"
    r".{0,140}?\breduction\s+to\s+cash(?:\s+and\s+cash\s+equivalents)?",
    re.I,
)


def _block_candidates(
    candidates: tuple[RecallCandidate, ...], block: TextBlock
) -> tuple[RecallCandidate, ...]:
    return tuple(item for item in candidates if item.block.char_start == block.char_start)


def augment_candidates_v262(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
) -> tuple[RecallCandidate, ...]:
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in candidates
    }
    blocks = {item.block.char_start: item.block for item in candidates}
    for block in blocks.values():
        for match in _ADJUSTED_EBIT_MARGIN.finditer(block.text):
            signature = (block.char_start, "OPERATING_MARGIN", match.start(), match.end())
            if signature in seen:
                continue
            quantities = tuple(
                quantity
                for quantity in extract_quantities(block.text)
                if quantity.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
                and abs(quantity.char_start - match.start()) <= 240
            )
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:OPERATING_MARGIN:"
                f"{match.start()}:{match.end()}:v262".encode()
            ).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(
                        "OPERATING_MARGIN",
                        match.group(0),
                        match.start(),
                        match.end(),
                    ),
                    quantities=quantities,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.TOKEN_WINDOW),
                    rule_ids=("v262.adjusted_ebit_margin_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _quantity(text: str, start: int, end: int) -> QuantityMention:
    quantities = [
        item
        for item in extract_quantities(text)
        if item.char_start >= start and item.char_end <= end
    ]
    if len(quantities) != 1:
        raise ValueError(f"Expected one quantity in span {text[start:end]!r}")
    return quantities[0]


def _anchor(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concept: str,
    start: int,
    end: int,
) -> _Anchor:
    match = next(
        (
            item
            for item in _block_candidates(candidates, block)
            if item.metric.concept == concept
            and item.metric.char_start <= start
            and item.metric.char_end >= end
        ),
        None,
    )
    candidate_id = (
        match.candidate_id
        if match
        else "v262.direct."
        + sha256(
            f"{document.source.sha256}:{block.char_start}:{start}:{concept}".encode()
        ).hexdigest()[:16]
    )
    return _Anchor(concept, start, end, candidate_id)


def _range_frame(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    match: re.Match[str],
    *,
    anchor_concept: str,
    output_concept: str,
    anchor_span: tuple[int, int],
    kind: QuantityKind,
    unit: str,
) -> KPIFrame | None:
    if kind is QuantityKind.MONEY:
        low_quantity = _quantity(block.text, match.start("low"), match.end("low"))
        high_quantity = _quantity(block.text, match.start("high"), match.end("high"))
        low, high = low_quantity.value, high_quantity.value
    else:
        low = float(match.group("low").replace(",", "").replace("$", "").strip())
        high = float(match.group("high").replace(",", "").replace("$", "").strip())
    midpoint = QuantityMention(
        kind=kind,
        value=(low + high) / 2,
        unit=unit,
        raw=match.group(0),
        char_start=match.start("low"),
        char_end=match.end("high"),
    )
    anchor = _anchor(document, block, candidates, anchor_concept, *anchor_span)
    frame = _frame(
        document,
        block,
        (0, len(block.text), block.text),
        anchor,
        concept=output_concept,
        semantic=SemanticFrame.RANGE_GUIDANCE,
        value=midpoint,
        rule_id="v262.range_guidance",
    )
    if frame is None:
        return None
    try:
        return replace(
            validate_kpi_frame(
                replace(frame, lower_value=low, upper_value=high),
                document,
            ),
            verified_by="V262_RANGE_GUIDANCE_VERIFIER",
        )
    except FrameValidationError:
        return None


def _direct_frame(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    *,
    concept: str,
    output_concept: str | None,
    anchor_span: tuple[int, int],
    value: QuantityMention,
    semantic: SemanticFrame,
    change: QuantityMention | None = None,
    direction: int = 1,
    rule_id: str,
) -> KPIFrame | None:
    return _frame(
        document,
        block,
        (0, len(block.text), block.text),
        _anchor(document, block, candidates, concept, *anchor_span),
        concept=output_concept or concept,
        semantic=semantic,
        value=value,
        change=change,
        direction=direction,
        rule_id=rule_id,
    )


def recover_v262_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        text = block.text
        for match in _REVENUE_GROWTH_RANGE.finditer(text):
            anchor_match = re.search(r"\brevenues?\b", match.group(0), re.I)
            assert anchor_match is not None
            start = match.start() + anchor_match.start()
            frame = _range_frame(
                document,
                block,
                candidates,
                match,
                anchor_concept="REVENUE",
                output_concept="REVENUE_GUIDANCE",
                anchor_span=(start, start + len(anchor_match.group(0))),
                kind=QuantityKind.PERCENT,
                unit="PERCENT",
            )
            if frame:
                output.append(frame)
        for match in _MARGIN_RANGE.finditer(text):
            anchor_match = _ADJUSTED_EBIT_MARGIN.search(text, match.start(), match.end())
            assert anchor_match is not None
            frame = _range_frame(
                document,
                block,
                candidates,
                match,
                anchor_concept="OPERATING_MARGIN",
                output_concept="OPERATING_MARGIN_GUIDANCE",
                anchor_span=(anchor_match.start(), anchor_match.end()),
                kind=QuantityKind.BASIS_POINTS,
                unit="BASIS_POINTS",
            )
            if frame:
                output.append(frame)
        for match in _REVENUE_LEVEL_RANGE.finditer(text):
            anchor_match = re.search(r"\brevenues?\b", match.group(0), re.I)
            assert anchor_match is not None
            start = match.start() + anchor_match.start()
            frame = _range_frame(
                document,
                block,
                candidates,
                match,
                anchor_concept="REVENUE",
                output_concept="REVENUE_GUIDANCE",
                anchor_span=(start, start + len(anchor_match.group(0))),
                kind=QuantityKind.MONEY,
                unit="USD",
            )
            if frame:
                output.append(frame)
        for match in _MARGIN_CHANGE.finditer(text):
            concept = "GROSS_MARGIN" if "gross" in match.group("label").casefold() else "OPERATING_MARGIN"
            delta = _quantity(text, match.start("delta"), match.end())
            delta = replace(delta, value=abs(delta.value))
            frame = _direct_frame(
                document,
                block,
                candidates,
                concept=concept,
                output_concept=None,
                anchor_span=(match.start("label"), match.end("label")),
                value=delta,
                semantic=SemanticFrame.CHANGE_BY,
                direction=-1 if match.group("delta").startswith("-") else 1,
                rule_id="v262.signed_margin_delta",
            )
            if frame:
                output.append(frame)
        for match in _EBIT_MARGIN_CHANGE_TO.finditer(text):
            anchor_match = _ADJUSTED_EBIT_MARGIN.search(text, match.start(), match.end())
            assert anchor_match is not None
            level = _quantity(text, match.start("level"), match.end("level") + 1)
            delta = _quantity(text, match.start("delta"), match.end("delta") + len(" basis points"))
            frame = _direct_frame(
                document,
                block,
                candidates,
                concept="OPERATING_MARGIN",
                output_concept=None,
                anchor_span=(anchor_match.start(), anchor_match.end()),
                value=level,
                change=delta,
                semantic=SemanticFrame.CHANGE_TO,
                rule_id="v262.ebit_margin_change",
            )
            if frame:
                output.append(frame)
        for match in _REVENUE_TOTAL_CHANGE.finditer(text):
            anchor_match = re.search(r"\brevenues?\b", match.group(0), re.I)
            assert anchor_match is not None
            start = match.start() + anchor_match.start()
            frame = _direct_frame(
                document,
                block,
                candidates,
                concept="REVENUE",
                output_concept=None,
                anchor_span=(start, start + len(anchor_match.group(0))),
                value=_quantity(text, match.start("level"), match.end("level")),
                change=_quantity(text, match.start("delta"), match.end("delta") + 1),
                semantic=SemanticFrame.CHANGE_TO,
                rule_id="v262.revenue_total_change",
            )
            if frame:
                output.append(frame)
        for match in _ORGANIC_SECOND_DELTA.finditer(text):
            revenue = re.search(r"\brevenues?\b", text, re.I)
            if revenue:
                frame = _direct_frame(
                    document,
                    block,
                    candidates,
                    concept="REVENUE",
                    output_concept=None,
                    anchor_span=(revenue.start(), revenue.end()),
                    value=_quantity(text, match.start("delta"), match.end("delta") + 1),
                    semantic=SemanticFrame.CHANGE_BY,
                    rule_id="v262.organic_secondary_delta",
                )
                if frame:
                    output.append(frame)
        for match in _REVENUE_TARGET.finditer(text):
            revenue = re.search(r"\brevenues?\b", match.group(0), re.I)
            assert revenue is not None
            start = match.start() + revenue.start()
            frame = _direct_frame(
                document,
                block,
                candidates,
                concept="REVENUE",
                output_concept="REVENUE_GUIDANCE",
                anchor_span=(start, start + len(revenue.group(0))),
                value=_quantity(text, match.start("level"), match.end("level")),
                semantic=SemanticFrame.CHANGE_TO,
                rule_id="v262.revenue_target",
            )
            if frame:
                output.append(frame)
        for match in _REVENUE_ABSOLUTE.finditer(text):
            local_tail = text[match.end() : min(len(text), match.end() + 100)]
            if re.search(
                r"\b(?:compared|increase|increased|grew|decrease|decreased|declined)\b",
                local_tail,
                re.I,
            ):
                continue
            revenue = re.search(r"\brevenues?\b", match.group(0), re.I)
            assert revenue is not None
            start = match.start() + revenue.start()
            frame = _direct_frame(
                document,
                block,
                candidates,
                concept="REVENUE",
                output_concept=None,
                anchor_span=(start, start + len(revenue.group(0))),
                value=_quantity(text, match.start("level"), match.end("level")),
                semantic=SemanticFrame.ABSOLUTE_VALUE,
                rule_id="v262.explicit_revenue_level",
            )
            if frame:
                output.append(frame)
        for pattern, concept, semantic, direction, rule_id in (
            (_CAPEX_AFTER, "CAPEX", SemanticFrame.ABSOLUTE_VALUE, 1, "v262.capital_investment"),
            (_CAPEX_BEFORE, "CAPEX", SemanticFrame.ABSOLUTE_VALUE, 1, "v262.invested_capex"),
            (_CASH_REDUCTION, "CASH", SemanticFrame.CHANGE_BY, -1, "v262.cash_reduction"),
        ):
            for match in pattern.finditer(text):
                anchor_pattern = re.compile(
                    r"capital\s+investments?|capital\s+expenditures?|cash(?:\s+and\s+cash\s+equivalents)?",
                    re.I,
                )
                anchor_match = anchor_pattern.search(text, match.start(), match.end())
                if anchor_match is None:
                    continue
                frame = _direct_frame(
                    document,
                    block,
                    candidates,
                    concept=concept,
                    output_concept=None,
                    anchor_span=(anchor_match.start(), anchor_match.end()),
                    value=_quantity(text, match.start("level"), match.end("level")),
                    semantic=semantic,
                    direction=direction,
                    rule_id=rule_id,
                )
                if frame:
                    output.append(frame)
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in output:
        unique.setdefault(
            (
                frame.concept,
                frame.frame,
                frame.value,
                frame.change,
                frame.lower_value,
                frame.upper_value,
                frame.source_span.char_start,
            ),
            frame,
        )
    return tuple(unique.values())


def safe_existing_frame_v262(frame: KPIFrame) -> bool:
    text = frame.source_span.literal
    if (
        frame.concept.removeprefix("PRIOR_YEAR_") == "REVENUE"
        and re.search(r"\bpre-tax\s+(?:income|profit)\b", text, re.I)
        and re.search(r"\brecord\s+quarterly\s+revenues?\b", text, re.I)
    ):
        return False
    if frame.concept == "EBIT" and _ADJUSTED_EBIT_MARGIN.search(text):
        margin = _EBIT_MARGIN_CHANGE_TO.search(text)
        if margin and (
            frame.change_unit == "BASIS_POINTS"
            or frame.change == float(margin.group("level"))
        ):
            return False
    if (
        frame.concept == "EBIT_GUIDANCE"
        and frame.frame is SemanticFrame.RANGE_GUIDANCE
        and frame.lower_value is not None
        and frame.upper_value is not None
        and re.search(
            rf"\badjusted\s+diluted\s+EPS\s+growth\s+of\s+"
            rf"{re.escape(str(frame.lower_value).removesuffix('.0'))}\s*%\s+to\s+"
            rf"{re.escape(str(frame.upper_value).removesuffix('.0'))}\s*%",
            text,
            re.I,
        )
    ):
        return False
    organic = _ORGANIC_SECOND_DELTA.search(text)
    if (
        organic
        and frame.concept == "REVENUE"
        and frame.frame is SemanticFrame.CHANGE_TO
        and frame.change == float(organic.group("delta"))
    ):
        return False
    return True
