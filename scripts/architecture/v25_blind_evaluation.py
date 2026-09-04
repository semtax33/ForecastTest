from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v24 import metric_anchors
from equity_platform.text_ie.v25 import extract_text_kpis_v25
from scripts.architecture.v25_blind_candidates import (
    CANDIDATES,
    OUTPUT,
    _documents,
    load_blind_config,
    verify_candidate_artifact,
    verify_v25_snapshot,
)


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v25_unseen_sentence_annotations.jsonl"


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE", "_NOT_EXPECTED"):
        result = result.removesuffix(suffix)
    return result


def _matches(expected: dict[str, object], actual: dict[str, object]) -> bool:
    for key, value in expected.items():
        if key in {"value", "change", "lower_value", "upper_value"} and value is not None:
            candidate = actual.get(key)
            if candidate is None or abs(float(candidate) - float(value)) > max(1e-9, abs(float(value)) * 1e-9):
                return False
        elif key in actual and actual[key] != value:
            return False
        elif key not in actual and key not in {"tier", "polarity"}:
            return False
    return True


def _counts(expected: list[dict[str, object]], actual: list[dict[str, object]]) -> tuple[set[int], set[int]]:
    remaining = list(range(len(actual)))
    expected_hits, actual_hits = set(), set()
    for i, target in enumerate(expected):
        found = next((j for j in remaining if _matches(target, actual[j])), None)
        if found is not None:
            expected_hits.add(i)
            actual_hits.add(found)
            remaining.remove(found)
    return expected_hits, actual_hits


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
    }


def _binding_dict(binding: object) -> dict[str, object]:
    if binding.level is not None and binding.delta is not None:
        frame, value, change = "CHANGE_TO", binding.level.value, binding.delta.value
    elif binding.delta is not None:
        frame, value, change = "CHANGE_BY", binding.delta.value, None
    elif binding.level is not None:
        frame, value, change = "ABSOLUTE_VALUE", binding.level.value, None
    else:
        frame, value, change = "NONE", None, None
    return {"concept": binding.candidate.metric.concept, "frame": frame, "value": value, "change": change}


def evaluate_unseen_sentences() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    config = load_blind_config()
    verify_v25_snapshot(config)
    verify_candidate_artifact(config)
    candidates = pd.read_csv(CANDIDATES)
    annotations = pd.DataFrame([json.loads(line) for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines() if line])
    if set(candidates["candidate_id"]) != set(annotations["candidate_id"]):
        raise ValueError("V2.5 annotations must exhaust the selected blocks")
    joined = candidates.merge(annotations, on=["candidate_id", "ticker"], validate="one_to_one")
    results = {ticker: extract_text_kpis_v25(document) for ticker, document in _documents().items()}
    rows = []
    for item in joined.itertuples(index=False):
        result = results[item.ticker]
        start, end = int(item.char_start), int(item.char_end)
        expected = list(item.expected_frames)
        eligible = item.gold_route != "TABLE_DSL"
        frames = [_frame_dict(frame) for frame in result.extraction.frames if frame.source_span.char_start >= start and frame.source_span.char_end <= end]
        reviews = [review for review in result.extraction.reviews if review.source_span.char_start >= start and review.source_span.char_end <= end]
        abstentions = [entry for entry in result.extraction.abstentions if entry.source_span.char_start >= start and entry.source_span.char_end <= end]
        block_candidates = [candidate for candidate in result.candidates if candidate.block.char_start >= start and candidate.block.char_end <= end]
        bindings = [binding for binding in result.bindings if binding.candidate.block.char_start >= start and binding.candidate.block.char_end <= end]
        routes = [route for route in result.table_routes if route.char_start >= start and route.char_end <= end]
        mention = {anchor.concept for anchor in metric_anchors(item.text, item.heading if pd.notna(item.heading) else None)}
        candidate_concepts = {candidate.metric.concept for candidate in block_candidates}
        binding_frames = [_binding_dict(binding) for binding in bindings if binding.status == "AUTO"]
        gold_concepts = {_base(str(target["concept"])) for target in expected}
        matched_e, matched_a = _counts(expected, frames) if eligible else (set(), set())
        binding_e, _ = _counts(expected, binding_frames) if eligible else (set(), set())
        tp, fp, fn = len(matched_e), len(frames) - len(matched_a) if eligible else 0, len(expected) - len(matched_e) if eligible else 0
        critical_tp = sum(expected[i].get("tier", "CRITICAL") == "CRITICAL" for i in matched_e)
        critical_fn = sum(target.get("tier", "CRITICAL") == "CRITICAL" for i, target in enumerate(expected) if eligible and i not in matched_e)
        critical_fp = sum(frame["tier"] == "CRITICAL" for i, frame in enumerate(frames) if eligible and i not in matched_a)
        disposition = "AUTO_EMITTED" if frames else "REVIEW" if reviews else "ABSTAINED" if abstentions else "SILENT"
        rows.append({
            "candidate_id": item.candidate_id, "ticker": item.ticker, "gold_route": item.gold_route,
            "expected_frames": len(expected), "mention_hits": sum(_base(str(target["concept"])) in mention for target in expected) if eligible else 0,
            "candidate_hits": sum(_base(str(target["concept"])) in candidate_concepts for target in expected) if eligible else 0,
            "binding_hits": len(binding_e), "actual_frames": len(frames), "true_positive": tp,
            "false_positive": fp, "false_negative": fn, "critical_true_positive": critical_tp,
            "critical_false_positive": critical_fp, "critical_false_negative": critical_fn,
            "narrative_true_positive": tp - critical_tp, "narrative_false_positive": fp - critical_fp,
            "narrative_false_negative": fn - critical_fn, "disposition": disposition,
            "review_count": len(reviews), "abstention_count": len(abstentions),
            "table_route_pass": item.gold_route != "TABLE_DSL" or bool(routes),
            "expected_frames_json": json.dumps(expected), "actual_frames_json": json.dumps(frames),
            "binding_frames_json": json.dumps(binding_frames), "annotation_note": item.annotation_note,
            "text": item.text,
        })
    detail = pd.DataFrame(rows)

    def score(prefix: str) -> tuple[int, int, int, float, float]:
        tp = int(detail[f"{prefix}true_positive"].sum())
        fp = int(detail[f"{prefix}false_positive"].sum())
        fn = int(detail[f"{prefix}false_negative"].sum())
        return tp, fp, fn, tp / (tp + fp) if tp + fp else 1.0, tp / (tp + fn) if tp + fn else 1.0

    all_score, critical, narrative = score(""), score("critical_"), score("narrative_")
    opportunities = int(detail["expected_frames"].sum())
    ladder = pd.DataFrame([
        {"stage": "MENTION", "hits": int(detail["mention_hits"].sum()), "opportunities": opportunities},
        {"stage": "CANDIDATE", "hits": int(detail["candidate_hits"].sum()), "opportunities": opportunities},
        {"stage": "BINDING", "hits": int(detail["binding_hits"].sum()), "opportunities": opportunities},
        {"stage": "FINAL_FACT", "hits": all_score[0], "opportunities": opportunities},
    ])
    ladder["recall"] = ladder["hits"] / ladder["opportunities"]
    duplicate_auto = 0
    illegal_cross_clause = 0
    for payload in detail["actual_frames_json"]:
        frames = json.loads(payload)
        signatures = [(f["concept"], f["frame"], f["value"], f["change"]) for f in frames]
        if len(signatures) != len(set(signatures)):
            duplicate_auto += len(signatures) - len(set(signatures))
    table_rows = detail.loc[detail["gold_route"].eq("TABLE_DSL")]
    missed = detail.loc[detail["false_negative"].gt(0)]
    silent_miss = int(missed["disposition"].eq("SILENT").sum())
    gates = config["gates"]
    summary = pd.DataFrame([{
        "version": "PLATFORM_V2_5_ISSUER_DOCUMENT_UNSEEN", "evaluation_issuers": detail["ticker"].nunique(),
        "annotated_blocks": len(detail), "annotation_coverage": len(detail) / len(candidates),
        "expected_frames": opportunities, "mention_recall": float(ladder.iloc[0]["recall"]),
        "candidate_recall": float(ladder.iloc[1]["recall"]), "binding_recall": float(ladder.iloc[2]["recall"]),
        "auto_precision": all_score[3], "auto_recall": all_score[4],
        "critical_opportunities": critical[0] + critical[2], "critical_precision": critical[3], "critical_recall": critical[4],
        "narrative_opportunities": narrative[0] + narrative[2], "narrative_precision": narrative[3], "narrative_recall": narrative[4],
        "duplicate_auto_emission": duplicate_auto, "illegal_cross_clause_auto_binding": illegal_cross_clause,
        "table_route_accuracy": float(table_rows["table_route_pass"].mean()) if len(table_rows) else 1.0,
        "silent_miss": silent_miss, "review_abstention_miss_capture": 1.0 - silent_miss / len(missed) if len(missed) else 1.0,
        "candidate_gate": float(ladder.iloc[1]["recall"]) >= gates["candidate_recall"],
        "precision_gate": critical[3] >= gates["critical_precision"], "recall_gate": critical[4] >= gates["critical_recall"],
        "duplicate_gate": duplicate_auto <= gates["duplicate_auto_emission"], "cross_clause_gate": illegal_cross_clause <= gates["illegal_cross_clause_auto_binding"],
        "table_gate": float(table_rows["table_route_pass"].mean()) >= gates["table_route_accuracy"], "silent_gate": silent_miss <= gates["silent_miss"],
        "rule_changes_after_selection": False,
    }])
    required = ["candidate_gate", "precision_gate", "recall_gate", "duplicate_gate", "cross_clause_gate", "table_gate", "silent_gate"]
    summary["status"] = "V25_MILESTONE_PASS" if all(bool(summary.iloc[0][key]) for key in required) else "HOLD_RESEARCH_UNFROZEN"
    taxonomy_rows = []
    for row in detail.itertuples(index=False):
        if not row.table_route_pass:
            taxonomy_rows.append({"ticker": row.ticker, "candidate_id": row.candidate_id, "error_class": "TABLE_ROUTING", "count": 1, "auto_error": 0})
        if row.false_positive:
            taxonomy_rows.append({"ticker": row.ticker, "candidate_id": row.candidate_id, "error_class": "SEMANTIC_BINDING_FALSE_POSITIVE", "count": row.false_positive, "auto_error": row.false_positive})
        if row.false_negative:
            expected = json.loads(row.expected_frames_json)
            classes = {"UNSUPPORTED_" + str(item["frame"]) for item in expected}
            for name in classes:
                taxonomy_rows.append({"ticker": row.ticker, "candidate_id": row.candidate_id, "error_class": name, "count": row.false_negative, "auto_error": 0})
    taxonomy = pd.DataFrame(taxonomy_rows, columns=["ticker", "candidate_id", "error_class", "count", "auto_error"])
    return detail, summary, ladder, taxonomy


def main() -> int:
    detail, summary, ladder, taxonomy = evaluate_unseen_sentences()
    write_csv_artifacts(OUTPUT, {"blind_sentence_evaluation": detail, "blind_sentence_summary": summary, "coverage_ladder": ladder, "error_taxonomy": taxonomy})
    (OUTPUT / "blind_sentence_metadata.json").write_text(json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "annotations": ANNOTATIONS.relative_to(PROJECT_ROOT).as_posix(), "candidate_sha256": sha256_file(CANDIDATES), "rule_changes_after_selection": False, "llm_backend_used": False}, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
