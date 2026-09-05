from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import CanonicalDocument, DocumentMetadata, DocumentSentence
from equity_platform.ir import SourceRef
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames
from equity_platform.text_ie.staged_evaluation import (
    staged_gate_results,
    summarize_route_aware_staged_validation,
)
from equity_platform.text_ie.training.staged_gold import (
    StagedGoldExample,
    load_staged_gold,
)
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v291 import extract_text_kpis_v291, native_stage_gold_row


CONFIG = PROJECT_ROOT / "configs/certification/platform_v291_native_abc_holdout.toml"
CANDIDATES = (
    PROJECT_ROOT
    / "output/platform_v2_9_1_staged_validation/native_abc_candidate_blocks.csv"
)
ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v291_native_abc_stage_gold.jsonl"
)
OUTPUT = PROJECT_ROOT / "output/platform_v2_9_1_staged_validation"
DETAIL = OUTPUT / "native_abc_replay_detail.csv"
SUMMARY = OUTPUT / "native_abc_replay_summary.csv"
ROOT_CAUSES = OUTPUT / "native_abc_replay_root_causes.csv"
METADATA = OUTPUT / "native_abc_replay_metadata.json"
SCRIPT = PROJECT_ROOT / "scripts/architecture/v291_native_abc_replay.py"

PARSER_SOURCES = {
    "role_graph": PROJECT_ROOT / "equity_platform/text_ie/role_graph.py",
    "v290_semantics": PROJECT_ROOT / "equity_platform/text_ie/v290/semantics.py",
    "v290_runtime": PROJECT_ROOT / "equity_platform/text_ie/v290/runtime.py",
    "v290_router": PROJECT_ROOT / "equity_platform/text_ie/v290/router.py",
    "v291_model": PROJECT_ROOT / "equity_platform/text_ie/v291/model.py",
    "v291_runtime": PROJECT_ROOT / "equity_platform/text_ie/v291/runtime.py",
    "v291_evaluation": PROJECT_ROOT / "equity_platform/text_ie/v291/evaluation.py",
    "v290_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v290_semantic_role_graph.arc",
}


def verify_frozen_inputs() -> dict[str, object]:
    with CONFIG.open("rb") as stream:
        manifest = tomllib.load(stream)
    checks = {
        CANDIDATES: manifest["selection_snapshot"]["artifact_sha256"],
        ANNOTATIONS: manifest["annotation_snapshot"]["artifact_sha256"],
        PROJECT_ROOT / "equity_platform/text_ie/training/staged_gold.py": (
            manifest["pre_annotation_schema_bugfix"]["staged_gold_sha256_after"]
        ),
        PROJECT_ROOT / "equity_platform/text_ie/staged_evaluation.py": (
            manifest["pre_annotation_schema_bugfix"]["staged_evaluation_sha256_after"]
        ),
        PROJECT_ROOT / manifest["annotation_snapshot"]["builder"]: (
            manifest["annotation_snapshot"]["builder_sha256"]
        ),
        PROJECT_ROOT / manifest["annotation_snapshot"]["test"]: (
            manifest["annotation_snapshot"]["test_sha256"]
        ),
    }
    checks.update(
        {
            path: manifest["parser_snapshot_sha256"][name]
            for name, path in PARSER_SOURCES.items()
        }
    )
    drift = {
        path.relative_to(PROJECT_ROOT).as_posix(): {
            "expected": str(expected),
            "actual": sha256_file(path),
        }
        for path, expected in checks.items()
        if sha256_file(path) != expected
    }
    if drift:
        raise ValueError(f"frozen native A/B/C replay input drift: {drift}")
    if manifest["annotation_snapshot"]["parser_predictions_generated_before_freeze"]:
        raise ValueError("annotation was not frozen before prediction")
    if manifest["pre_annotation_schema_bugfix"]["parser_inference_changed"]:
        raise ValueError("pre-annotation amendment changed parser inference")
    return manifest


def _canonical_document(example: StagedGoldExample) -> CanonicalDocument:
    metadata = DocumentMetadata(
        entity=example.entity,
        source_kind=example.source_kind,
        document_kind="V291_NATIVE_ABC_EXACT_BLOCK_REPLAY",
        available_at=example.available_at,
        report_period=example.document_period,
    )
    source = SourceRef(
        source_type=example.source_kind,
        uri=f"holdout://v291-native-abc/{example.example_id}",
        local_path=f"frozen-selection/{example.example_id}",
        sha256=example.source_sha256,
        available_at=example.available_at,
    )
    return CanonicalDocument(
        metadata=metadata,
        source=source,
        text=example.text,
        tables=(),
        inline_facts=(),
        sentences=(
            DocumentSentence(
                sentence_index=0,
                text=example.text,
                char_start=0,
                char_end=len(example.text),
            ),
        ),
    )


def _predicted_table(result) -> bool:
    return any(
        route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in result.routed_blocks
    )


def _cross_clause_violations(result) -> int:
    violations = 0
    for trace in result.telemetry.clauses:
        clause_length = trace.clause_char_end - trace.clause_char_start
        for edge in (*trace.bindings, *trace.roles):
            quantity = edge.quantity
            if not (
                0 <= edge.concept_char_start < edge.concept_char_end <= clause_length
                and 0 <= quantity.char_start < quantity.char_end <= clause_length
            ):
                violations += 1
    return violations


def _payload(record: Mapping[str, object]) -> dict[str, object]:
    value = record["payload"]
    return json.loads(value) if isinstance(value, str) else dict(value)


def _grouped_summaries(records: Iterable[Mapping[str, object]]) -> pd.DataFrame:
    items = list(records)
    groups: list[tuple[str, str, list[Mapping[str, object]]]] = [
        ("ALL", "ALL", items)
    ]
    for field, group_type in (
        ("axis", "AXIS"),
        ("source_kind", "SOURCE_KIND"),
        ("gold_route", "GOLD_ROUTE"),
    ):
        def group_value(item: Mapping[str, object]) -> str:
            if field in item:
                return str(item[field])
            return str(_payload(item)[field])

        values = sorted({group_value(item) for item in items})
        groups.extend(
            (
                group_type,
                value,
                [item for item in items if group_value(item) == value],
            )
            for value in values
        )

    output = []
    for group_type, group, selected in groups:
        payloads = [_payload(item) for item in selected]
        summary = summarize_route_aware_staged_validation(payloads)
        summary["duplicate_auto_emission"] = count_semantic_duplicate_frames(
            payload["actual_frames"] for payload in payloads
        )
        summary["illegal_cross_clause_auto_binding"] = sum(
            int(payload.get("illegal_cross_clause_auto_binding", 0))
            for payload in payloads
        )
        gates = staged_gate_results(summary)
        output.append(
            {
                "version": "PLATFORM_V2_9_1_1_NATIVE_ABC_RESEARCH_REPLAY",
                "group_type": group_type,
                "group": group,
                "certification_eligible": False,
                "annotation_independently_human_adjudicated": False,
                "route_aware_intermediate_scoring": True,
                **summary,
                **{f"gate_{name}": passed for name, passed in gates.items()},
                "all_numeric_gates": all(gates.values()),
                "status": "RESEARCH_DIAGNOSTIC_NOT_CERTIFICATION_ELIGIBLE",
            }
        )
    return pd.DataFrame(output)


def evaluate_native_abc() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    detail_rows = []
    root_causes: Counter[tuple[str, str, str]] = Counter()
    for index, example in enumerate(examples):
        document = _canonical_document(example)
        result = extract_text_kpis_v291(document)
        row = native_stage_gold_row(
            result,
            example,
            block_char_start=0,
            block_char_end=len(example.text),
            predicted_table=_predicted_table(result),
        )
        row["illegal_cross_clause_auto_binding"] = _cross_clause_violations(result)
        annotation = raw[example.example_id]
        for cause in row["trace_root_causes"]:
            root_causes[(example.holdout_axis.value, example.source_kind, cause)] += 1
        detail_rows.append(
            {
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
                "candidate_expected": int(row["candidate_expected"]),
                "candidate_hits": int(row["candidate_hits"]),
                "rejection_count": int(row["rejection_count"]),
                "review_count": int(row["review_count"]),
                "observable_abstained_frames": int(row["observable_abstained_frames"]),
                "unresolved_binding_count": int(row["unresolved_binding_count"]),
                "untraced_candidate_count": int(row["untraced_candidate_count"]),
                "illegal_cross_clause_auto_binding": int(
                    row["illegal_cross_clause_auto_binding"]
                ),
                "trace_root_causes": "|".join(row["trace_root_causes"]),
                "expected_frames_json": json.dumps(row["expected_frames"]),
                "actual_frames_json": json.dumps(row["actual_frames"]),
                "expected_quantities_json": json.dumps(row["expected_quantities"]),
                "detected_quantities_json": json.dumps(row["detected_quantities"]),
                "expected_concepts_json": json.dumps(row["expected_concepts"]),
                "detected_concepts_json": json.dumps(row["detected_concepts"]),
                "expected_bindings_json": json.dumps(row["expected_bindings"]),
                "detected_bindings_json": json.dumps(row["detected_bindings"]),
                "expected_roles_json": json.dumps(row["expected_roles"]),
                "detected_roles_json": json.dumps(row["detected_roles"]),
                "payload": json.dumps(row),
            }
        )
    detail = pd.DataFrame(detail_rows)
    summary = _grouped_summaries(detail.to_dict("records"))
    roots = pd.DataFrame(
        {
            "axis": axis,
            "source_kind": source_kind,
            "primary_root_cause": cause,
            "observation_count": count,
            "is_failure_signal": cause not in {"EMITTED", "NO_QUANTITY_IN_CLAUSE"},
        }
        for (axis, source_kind, cause), count in root_causes.most_common()
    )
    return detail, summary, roots


def main() -> int:
    detail, summary, roots = evaluate_native_abc()
    write_csv_artifacts(
        OUTPUT,
        {
            "native_abc_replay_detail": detail,
            "native_abc_replay_summary": summary,
            "native_abc_replay_root_causes": roots,
        },
    )
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "PLATFORM_V2_9_1_1_NATIVE_ABC_RESEARCH_REPLAY",
        "config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "config_sha256": sha256_file(CONFIG),
        "candidate_selection_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "replay_script_sha256": sha256_file(SCRIPT),
        "rows": len(detail),
        "parser_predictions_generated_after_annotation_freeze": True,
        "parser_inference_snapshot_unchanged": True,
        "route_aware_intermediate_scoring": True,
        "document_period_release_period_separated_in_gold": True,
        "annotation_independently_human_adjudicated": False,
        "certification_eligible": False,
        "output_sha256": {
            DETAIL.name: sha256_file(DETAIL),
            SUMMARY.name: sha256_file(SUMMARY),
            ROOT_CAUSES.name: sha256_file(ROOT_CAUSES),
        },
    }
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    all_row = summary.loc[
        (summary["group_type"] == "ALL") & (summary["group"] == "ALL")
    ].iloc[0]
    print(f"BLOCKS={len(detail)} EXPECTED_FRAMES={int(all_row.expected_frames)}")
    print(
        "CANDIDATE_RECALL="
        f"{float(all_row.candidate_recall):.6f} "
        f"FRAME_PRECISION={float(all_row.frame_precision):.6f} "
        f"FRAME_RECALL={float(all_row.frame_recall):.6f}"
    )
    print(
        f"TABLE_ROUTE_ACCURACY={float(all_row.table_route_accuracy):.6f} "
        f"SILENT_MISS={int(all_row.silent_frame_miss)}"
    )
    print(f"CERTIFICATION_ELIGIBLE={bool(all_row.certification_eligible)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
