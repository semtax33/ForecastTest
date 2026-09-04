from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v24 import extract_text_kpis_v24, metric_anchors
from scripts.architecture.v24_blind_candidates import (
    CANDIDATES,
    OUTPUT,
    _documents,
    load_blind_config,
    verify_candidate_artifact,
    verify_v24_snapshot,
)


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v24_unseen_sentence_annotations.jsonl"
)


def _base_concept(concept: str) -> str:
    base = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE", "_NOT_EXPECTED"):
        base = base.removesuffix(suffix)
    return base


def _annotations() -> pd.DataFrame:
    rows = [
        json.loads(line)
        for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    frame = pd.DataFrame(rows)
    if frame.empty or frame["candidate_id"].duplicated().any():
        raise ValueError("V2.4 unseen annotations must be non-empty and unique")
    return frame


def _frame_dict(frame: object) -> dict[str, object]:
    return {
        "concept": frame.concept,
        "frame": frame.frame.value,
        "value": frame.value,
        "change": frame.change,
        "lower_value": frame.lower_value,
        "upper_value": frame.upper_value,
        "polarity": "POSITIVE" if frame.polarity.positive else "NEGATIVE",
        "tier": frame.tier.value,
        "rule_id": frame.rule_id,
        "source_span_exact": bool(frame.source_span.literal),
    }


def _binding_dict(binding: object) -> dict[str, object]:
    return {
        "concept": binding.output_concept,
        "frame": binding.frame.value,
        "value": binding.value.value if binding.value else None,
        "change": None,
        "lower_value": binding.lower_value,
        "upper_value": binding.upper_value,
    }


def _matches(expected: dict[str, object], actual: dict[str, object]) -> bool:
    for key, value in expected.items():
        if key in {"value", "change", "lower_value", "upper_value"} and value is not None:
            candidate = actual.get(key)
            if candidate is None or abs(float(candidate) - float(value)) > max(
                1e-9, abs(float(value)) * 1e-9
            ):
                return False
        elif key in actual and actual.get(key) != value:
            return False
        elif key not in actual and key not in {"tier", "polarity"}:
            return False
    return True


def _within_span(item: object, start: int, end: int) -> bool:
    span = item.source_span
    return span.char_start >= start and span.char_end <= end


def _within_block(item: object, start: int, end: int) -> bool:
    block = item.block
    return block.char_start >= start and block.char_end <= end


def _match_counts(
    expected: list[dict[str, object]],
    actual: list[dict[str, object]],
) -> tuple[set[int], set[int]]:
    remaining = list(range(len(actual)))
    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    for expected_index, target in enumerate(expected):
        actual_index = next(
            (index for index in remaining if _matches(target, actual[index])),
            None,
        )
        if actual_index is not None:
            matched_expected.add(expected_index)
            matched_actual.add(actual_index)
            remaining.remove(actual_index)
    return matched_expected, matched_actual


def evaluate_unseen_sentences() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    config = load_blind_config()
    verify_v24_snapshot(config)
    verify_candidate_artifact(config)
    candidates = pd.read_csv(CANDIDATES)
    annotations = _annotations()
    if set(candidates["candidate_id"]) != set(annotations["candidate_id"]):
        raise ValueError("Every V2.4 selected block must be exhaustively annotated")
    joined = candidates.merge(
        annotations,
        on=["candidate_id", "ticker"],
        how="left",
        validate="one_to_one",
    )
    documents = _documents()
    results = {ticker: extract_text_kpis_v24(document) for ticker, document in documents.items()}

    rows: list[dict[str, object]] = []
    candidate_tp = candidate_fp = 0
    for item in joined.itertuples(index=False):
        result = results[item.ticker]
        extraction = result.extraction
        start, end = int(item.char_start), int(item.char_end)
        expected = list(item.expected_frames)
        eligible = item.gold_route != "TABLE_DSL"
        frames = [_frame_dict(frame) for frame in extraction.frames if _within_span(frame, start, end)]
        reviews = [review for review in extraction.reviews if _within_span(review, start, end)]
        abstentions = [a for a in extraction.abstentions if _within_span(a, start, end)]
        recall_candidates = [
            candidate for candidate in result.candidates if _within_block(candidate, start, end)
        ]
        bindings = [binding for binding in result.bindings if _within_block(binding, start, end)]
        table_routes = [
            table
            for table in result.table_routes
            if table.char_start >= start and table.char_end <= end
        ]
        mention_concepts = {
            anchor.concept for anchor in metric_anchors(item.text, item.heading if pd.notna(item.heading) else None)
        }
        candidate_concepts = {candidate.metric.concept for candidate in recall_candidates}
        gold_concepts = {_base_concept(str(frame["concept"])) for frame in expected}
        if eligible:
            candidate_tp += sum(candidate.metric.concept in gold_concepts for candidate in recall_candidates)
            candidate_fp += sum(candidate.metric.concept not in gold_concepts for candidate in recall_candidates)

        legacy_binding_frames = [
            frame for frame in frames if not str(frame["rule_id"]).startswith("v24.")
        ]
        binding_frames = [_binding_dict(binding) for binding in bindings] + legacy_binding_frames
        binding_matched, _ = _match_counts(expected, binding_frames) if eligible else (set(), set())
        matched_expected, matched_actual = _match_counts(expected, frames) if eligible else (set(), set())
        tp = len(matched_expected)
        fp = len(frames) - len(matched_actual) if eligible else 0
        fn = len(expected) - tp if eligible else 0
        critical_tp = sum(
            expected[index].get("tier", "CRITICAL") == "CRITICAL"
            for index in matched_expected
        )
        critical_fn = sum(
            target.get("tier", "CRITICAL") == "CRITICAL"
            for index, target in enumerate(expected)
            if eligible and index not in matched_expected
        )
        critical_fp = sum(
            frame["tier"] == "CRITICAL"
            for index, frame in enumerate(frames)
            if eligible and index not in matched_actual
        )
        narrative_tp = tp - critical_tp
        narrative_fn = fn - critical_fn
        narrative_fp = fp - critical_fp
        if frames:
            disposition = "AUTO_EMITTED"
        elif reviews:
            disposition = "REVIEW"
        elif abstentions:
            disposition = "ABSTAINED"
        else:
            disposition = "SILENT"
        table_pass = item.gold_route != "TABLE_DSL" or bool(table_routes)
        rows.append(
            {
                "candidate_id": item.candidate_id,
                "ticker": item.ticker,
                "gold_route": item.gold_route,
                "sampling_stratum": item.sampling_stratum,
                "expected_frames": len(expected),
                "mention_hits": sum(
                    _base_concept(str(target["concept"])) in mention_concepts for target in expected
                ) if eligible else 0,
                "candidate_hits": sum(
                    _base_concept(str(target["concept"])) in candidate_concepts for target in expected
                ) if eligible else 0,
                "binding_hits": len(binding_matched),
                "actual_frames": len(frames),
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
                "table_route_pass": table_pass,
                "source_span_coverage": (
                    min((frame["source_span_exact"] for frame in frames), default=True)
                ),
                "expected_frames_json": json.dumps(expected, ensure_ascii=False),
                "actual_frames_json": json.dumps(frames, ensure_ascii=False),
                "mention_concepts": "|".join(sorted(mention_concepts)),
                "candidate_concepts": "|".join(sorted(candidate_concepts)),
                "binding_frames_json": json.dumps(binding_frames, ensure_ascii=False),
                "annotation_note": item.annotation_note,
                "text": item.text,
            }
        )
    detail = pd.DataFrame(rows)

    def totals(prefix: str) -> tuple[int, int, int, float, float, float]:
        tp = int(detail[f"{prefix}true_positive"].sum())
        fp = int(detail[f"{prefix}false_positive"].sum())
        fn = int(detail[f"{prefix}false_negative"].sum())
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return tp, fp, fn, precision, recall, f1

    all_score = totals("")
    critical = totals("critical_")
    narrative = totals("narrative_")
    gold_opportunities = int(detail["expected_frames"].sum())
    ladder = pd.DataFrame(
        [
            {"stage": "MENTION", "hits": int(detail["mention_hits"].sum()), "opportunities": gold_opportunities},
            {"stage": "CANDIDATE", "hits": int(detail["candidate_hits"].sum()), "opportunities": gold_opportunities},
            {"stage": "BINDING", "hits": int(detail["binding_hits"].sum()), "opportunities": gold_opportunities},
            {"stage": "FINAL_FACT", "hits": all_score[0], "opportunities": gold_opportunities},
        ]
    )
    ladder["recall"] = ladder["hits"] / ladder["opportunities"]
    dispositions = detail["disposition"].value_counts()
    missed = detail.loc[detail["false_negative"].gt(0)]
    routed_misses = missed["disposition"].isin(["REVIEW", "ABSTAINED", "AUTO_EMITTED"])
    table_rows = detail.loc[detail["gold_route"].eq("TABLE_DSL")]
    gates = dict(config["gates"])
    summary = pd.DataFrame(
        [
            {
                "version": "PLATFORM_V2_4_ISSUER_DOCUMENT_UNSEEN",
                "issuer_unseen": True,
                "document_unseen": True,
                "parser_snapshot_verified": True,
                "candidate_artifact_verified": True,
                "evaluation_issuers": detail["ticker"].nunique(),
                "annotated_blocks": len(detail),
                "annotation_coverage": len(detail) / len(candidates),
                "expected_frames": gold_opportunities,
                "candidate_precision": candidate_tp / (candidate_tp + candidate_fp) if candidate_tp + candidate_fp else 1.0,
                "mention_recall": float(ladder.loc[ladder["stage"].eq("MENTION"), "recall"].iloc[0]),
                "candidate_recall": float(ladder.loc[ladder["stage"].eq("CANDIDATE"), "recall"].iloc[0]),
                "binding_recall": float(ladder.loc[ladder["stage"].eq("BINDING"), "recall"].iloc[0]),
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
                "auto_coverage": dispositions.get("AUTO_EMITTED", 0) / len(detail),
                "review_rate": dispositions.get("REVIEW", 0) / len(detail),
                "abstention_rate": dispositions.get("ABSTAINED", 0) / len(detail),
                "silent_rate": dispositions.get("SILENT", 0) / len(detail),
                "review_plus_abstention_miss_capture": float(routed_misses.mean()) if len(missed) else 1.0,
                "table_route_accuracy": float(table_rows["table_route_pass"].mean()) if len(table_rows) else 1.0,
                "source_span_coverage": float(detail["source_span_coverage"].min()),
                "precision_gate_99pct": critical[3] >= float(gates["critical_precision"]),
                "v24_recall_milestone_50pct": critical[4] >= float(gates["v24_recall_milestone"]),
                "final_recall_gate_95pct": critical[4] >= float(gates["final_critical_recall"]),
                "rule_changes_after_selection": False,
                "status": (
                    "V24_MILESTONE_PASS"
                    if critical[3] >= float(gates["critical_precision"])
                    and critical[4] >= float(gates["v24_recall_milestone"])
                    else "HOLD_RESEARCH_UNFROZEN"
                ),
            }
        ]
    )
    return detail, summary, ladder


def main() -> int:
    detail, summary, ladder = evaluate_unseen_sentences()
    write_csv_artifacts(
        OUTPUT,
        {
            "blind_sentence_evaluation": detail,
            "blind_sentence_summary": summary,
            "coverage_ladder": ladder,
        },
    )
    (OUTPUT / "blind_sentence_metadata.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "annotations": ANNOTATIONS.relative_to(PROJECT_ROOT).as_posix(),
                "candidate_sha256": sha256_file(CANDIDATES),
                "llm_backend_used": False,
                "rule_changes_after_selection": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
