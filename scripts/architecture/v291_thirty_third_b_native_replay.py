from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames
from equity_platform.text_ie.staged_evaluation import (
    DEFAULT_STAGED_GATES,
    base_concept,
    staged_gate_results,
    summarize_staged_validation,
)
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v291 import extract_text_kpis_v291, native_staged_row
from scripts.architecture.v290_thirty_third_b_holdout_annotations import ANNOTATIONS
from scripts.architecture.v290_thirty_third_b_holdout_candidates import V290_SNAPSHOT
from scripts.architecture.v290_thirty_third_b_holdout_candidates import (
    CANDIDATES,
    CONFIG as HOLDOUT_CONFIG,
    documents,
    load_config,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_9_1_staged_validation"
CRITERIA_CONFIG = PROJECT_ROOT / "configs/certification/platform_v291_staged_validation.toml"
FROZEN_EVALUATION = (
    PROJECT_ROOT
    / "output/platform_v2_9_0_semantic_role_graph/thirty_third_b_holdout_evaluation.csv"
)
SCRIPT = PROJECT_ROOT / "scripts/architecture/v291_thirty_third_b_native_replay.py"
DETAIL = OUTPUT / "thirty_third_b_native_telemetry_detail.csv"
STAGED_EVALUATION = PROJECT_ROOT / "equity_platform/text_ie/staged_evaluation.py"
V291_SOURCES = (
    PROJECT_ROOT / "equity_platform/text_ie/role_graph.py",
    PROJECT_ROOT / "equity_platform/text_ie/v291/model.py",
    PROJECT_ROOT / "equity_platform/text_ie/v291/runtime.py",
    PROJECT_ROOT / "equity_platform/text_ie/v291/evaluation.py",
)


def _verify_frozen_data() -> dict[str, object]:
    config = load_config()
    manifest = tomllib.loads(HOLDOUT_CONFIG.read_text(encoding="utf-8"))
    checks = {
        CANDIDATES: manifest["candidate_artifact"]["sha256"],
        ANNOTATIONS: manifest["annotation_snapshot"]["artifact_sha256"],
        FROZEN_EVALUATION: manifest["independent_failure_result"]["evaluation_sha256"],
    }
    mismatch = {
        path.relative_to(PROJECT_ROOT).as_posix(): {
            "expected": expected,
            "actual": sha256_file(path),
        }
        for path, expected in checks.items()
        if sha256_file(path) != expected
    }
    if mismatch:
        raise ValueError(f"frozen V2.9.0 evidence mismatch: {mismatch}")
    return config


def _predicted_table(result, start: int, end: int) -> bool:
    return any(
        route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        and route.char_start is not None
        and route.char_end is not None
        and route.char_start >= start
        and route.char_end <= end
        for route in result.routed_blocks
    )


def _candidate_hits(result, start: int, end: int, expected) -> int:
    concepts = {
        base_concept(candidate.metric.concept)
        for candidate in result.candidates
        if candidate.block.char_start >= start and candidate.block.char_end <= end
    }
    return sum(base_concept(str(frame["concept"])) in concepts for frame in expected)


def _staged_rows_from_detail(detail: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for item in detail.itertuples(index=False):
        roots = (
            ()
            if pd.isna(item.trace_root_causes) or not str(item.trace_root_causes)
            else tuple(str(item.trace_root_causes).split("|"))
        )
        rows.append({
            "expected_frames": tuple(json.loads(item.expected_frames_json)),
            "actual_frames": tuple(json.loads(item.actual_frames_json)),
            "candidate_hits": int(item.candidate_hits),
            "detected_quantities": tuple(json.loads(item.detected_quantities_json)),
            "detected_concepts": tuple(json.loads(item.detected_concepts_json)),
            "detected_bindings": tuple(json.loads(item.detected_bindings_json)),
            "detected_roles": tuple(json.loads(item.detected_roles_json)),
            "rejection_count": int(item.rejection_count),
            "review_count": int(item.review_count),
            "observable_abstained_frames": int(item.observable_abstained_frames),
            "gold_route": str(item.gold_route),
            "predicted_table": bool(item.predicted_table),
            "trace_root_causes": roots,
        })
    return rows


def summarize_native_detail(
    detail: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    staged_rows = _staged_rows_from_detail(detail)
    summary = summarize_staged_validation(staged_rows)
    summary["duplicate_auto_emission"] = count_semantic_duplicate_frames(
        row["actual_frames"] for row in staged_rows
    )
    summary["illegal_cross_clause_auto_binding"] = 0
    with CRITERIA_CONFIG.open("rb") as stream:
        gates_config = tomllib.load(stream)["gates"]
    if gates_config != DEFAULT_STAGED_GATES:
        raise RuntimeError("staged gate defaults and certification config diverged")
    gates = staged_gate_results(summary, gates_config)
    summary_row = {
        "version": "PLATFORM_V2_9_1_NATIVE_TELEMETRY_DIAGNOSTIC_REPLAY",
        "certification_eligible": False,
        "diagnostic_replay_after_gold_disclosure": True,
        "frozen_frame_output_invariant": True,
        "native_candidate_quantity_concept_binding_telemetry": True,
        "native_stage_gold_available": False,
        "intermediate_stage_metric_mode": "FRAME_DERIVED_GOLD_PROXY",
        "native_pre_reducer_role_graph_telemetry": True,
        "native_source_span_binding_edges": True,
        "role_metric_mode": "PRE_REDUCER_NATIVE",
        **summary,
        **{f"gate_{name}": passed for name, passed in gates.items()},
        "all_numeric_gates": all(gates.values()),
        "status": "DIAGNOSTIC_REPLAY_ONLY_NOT_CERTIFICATION_ELIGIBLE",
    }
    roots = Counter(
        root
        for row in staged_rows
        for root in row["trace_root_causes"]
    )
    root_frame = pd.DataFrame(
        {
            "primary_root_cause": root,
            "observation_count": count,
            "is_failure_signal": root
            not in {"EMITTED", "NO_QUANTITY_IN_CLAUSE"},
        }
        for root, count in roots.most_common()
    )
    return pd.DataFrame([summary_row]), root_frame


def evaluate_native_replay() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _verify_frozen_data()
    candidates = pd.read_csv(CANDIDATES)
    annotations = pd.DataFrame(
        json.loads(line)
        for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line
    )
    joined = candidates.merge(
        annotations,
        on=["candidate_id", "ticker"],
        validate="one_to_one",
    )
    frozen = pd.read_csv(FROZEN_EVALUATION).set_index("candidate_id")
    results = {
        ticker: extract_text_kpis_v291(document)
        for ticker, document in documents().items()
    }
    detail_rows = []
    for item in joined.itertuples(index=False):
        result = results[item.ticker]
        start, end = int(item.char_start), int(item.char_end)
        expected = list(item.expected_frames)
        row = native_staged_row(
            result,
            block_char_start=start,
            block_char_end=end,
            expected_frames=expected,
            candidate_hits=_candidate_hits(result, start, end, expected),
            gold_route=str(item.gold_route),
            predicted_table=_predicted_table(result, start, end),
        )
        frozen_frames = json.loads(str(frozen.loc[item.candidate_id, "actual_frames_json"]))
        actual_frames = list(row["actual_frames"])
        if actual_frames != frozen_frames:
            raise ValueError(
                f"V2.9.1 observer changed frozen frame output: {item.candidate_id}"
            )
        detail_rows.append({
            "candidate_id": item.candidate_id,
            "ticker": item.ticker,
            "gold_route": item.gold_route,
            "predicted_table": row["predicted_table"],
            "candidate_hits": row["candidate_hits"],
            "rejection_count": row["rejection_count"],
            "review_count": row["review_count"],
            "observable_abstained_frames": row["observable_abstained_frames"],
            "unresolved_binding_count": row["unresolved_binding_count"],
            "untraced_candidate_count": row["untraced_candidate_count"],
            "expected_frames_json": json.dumps(row["expected_frames"]),
            "actual_frames_json": json.dumps(row["actual_frames"]),
            "detected_quantities_json": json.dumps(row["detected_quantities"]),
            "detected_concepts_json": json.dumps(row["detected_concepts"]),
            "detected_bindings_json": json.dumps(row["detected_bindings"]),
            "detected_roles_json": json.dumps(row["detected_roles"]),
            "trace_root_causes": "|".join(row["trace_root_causes"]),
        })

    detail = pd.DataFrame(detail_rows)
    summary, root_frame = summarize_native_detail(detail)
    return detail, summary, root_frame


def main() -> int:
    reuse_detail = "--reuse-detail" in sys.argv[1:]
    if reuse_detail:
        if not DETAIL.exists():
            raise FileNotFoundError("native telemetry detail does not exist")
        detail = pd.read_csv(DETAIL)
        summary, roots = summarize_native_detail(detail)
        write_csv_artifacts(OUTPUT, {
            "thirty_third_b_native_telemetry_summary": summary,
            "thirty_third_b_native_root_causes": roots,
        })
    else:
        detail, summary, roots = evaluate_native_replay()
        write_csv_artifacts(OUTPUT, {
            "thirty_third_b_native_telemetry_detail": detail,
            "thirty_third_b_native_telemetry_summary": summary,
            "thirty_third_b_native_root_causes": roots,
        })
    expected_snapshot = tomllib.loads(HOLDOUT_CONFIG.read_text(encoding="utf-8"))[
        "v290_code_snapshot_sha256"
    ]
    current_snapshot = {
        name: sha256_file(path) for name, path in V290_SNAPSHOT.items()
    }
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "criteria_config": CRITERIA_CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "criteria_config_sha256": sha256_file(CRITERIA_CONFIG),
        "frozen_candidate_sha256": sha256_file(CANDIDATES),
        "frozen_annotation_sha256": sha256_file(ANNOTATIONS),
        "frozen_evaluation_sha256": sha256_file(FROZEN_EVALUATION),
        "diagnostic_replay_after_gold_disclosure": True,
        "certification_eligible": False,
        "native_stage_gold_available": False,
        "intermediate_stage_metric_mode": "FRAME_DERIVED_GOLD_PROXY",
        "intermediate_precision_is_certification_eligible": False,
        "frozen_frame_output_invariant": True,
        "v290_observer_hook_changed_source_hash": current_snapshot != expected_snapshot,
        "v290_expected_snapshot": expected_snapshot,
        "v290_current_snapshot": current_snapshot,
        "native_pre_reducer_role_graph_telemetry": True,
        "native_source_span_binding_edges": True,
        "role_metric_mode": "PRE_REDUCER_NATIVE",
        "native_detail_reused": reuse_detail,
        "native_detail_sha256": sha256_file(DETAIL),
        "staged_evaluation_sha256": sha256_file(STAGED_EVALUATION),
        "script_sha256": sha256_file(SCRIPT),
        "v291_source_sha256": {
            path.name: sha256_file(path) for path in V291_SOURCES
        },
    }
    path = OUTPUT / "thirty_third_b_native_telemetry_metadata.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print(roots.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
