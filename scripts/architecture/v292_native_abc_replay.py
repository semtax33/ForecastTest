from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.training.staged_gold import load_staged_gold
from equity_platform.text_ie.v291 import native_stage_gold_row
from equity_platform.text_ie.v292 import extract_text_kpis_v292
from scripts.architecture.v291_native_abc_replay import (
    ANNOTATIONS,
    CANDIDATES,
    CONFIG as PARENT_CONFIG,
    _canonical_document,
    _cross_clause_violations,
    _grouped_summaries,
    _predicted_table,
    _root_causes_from_detail,
    verify_frozen_inputs,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_9_2_staged_validation"
DETAIL = OUTPUT / "native_abc_tuned_replay_detail.csv"
SUMMARY = OUTPUT / "native_abc_tuned_replay_summary.csv"
ROOT_CAUSES = OUTPUT / "native_abc_tuned_replay_root_causes.csv"
METADATA = OUTPUT / "native_abc_tuned_replay_metadata.json"
SCRIPT = PROJECT_ROOT / "scripts/architecture/v292_native_abc_replay.py"
RULES = PROJECT_ROOT / "configs/parser_rules/text_ie/v292_semantic_context.arc"
RUNTIME = PROJECT_ROOT / "equity_platform/text_ie/v292/runtime.py"
SEMANTICS = PROJECT_ROOT / "equity_platform/text_ie/v292/semantics.py"
VERSION = "PLATFORM_V2_9_2_TYPED_SEMANTIC_CONTEXT_TUNED_REPLAY"


def _selected_records(records, group_type: str, group: str):
    if group_type == "ALL":
        return records
    field = {
        "AXIS": "axis",
        "SOURCE_KIND": "source_kind",
        "GOLD_ROUTE": "gold_route",
    }[group_type]
    return [item for item in records if str(item[field]) == group]


def _v292_summary(detail: pd.DataFrame) -> pd.DataFrame:
    records = detail.to_dict("records")
    summary = _grouped_summaries(records)
    summary["version"] = VERSION
    summary["critical_precision"] = summary["text_ie_frame_precision"]
    summary["critical_recall"] = summary["text_ie_frame_recall"]
    source_valid = []
    source_total = []
    source_accuracy = []
    for row in summary.itertuples(index=False):
        selected = _selected_records(records, str(row.group_type), str(row.group))
        valid = sum(int(item["source_span_valid_count"]) for item in selected)
        total = sum(int(item["source_span_total_count"]) for item in selected)
        source_valid.append(valid)
        source_total.append(total)
        source_accuracy.append(valid / total if total else 1.0)
    summary["source_span_valid_count"] = source_valid
    summary["source_span_total_count"] = source_total
    summary["source_span_accuracy"] = source_accuracy
    summary["v292_gate_candidate_recall"] = summary["candidate_recall"] >= 1.0
    summary["v292_gate_critical_precision"] = summary["critical_precision"] >= 0.99
    summary["v292_gate_critical_recall"] = summary["critical_recall"] >= 0.50
    summary["v292_gate_table_route_accuracy"] = summary["table_route_accuracy"] >= 0.95
    summary["v292_gate_source_span"] = summary["source_span_accuracy"] >= 1.0
    summary["v292_gate_invariants"] = (
        (summary["duplicate_auto_emission"] == 0)
        & (summary["illegal_cross_clause_auto_binding"] == 0)
        & (summary["silent_frame_miss"] == 0)
    )
    summary["v292_route_aware_recovery_targets"] = summary[[
        "v292_gate_candidate_recall",
        "v292_gate_critical_precision",
        "v292_gate_critical_recall",
        "v292_gate_table_route_accuracy",
        "v292_gate_source_span",
        "v292_gate_invariants",
    ]].all(axis=1)
    summary["layer_gate_candidate_recall"] = summary["candidate_recall"] >= 0.99
    summary["layer_gate_quantity_detection"] = (
        (summary["quantity_precision"] >= 0.995)
        & (summary["quantity_recall"] >= 0.995)
    )
    summary["layer_gate_concept_precision"] = summary["concept_precision"] >= 0.99
    summary["layer_gate_binding_accuracy"] = (
        (summary["binding_precision"] >= 0.99)
        & (summary["binding_recall"] >= 0.99)
    )
    summary["layer_gate_role_accuracy"] = (
        (summary["role_precision"] >= 0.99)
        & (summary["role_recall"] >= 0.99)
    )
    summary["layer_gate_frame_precision"] = summary["critical_precision"] >= 0.99
    summary["layer_gate_frame_recall"] = summary["critical_recall"] >= 0.97
    summary["layer_all_quality_targets"] = summary[[
        "layer_gate_candidate_recall",
        "layer_gate_quantity_detection",
        "layer_gate_concept_precision",
        "layer_gate_binding_accuracy",
        "layer_gate_role_accuracy",
        "layer_gate_frame_precision",
        "layer_gate_frame_recall",
        "v292_gate_invariants",
    ]].all(axis=1)
    summary["certification_eligible"] = False
    summary["status"] = "TUNED_REPLAY_LAYER_GATES_OPEN_NOT_BLIND_CERTIFICATION"
    return summary


def evaluate_native_abc_v292() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replay V2.9.2 on frozen A/B/C; this is tuned research, never a blind claim."""

    verify_frozen_inputs()
    examples = load_staged_gold(ANNOTATIONS)
    raw = {
        row["example_id"]: row
        for row in (
            json.loads(line)
            for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
            if line
        )
    }
    rows = []
    for index, example in enumerate(examples):
        document = _canonical_document(example)
        result = extract_text_kpis_v292(document)
        row = native_stage_gold_row(
            result,
            example,
            block_char_start=0,
            block_char_end=len(example.text),
            predicted_table=_predicted_table(result),
        )
        row["illegal_cross_clause_auto_binding"] = _cross_clause_violations(result)
        relevant_frames = tuple(
            frame
            for frame in result.extraction.frames
            if frame.source_span.char_start >= 0
            and frame.source_span.char_end <= len(example.text)
        )
        source_valid = sum(
            frame.source.sha256 == example.source_sha256
            and frame.source_span.char_start == 0
            and frame.source_span.char_end == len(example.text)
            and frame.source_span.literal == example.text
            for frame in relevant_frames
        )
        annotation = raw[example.example_id]
        rows.append({
            "selection_index": index,
            "candidate_id": example.example_id,
            "axis": example.holdout_axis.value,
            "entity": example.entity,
            "source_kind": example.source_kind,
            "gold_route": example.gold_route,
            "predicted_table": bool(row["predicted_table"]),
            "review_decision": annotation["review_decision"],
            "expected_frame_count": len(row["expected_frames"]),
            "actual_frame_count": len(row["actual_frames"]),
            "source_span_valid_count": source_valid,
            "source_span_total_count": len(relevant_frames),
            "candidate_expected": int(row["candidate_expected"]),
            "candidate_hits": int(row["candidate_hits"]),
            "rejection_count": int(row["rejection_count"]),
            "review_count": int(row["review_count"]),
            "observable_abstained_frames": int(row["observable_abstained_frames"]),
            "unresolved_binding_count": int(row["unresolved_binding_count"]),
            "untraced_candidate_count": int(row["untraced_candidate_count"]),
            "illegal_cross_clause_auto_binding": int(row["illegal_cross_clause_auto_binding"]),
            "trace_root_causes": "|".join(row["trace_root_causes"]),
            "expected_frames_json": json.dumps(row["expected_frames"]),
            "actual_frames_json": json.dumps(row["actual_frames"]),
            "payload": json.dumps(row),
        })
    detail = pd.DataFrame(rows)
    summary = _v292_summary(detail)
    roots = _root_causes_from_detail(detail)
    return detail, summary, roots


def main() -> int:
    detail, summary, roots = evaluate_native_abc_v292()
    write_csv_artifacts(OUTPUT, {
        "native_abc_tuned_replay_detail": detail,
        "native_abc_tuned_replay_summary": summary,
        "native_abc_tuned_replay_root_causes": roots,
    })
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "parent_frozen_config": PARENT_CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_selection_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "script_sha256": sha256_file(SCRIPT),
        "parser_sources_sha256": {
            path.relative_to(PROJECT_ROOT).as_posix(): sha256_file(path)
            for path in (RULES, RUNTIME, SEMANTICS)
        },
        "rows": len(detail),
        "same_frozen_abc_used_for_diagnosis_and_tuning": True,
        "annotation_independently_human_adjudicated": False,
        "certification_eligible": False,
        "table_expected_frames_status": "NOT_EVALUATED_BY_TEXT_IE",
        "dcf_kernel_changed": False,
        "output_sha256": {},
    }
    metadata["output_sha256"] = {
        path.name: sha256_file(path)
        for path in (DETAIL, SUMMARY, ROOT_CAUSES)
    }
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    row = summary.loc[
        (summary["group_type"] == "ALL") & (summary["group"] == "ALL")
    ].iloc[0]
    print(f"BLOCKS={len(detail)} TEXT_FRAME_OPPORTUNITIES={int(row.evaluated_frame_opportunities)}")
    print(
        f"CANDIDATE_RECALL={row.candidate_recall:.6f} "
        f"CRITICAL_PRECISION={row.critical_precision:.6f} "
        f"CRITICAL_RECALL={row.critical_recall:.6f}"
    )
    print(
        f"TABLE_ROUTE_ACCURACY={row.table_route_accuracy:.6f} "
        f"SOURCE_SPAN_ACCURACY={row.source_span_accuracy:.6f} "
        f"ROUTE_RECOVERY_TARGETS={bool(row.v292_route_aware_recovery_targets)} "
        f"ALL_LAYER_TARGETS={bool(row.layer_all_quality_targets)}"
    )
    print("STATUS=TUNED_REPLAY_LAYER_GATES_OPEN_NOT_BLIND_CERTIFICATION DCF_CHANGED=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
