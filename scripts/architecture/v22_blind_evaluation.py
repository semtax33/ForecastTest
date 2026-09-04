from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie import extract_text_kpis
from scripts.architecture.universe_certification_v21 import _latest_ir_source
from scripts.architecture.v22_blind_candidates import (
    OUTPUT,
    candidate_blocks,
    load_blind_config,
    verify_parser_snapshot,
)


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v22_blind_sentence_annotations.jsonl"
)


def _annotations() -> pd.DataFrame:
    rows = [
        json.loads(raw)
        for raw in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    frame = pd.DataFrame(rows)
    if frame.empty or frame["candidate_id"].duplicated().any():
        raise ValueError("Blind sentence annotations must be non-empty and unique")
    return frame


def _actual_documents(tickers: set[str]) -> dict[str, object]:
    documents: dict[str, object] = {}
    for ticker in sorted(tickers):
        path = _latest_ir_source(ticker)
        if path is None:
            raise FileNotFoundError(f"No latest Arcana IR HTML for {ticker}")
        available_at = path.name[:10]
        documents[ticker] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(
                entity=ticker,
                source_kind="COMPANY_IR_SEC",
                document_kind="EARNINGS_RELEASE",
                available_at=available_at,
                report_period=str(pd.Timestamp(available_at).to_period("Q")),
            ),
            expected_sha256=sha256_file(path),
            source_uri=path.as_uri(),
            include_tables=False,
            include_inline_facts=False,
        )
    return documents


def _frame_dict(frame: object) -> dict[str, object]:
    return {
        "concept": frame.concept,
        "frame": frame.frame.value,
        "value": frame.value,
        "change": frame.change,
        "tier": frame.tier.value,
        "source_span_exact": bool(frame.source_span.literal),
    }


def _matches(expected: dict[str, object], actual: dict[str, object]) -> bool:
    for key, value in expected.items():
        if key in {"value", "change"} and value is not None:
            candidate = actual.get(key)
            if candidate is None or abs(float(candidate) - float(value)) > max(
                1e-9, abs(float(value)) * 1e-9
            ):
                return False
        elif actual.get(key) != value:
            return False
    return True


def evaluate_blind_sentences() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_blind_config()
    verify_parser_snapshot(config)
    candidates = candidate_blocks()
    annotations = _annotations()
    if set(candidates["candidate_id"]) != set(annotations["candidate_id"]):
        raise ValueError("Every selected blind sentence must be exhaustively annotated")
    joined = candidates.merge(
        annotations,
        on=["candidate_id", "ticker"],
        how="left",
        validate="one_to_one",
    )
    documents = _actual_documents(set(joined["ticker"]))
    extractions = {
        ticker: extract_text_kpis(document)
        for ticker, document in documents.items()
    }
    rows: list[dict[str, object]] = []
    for item in joined.itertuples(index=False):
        result = extractions[item.ticker]
        actual_frames = [
            _frame_dict(frame)
            for frame in result.frames
            if frame.source_span.char_start == int(item.char_start)
        ]
        reviews = [
            review
            for review in result.reviews
            if review.source_span.char_start == int(item.char_start)
        ]
        abstentions = [
            abstention
            for abstention in result.abstentions
            if abstention.source_span.char_start == int(item.char_start)
        ]
        if actual_frames:
            disposition = "AUTO_EMITTED"
        elif reviews:
            disposition = "REVIEW"
        elif abstentions:
            disposition = "ABSTAINED"
        else:
            disposition = "SILENT"
        expected = list(item.expected_frames)
        eligible = item.gold_route != "TABLE_DSL"
        remaining = list(range(len(actual_frames)))
        matched_expected: set[int] = set()
        matched_actual: set[int] = set()
        if eligible:
            for expected_index, target in enumerate(expected):
                actual_index = next(
                    (
                        index
                        for index in remaining
                        if _matches(target, actual_frames[index])
                    ),
                    None,
                )
                if actual_index is not None:
                    matched_expected.add(expected_index)
                    matched_actual.add(actual_index)
                    remaining.remove(actual_index)
        tp = len(matched_expected)
        fp = len(actual_frames) - len(matched_actual) if eligible else 0
        fn = len(expected) - tp if eligible else 0
        critical_tp = sum(
            expected[index].get("tier", "CRITICAL") == "CRITICAL"
            for index in matched_expected
        )
        critical_fn = sum(
            target.get("tier", "CRITICAL") == "CRITICAL"
            for index, target in enumerate(expected)
            if index not in matched_expected
        ) if eligible else 0
        critical_fp = sum(
            frame["tier"] == "CRITICAL"
            for index, frame in enumerate(actual_frames)
            if eligible and index not in matched_actual
        )
        narrative_tp = tp - critical_tp
        narrative_fn = fn - critical_fn
        narrative_fp = fp - critical_fp
        table_route_pass = (
            item.gold_route != "TABLE_DSL"
            or (
                disposition == "ABSTAINED"
                and any(
                    abstention.failure_class == "TABLE_TEXT_BOUNDARY"
                    for abstention in abstentions
                )
            )
        )
        rows.append(
            {
                "candidate_id": item.candidate_id,
                "ticker": item.ticker,
                "gold_route": item.gold_route,
                "sampling_stratum": item.sampling_stratum,
                "expected_frames": len(expected),
                "actual_frames": len(actual_frames),
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "critical_true_positive": critical_tp,
                "critical_false_positive": critical_fp,
                "critical_false_negative": critical_fn,
                "narrative_true_positive": narrative_tp,
                "narrative_false_positive": narrative_fp,
                "narrative_false_negative": narrative_fn,
                "disposition": disposition,
                "review_count": len(reviews),
                "abstention_count": len(abstentions),
                "table_route_pass": table_route_pass,
                "source_span_coverage": (
                    sum(bool(frame["source_span_exact"]) for frame in actual_frames)
                    / len(actual_frames)
                    if actual_frames
                    else 1.0
                ),
                "expected_frames_json": json.dumps(expected, ensure_ascii=False),
                "actual_frames_json": json.dumps(actual_frames, ensure_ascii=False),
                "annotation_note": item.annotation_note,
                "text": item.text,
            }
        )
    detail = pd.DataFrame(rows)

    def total(column: str) -> int:
        return int(detail[column].sum())

    def score(prefix: str) -> tuple[int, int, int, float, float, float]:
        tp = total(f"{prefix}true_positive")
        fp = total(f"{prefix}false_positive")
        fn = total(f"{prefix}false_negative")
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return tp, fp, fn, precision, recall, f1

    all_score = score("")
    critical = score("critical_")
    narrative = score("narrative_")
    dispositions = detail["disposition"].value_counts()
    decision_count = len(detail)
    missed = detail.loc[detail["false_negative"].gt(0)]
    routed_misses = missed["disposition"].isin(["REVIEW", "ABSTAINED"])
    summary = pd.DataFrame(
        [
            {
                "version": "PLATFORM_V2_2_BLIND_B_SENTENCE_GOLD",
                "parser_snapshot_verified": True,
                "evaluation_issuers": detail["ticker"].nunique(),
                "annotated_blocks": len(detail),
                "annotation_coverage": len(detail) / len(candidates),
                "expected_frames": int(detail["expected_frames"].sum()),
                "auto_emitted_frames": int(detail["actual_frames"].sum()),
                "auto_precision": all_score[3],
                "auto_recall": all_score[4],
                "auto_f1": all_score[5],
                "critical_opportunities": critical[0] + critical[2],
                "critical_precision": critical[3],
                "critical_recall": critical[4],
                "critical_f1": critical[5],
                "narrative_opportunities": narrative[0] + narrative[2],
                "narrative_precision": narrative[3],
                "narrative_recall": narrative[4],
                "narrative_status": (
                    "MEASURED"
                    if narrative[0] + narrative[2] > 0
                    else "NOT_MEASURED_NO_OPPORTUNITIES"
                ),
                "auto_coverage": dispositions.get("AUTO_EMITTED", 0) / decision_count,
                "review_rate": dispositions.get("REVIEW", 0) / decision_count,
                "abstention_rate": dispositions.get("ABSTAINED", 0) / decision_count,
                "silent_rate": dispositions.get("SILENT", 0) / decision_count,
                "review_plus_abstention_miss_capture": (
                    float(routed_misses.mean()) if len(missed) else 1.0
                ),
                "table_route_accuracy": float(
                    detail.loc[detail["gold_route"].eq("TABLE_DSL"), "table_route_pass"].mean()
                ),
                "source_span_coverage": float(detail["source_span_coverage"].min()),
                "critical_precision_gate_99pct": critical[3] >= 0.99,
                "critical_recall_gate_95pct": critical[4] >= 0.95,
                "rule_changes_after_selection": False,
                "status": (
                    "PASS"
                    if critical[3] >= 0.99 and critical[4] >= 0.95
                    else "HOLD_RESEARCH_UNFROZEN"
                ),
            }
        ]
    )
    return detail, summary


def main() -> int:
    detail, summary = evaluate_blind_sentences()
    write_csv_artifacts(
        OUTPUT,
        {
            "blind_sentence_evaluation": detail,
            "blind_sentence_summary": summary,
        },
    )
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "annotations": ANNOTATIONS.relative_to(PROJECT_ROOT).as_posix(),
        "rule_changes_after_selection": False,
    }
    (OUTPUT / "blind_sentence_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
