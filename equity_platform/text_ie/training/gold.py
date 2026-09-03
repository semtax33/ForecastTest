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
            }
            for frame in result.frames
        ]
        expected_match = all(
            any(
                all(
                    (
                        abs(float(candidate[key]) - float(value)) <= max(1e-9, abs(float(value)) * 1e-9)
                        if key in {"value", "change"} and value is not None
                        else candidate.get(key) == value
                    )
                    for key, value in expected.items()
                )
                for candidate in actual
            )
            for expected in example.expected_frames
        )
        counts_match = (
            len(result.facts) == example.expected_fact_count
            and len(result.evidence_claims) == example.expected_claim_count
            and len(result.reviews) == example.expected_review_count
        )
        rows.append(
            {
                "example_id": example.example_id,
                "expected_frames": len(example.expected_frames),
                "actual_frames": len(result.frames),
                "actual_facts": len(result.facts),
                "actual_claims": len(result.evidence_claims),
                "actual_reviews": len(result.reviews),
                "frame_match": expected_match,
                "count_match": counts_match,
                "passed": expected_match and counts_match,
            }
        )
    return tuple(rows)

