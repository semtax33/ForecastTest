from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from equity_platform.documents import CanonicalDocument
from equity_platform.documents.table_reconstruction import reconstruct_flattened_table
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import TextRuleIR, compile_text_rule_file
from ..ontology import definition_for, find_concepts
from ..model import QuantityKind, QuantityMention
from ..quantities import extract_quantities
from .model import CandidateOrigin, MetricAnchor, RecallCandidate


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v24_high_recall.arc"
V24_RULES = compile_text_rule_file(RULE_PATH)
_ALIAS_BLOCK = re.compile(r'alias\s+"([A-Z0-9_]+)"\s*\{(.*?)\}', re.DOTALL)
_TERMS = re.compile(r"terms\s*=\s*(\[[^\]]*\])", re.DOTALL)
_BOUNDARY = re.compile(r"(?:[.!?][\"”']?\s+(?=[A-Z$])|[•·])")
_HYPHENATED_BPS = re.compile(
    r"(?P<raw>(?P<number>-?\d[\d,]*(?:\.\d+)?)\s*[-–]?\s*basis[- ]points?)",
    re.IGNORECASE,
)


def extract_candidate_quantities(text: str) -> tuple[QuantityMention, ...]:
    quantities = list(extract_quantities(text))
    occupied = [(item.char_start, item.char_end) for item in quantities]
    for match in _HYPHENATED_BPS.finditer(text):
        if any(match.start() < end and start < match.end() for start, end in occupied):
            continue
        quantities.append(
            QuantityMention(
                kind=QuantityKind.BASIS_POINTS,
                value=float(match.group("number").replace(",", "")),
                unit="BASIS_POINTS",
                raw=match.group("raw"),
                char_start=match.start(),
                char_end=match.end(),
            )
        )
    return tuple(sorted(quantities, key=lambda item: item.char_start))


def load_v24_aliases(path: Path = RULE_PATH) -> dict[str, tuple[str, ...]]:
    text = path.read_text(encoding="utf-8")
    aliases: dict[str, tuple[str, ...]] = {}
    for concept, body in _ALIAS_BLOCK.findall(text):
        match = _TERMS.search(body)
        if match is None:
            raise ValueError(f"V2.4 alias {concept} has no terms")
        terms = json.loads(match.group(1))
        definition_for(concept)
        aliases[concept] = tuple(str(term) for term in terms)
    return aliases


def metric_anchors(text: str, heading: str | None) -> tuple[MetricAnchor, ...]:
    anchors = [
        MetricAnchor(item.concept, item.alias, item.char_start, item.char_end)
        for item in find_concepts(text)
    ]
    for concept, aliases in load_v24_aliases().items():
        for alias in aliases:
            for match in re.finditer(
                rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
                text,
                re.IGNORECASE,
            ):
                anchors.append(
                    MetricAnchor(concept, match.group(0), match.start(), match.end())
                )
    selected: list[MetricAnchor] = []
    for anchor in sorted(
        anchors,
        key=lambda item: (item.char_start, -(item.char_end - item.char_start)),
    ):
        if any(
            anchor.char_start < prior.char_end and prior.char_start < anchor.char_end
            for prior in selected
        ):
            continue
        selected.append(anchor)
    if not selected and heading:
        heading_mentions = find_concepts(heading)
        selected.extend(
            MetricAnchor(
                item.concept,
                item.alias,
                0,
                0,
                inherited_from="HEADING",
            )
            for item in heading_mentions
        )
    return tuple(selected)


def _same_fragment(text: str, anchor: MetricAnchor, quantity: object) -> bool:
    if anchor.inherited_from:
        return True
    left = min(anchor.char_end, quantity.char_end)
    right = max(anchor.char_start, quantity.char_start)
    return _BOUNDARY.search(text[left:right]) is None


def _compatible(anchor: MetricAnchor, quantity: object) -> bool:
    kinds = definition_for(anchor.concept).quantity_kinds
    return not kinds or quantity.kind in kinds or quantity.unit in {"PERCENT", "BASIS_POINTS"}


def generate_recall_candidates(
    document: CanonicalDocument,
    rules: tuple[TextRuleIR, ...] = V24_RULES,
) -> tuple[tuple[RecallCandidate, ...], tuple[object, ...]]:
    candidates: list[RecallCandidate] = []
    table_routes: list[object] = []
    for block in document_text_blocks(document):
        table = reconstruct_flattened_table(block)
        if table is not None:
            table_routes.append(table)
            continue
        anchors = metric_anchors(block.text, block.nearest_heading)
        quantities = extract_candidate_quantities(block.text)
        folded = block.text.casefold()
        active_rules = tuple(
            rule.rule_id
            for rule in rules
            if any(trigger in folded for trigger in rule.triggers)
        )
        for anchor in anchors:
            nearby = tuple(
                quantity
                for quantity in quantities
                if _compatible(anchor, quantity)
                and _same_fragment(block.text, anchor, quantity)
                and (
                    anchor.inherited_from is not None
                    or max(anchor.char_start, quantity.char_start)
                    - min(anchor.char_end, quantity.char_end)
                    <= 360
                )
            )
            origins = {CandidateOrigin.SENTENCE_WINDOW}
            if any(
                abs(quantity.char_start - anchor.char_start) <= 200
                for quantity in nearby
            ):
                origins.add(CandidateOrigin.TOKEN_WINDOW)
            if anchor.inherited_from:
                origins.add(CandidateOrigin.HEADING_INHERITANCE)
            if any(
                symbol in block.text[
                    min(anchor.char_end, quantity.char_end) : max(anchor.char_start, quantity.char_start)
                ]
                for quantity in nearby
                for symbol in (":", ";", "(", ")", "•", "·")
            ):
                origins.add(CandidateOrigin.PUNCTUATION_PATTERN)
            if block.inline_fact_indices:
                origins.add(CandidateOrigin.INLINE_XBRL)
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{anchor.concept}:"
                f"{anchor.char_start}:{anchor.char_end}".encode()
            ).hexdigest()[:20]
            candidates.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=anchor,
                    quantities=nearby,
                    origins=tuple(sorted(origins, key=str)),
                    rule_ids=active_rules or ("v24.proximity",),
                )
            )
    return tuple(candidates), tuple(table_routes)
