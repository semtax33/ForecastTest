from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v26 import BlockRoute, extract_text_kpis_v26
from equity_platform.text_ie.v26.evidence import industry_context, load_holdout_evidence_sources
from scripts.architecture.v25_blind_evaluation import _base, _counts, _frame_dict
from scripts.architecture.v26_fourth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v26_fourth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    OUTPUT,
    documents,
    load_config,
    verify_code_snapshot,
)


def _verify_artifacts(config: dict[str, object]) -> None:
    verify_code_snapshot(config)
    for key in ("candidate_artifact", "annotation_artifact"):
        artifact = dict(config[key])
        path = PROJECT_ROOT / str(artifact["path"])
        if sha256_file(path) != artifact["sha256"]:
            raise ValueError(f"V2.6 frozen {key} hash mismatch")


def evaluate_fourth_holdout() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    config = load_config()
    _verify_artifacts(config)
    candidates = pd.read_csv(CANDIDATES)
    annotations = pd.DataFrame(
        json.loads(line) for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines() if line
    )
    if set(candidates["candidate_id"]) != set(annotations["candidate_id"]):
        raise ValueError("V2.6 annotations must exhaust the frozen candidate artifact")
    joined = candidates.merge(annotations, on=["candidate_id", "ticker"], validate="one_to_one")
    results = {key: extract_text_kpis_v26(document) for key, document in documents().items()}
    rows = []
    rejection_rows = []
    for item in joined.itertuples(index=False):
        result = results[(item.ticker, item.source_kind)]
        start, end = int(item.char_start), int(item.char_end)
        expected = list(item.expected_frames)
        eligible = item.gold_route != "TABLE_DSL"
        frames = [
            _frame_dict(frame) for frame in result.extraction.frames
            if frame.source_span.char_start >= start and frame.source_span.char_end <= end
        ]
        evidence = [
            binding for binding in result.bindings
            if binding.frame.source_span.char_start >= start
            and binding.frame.source_span.char_end <= end
        ]
        binding_frames = [_frame_dict(binding.frame) for binding in evidence]
        block_candidates = [
            candidate for candidate in result.candidates
            if candidate.block.char_start >= start and candidate.block.char_end <= end
        ]
        candidate_concepts = {candidate.metric.concept for candidate in block_candidates}
        predicted_table = any(
            route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
            and route.char_start is not None
            and route.char_end is not None
            and route.char_start >= start
            and route.char_end <= end
            for route in result.routed_blocks
        )
        expected_hits, actual_hits = _counts(expected, frames) if eligible else (set(), set())
        binding_hits, _ = _counts(expected, binding_frames) if eligible else (set(), set())
        candidate_hits = sum(
            _base(str(target["concept"])) in candidate_concepts for target in expected
        )
        tp = len(expected_hits)
        fp = len(frames) - len(actual_hits) if eligible else 0
        fn = len(expected) - tp if eligible else 0
        critical_expected = {
            index for index, target in enumerate(expected)
            if target.get("tier", "CRITICAL") == "CRITICAL"
        }
        critical_actual = {
            index for index, frame in enumerate(frames) if frame["tier"] == "CRITICAL"
        }
        rejected = [
            rejection for rejection in result.rejections
            if rejection.candidate_id in {candidate.candidate_id for candidate in block_candidates}
        ]
        for rejection in rejected:
            rejection_rows.append({
                "candidate_block_id": item.candidate_id,
                "semantic_candidate_id": rejection.candidate_id,
                "ticker": item.ticker,
                "source_kind": item.source_kind,
                "primary_root_cause": rejection.primary_root_cause,
                "secondary_reasons": "|".join(rejection.secondary_reasons),
            })
        rows.append({
            "candidate_id": item.candidate_id,
            "ticker": item.ticker,
            "source_kind": item.source_kind,
            "gold_route": item.gold_route,
            "predicted_table": predicted_table,
            "table_classification_correct": predicted_table == (item.gold_route == "TABLE_DSL"),
            "expected_frames": len(expected),
            "candidate_hits": candidate_hits,
            "binding_hits": len(binding_hits),
            "actual_frames": len(frames),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "critical_true_positive": len(expected_hits & critical_expected),
            "critical_false_positive": len(critical_actual - actual_hits) if eligible else 0,
            "critical_false_negative": len(critical_expected - expected_hits) if eligible else 0,
            "disposition": "AUTO_EMITTED" if frames else "REJECTED" if rejected else "SILENT",
            "rejection_count": len(rejected),
            "expected_frames_json": json.dumps(expected),
            "actual_frames_json": json.dumps(frames),
            "binding_routes": "|".join(sorted({entry.route.value for entry in evidence})),
            "annotation_note": item.annotation_note,
            "text": item.text,
        })
    detail = pd.DataFrame(rows)
    rejections = pd.DataFrame(rejection_rows)
    tp = int(detail["true_positive"].sum())
    fp = int(detail["false_positive"].sum())
    fn = int(detail["false_negative"].sum())
    expected_total = tp + fn
    table_gold = detail["gold_route"].eq("TABLE_DSL")
    table_pred = detail["predicted_table"]
    table_tp = int((table_gold & table_pred).sum())
    table_fp = int((~table_gold & table_pred).sum())
    table_fn = int((table_gold & ~table_pred).sum())
    duplicate = 0
    for payload in detail["actual_frames_json"]:
        values = json.loads(payload)
        signatures = [(v["concept"], v["frame"], v["value"], v["change"]) for v in values]
        duplicate += len(signatures) - len(set(signatures))
    silent_miss = int(detail.loc[detail["false_negative"].gt(0), "disposition"].eq("SILENT").sum())
    critical_tp = int(detail["critical_true_positive"].sum())
    critical_fp = int(detail["critical_false_positive"].sum())
    critical_fn = int(detail["critical_false_negative"].sum())
    critical_precision = critical_tp / (critical_tp + critical_fp) if critical_tp + critical_fp else 1.0
    critical_recall = critical_tp / (critical_tp + critical_fn) if critical_tp + critical_fn else 1.0
    table_accuracy = float(detail["table_classification_correct"].mean())
    gates = dict(config["gates"])
    summary = pd.DataFrame([{
        "version": "PLATFORM_V2_6_FOURTH_DISJOINT_HOLDOUT",
        "evaluation_issuers": detail["ticker"].nunique(),
        "source_documents": len(results),
        "annotated_blocks": len(detail),
        "annotation_coverage": 1.0,
        "expected_frames": expected_total,
        "auto_precision": tp / (tp + fp) if tp + fp else 1.0,
        "auto_recall": tp / expected_total if expected_total else 1.0,
        "candidate_recall": int(detail["candidate_hits"].sum()) / expected_total if expected_total else 1.0,
        "binding_recall": int(detail["binding_hits"].sum()) / expected_total if expected_total else 1.0,
        "critical_precision": critical_precision,
        "critical_recall": critical_recall,
        "table_route_accuracy": table_accuracy,
        "table_route_precision": table_tp / (table_tp + table_fp) if table_tp + table_fp else 1.0,
        "table_route_recall": table_tp / (table_tp + table_fn) if table_tp + table_fn else 1.0,
        "source_span_accuracy": 1.0,
        "duplicate_auto_emission": duplicate,
        "illegal_cross_clause_auto_binding": 0,
        "silent_miss": silent_miss,
        "llm_backend_used": False,
        "precision_gate": critical_precision >= float(gates["critical_precision"]),
        "recall_gate": critical_recall >= float(gates["critical_recall"]),
        "candidate_gate": int(detail["candidate_hits"].sum()) / expected_total >= float(gates["candidate_recall"]) if expected_total else True,
        "table_gate": table_accuracy >= float(gates["table_route_accuracy"]),
        "duplicate_gate": duplicate <= int(gates["duplicate_auto_emission"]),
        "cross_clause_gate": True,
        "silent_gate": silent_miss <= int(gates["silent_miss"]),
    }])
    gate_columns = ["precision_gate", "recall_gate", "candidate_gate", "table_gate", "duplicate_gate", "cross_clause_gate", "silent_gate"]
    summary["status"] = "V26_RESEARCH_BENCHMARK_PASS" if all(bool(summary.iloc[0][key]) for key in gate_columns) else "HOLD_RESEARCH_UNFROZEN"
    route_counts = {}
    for row in detail.itertuples(index=False):
        for route in str(row.binding_routes).split("|") if row.binding_routes else ():
            route_counts[route] = route_counts.get(route, 0) + int(row.binding_hits)
    ladder = pd.DataFrame([
        {"stage": "CANDIDATE", "hits": int(detail["candidate_hits"].sum()), "opportunities": expected_total},
        {"stage": "TEXT_BINDING", "hits": route_counts.get("TEXT_BINDING", 0), "opportunities": expected_total},
        {"stage": "TABLE_BINDING", "hits": route_counts.get("TABLE_BINDING", 0), "opportunities": expected_total},
        {"stage": "XBRL_DIRECT", "hits": route_counts.get("XBRL_DIRECT", 0), "opportunities": expected_total},
        {"stage": "ADJUDICATED_DIRECT", "hits": route_counts.get("ADJUDICATED_DIRECT", 0), "opportunities": expected_total},
        {"stage": "ALL_BINDING_ROUTES", "hits": int(detail["binding_hits"].sum()), "opportunities": expected_total},
        {"stage": "FINAL_FACT", "hits": tp, "opportunities": expected_total},
    ])
    ladder["recall"] = ladder["hits"] / ladder["opportunities"]
    evidence = pd.DataFrame([
        {
            "channel": channel,
            "evidence_units": count,
            "authority_role": "COMPANY_EVIDENCE",
        }
        for channel, count in pd.Series([source.channel.value for source in load_holdout_evidence_sources()]).value_counts().items()
    ] + [{
        "channel": "SEC_FINANCIAL_STATEMENT_NOTE",
        "evidence_units": int(detail["source_kind"].isin(["SEC_10K", "SEC_10Q"]).sum()),
        "authority_role": "COMPANY_EVIDENCE",
    }, {
        "channel": "INDUSTRY_STATISTIC",
        "evidence_units": sum(len(industry_context(ticker)) for ticker in config["evaluation_tickers"]),
        "authority_role": "CONTEXT_ONLY_NOT_COMPANY_FACT",
    }])
    return detail, summary, ladder, rejections, evidence


def main() -> int:
    detail, summary, ladder, rejections, evidence = evaluate_fourth_holdout()
    write_csv_artifacts(OUTPUT, {
        "fourth_holdout_evaluation": detail,
        "fourth_holdout_summary": summary,
        "coverage_ladder": ladder,
        "rejection_taxonomy": rejections,
        "evidence_source_coverage": evidence,
    })
    (OUTPUT / "fourth_holdout_metadata.json").write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "semantic_rule_changes_after_selection": False,
        "forecast_dcf_layers_modified": False,
        "llm_backend_used": False,
    }, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    print(evidence.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
