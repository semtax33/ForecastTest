from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
import re

from ..ontology import find_concepts
from ..quantities import extract_quantities
from .annotation import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    PairProposal,
    TextSpan,
)


@dataclass(frozen=True)
class HistoricalReviewQueue:
    items: tuple[AnnotationReviewItem, ...]
    annotation_row_count: int
    unique_candidate_count: int
    superseded_annotation_rows: int
    missing_candidate_ids: tuple[str, ...]
    selected_expected_frames: int
    matched_expected_frames: int
    unmatched_expected_frames: int
    archived_table_contexts: int


def _version_key(path: Path) -> tuple[int, int, str]:
    match = re.match(r"v(?P<digits>\d+)", path.name, re.IGNORECASE)
    if match is None:
        return (0, 0, path.name)
    digits = match.group("digits")
    if len(digits) <= 2:
        return (int(digits), 0, path.name)
    return (int(digits[:2]), int(digits[2:]), path.name)


def _source_slice(row: dict[str, str]) -> AnnotationSourceSlice:
    path = row.get("source_path", "").replace("\\", "/").casefold()
    kind = row.get("source_kind", "").casefold()
    if "/ir/" in path or kind == "ir":
        return AnnotationSourceSlice.IR_UNSPECIFIED
    if "10-k" in kind or "/10-k/" in path or "_10-k" in path:
        return AnnotationSourceSlice.SEC_10K
    if "10-q" in kind or "/10-q/" in path or "_10-q" in path:
        return AnnotationSourceSlice.SEC_10Q
    if "industry" in kind or "/industry" in path:
        return AnnotationSourceSlice.INDUSTRY_DATA
    return AnnotationSourceSlice.UNKNOWN


def _role_for_value(frame: dict[str, object], field: str) -> str | None:
    semantic = str(frame.get("frame", ""))
    if field == "change" or semantic == "CHANGE_BY":
        return "DELTA"
    if semantic == "RANGE_GUIDANCE":
        return {
            "lower_value": "GUIDANCE_LOW",
            "upper_value": "GUIDANCE_HIGH",
        }.get(field)
    if semantic == "COMPOSITION":
        return "COMPOSITION"
    if semantic in {"ABSOLUTE_VALUE", "CHANGE_TO", "COMPARATIVE"}:
        return (
            "VALUE_PRIOR"
            if str(frame.get("concept", "")).startswith("PRIOR_YEAR_")
            else "VALUE_CURRENT"
        )
    return None


def _matching_role(
    concept: str,
    quantity_value: float,
    frames: tuple[dict[str, object], ...],
) -> str | None:
    for frame in frames:
        if str(frame.get("concept", "")) != concept:
            continue
        for field in ("value", "change", "lower_value", "upper_value"):
            raw = frame.get(field)
            if raw is None:
                continue
            if isclose(float(raw), quantity_value, rel_tol=1e-9, abs_tol=1e-9):
                role = _role_for_value(frame, field)
                if role is not None:
                    return role
    return None


def _queue_id(candidate_id: str, suffix: str) -> str:
    return sha256(f"{candidate_id}|{suffix}".encode()).hexdigest()[:24]


def _load_candidates(paths: tuple[Path, ...]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    signatures: dict[str, tuple[str, str, str, str]] = {}
    for path in sorted(paths):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                candidate_id = str(row.get("candidate_id", ""))
                if not candidate_id:
                    raise ValueError(f"candidate row without id in {path}")
                signature = (
                    str(row.get("source_sha256", "")),
                    str(row.get("char_start", "")),
                    str(row.get("char_end", "")),
                    str(row.get("text", "")),
                )
                if candidate_id in signatures and signatures[candidate_id] != signature:
                    raise ValueError(f"conflicting candidate payload for {candidate_id}")
                signatures[candidate_id] = signature
                output.setdefault(candidate_id, dict(row))
    return output


def _load_annotations(
    paths: tuple[Path, ...],
) -> tuple[dict[str, tuple[Path, dict[str, object]]], dict[str, tuple[Path, ...]], int]:
    grouped: dict[str, list[tuple[Path, dict[str, object]]]] = {}
    total = 0
    for path in sorted(paths, key=_version_key):
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            candidate_id = str(row.get("candidate_id", ""))
            if not candidate_id:
                raise ValueError(f"annotation without candidate_id: {path}:{line_number}")
            grouped.setdefault(candidate_id, []).append((path, row))
            total += 1
    selected = {
        candidate_id: max(rows, key=lambda item: _version_key(item[0]))
        for candidate_id, rows in grouped.items()
    }
    lineage = {
        candidate_id: tuple(
            path for path, _ in sorted(rows, key=lambda item: _version_key(item[0]))
        )
        for candidate_id, rows in grouped.items()
    }
    return selected, lineage, total


def build_historical_review_queue(
    *,
    candidate_csvs: tuple[Path, ...],
    annotation_files: tuple[Path, ...],
) -> HistoricalReviewQueue:
    candidates = _load_candidates(candidate_csvs)
    selected, lineage, annotation_rows = _load_annotations(annotation_files)
    missing = tuple(sorted(set(selected) - set(candidates)))
    items: list[AnnotationReviewItem] = []
    selected_frame_total = sum(
        len(row.get("expected_frames", ())) for _, row in selected.values()
    )
    unmatched_total = sum(
        len(selected[candidate_id][1].get("expected_frames", ()))
        for candidate_id in missing
    )
    archived_tables = 0
    for candidate_id in sorted(set(selected) & set(candidates)):
        _, annotation = selected[candidate_id]
        candidate = candidates[candidate_id]
        text = str(candidate["text"])
        start = int(candidate["char_start"])
        end = int(candidate["char_end"])
        route = str(annotation["gold_route"])
        frames = tuple(dict(frame) for frame in annotation.get("expected_frames", ()))
        annotation_names = tuple(path.name for path in lineage[candidate_id])
        common = {
            "schema_version": "1.0.0",
            "candidate_id": candidate_id,
            "entity": str(candidate.get("ticker", annotation.get("ticker", "UNKNOWN"))),
            "source_path": str(candidate["source_path"]),
            "source_sha256": str(candidate["source_sha256"]),
            "source_slice": _source_slice(candidate),
            "document_char_start": start,
            "document_char_end": end,
            "text": text,
            "legacy_route": route,
            "legacy_expected_frames": frames,
            "legacy_annotation_files": annotation_names,
            "quality_tier": AnnotationQualityTier.WEAK,
            "split": "UNASSIGNED",
        }
        if route == "TABLE_DSL":
            items.append(AnnotationReviewItem(
                queue_item_id=_queue_id(candidate_id, "TABLE_ARCHIVE"),
                proposal=None,
                adjudication_status=AdjudicationStatus.ARCHIVE_ONLY,
                **common,
            ))
            archived_tables += 1
            continue
        concepts = find_concepts(text)
        quantities = extract_quantities(text)
        matched_frames: set[int] = set()
        for concept in concepts:
            for quantity in quantities:
                role = _matching_role(concept.concept, quantity.value, frames)
                if role is not None:
                    binding = "BELONGS_TO"
                    generator = "LEGACY_FRAME_VALUE_MATCH"
                    for index, frame in enumerate(frames):
                        if str(frame.get("concept", "")) != concept.concept:
                            continue
                        if any(
                            raw is not None
                            and isclose(float(raw), quantity.value, rel_tol=1e-9, abs_tol=1e-9)
                            for raw in (
                                frame.get("value"),
                                frame.get("change"),
                                frame.get("lower_value"),
                                frame.get("upper_value"),
                            )
                        ):
                            matched_frames.add(index)
                else:
                    binding = "NOT_RELATED"
                    generator = "LOCAL_CROSS_PRODUCT_NEGATIVE_HINT"
                proposal = PairProposal(
                    metric_span=TextSpan(
                        concept.char_start,
                        concept.char_end,
                        text[concept.char_start : concept.char_end],
                    ),
                    quantity_span=TextSpan(
                        quantity.char_start,
                        quantity.char_end,
                        text[quantity.char_start : quantity.char_end],
                    ),
                    concept_label=concept.concept,
                    binding_hint=binding,
                    role_hint=role,
                    generator=generator,
                    quantity_kind=quantity.kind.value,
                )
                suffix = (
                    f"PAIR|{concept.char_start}:{concept.char_end}|"
                    f"{quantity.char_start}:{quantity.char_end}"
                )
                items.append(AnnotationReviewItem(
                    queue_item_id=_queue_id(candidate_id, suffix),
                    proposal=proposal,
                    adjudication_status=AdjudicationStatus.PENDING,
                    **common,
                ))
        unmatched = len(frames) - len(matched_frames)
        unmatched_total += unmatched
        if not concepts or not quantities or unmatched:
            items.append(AnnotationReviewItem(
                queue_item_id=_queue_id(candidate_id, "CONTEXT_RECOVERY"),
                proposal=None,
                adjudication_status=AdjudicationStatus.PENDING,
                **common,
            ))
    return HistoricalReviewQueue(
        items=tuple(items),
        annotation_row_count=annotation_rows,
        unique_candidate_count=len(selected),
        superseded_annotation_rows=annotation_rows - len(selected),
        missing_candidate_ids=missing,
        selected_expected_frames=selected_frame_total,
        matched_expected_frames=selected_frame_total - unmatched_total,
        unmatched_expected_frames=unmatched_total,
        archived_table_contexts=archived_tables,
    )


__all__ = ["HistoricalReviewQueue", "build_historical_review_queue"]
