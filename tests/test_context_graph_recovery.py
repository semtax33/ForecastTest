from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path

import pytest

from equity_platform.text_ie.training.context_recovery import (
    apply_context_recovery_review,
    build_context_recovery_cases,
    select_recovery_contexts_for_source_gaps,
    write_context_recovery_package,
)
from equity_platform.text_ie.training import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    PairProposal,
    TextSpan,
)


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _row(channel: str, *, complete: bool = False) -> dict[str, object]:
    text = "Revenue was $10 million and assets were $20 million."
    return {
        "annotation_channel": channel,
        "context_id": "context-1",
        "source_slice": "SEC_10K",
        "entity": "TEST",
        "source_sha256": "a" * 64,
        "source_path": "D:/test.htm",
        "document_char_start": 10,
        "document_char_end": 10 + len(text),
        "text": text,
        "candidate_pair_count": 1,
        "candidate_graph_complete": "TRUE" if complete else "FALSE",
        "missing_metric_mentions": "" if complete else "assets@28",
        "missing_quantity_mentions": (
            "" if complete else "$20 million@40; uncaptured quantity requires reread"
        ),
        "missing_pairs": "" if complete else "assets@28 <-> $20 million@40",
        "annotator_id": f"annotator-{channel.casefold()}",
        "notes": "",
    }


def _batch(tmp_path: Path, a: dict[str, object], b: dict[str, object]) -> tuple[Path, Path]:
    a_path = tmp_path / "a.csv"
    b_path = tmp_path / "b.csv"
    _write(a_path, [a])
    _write(b_path, [b])
    return a_path, b_path


def test_recovery_case_preserves_explicit_hints_and_unresolved_text(tmp_path) -> None:
    a_path, b_path = _batch(tmp_path, _row("A"), _row("B", complete=True))

    cases = build_context_recovery_cases(a_path, b_path)

    assert len(cases) == 1
    case = cases[0]
    assert case.context_id == "context-1"
    assert case.incomplete_channels == ("A",)
    assert [hint.literal for hint in case.metric_hints] == ["assets"]
    assert [hint.char_start for hint in case.metric_hints] == [28]
    assert [hint.literal for hint in case.quantity_hints] == ["$20 million"]
    assert case.quantity_hints[0].channels == ("A",)
    assert case.unresolved_hints == (
        "A:missing_quantity_mentions:uncaptured quantity requires reread",
    )


def test_recovery_case_merges_same_hint_from_independent_channels(tmp_path) -> None:
    a_path, b_path = _batch(tmp_path, _row("A"), _row("B"))

    case = build_context_recovery_cases(a_path, b_path)[0]

    assert case.incomplete_channels == ("A", "B")
    assert case.metric_hints[0].channels == ("A", "B")
    assert case.quantity_hints[0].channels == ("A", "B")


def test_recovery_rejects_hint_whose_literal_does_not_match_source(tmp_path) -> None:
    a = _row("A")
    a["missing_metric_mentions"] = "assets@29"
    a_path, b_path = _batch(tmp_path, a, _row("B", complete=True))

    with pytest.raises(ValueError, match="missing mention hint does not match source"):
        build_context_recovery_cases(a_path, b_path)


def test_recovery_rejects_cross_channel_source_drift(tmp_path) -> None:
    b = _row("B", complete=True)
    b["source_sha256"] = "b" * 64
    a_path, b_path = _batch(tmp_path, _row("A"), b)

    with pytest.raises(ValueError, match="context audit source identity drift"):
        build_context_recovery_cases(a_path, b_path)


def test_recovery_package_is_review_only_and_reports_counts(tmp_path) -> None:
    a_path, b_path = _batch(tmp_path, _row("A"), _row("B", complete=True))
    cases = build_context_recovery_cases(a_path, b_path)

    summary = write_context_recovery_package(tmp_path / "output", cases)

    assert summary["status"] == "AWAITING_CONTEXT_RECOVERY_REVIEW"
    assert summary["production_enabled"] is False
    assert summary["contexts"] == 1
    assert summary["contexts_requiring_source_reread"] == 1
    review_rows = list(csv.DictReader(
        (tmp_path / "output" / "context_recovery_review.csv").open(
            encoding="utf-8-sig", newline=""
        )
    ))
    assert review_rows[0]["recovery_action"] == ""
    assert review_rows[0]["reviewer_id"] == ""
    assert json.loads(review_rows[0]["metric_hints"])[0]["literal"] == "assets"


def _source_item() -> AnnotationReviewItem:
    text = "Revenue was $10 million and assets were $20 million."
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id="pair-original",
        candidate_id="context-1",
        entity="TEST",
        source_path="D:/test.htm",
        source_sha256="a" * 64,
        source_slice=AnnotationSourceSlice.SEC_10K,
        document_char_start=10,
        document_char_end=10 + len(text),
        text=text,
        proposal=PairProposal(
            metric_span=TextSpan(0, 7, "Revenue"),
            quantity_span=TextSpan(12, 23, "$10 million"),
            concept_label="REVENUE",
            binding_hint="UNREVIEWED",
            role_hint=None,
            generator="ORIGINAL",
            quantity_kind="MONEY",
        ),
        legacy_route="TEXT_IE",
        legacy_expected_frames=(),
        legacy_annotation_files=("source.jsonl",),
        adjudication_status=AdjudicationStatus.PENDING,
        quality_tier=AnnotationQualityTier.WEAK,
        split="UNASSIGNED",
    )


def _labeled_recovery(tmp_path: Path, *, action: str = "ADD_MISSING_CANDIDATES"):
    a_path, b_path = _batch(tmp_path, _row("A"), _row("B", complete=True))
    cases = build_context_recovery_cases(a_path, b_path)
    output = tmp_path / "recovery"
    write_context_recovery_package(output, cases)
    template = output / "context_recovery_review.csv"
    rows = list(csv.DictReader(template.open(encoding="utf-8-sig", newline="")))
    rows[0].update({
        "recovery_action": action,
        "reviewed_missing_metric_mentions": json.dumps([{
            "kind": "METRIC",
            "literal": "assets",
            "char_start": 28,
            "char_end": 34,
            "channels": ["REVIEW"],
        }]),
        "reviewed_missing_quantity_mentions": json.dumps([{
            "kind": "QUANTITY",
            "literal": "$20 million",
            "char_start": 40,
            "char_end": 51,
            "channels": ["REVIEW"],
        }]),
        "reviewed_missing_pairs": json.dumps([{
            "metric_literal": "assets",
            "metric_char_start": 28,
            "metric_char_end": 34,
            "quantity_literal": "$20 million",
            "quantity_char_start": 40,
            "quantity_char_end": 51,
            "candidate_only": True,
            "binding_unadjudicated": True,
        }]),
        "reviewer_id": "reviewer-c",
        "review_notes": "source reread complete",
    })
    labeled = tmp_path / "labeled.csv"
    _write(labeled, rows)
    return template, labeled


def test_labeled_recovery_regenerates_the_full_candidate_cross_product(
    tmp_path,
) -> None:
    template, labeled = _labeled_recovery(tmp_path)

    result = apply_context_recovery_review(
        template_path=template,
        labeled_path=labeled,
        source_items=(_source_item(),),
        forbidden_reviewer_ids=frozenset({"annotator-a", "annotator-b"}),
    )

    assert result.context_count == 1
    assert result.original_pair_count == 1
    assert result.recovered_pair_count == 4
    assert result.added_pair_count == 3
    assert result.action_counts == {"ADD_MISSING_CANDIDATES": 1}
    observed = {
        (
            item.proposal.metric_span.literal,
            item.proposal.quantity_span.literal,
        )
        for item in result.items
    }
    assert observed == {
        ("Revenue", "$10 million"),
        ("Revenue", "$20 million"),
        ("assets", "$10 million"),
        ("assets", "$20 million"),
    }
    assert all(item.quality_tier is AnnotationQualityTier.WEAK for item in result.items)


def test_labeled_recovery_rejects_source_drift_and_non_independent_reviewer(
    tmp_path,
) -> None:
    template, labeled = _labeled_recovery(tmp_path)
    rows = list(csv.DictReader(labeled.open(encoding="utf-8-sig", newline="")))
    rows[0]["reviewer_id"] = "annotator-a"
    _write(labeled, rows)

    with pytest.raises(ValueError, match="independent"):
        apply_context_recovery_review(
            template_path=template,
            labeled_path=labeled,
            source_items=(_source_item(),),
            forbidden_reviewer_ids=frozenset({"annotator-a", "annotator-b"}),
        )

    rows[0]["reviewer_id"] = "reviewer-c"
    rows[0]["text"] = "tampered"
    _write(labeled, rows)
    with pytest.raises(ValueError, match="identity drift"):
        apply_context_recovery_review(
            template_path=template,
            labeled_path=labeled,
            source_items=(_source_item(),),
        )


def test_recovery_closure_selection_is_source_exact_and_context_unique() -> None:
    base = _source_item()
    items = []
    for source_slice, contexts in (
        (AnnotationSourceSlice.SEC_10K, (("k1", "A"), ("k2", "B"), ("k3", "A"))),
        (AnnotationSourceSlice.SEC_10Q, (("q1", "C"), ("q2", "D"))),
    ):
        for context_id, entity in contexts:
            items.append(replace(
                base,
                queue_item_id=f"pair-{context_id}",
                candidate_id=context_id,
                entity=entity,
                source_path=f"D:/{context_id}.htm",
                source_slice=source_slice,
            ))

    selection = select_recovery_contexts_for_source_gaps(
        tuple(items),
        source_gaps={"SEC_10K": 2, "SEC_10Q": 1},
    )

    assert len(selection.context_ids) == 3
    assert selection.context_counts == {"SEC_10K": 2, "SEC_10Q": 1}
    assert selection.pair_count == 3
    assert selection.entity_count == 3
