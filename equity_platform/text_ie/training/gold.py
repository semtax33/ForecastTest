from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments

from ..runtime import extract_text_kpis


@dataclass(frozen=True)
class GoldExample:
    example_id: str
    entity: str
    document_period: str
    heading: str | None
    text: str
    expected_frames: tuple[dict[str, object], ...]
    expected_fact_count: int
    expected_claim_count: int
    expected_review_count: int
    expected_relation_count: int
    expected_abstention_count: int | None
    annotation_source: str


def load_gold_corpus(path: Path) -> tuple[GoldExample, ...]:
    examples: list[GoldExample] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            examples.append(
                GoldExample(
                    example_id=str(row["example_id"]),
                    entity=str(row["entity"]),
                    document_period=str(row["document_period"]),
                    heading=row.get("heading"),
                    text=str(row["text"]),
                    expected_frames=tuple(row.get("expected_frames", ())),
                    expected_fact_count=int(row.get("expected_fact_count", 0)),
                    expected_claim_count=int(row.get("expected_claim_count", 0)),
                    expected_review_count=int(row.get("expected_review_count", 0)),
                    expected_relation_count=int(row.get("expected_relation_count", 0)),
                    expected_abstention_count=(
                        int(row["expected_abstention_count"])
                        if "expected_abstention_count" in row
                        else None
                    ),
                    annotation_source=str(row.get("annotation_source", "HUMAN_SEED")),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid gold example on line {line_number}") from exc
    ids = [example.example_id for example in examples]
    if len(ids) != len(set(ids)):
        raise ValueError("Gold example ids must be unique")
    if not examples:
        raise ValueError("Gold corpus cannot be empty")
    return tuple(examples)


def _document(example: GoldExample):
    heading = f"<h2>{example.heading}</h2>" if example.heading else ""
    html = f"<html><body>{heading}<p>{example.text}</p></body></html>".encode()
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                content=html,
                source_uri=f"gold://{example.example_id}",
                source_description="TEXT_IE_GOLD",
                expected_sha256=sha256(html).hexdigest(),
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            entity=example.entity,
            source_kind="GOLD_CORPUS",
            document_kind="TEXT_IE_EXAMPLE",
            available_at="2026-09-04",
            report_period=example.document_period,
        ),
    )


def evaluate_gold_corpus(path: Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for example in load_gold_corpus(path):
        result = extract_text_kpis(_document(example))
        actual = [
            {
                "concept": frame.concept,
                "frame": frame.frame.value,
                "value": frame.value,
                "change": frame.change,
                "scope": frame.scope,
                "period": frame.period,
                "polarity": "POSITIVE" if frame.polarity.positive else "NEGATED",
                "tier": frame.tier.value,
            }
            for frame in result.frames
        ]
        def matches(expected: dict[str, object], candidate: dict[str, object]) -> bool:
            return all(
                (
                    abs(float(candidate[key]) - float(value)) <= max(1e-9, abs(float(value)) * 1e-9)
                    if key in {"value", "change"} and value is not None
                    else candidate.get(key) == value
                )
                for key, value in expected.items()
            )

        remaining = list(range(len(actual)))
        true_positive = 0
        matched_expected: set[int] = set()
        matched_actual: set[int] = set()
        for expected_index, expected in enumerate(example.expected_frames):
            matched_index = next(
                (
                    index
                    for index in remaining
                    if matches(expected, actual[index])
                ),
                None,
            )
            if matched_index is not None:
                true_positive += 1
                remaining.remove(matched_index)
                matched_expected.add(expected_index)
                matched_actual.add(matched_index)
        false_positive = len(actual) - true_positive
        false_negative = len(example.expected_frames) - true_positive
        expected_match = false_positive == 0 and false_negative == 0
        counts_match = (
            len(result.facts) == example.expected_fact_count
            and len(result.evidence_claims) == example.expected_claim_count
            and len(result.reviews) == example.expected_review_count
            and len(result.relations) == example.expected_relation_count
            and (
                example.expected_abstention_count is None
                or len(result.abstentions) == example.expected_abstention_count
            )
        )
        def expected_tier(frame: dict[str, object]) -> str:
            if "tier" in frame:
                return str(frame["tier"])
            return (
                "CRITICAL"
                if frame.get("value") is not None or frame.get("change") is not None
                else "NARRATIVE"
            )

        critical_tp = sum(
            expected_tier(example.expected_frames[index]) == "CRITICAL"
            for index in matched_expected
        )
        narrative_tp = true_positive - critical_tp
        critical_fp = sum(
            actual[index]["tier"] == "CRITICAL"
            for index in range(len(actual))
            if index not in matched_actual
        )
        narrative_fp = false_positive - critical_fp
        critical_fn = sum(
            expected_tier(frame) == "CRITICAL"
            for index, frame in enumerate(example.expected_frames)
            if index not in matched_expected
        )
        narrative_fn = false_negative - critical_fn
        rows.append(
            {
                "example_id": example.example_id,
                "expected_frames": len(example.expected_frames),
                "actual_frames": len(result.frames),
                "actual_facts": len(result.facts),
                "actual_claims": len(result.evidence_claims),
                "actual_reviews": len(result.reviews),
                "actual_abstentions": len(result.abstentions),
                "actual_relations": len(result.relations),
                "frame_true_positive": true_positive,
                "frame_false_positive": false_positive,
                "frame_false_negative": false_negative,
                "critical_true_positive": critical_tp,
                "critical_false_positive": critical_fp,
                "critical_false_negative": critical_fn,
                "narrative_true_positive": narrative_tp,
                "narrative_false_positive": narrative_fp,
                "narrative_false_negative": narrative_fn,
                "critical_reviews": sum(item.tier.value == "CRITICAL" for item in result.reviews),
                "narrative_reviews": sum(item.tier.value == "NARRATIVE" for item in result.reviews),
                "critical_abstentions": sum(item.tier.value == "CRITICAL" for item in result.abstentions),
                "narrative_abstentions": sum(item.tier.value == "NARRATIVE" for item in result.abstentions),
                "review_true_positive": min(len(result.reviews), example.expected_review_count),
                "review_false_positive": max(0, len(result.reviews) - example.expected_review_count),
                "review_false_negative": max(0, example.expected_review_count - len(result.reviews)),
                "annotation_source": example.annotation_source,
                "frame_match": expected_match,
                "count_match": counts_match,
                "passed": expected_match and counts_match,
            }
        )
    return tuple(rows)


def corpus_metrics(rows: tuple[dict[str, object], ...]) -> dict[str, object]:
    def total(key: str) -> int:
        return sum(int(row[key]) for row in rows)

    frame_tp = total("frame_true_positive")
    frame_fp = total("frame_false_positive")
    frame_fn = total("frame_false_negative")
    review_tp = total("review_true_positive")
    review_fp = total("review_false_positive")
    review_fn = total("review_false_negative")
    return {
        "examples": len(rows),
        "exact_passed": sum(bool(row["passed"]) for row in rows),
        "exact_accuracy": sum(bool(row["passed"]) for row in rows) / len(rows),
        "frame_precision": frame_tp / (frame_tp + frame_fp) if frame_tp + frame_fp else 1.0,
        "frame_recall": frame_tp / (frame_tp + frame_fn) if frame_tp + frame_fn else 1.0,
        "review_precision": review_tp / (review_tp + review_fp) if review_tp + review_fp else 1.0,
        "review_recall": review_tp / (review_tp + review_fn) if review_tp + review_fn else 1.0,
    }


def calibration_metrics(rows: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Score auto emission, review, and abstention for exhaustive gold."""

    if not rows:
        raise ValueError("Calibration rows cannot be empty")

    def total(key: str) -> int:
        return sum(int(row[key]) for row in rows)

    def scores(prefix: str) -> tuple[float, float, float]:
        tp = total(f"{prefix}true_positive")
        fp = total(f"{prefix}false_positive")
        fn = total(f"{prefix}false_negative")
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return precision, recall, f1

    precision, recall, f1 = scores("frame_")
    critical_precision, critical_recall, critical_f1 = scores("critical_")
    narrative_precision, narrative_recall, narrative_f1 = scores("narrative_")
    auto = total("actual_frames")
    review = total("actual_reviews")
    abstain = total("actual_abstentions")
    decisions = auto + review + abstain
    false_negative = total("frame_false_negative")
    review_capture = sum(
        min(int(row["frame_false_negative"]), int(row["actual_reviews"]))
        for row in rows
    )
    abstention_capture = sum(
        min(
            max(0, int(row["frame_false_negative"]) - int(row["actual_reviews"])),
            int(row["actual_abstentions"]),
        )
        for row in rows
    )
    return {
        "examples": len(rows),
        "expected_frames": total("expected_frames"),
        "auto_emitted": auto,
        "reviews": review,
        "abstentions": abstain,
        "auto_precision": precision,
        "auto_recall": recall,
        "auto_f1": f1,
        "critical_precision": critical_precision,
        "critical_recall": critical_recall,
        "critical_f1": critical_f1,
        "narrative_precision": narrative_precision,
        "narrative_recall": narrative_recall,
        "narrative_f1": narrative_f1,
        "auto_coverage": auto / decisions if decisions else 1.0,
        "review_rate": review / decisions if decisions else 0.0,
        "abstention_rate": abstain / decisions if decisions else 0.0,
        "review_capture": review_capture / false_negative if false_negative else 1.0,
        "review_plus_abstention_capture": (
            (review_capture + abstention_capture) / false_negative
            if false_negative
            else 1.0
        ),
    }
