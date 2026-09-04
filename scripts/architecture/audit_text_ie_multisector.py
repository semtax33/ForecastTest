from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pandas as pd

from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table
from equity_platform.text_ie import default_spacy_backend, extract_text_kpis
from equity_platform.text_ie.training import (
    load_review_annotations,
    review_precision,
    weak_labels_from_result,
)


OUTPUT = PROJECT_ROOT / "output/platform_architecture_v2/text_ie_multisector"
COMPANIES = {
    "GD": "INDUSTRIALS",
    "HII": "INDUSTRIALS",
    "LMT": "INDUSTRIALS",
    "EOG": "ENERGY",
    "FANG": "ENERGY",
    "COP": "ENERGY",
    "DVN": "ENERGY",
    "AR": "ENERGY",
}
REVIEW_ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/multisector_review_annotations.jsonl"
)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _sources(ir_root: Path, ticker: str, count: int = 2) -> tuple[Path, ...]:
    candidates = sorted(
        (
            path
            for path in (ir_root / ticker).glob("*.htm")
            if "EX-99.1" in path.name.upper() and path.stat().st_size <= 8_000_000
        ),
        reverse=True,
    )
    return tuple(candidates[:count])


def main() -> int:
    arcana = Path(
        os.environ.get("ARCANA_ROOT", "D:/Programming/python_example/Arcana")
    )
    ir_root = arcana / "data-lake/bronze/sec/fillings/ir"
    backend = default_spacy_backend()
    if backend is None:
        raise RuntimeError("spaCy en_core_web_sm is required for the multisector audit")
    documents: list[dict[str, object]] = []
    frames: list[dict[str, object]] = []
    relations: list[dict[str, object]] = []
    reviews: list[dict[str, object]] = []
    weak_labels: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for ticker, sector in COMPANIES.items():
        paths = _sources(ir_root, ticker)
        if len(paths) != 2:
            errors.append({"ticker": ticker, "path": str(ir_root / ticker), "error": "EXPECTED_TWO_EX_99_1_FILES"})
            continue
        for path in paths:
            available_at = path.name[:10]
            digest = _sha(path)
            try:
                period = str(pd.Timestamp(available_at).to_period("Q"))
                document = adapt_html_document(
                    path=path,
                    metadata=DocumentMetadata(
                        entity=ticker,
                        source_kind="COMPANY_IR_SEC",
                        document_kind="EARNINGS_RELEASE",
                        available_at=available_at,
                        report_period=period,
                    ),
                    expected_sha256=digest,
                    source_uri=path.as_uri(),
                    include_tables=False,
                    include_inline_facts=False,
                )
                result = extract_text_kpis(document, backend=backend)
            except Exception as exc:  # audit records source-local failures
                errors.append({"ticker": ticker, "path": str(path), "error": repr(exc)})
                continue
            method_counts = Counter(frame.extraction_method.value for frame in result.frames)
            documents.append(
                {
                    "ticker": ticker,
                    "sector": sector,
                    "available_at": available_at,
                    "report_period": period,
                    "source_path": str(path),
                    "source_sha256": digest,
                    "sentences": len(document.sentences),
                    "frames": len(result.frames),
                    "facts": len(result.facts),
                    "claims": len(result.evidence_claims),
                    "relations": len(result.relations),
                    "reviews": len(result.reviews),
                    "dependency_frames": method_counts["DEPENDENCY_RULE"],
                    "context_frames": method_counts["CONTEXT_RULE"],
                }
            )
            for frame in result.frames:
                frames.append(
                    {
                        "ticker": ticker,
                        "sector": sector,
                        "concept": frame.concept,
                        "semantic_frame": frame.frame.value,
                        "period": frame.period,
                        "value": frame.value,
                        "unit": frame.unit,
                        "scope": frame.scope,
                        "method": frame.extraction_method.value,
                        "confidence": frame.extraction_confidence,
                        "authority": frame.authority.name,
                        "rule_id": frame.rule_id,
                        "source_sha256": digest,
                        "source_literal": frame.source_span.literal,
                    }
                )
            for relation in result.relations:
                relations.append(
                    {
                        "ticker": ticker,
                        "sector": sector,
                        "cause": relation.cause,
                        "effect": relation.effect,
                        "direction": relation.direction,
                        "relation_type": relation.relation_type,
                        "method": "DEPENDENCY_RULE",
                        "source_sha256": digest,
                        "source_literal": relation.source_span.literal,
                    }
                )
            for review in result.reviews:
                review_id = sha256(
                    f"{digest}:{review.rule_id}:{review.source_span.char_start}".encode()
                ).hexdigest()[:20]
                reviews.append(
                    {
                        "review_id": review_id,
                        "ticker": ticker,
                        "sector": sector,
                        "rule_id": review.rule_id,
                        "status": review.status,
                        "reason": review.reason,
                        "candidates": "|".join(review.candidates),
                        "source_sha256": digest,
                        "source_literal": review.source_span.literal,
                        "annotation_status": "UNREVIEWED",
                        "gold_decision": "",
                    }
                )
            for label in weak_labels_from_result(result):
                weak_labels.append(
                    {
                        "ticker": ticker,
                        "sector": sector,
                        "source_sha256": label.source_sha256 or digest,
                        "sentence_start": label.sentence_start,
                        "sentence_end": label.sentence_end,
                        "labeling_function": label.labeling_function,
                        "label": label.label,
                        "confidence": label.confidence,
                        "abstained": label.abstained,
                    }
                )
    document_frame = pd.DataFrame(documents)
    frame_frame = pd.DataFrame(frames)
    relation_frame = pd.DataFrame(relations)
    review_frame = pd.DataFrame(reviews)
    annotations = load_review_annotations(REVIEW_ANNOTATIONS)
    annotation_map = {row.review_id: row for row in annotations}
    review_stats = review_precision(set(review_frame["review_id"]), annotations)
    review_frame["annotation_status"] = review_frame["review_id"].map(
        lambda value: "REVIEWED" if value in annotation_map else "UNREVIEWED"
    )
    review_frame["gold_decision"] = review_frame["review_id"].map(
        lambda value: (
            "SHOULD_REVIEW" if annotation_map[value].should_review else "SHOULD_NOT_REVIEW"
        )
        if value in annotation_map
        else ""
    )
    review_frame["annotation_category"] = review_frame["review_id"].map(
        lambda value: annotation_map[value].category if value in annotation_map else ""
    )
    weak_frame = pd.DataFrame(weak_labels)
    summary = pd.DataFrame(
        [
            {
                "tickers": int(document_frame["ticker"].nunique()) if not document_frame.empty else 0,
                "documents": len(document_frame),
                "industrials_documents": int(document_frame["sector"].eq("INDUSTRIALS").sum()) if not document_frame.empty else 0,
                "energy_documents": int(document_frame["sector"].eq("ENERGY").sum()) if not document_frame.empty else 0,
                "documents_with_frames": int(document_frame["frames"].gt(0).sum()) if not document_frame.empty else 0,
                "frames": len(frame_frame),
                "facts": int(document_frame["facts"].sum()) if not document_frame.empty else 0,
                "claims": int(document_frame["claims"].sum()) if not document_frame.empty else 0,
                "dependency_relations": len(relation_frame),
                "review_queue": len(review_frame),
                "review_annotations": review_stats["annotated"],
                "review_annotation_coverage": review_stats["annotation_coverage"],
                "queue_annotation_coverage": review_stats["queue_annotation_coverage"],
                "actual_review_precision": review_stats["precision"],
                "actual_review_recall": review_stats["recall"],
                "weak_labels": len(weak_frame),
                "errors": len(errors),
                "spacy_model": backend.model,
                "status": (
                    "PASS"
                    if len(document_frame) == 16
                    and not errors
                    and review_stats["annotation_coverage"] == 1.0
                    and review_stats["queue_annotation_coverage"] == 1.0
                    else "FAIL"
                ),
            }
        ]
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    document_frame.to_csv(OUTPUT / "document_coverage.csv", index=False)
    frame_frame.to_csv(OUTPUT / "frames.csv", index=False)
    relation_frame.to_csv(OUTPUT / "relations.csv", index=False)
    review_frame.to_csv(OUTPUT / "review_queue.csv", index=False)
    weak_frame.to_csv(OUTPUT / "weak_labels.csv", index=False)
    pd.DataFrame(errors).to_csv(OUTPUT / "errors.csv", index=False)
    summary.to_csv(OUTPUT / "gate.csv", index=False)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "arcana_ir_root": str(ir_root),
                "selection": "latest two EX-99.1 HTML files <=8MB per ticker",
                "backend": backend.name,
                "model": backend.model,
                "actual_review_annotations": "review_queue.csv",
                "review_annotation_source": str(REVIEW_ANNOTATIONS),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "report.md").write_text(
        f"""# Multisector semantic text-IE audit

## Gate

{markdown_table(summary)}

The audit reads real HTML from Arcana bronze IR storage. It covers GD, HII and
LMT plus EOG, FANG, COP, DVN and AR. All DSL extraction remains capped at
research authority; the review queue is exported separately and never becomes
a fact implicitly.
""",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    return 0 if summary.iloc[0]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
