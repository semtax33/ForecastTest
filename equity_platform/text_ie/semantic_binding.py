from __future__ import annotations

from dataclasses import dataclass
import re

from .model import ConceptMention, QuantityMention
from .ontology import definition_for


@dataclass(frozen=True)
class MetricValueBinding:
    metric: ConceptMention
    value: QuantityMention
    relation: str


_BOUNDARY = re.compile(r"(?:[.!?][\"”']?\s+(?=[A-Z$])|\s*[•]\s*)")
_FORWARD_CUE = re.compile(
    r"\b(?:expect(?:s|ed)?|forecast(?:s|ed)?|project(?:s|ed)?|guidance|"
    r"target(?:s|ed)?|will|outlook)\b",
    re.IGNORECASE,
)
_METRIC_BEFORE_BRIDGE = re.compile(
    r"\b(?:was|were|is|are|stood\s+at|total(?:ed|s)?|generated|generates|"
    r"reached|approach(?:es|ed)?|had|has|of|to\s+be|to\s+total)\b",
    re.IGNORECASE,
)
_VALUE_BEFORE_BRIDGE = re.compile(
    r"^\s*(?:of|in)\s+(?:(?:annual|quarterly|pro\s+forma|total|segment)\s+){0,3}$",
    re.IGNORECASE,
)
_VALUE_LEADING_VERB = re.compile(
    r"\b(?:generated|generates|approach(?:es|ed)?|had|has|reported|reached|"
    r"represented|accounted\s+for|comprised|made\s+up)\s+"
    r"(?:approximately\s+|about\s+|roughly\s+)?$",
    re.IGNORECASE,
)
_ALTERNATE_OWNER = re.compile(
    r"\b(?:net income|operating income|operating profit|turnaround costs?|"
    r"dividends?|repurchases?|free cash flow|earnings per share|eps|"
    r"cash flow|credit facilit(?:y|ies)|acquisitions?|proceeds)\b",
    re.IGNORECASE,
)
_SENSITIVITY_SUFFIX = re.compile(
    r"^\s*(?:for\s+each|for\s+every|per\s+every)\b",
    re.IGNORECASE,
)


def _same_clause(text: str, left: int, right: int) -> bool:
    return _BOUNDARY.search(text[min(left, right) : max(left, right)]) is None


def _clause_start(text: str, position: int, limit: int = 160) -> int:
    start = max(0, position - limit)
    boundaries = tuple(_BOUNDARY.finditer(text[start:position]))
    return start + boundaries[-1].end() if boundaries else start


def _compatible(metric: ConceptMention, value: QuantityMention) -> bool:
    allowed = definition_for(metric.concept).quantity_kinds
    return not allowed or value.kind in allowed


def _safe_pair(
    text: str,
    metric: ConceptMention,
    value: QuantityMention,
    *,
    forward_only: bool,
) -> str | None:
    if not _compatible(metric, value) or not _same_clause(text, metric.char_start, value.char_start):
        return None
    if metric.char_end <= value.char_start:
        bridge = text[metric.char_end : value.char_start]
        if len(bridge) > 160 or _ALTERNATE_OWNER.search(bridge):
            return None
        if _METRIC_BEFORE_BRIDGE.search(bridge) is None:
            return None
        suffix = text[value.char_end : min(len(text), value.char_end + 32)]
        if _SENSITIVITY_SUFFIX.search(suffix) is not None:
            return None
        cue_window = text[_clause_start(text, metric.char_start) : value.char_start]
        if forward_only and _FORWARD_CUE.search(cue_window) is None:
            return None
        return "METRIC_BEFORE_VALUE"

    bridge = text[value.char_end : metric.char_start]
    if len(bridge) > 72 or _ALTERNATE_OWNER.search(bridge):
        return None
    if _VALUE_BEFORE_BRIDGE.fullmatch(bridge) is None:
        return None
    prefix = text[_clause_start(text, value.char_start) : value.char_start]
    if _VALUE_LEADING_VERB.search(prefix) is None and _FORWARD_CUE.search(prefix) is None:
        return None
    if forward_only and _FORWARD_CUE.search(prefix) is None:
        return None
    return "VALUE_BEFORE_METRIC"


def bind_metric_values(
    text: str,
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
    *,
    forward_only: bool = False,
) -> tuple[MetricValueBinding, ...]:
    """Return deterministic one-to-one local KPI/value bindings.

    The resolver supports both common English orders (``revenue was $X`` and
    ``generated $X in annual revenue``), but only across bounded lexical
    bridges.  It never uses issuer identity or a positional table selector.
    """

    proposals: list[tuple[int, ConceptMention, QuantityMention, str]] = []
    for metric in concepts:
        for value in quantities:
            left = min(metric.char_end, value.char_end)
            right = max(metric.char_start, value.char_start)
            if any(
                other is not value
                and left <= other.char_start
                and other.char_end <= right
                for other in quantities
            ):
                continue
            relation = _safe_pair(
                text,
                metric,
                value,
                forward_only=forward_only,
            )
            if relation is None:
                continue
            distance = max(metric.char_start, value.char_start) - min(
                metric.char_end, value.char_end
            )
            proposals.append((max(0, distance), metric, value, relation))

    used_metrics: set[tuple[int, int]] = set()
    used_values: set[tuple[int, int]] = set()
    selected: list[MetricValueBinding] = []
    for _, metric, value, relation in sorted(
        proposals,
        key=lambda item: (
            item[0],
            min(item[1].char_start, item[2].char_start),
            item[1].char_start,
        ),
    ):
        metric_key = (metric.char_start, metric.char_end)
        value_key = (value.char_start, value.char_end)
        if metric_key in used_metrics or value_key in used_values:
            continue
        used_metrics.add(metric_key)
        used_values.add(value_key)
        selected.append(MetricValueBinding(metric, value, relation))
    return tuple(sorted(selected, key=lambda item: item.metric.char_start))
