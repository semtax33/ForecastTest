from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .annotation import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    PairProposal,
    TextSpan,
)


_IDENTITY_FIELDS = (
    "context_id",
    "source_slice",
    "entity",
    "source_sha256",
    "source_path",
    "document_char_start",
    "document_char_end",
    "text",
    "candidate_pair_count",
)
_MISSING_FIELDS = (
    "missing_metric_mentions",
    "missing_quantity_mentions",
)
_TRUE = {"TRUE", "YES"}
_FALSE = {"FALSE", "NO"}
_RECOVERY_ACTIONS = {
    "FALSE_ALARM_GRAPH_COMPLETE",
    "ADD_MISSING_CANDIDATES",
    "ARCHIVE_UNRECOVERABLE",
}
_REVIEW_FIELDS = {
    "recovery_action",
    "reviewed_missing_metric_mentions",
    "reviewed_missing_quantity_mentions",
    "reviewed_missing_pairs",
    "reviewer_id",
    "review_notes",
}


@dataclass(frozen=True)
class MissingMentionHint:
    kind: str
    literal: str
    char_start: int
    char_end: int
    channels: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "literal": self.literal,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "channels": list(self.channels),
        }


@dataclass(frozen=True)
class ContextRecoveryCase:
    context_id: str
    source_slice: str
    entity: str
    source_sha256: str
    source_path: str
    document_char_start: int
    document_char_end: int
    text: str
    candidate_pair_count: int
    incomplete_channels: tuple[str, ...]
    metric_hints: tuple[MissingMentionHint, ...]
    quantity_hints: tuple[MissingMentionHint, ...]
    unresolved_hints: tuple[str, ...]
    reported_missing_pairs: tuple[str, ...]


@dataclass(frozen=True)
class ContextRecoveryApplication:
    items: tuple[AnnotationReviewItem, ...]
    context_ids: frozenset[str]
    action_counts: dict[str, int]
    context_count: int
    archived_context_count: int
    original_pair_count: int
    recovered_pair_count: int
    added_pair_count: int


@dataclass(frozen=True)
class RecoveryClosureSelection:
    context_ids: frozenset[str]
    context_counts: dict[str, int]
    pair_counts: dict[str, int]
    pair_count: int
    entity_count: int


def _read_index(path: Path, expected_channel: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise ValueError(f"missing context audit file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(dict(row) for row in csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty context audit file: {path}")
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        context_id = row.get("context_id", "").strip()
        if not context_id or context_id in output:
            raise ValueError("context audits require unique non-empty context_id")
        if row.get("annotation_channel", "").strip() != expected_channel:
            raise ValueError(f"context audit channel must be {expected_channel}")
        output[context_id] = row
    return output


def _is_complete(row: dict[str, str], channel: str) -> bool:
    value = row.get("candidate_graph_complete", "").strip().upper()
    if value in _TRUE:
        if any(row.get(field, "").strip() for field in (*_MISSING_FIELDS, "missing_pairs")):
            raise ValueError(f"complete channel {channel} cannot report missing candidates")
        return True
    if value not in _FALSE:
        raise ValueError(f"channel {channel} requires a TRUE/FALSE graph decision")
    if not any(row.get(field, "").strip() for field in (*_MISSING_FIELDS, "missing_pairs")):
        raise ValueError(f"incomplete channel {channel} requires recovery details")
    return False


def _hint_parts(raw: str) -> tuple[str, int] | None:
    value = raw.strip()
    if "@" not in value:
        return None
    literal, offset = value.rsplit("@", 1)
    literal = literal.strip()
    offset = offset.strip()
    if not literal or not offset.isdecimal():
        return None
    return literal, int(offset)


def _collect_hints(
    *,
    rows: tuple[tuple[str, dict[str, str]], ...],
    text: str,
) -> tuple[
    tuple[MissingMentionHint, ...],
    tuple[MissingMentionHint, ...],
    tuple[str, ...],
]:
    hints: dict[tuple[str, str, int], set[str]] = {}
    unresolved: list[str] = []
    for channel, row in rows:
        for field, kind in (
            ("missing_metric_mentions", "METRIC"),
            ("missing_quantity_mentions", "QUANTITY"),
        ):
            for raw in row.get(field, "").split(";"):
                value = raw.strip()
                if not value:
                    continue
                parsed = _hint_parts(value)
                if parsed is None:
                    unresolved.append(f"{channel}:{field}:{value}")
                    continue
                literal, start = parsed
                end = start + len(literal)
                if start < 0 or end > len(text) or text[start:end] != literal:
                    raise ValueError(
                        "missing mention hint does not match source: "
                        f"{channel}:{field}:{value}"
                    )
                hints.setdefault((kind, literal, start), set()).add(channel)
    materialized = tuple(
        MissingMentionHint(
            kind=kind,
            literal=literal,
            char_start=start,
            char_end=start + len(literal),
            channels=tuple(sorted(channels)),
        )
        for (kind, literal, start), channels in sorted(
            hints.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])
        )
    )
    return (
        tuple(hint for hint in materialized if hint.kind == "METRIC"),
        tuple(hint for hint in materialized if hint.kind == "QUANTITY"),
        tuple(unresolved),
    )


def build_context_recovery_cases(
    annotator_a_context_audit: Path,
    annotator_b_context_audit: Path,
) -> tuple[ContextRecoveryCase, ...]:
    """Build a review-only recovery queue without promoting incomplete graphs."""

    a_rows = _read_index(annotator_a_context_audit, "A")
    b_rows = _read_index(annotator_b_context_audit, "B")
    if set(a_rows) != set(b_rows):
        raise ValueError("A/B context audit sets do not match")
    cases = []
    for context_id in sorted(a_rows):
        a_row = a_rows[context_id]
        b_row = b_rows[context_id]
        for field in _IDENTITY_FIELDS:
            if a_row.get(field, "") != b_row.get(field, ""):
                raise ValueError(f"context audit source identity drift: {field}")
        a_complete = _is_complete(a_row, "A")
        b_complete = _is_complete(b_row, "B")
        if a_complete and b_complete:
            continue
        incomplete_rows = tuple(
            (channel, row)
            for channel, row, complete in (
                ("A", a_row, a_complete),
                ("B", b_row, b_complete),
            )
            if not complete
        )
        text = a_row["text"]
        metric_hints, quantity_hints, unresolved = _collect_hints(
            rows=incomplete_rows,
            text=text,
        )
        reported_missing_pairs = tuple(
            f"{channel}:{row['missing_pairs'].strip()}"
            for channel, row in incomplete_rows
            if row.get("missing_pairs", "").strip()
        )
        cases.append(ContextRecoveryCase(
            context_id=context_id,
            source_slice=a_row["source_slice"],
            entity=a_row["entity"],
            source_sha256=a_row["source_sha256"],
            source_path=a_row["source_path"],
            document_char_start=int(a_row["document_char_start"]),
            document_char_end=int(a_row["document_char_end"]),
            text=text,
            candidate_pair_count=int(a_row["candidate_pair_count"]),
            incomplete_channels=tuple(channel for channel, _ in incomplete_rows),
            metric_hints=metric_hints,
            quantity_hints=quantity_hints,
            unresolved_hints=unresolved,
            reported_missing_pairs=reported_missing_pairs,
        ))
    return tuple(cases)


def write_context_recovery_package(
    output: Path,
    cases: tuple[ContextRecoveryCase, ...],
) -> dict[str, object]:
    if not cases:
        raise ValueError("context recovery package requires at least one case")
    output.mkdir(parents=True, exist_ok=True)
    review_path = output / "context_recovery_review.csv"
    rows = []
    for case in cases:
        rows.append({
            "context_id": case.context_id,
            "source_slice": case.source_slice,
            "entity": case.entity,
            "source_sha256": case.source_sha256,
            "source_path": case.source_path,
            "document_char_start": case.document_char_start,
            "document_char_end": case.document_char_end,
            "text": case.text,
            "candidate_pair_count": case.candidate_pair_count,
            "incomplete_channels": ";".join(case.incomplete_channels),
            "metric_hints": json.dumps(
                [hint.to_dict() for hint in case.metric_hints], ensure_ascii=False
            ),
            "quantity_hints": json.dumps(
                [hint.to_dict() for hint in case.quantity_hints], ensure_ascii=False
            ),
            "unresolved_hints": json.dumps(case.unresolved_hints, ensure_ascii=False),
            "reported_missing_pairs": json.dumps(
                case.reported_missing_pairs, ensure_ascii=False
            ),
            "recovery_action": "",
            "reviewed_missing_metric_mentions": "",
            "reviewed_missing_quantity_mentions": "",
            "reviewed_missing_pairs": "",
            "reviewer_id": "",
            "review_notes": "",
        })
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_source = Counter(case.source_slice for case in cases)
    patterns = Counter("+".join(case.incomplete_channels) for case in cases)
    summary = {
        "status": "AWAITING_CONTEXT_RECOVERY_REVIEW",
        "production_enabled": False,
        "gold_a_promoted": 0,
        "contexts": len(cases),
        "contexts_by_source": dict(sorted(by_source.items())),
        "incomplete_channel_patterns": dict(sorted(patterns.items())),
        "explicit_metric_hints": sum(len(case.metric_hints) for case in cases),
        "explicit_quantity_hints": sum(len(case.quantity_hints) for case in cases),
        "contexts_with_explicit_hints": sum(
            bool(case.metric_hints or case.quantity_hints) for case in cases
        ),
        "contexts_requiring_source_reread": sum(
            bool(case.unresolved_hints) for case in cases
        ),
        "review_file": review_path.name,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(
        "# Candidate-graph recovery\n\n"
        "This package does not promote any context automatically. Review the exact "
        "source text and the A/B omission reports. Set `recovery_action` to "
        "`FALSE_ALARM_GRAPH_COMPLETE`, `ADD_MISSING_CANDIDATES`, or "
        "`ARCHIVE_UNRECOVERABLE`; record corrected mentions/pairs and a distinct "
        "`reviewer_id`. `ADD_MISSING_CANDIDATES` still requires a new blind A/B pair "
        "annotation and adjudication pass before GOLD_A promotion.\n",
        encoding="utf-8",
    )
    return summary


def _read_recovery_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    if not path.exists():
        raise ValueError(f"missing context recovery file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        rows = tuple(dict(row) for row in reader)
    if not rows or not header:
        raise ValueError("context recovery file cannot be empty")
    identifiers = [row.get("context_id", "").strip() for row in rows]
    if "" in identifiers or len(identifiers) != len(set(identifiers)):
        raise ValueError("context recovery rows require unique context ids")
    return header, rows


def _span(
    text: str,
    row: dict[str, object],
    *,
    literal_field: str,
    start_field: str,
    end_field: str,
) -> TextSpan:
    span = TextSpan(
        char_start=int(row[start_field]),
        char_end=int(row[end_field]),
        literal=str(row[literal_field]),
    )
    if span.char_end > len(text) or text[span.char_start : span.char_end] != span.literal:
        raise ValueError("reviewed recovery span does not match source text")
    return span


def _reviewed_mentions(
    raw: str,
    *,
    expected_kind: str,
    text: str,
) -> tuple[TextSpan, ...]:
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("reviewed recovery mentions must be valid JSON") from exc
    if not isinstance(rows, list):
        raise ValueError("reviewed recovery mentions must be a JSON list")
    output = []
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") != expected_kind:
            raise ValueError(f"reviewed recovery mention must have kind {expected_kind}")
        output.append(_span(
            text,
            row,
            literal_field="literal",
            start_field="char_start",
            end_field="char_end",
        ))
    return tuple(dict.fromkeys(output))


def _reviewed_pair_spans(
    raw: str,
    *,
    text: str,
) -> tuple[tuple[TextSpan, TextSpan], ...]:
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("reviewed recovery pairs must be valid JSON") from exc
    if not isinstance(rows, list):
        raise ValueError("reviewed recovery pairs must be a JSON list")
    output = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("reviewed recovery pairs must contain JSON objects")
        if row.get("candidate_only") is not True or row.get(
            "binding_unadjudicated"
        ) is not True:
            raise ValueError("recovered pairs must remain candidate-only/unadjudicated")
        metric = _span(
            text,
            row,
            literal_field="metric_literal",
            start_field="metric_char_start",
            end_field="metric_char_end",
        )
        quantity = _span(
            text,
            row,
            literal_field="quantity_literal",
            start_field="quantity_char_start",
            end_field="quantity_char_end",
        )
        output.append((metric, quantity))
    return tuple(dict.fromkeys(output))


def _new_recovery_item(
    prototype: AnnotationReviewItem,
    metric: TextSpan,
    quantity: TextSpan,
    *,
    concept_label: str,
    quantity_kind: str,
) -> AnnotationReviewItem:
    identity = (
        f"TEXT_IE_CONTEXT_RECOVERY_V1|{prototype.candidate_id}|"
        f"{metric.char_start}|{metric.char_end}|"
        f"{quantity.char_start}|{quantity.char_end}"
    )
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id=sha256(identity.encode()).hexdigest()[:24],
        candidate_id=prototype.candidate_id,
        entity=prototype.entity,
        source_path=prototype.source_path,
        source_sha256=prototype.source_sha256,
        source_slice=prototype.source_slice,
        document_char_start=prototype.document_char_start,
        document_char_end=prototype.document_char_end,
        text=prototype.text,
        proposal=PairProposal(
            metric_span=metric,
            quantity_span=quantity,
            concept_label=concept_label,
            binding_hint="UNREVIEWED",
            role_hint=None,
            generator="HUMAN_CONTEXT_RECOVERY_V1",
            quantity_kind=quantity_kind,
        ),
        legacy_route="TEXT_IE",
        legacy_expected_frames=(),
        legacy_annotation_files=tuple(dict.fromkeys((
            *prototype.legacy_annotation_files,
            "HUMAN_CONTEXT_RECOVERY_V1",
        ))),
        adjudication_status=AdjudicationStatus.PENDING,
        quality_tier=AnnotationQualityTier.WEAK,
        split="UNASSIGNED",
    )


def apply_context_recovery_review(
    *,
    template_path: Path,
    labeled_path: Path,
    source_items: tuple[AnnotationReviewItem, ...],
    forbidden_reviewer_ids: frozenset[str] = frozenset(),
) -> ContextRecoveryApplication:
    """Apply candidate recovery only; never infer or promote semantic labels."""

    template_header, template_rows = _read_recovery_csv(template_path)
    labeled_header, labeled_rows = _read_recovery_csv(labeled_path)
    if labeled_header != template_header:
        raise ValueError("context recovery labeled header does not match template")
    template_by_id = {row["context_id"]: row for row in template_rows}
    labeled_by_id = {row["context_id"]: row for row in labeled_rows}
    if set(template_by_id) != set(labeled_by_id):
        raise ValueError("context recovery labeled context set does not match template")
    immutable_fields = tuple(
        field for field in template_header if field not in _REVIEW_FIELDS
    )
    for context_id, labeled in labeled_by_id.items():
        template = template_by_id[context_id]
        for field in immutable_fields:
            if labeled.get(field, "") != template.get(field, ""):
                raise ValueError(f"context recovery identity drift: {context_id}:{field}")

    grouped: dict[str, list[AnnotationReviewItem]] = {}
    for item in source_items:
        if item.candidate_id in template_by_id and item.proposal is not None:
            grouped.setdefault(item.candidate_id, []).append(item)
    if set(grouped) != set(template_by_id):
        missing = sorted(set(template_by_id) - set(grouped))
        raise ValueError(f"source queue is missing recovery contexts: {missing}")

    recovered = []
    action_counts: Counter[str] = Counter()
    archived = 0
    original_pair_count = 0
    for context_id in sorted(template_by_id):
        decision = labeled_by_id[context_id]
        action = decision.get("recovery_action", "").strip()
        if action not in _RECOVERY_ACTIONS:
            raise ValueError(f"unsupported recovery action: {context_id}:{action}")
        reviewer = decision.get("reviewer_id", "").strip()
        if not reviewer:
            raise ValueError(f"context recovery requires reviewer_id: {context_id}")
        if reviewer in forbidden_reviewer_ids:
            raise ValueError("context recovery reviewer must be independent")
        action_counts[action] += 1
        originals = tuple(sorted(grouped[context_id], key=lambda item: item.queue_item_id))
        original_pair_count += len(originals)
        template = template_by_id[context_id]
        if len(originals) != int(template["candidate_pair_count"]):
            raise ValueError(f"source candidate count drift: {context_id}")
        prototype = originals[0]
        source_identity = {
            "source_slice": prototype.source_slice.value,
            "entity": prototype.entity,
            "source_sha256": prototype.source_sha256,
            "source_path": prototype.source_path,
            "document_char_start": str(prototype.document_char_start),
            "document_char_end": str(prototype.document_char_end),
            "text": prototype.text,
        }
        if any(decision[field] != value for field, value in source_identity.items()):
            raise ValueError(f"context recovery source identity drift: {context_id}")
        if action == "ARCHIVE_UNRECOVERABLE":
            archived += 1
            continue
        if action == "FALSE_ALARM_GRAPH_COMPLETE":
            recovered.extend(originals)
            continue

        text = prototype.text
        metrics = {
            item.proposal.metric_span for item in originals if item.proposal is not None
        }
        quantities = {
            item.proposal.quantity_span for item in originals if item.proposal is not None
        }
        metrics.update(_reviewed_mentions(
            decision.get("reviewed_missing_metric_mentions", ""),
            expected_kind="METRIC",
            text=text,
        ))
        quantities.update(_reviewed_mentions(
            decision.get("reviewed_missing_quantity_mentions", ""),
            expected_kind="QUANTITY",
            text=text,
        ))
        pair_spans = _reviewed_pair_spans(
            decision.get("reviewed_missing_pairs", ""), text=text
        )
        for metric, quantity in pair_spans:
            metrics.add(metric)
            quantities.add(quantity)
        if not pair_spans and len(metrics) * len(quantities) <= len(originals):
            raise ValueError(f"ADD_MISSING_CANDIDATES adds no candidates: {context_id}")

        existing = {
            (item.proposal.metric_span, item.proposal.quantity_span): item
            for item in originals
            if item.proposal is not None
        }
        if len(existing) != len(originals):
            raise ValueError(f"source queue contains duplicate candidate pairs: {context_id}")
        concept_hints: dict[TextSpan, set[str]] = {}
        quantity_kinds: dict[TextSpan, set[str]] = {}
        for item in originals:
            proposal = item.proposal
            concept_hints.setdefault(proposal.metric_span, set()).add(
                proposal.concept_label
            )
            quantity_kinds.setdefault(proposal.quantity_span, set()).add(
                proposal.quantity_kind
            )
        for metric in sorted(metrics, key=lambda span: (span.char_start, span.char_end)):
            for quantity in sorted(
                quantities, key=lambda span: (span.char_start, span.char_end)
            ):
                current = existing.get((metric, quantity))
                if current is not None:
                    recovered.append(current)
                    continue
                metric_labels = concept_hints.get(metric, set())
                kinds = quantity_kinds.get(quantity, set())
                recovered.append(_new_recovery_item(
                    prototype,
                    metric,
                    quantity,
                    concept_label=(
                        next(iter(metric_labels))
                        if len(metric_labels) == 1
                        else "UNREVIEWED"
                    ),
                    quantity_kind=(
                        next(iter(kinds)) if len(kinds) == 1 else "UNKNOWN"
                    ),
                ))

    identifiers = [item.queue_item_id for item in recovered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("recovered candidate graph contains duplicate pair ids")
    ordered = tuple(sorted(
        recovered,
        key=lambda item: (
            item.source_slice.value,
            item.candidate_id,
            item.queue_item_id,
        ),
    ))
    return ContextRecoveryApplication(
        items=ordered,
        context_ids=frozenset(item.candidate_id for item in ordered),
        action_counts=dict(sorted(action_counts.items())),
        context_count=len(template_rows),
        archived_context_count=archived,
        original_pair_count=original_pair_count,
        recovered_pair_count=len(ordered),
        added_pair_count=len(ordered) - (original_pair_count - sum(
            len(grouped[context_id])
            for context_id, row in labeled_by_id.items()
            if row["recovery_action"].strip() == "ARCHIVE_UNRECOVERABLE"
        )),
    )


def select_recovery_contexts_for_source_gaps(
    items: tuple[AnnotationReviewItem, ...],
    *,
    source_gaps: dict[str, int],
) -> RecoveryClosureSelection:
    """Select the smallest issuer-diverse blind round needed to close source gaps."""

    if not source_gaps or any(value < 0 for value in source_gaps.values()):
        raise ValueError("source gaps must be non-empty non-negative counts")
    contexts: dict[str, list[AnnotationReviewItem]] = {}
    for item in items:
        if item.proposal is not None:
            contexts.setdefault(item.candidate_id, []).append(item)
    selected_ids = set()
    context_counts = {}
    pair_counts = {}
    for source, required in source_gaps.items():
        if required == 0:
            context_counts[source] = 0
            pair_counts[source] = 0
            continue
        by_entity: dict[str, list[tuple[int, str]]] = {}
        for context_id, rows in contexts.items():
            prototype = rows[0]
            if any(
                item.source_slice != prototype.source_slice
                or item.entity != prototype.entity
                for item in rows[1:]
            ):
                raise ValueError("recovery selection context identity drift")
            if prototype.source_slice.value == source:
                by_entity.setdefault(prototype.entity, []).append(
                    (len(rows), context_id)
                )
        for values in by_entity.values():
            values.sort()
        chosen = []
        round_index = 0
        while len(chosen) < required:
            candidates = sorted(
                (values[round_index][0], values[round_index][1], entity)
                for entity, values in by_entity.items()
                if round_index < len(values)
            )
            if not candidates:
                raise ValueError(
                    f"source gap cannot be closed: {source} requires {required}"
                )
            for _, context_id, _ in candidates:
                chosen.append(context_id)
                if len(chosen) == required:
                    break
            round_index += 1
        selected_ids.update(chosen)
        context_counts[source] = len(chosen)
        pair_counts[source] = sum(len(contexts[context_id]) for context_id in chosen)
    selected_entities = {
        contexts[context_id][0].entity for context_id in selected_ids
    }
    return RecoveryClosureSelection(
        context_ids=frozenset(selected_ids),
        context_counts=dict(context_counts),
        pair_counts=dict(pair_counts),
        pair_count=sum(pair_counts.values()),
        entity_count=len(selected_entities),
    )


__all__ = [
    "ContextRecoveryCase",
    "ContextRecoveryApplication",
    "MissingMentionHint",
    "RecoveryClosureSelection",
    "apply_context_recovery_review",
    "build_context_recovery_cases",
    "select_recovery_contexts_for_source_gaps",
    "write_context_recovery_package",
]
