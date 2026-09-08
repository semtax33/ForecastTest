from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import json
from pathlib import Path
from typing import Mapping


class AdjudicationStatus(StrEnum):
    PENDING = "PENDING"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"
    DISAGREEMENT = "DISAGREEMENT"
    ADJUDICATED = "ADJUDICATED"
    ARCHIVE_ONLY = "ARCHIVE_ONLY"


class AnnotationQualityTier(StrEnum):
    WEAK = "WEAK"
    SILVER = "SILVER"
    GOLD_B = "GOLD_B"
    GOLD_A = "GOLD_A"


class AnnotationSourceSlice(StrEnum):
    SEC_10K = "SEC_10K"
    SEC_10Q = "SEC_10Q"
    IR_PREPARED_REMARKS = "IR_PREPARED_REMARKS"
    IR_QA = "IR_QA"
    IR_UNSPECIFIED = "IR_UNSPECIFIED"
    INDUSTRY_DATA = "INDUSTRY_DATA"
    UNKNOWN = "UNKNOWN"


_BINDING_LABELS = {"UNREVIEWED", "BELONGS_TO", "NOT_RELATED"}
_SPLITS = {"UNASSIGNED", "TRAIN", "CALIBRATION", "CERTIFICATION"}


@dataclass(frozen=True)
class TextSpan:
    char_start: int
    char_end: int
    literal: str

    def __post_init__(self) -> None:
        if self.char_start < 0 or self.char_end <= self.char_start or not self.literal:
            raise ValueError("text spans require ordered offsets and a literal")


@dataclass(frozen=True)
class PairProposal:
    metric_span: TextSpan
    quantity_span: TextSpan
    concept_label: str
    binding_hint: str
    role_hint: str | None
    generator: str
    quantity_kind: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if not self.concept_label or not self.generator or not self.quantity_kind:
            raise ValueError("pair proposals require a concept and generator")
        if self.binding_hint not in _BINDING_LABELS:
            raise ValueError("unsupported proposal binding hint")
        if self.binding_hint == "NOT_RELATED" and self.role_hint is not None:
            raise ValueError("NOT_RELATED proposals cannot receive a numeric role")


@dataclass(frozen=True)
class FinalPairAnnotation:
    metric_span: TextSpan
    quantity_span: TextSpan
    concept_label: str
    binding_label: str
    role_label: str | None
    scope: str
    period: str
    quantity_kind: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if self.binding_label not in {"BELONGS_TO", "NOT_RELATED"}:
            raise ValueError("final annotations require a reviewed binding label")
        if self.binding_label == "NOT_RELATED" and self.role_label is not None:
            raise ValueError("NOT_RELATED final pairs cannot receive a numeric role")
        if self.binding_label == "BELONGS_TO" and not self.role_label:
            raise ValueError("BELONGS_TO final pairs require a numeric role")
        if not self.concept_label:
            raise ValueError("final annotation identity cannot be blank")
        if self.binding_label == "BELONGS_TO" and (not self.scope or not self.period):
            raise ValueError("related final annotation scope and period cannot be blank")


@dataclass(frozen=True)
class HumanPairAnnotation:
    annotator_id: str
    annotation: FinalPairAnnotation

    def __post_init__(self) -> None:
        if not self.annotator_id:
            raise ValueError("human annotations require an annotator identity")


@dataclass(frozen=True)
class AnnotationReviewItem:
    schema_version: str
    queue_item_id: str
    candidate_id: str
    entity: str
    source_path: str
    source_sha256: str
    source_slice: AnnotationSourceSlice
    document_char_start: int
    document_char_end: int
    text: str
    proposal: PairProposal | None
    legacy_route: str
    legacy_expected_frames: tuple[dict[str, object], ...]
    legacy_annotation_files: tuple[str, ...]
    adjudication_status: AdjudicationStatus
    quality_tier: AnnotationQualityTier
    split: str
    human_annotations: tuple[HumanPairAnnotation, ...] = ()
    adjudicator_id: str | None = None
    final_annotation: FinalPairAnnotation | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "1.0.0":
            raise ValueError("unsupported annotation schema version")
        if not self.queue_item_id or not self.candidate_id or not self.entity:
            raise ValueError("annotation review identity cannot be blank")
        if not self.source_path or len(self.source_sha256) != 64:
            raise ValueError("annotation review source provenance is incomplete")
        if any(char not in "0123456789abcdef" for char in self.source_sha256.casefold()):
            raise ValueError("source sha256 must be hexadecimal")
        if (
            self.document_char_start < 0
            or self.document_char_end - self.document_char_start != len(self.text)
        ):
            raise ValueError("document offsets must exactly bound the review text")
        if self.legacy_route not in {"TEXT_IE", "NO_FACT", "TABLE_DSL"}:
            raise ValueError("unsupported legacy evidence route")
        if not self.legacy_annotation_files or self.split not in _SPLITS:
            raise ValueError("annotation lineage and split are required")
        for span in self._spans():
            if span.char_end > len(self.text):
                raise ValueError("annotation span falls outside review text")
            if self.text[span.char_start : span.char_end] != span.literal:
                raise ValueError("annotation span literal does not match review text")
        if self.adjudication_status is AdjudicationStatus.PENDING:
            if self.quality_tier is not AnnotationQualityTier.WEAK:
                raise ValueError("pending items must remain WEAK")
            if self.final_annotation is not None:
                raise ValueError("pending items cannot contain a final annotation")
        if self.quality_tier is AnnotationQualityTier.GOLD_A:
            annotator_ids = {
                annotation.annotator_id for annotation in self.human_annotations
            }
            if len(annotator_ids) < 2:
                raise ValueError("GOLD_A requires two independent annotators")
            if (
                self.adjudication_status is not AdjudicationStatus.ADJUDICATED
                or not self.adjudicator_id
                or self.final_annotation is None
            ):
                raise ValueError("GOLD_A requires an adjudicated final pair")
            if self.adjudicator_id in annotator_ids:
                raise ValueError("GOLD_A adjudicator must be separate from annotators")
        if self.quality_tier is AnnotationQualityTier.GOLD_B:
            if not self.human_annotations or self.final_annotation is None:
                raise ValueError("GOLD_B requires one human verifier and a final pair")

    def _spans(self) -> tuple[TextSpan, ...]:
        output = []
        if self.proposal is not None:
            output.extend((self.proposal.metric_span, self.proposal.quantity_span))
        if self.final_annotation is not None:
            output.extend((
                self.final_annotation.metric_span,
                self.final_annotation.quantity_span,
            ))
        return tuple(output)

    @property
    def certification_eligible(self) -> bool:
        return (
            self.quality_tier is AnnotationQualityTier.GOLD_A
            and self.adjudication_status is AdjudicationStatus.ADJUDICATED
        )

    def to_dict(self) -> dict[str, object]:
        def span(value: TextSpan) -> dict[str, object]:
            return {
                "char_start": value.char_start,
                "char_end": value.char_end,
                "literal": value.literal,
            }

        proposal = None
        if self.proposal is not None:
            proposal = {
                "metric_span": span(self.proposal.metric_span),
                "quantity_span": span(self.proposal.quantity_span),
                "concept_label": self.proposal.concept_label,
                "binding_hint": self.proposal.binding_hint,
                "role_hint": self.proposal.role_hint,
                "generator": self.proposal.generator,
                "quantity_kind": self.proposal.quantity_kind,
            }
        final = None
        if self.final_annotation is not None:
            final = {
                "metric_span": span(self.final_annotation.metric_span),
                "quantity_span": span(self.final_annotation.quantity_span),
                "concept_label": self.final_annotation.concept_label,
                "binding_label": self.final_annotation.binding_label,
                "role_label": self.final_annotation.role_label,
                "scope": self.final_annotation.scope,
                "period": self.final_annotation.period,
                "quantity_kind": self.final_annotation.quantity_kind,
            }
        return {
            "schema_version": self.schema_version,
            "queue_item_id": self.queue_item_id,
            "candidate_id": self.candidate_id,
            "entity": self.entity,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_slice": self.source_slice.value,
            "document_char_start": self.document_char_start,
            "document_char_end": self.document_char_end,
            "text": self.text,
            "proposal": proposal,
            "legacy_route": self.legacy_route,
            "legacy_expected_frames": [dict(frame) for frame in self.legacy_expected_frames],
            "legacy_annotation_files": list(self.legacy_annotation_files),
            "adjudication_status": self.adjudication_status.value,
            "quality_tier": self.quality_tier.value,
            "split": self.split,
            "human_annotations": [
                {
                    "annotator_id": item.annotator_id,
                    "annotation": {
                        "metric_span": span(item.annotation.metric_span),
                        "quantity_span": span(item.annotation.quantity_span),
                        "concept_label": item.annotation.concept_label,
                        "binding_label": item.annotation.binding_label,
                        "role_label": item.annotation.role_label,
                        "scope": item.annotation.scope,
                        "period": item.annotation.period,
                        "quantity_kind": item.annotation.quantity_kind,
                    },
                }
                for item in self.human_annotations
            ],
            "adjudicator_id": self.adjudicator_id,
            "final_annotation": final,
        }


def _span_from_dict(row: Mapping[str, object]) -> TextSpan:
    return TextSpan(int(row["char_start"]), int(row["char_end"]), str(row["literal"]))


def annotation_review_item_from_dict(row: Mapping[str, object]) -> AnnotationReviewItem:
    proposal_row = row.get("proposal")
    proposal = None
    if proposal_row is not None:
        proposal = PairProposal(
            metric_span=_span_from_dict(proposal_row["metric_span"]),
            quantity_span=_span_from_dict(proposal_row["quantity_span"]),
            concept_label=str(proposal_row["concept_label"]),
            binding_hint=str(proposal_row["binding_hint"]),
            role_hint=(
                str(proposal_row["role_hint"])
                if proposal_row.get("role_hint") is not None
                else None
            ),
            generator=str(proposal_row["generator"]),
            quantity_kind=str(proposal_row.get("quantity_kind", "UNKNOWN")),
        )
    def final_from_dict(final_row: Mapping[str, object]) -> FinalPairAnnotation:
        return FinalPairAnnotation(
            metric_span=_span_from_dict(final_row["metric_span"]),
            quantity_span=_span_from_dict(final_row["quantity_span"]),
            concept_label=str(final_row["concept_label"]),
            binding_label=str(final_row["binding_label"]),
            role_label=(
                str(final_row["role_label"])
                if final_row.get("role_label") is not None
                else None
            ),
            scope=str(final_row["scope"]),
            period=str(final_row["period"]),
            quantity_kind=str(final_row.get("quantity_kind", "UNKNOWN")),
        )

    final_row = row.get("final_annotation")
    final = final_from_dict(final_row) if final_row is not None else None
    human_annotations = tuple(
        HumanPairAnnotation(
            annotator_id=str(item["annotator_id"]),
            annotation=final_from_dict(item["annotation"]),
        )
        for item in row.get("human_annotations", ())
    )
    return AnnotationReviewItem(
        schema_version=str(row["schema_version"]),
        queue_item_id=str(row["queue_item_id"]),
        candidate_id=str(row["candidate_id"]),
        entity=str(row["entity"]),
        source_path=str(row["source_path"]),
        source_sha256=str(row["source_sha256"]),
        source_slice=AnnotationSourceSlice(str(row["source_slice"])),
        document_char_start=int(row["document_char_start"]),
        document_char_end=int(row["document_char_end"]),
        text=str(row["text"]),
        proposal=proposal,
        legacy_route=str(row["legacy_route"]),
        legacy_expected_frames=tuple(dict(frame) for frame in row["legacy_expected_frames"]),
        legacy_annotation_files=tuple(str(value) for value in row["legacy_annotation_files"]),
        adjudication_status=AdjudicationStatus(str(row["adjudication_status"])),
        quality_tier=AnnotationQualityTier(str(row["quality_tier"])),
        split=str(row["split"]),
        human_annotations=human_annotations,
        adjudicator_id=(
            str(row["adjudicator_id"])
            if row.get("adjudicator_id") is not None
            else None
        ),
        final_annotation=final,
    )


def write_annotation_review_queue(
    path: Path,
    items: tuple[AnnotationReviewItem, ...],
) -> None:
    ids = [item.queue_item_id for item in items]
    if not items or len(ids) != len(set(ids)):
        raise ValueError("annotation review queue requires non-empty unique item ids")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(item.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
            for item in items
        ),
        encoding="utf-8",
    )


def load_annotation_review_queue(path: Path) -> tuple[AnnotationReviewItem, ...]:
    items = tuple(
        annotation_review_item_from_dict(json.loads(raw))
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    )
    ids = [item.queue_item_id for item in items]
    if not items or len(ids) != len(set(ids)):
        raise ValueError("annotation review queue requires non-empty unique item ids")
    return items


def record_human_annotation(
    item: AnnotationReviewItem,
    annotation: HumanPairAnnotation,
) -> AnnotationReviewItem:
    if item.adjudication_status in {
        AdjudicationStatus.ARCHIVE_ONLY,
        AdjudicationStatus.ADJUDICATED,
    }:
        raise ValueError("closed review items cannot receive another annotation")
    if annotation.annotator_id in {
        prior.annotator_id for prior in item.human_annotations
    }:
        raise ValueError("an annotator can submit only one independent judgment")
    human_annotations = (*item.human_annotations, annotation)
    judgments = {prior.annotation for prior in human_annotations}
    if len(judgments) == 1:
        return replace(
            item,
            human_annotations=human_annotations,
            adjudication_status=AdjudicationStatus.HUMAN_VERIFIED,
            quality_tier=AnnotationQualityTier.GOLD_B,
            final_annotation=annotation.annotation,
        )
    return replace(
        item,
        human_annotations=human_annotations,
        adjudication_status=AdjudicationStatus.DISAGREEMENT,
        quality_tier=AnnotationQualityTier.WEAK,
        final_annotation=None,
    )


def adjudicate_review_item(
    item: AnnotationReviewItem,
    *,
    adjudicator_id: str,
    final_annotation: FinalPairAnnotation,
) -> AnnotationReviewItem:
    if len({value.annotator_id for value in item.human_annotations}) < 2:
        raise ValueError("adjudication requires two independent annotations")
    return replace(
        item,
        adjudication_status=AdjudicationStatus.ADJUDICATED,
        quality_tier=AnnotationQualityTier.GOLD_A,
        adjudicator_id=adjudicator_id,
        final_annotation=final_annotation,
    )


__all__ = [
    "AdjudicationStatus",
    "AnnotationQualityTier",
    "AnnotationReviewItem",
    "AnnotationSourceSlice",
    "FinalPairAnnotation",
    "HumanPairAnnotation",
    "PairProposal",
    "TextSpan",
    "annotation_review_item_from_dict",
    "adjudicate_review_item",
    "load_annotation_review_queue",
    "record_human_annotation",
    "write_annotation_review_queue",
]
