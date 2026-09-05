from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.spacy_backend import default_spacy_backend
from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames
from equity_platform.text_ie.staged_evaluation import (
    DEFAULT_STAGED_GATES,
    staged_gate_results,
    summarize_staged_validation,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_9_1_staged_validation"
CONFIG = PROJECT_ROOT / "configs/certification/platform_v291_staged_validation.toml"
STAGED_EVALUATION = PROJECT_ROOT / "equity_platform/text_ie/staged_evaluation.py"

VERSION_OUTPUTS = {
    268: "platform_v2_6_8_spacy_semantic_ownership",
    269: "platform_v2_6_9_spacy_semantic_ownership",
    270: "platform_v2_7_0_spacy_semantic_ownership",
    271: "platform_v2_7_1_spacy_semantic_ownership",
    272: "platform_v2_7_2_spacy_semantic_ownership",
    273: "platform_v2_7_3_spacy_semantic_clause",
    274: "platform_v2_7_4_spacy_bounded_context",
    275: "platform_v2_7_5_spacy_document_context",
    276: "platform_v2_7_6_spacy_cross_industry_semantics",
    277: "platform_v2_7_7_spacy_semantic_ownership",
    278: "platform_v2_7_8_spacy_semantic_roles",
    279: "platform_v2_7_9_spacy_semantic_ownership",
    280: "platform_v2_8_0_hierarchical_semantic_context",
    281: "platform_v2_8_1_hierarchical_context_recovery",
    282: "platform_v2_8_2_upper_context",
    283: "platform_v2_8_3_bounded_upper_context",
    284: "platform_v2_8_4_economic_roles",
    285: "platform_v2_8_5_generalized_financial_roles",
    286: "platform_v2_8_6_strict_adjudication",
    287: "platform_v2_8_7_role_expansion",
    288: "platform_v2_8_8_local_role_binder",
    289: "platform_v2_8_9_clause_transducer",
    290: "platform_v2_9_0_semantic_role_graph",
}


def _detector(version: int):
    module = importlib.import_module(f"equity_platform.text_ie.v{version}.semantics")
    # Some releases intentionally reused the immediately preceding detector
    # without publishing a version-local alias (V2.7.7 is the known example).
    # Resolve that inherited public function instead of inventing an alias in
    # the frozen parser package.
    for detector_version in range(version, 267, -1):
        detector = getattr(module, f"semantic_quantities_v{detector_version}", None)
        if detector is not None:
            return detector
    raise AttributeError(f"no compatible quantity detector exported by V{version}")


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).casefold() in {"true", "1", "yes"}


def _legacy_summary(path: Path) -> dict[str, object]:
    summary_path = path.with_name(path.name.replace("evaluation.csv", "summary.csv"))
    if not summary_path.exists():
        return {}
    rows = pd.read_csv(summary_path)
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _axis(path: Path) -> str:
    name = path.name.casefold()
    if "disclosed" in name or "regression" in name:
        return "DISCLOSED_DEVELOPMENT"
    # These artifacts predate the V2.9.1 A/B/C protocol.  Even filenames that
    # contain "b" or "c" do not prove all of the new issuer/industry split
    # invariants, so do not retroactively promote them to a native axis.
    return "LEGACY_HOLDOUT_NOT_NATIVE_ABC"


def _historical_status(numeric_gates_pass: bool) -> str:
    return (
        "HISTORICAL_PROXY_NUMERIC_PASS_NOT_CERTIFICATION_ELIGIBLE"
        if numeric_gates_pass
        else "HISTORICAL_PROXY_HOLD"
    )


def _rescore(
    path: Path,
    version: int,
    backend,
    gates_config: dict[str, float | int],
) -> dict[str, object]:
    detail = pd.read_csv(path)
    detector = _detector(version)
    rows = []
    for item in detail.to_dict(orient="records"):
        expected = json.loads(str(item["expected_frames_json"]))
        actual = json.loads(str(item["actual_frames_json"]))
        detected = []
        # Quantity precision is deliberately diagnostic.  Parse gold-positive
        # text blocks only so a broad candidate pool is not mislabeled as a
        # quantity detector error.
        if expected and str(item["gold_route"]) != "TABLE_DSL":
            detected = [
                float(quantity.value)
                for quantity in detector(str(item["text"]), backend)
            ]
        rows.append({
            "expected_frames": expected,
            "actual_frames": actual,
            "candidate_hits": int(item.get("candidate_hits", 0)),
            "detected_quantities": detected,
            "rejection_count": int(item.get("rejection_count", 0)),
            "review_count": 0,
            "gold_route": str(item["gold_route"]),
            "predicted_table": _boolean(item["predicted_table"]),
        })
    staged = summarize_staged_validation(rows)
    legacy = _legacy_summary(path)
    staged["duplicate_auto_emission"] = count_semantic_duplicate_frames(
        json.loads(str(payload)) for payload in detail["actual_frames_json"]
    )
    staged["illegal_cross_clause_auto_binding"] = int(
        legacy.get("illegal_cross_clause_auto_binding", 0)
    )
    gates = staged_gate_results(staged, gates_config)
    numeric_gates_pass = all(gates.values())
    return {
        "parser_version": f"V{version // 100}.{(version % 100) // 10}.{version % 10}",
        "dataset": path.stem.removesuffix("_evaluation"),
        "generalization_axis": _axis(path),
        "source_evaluation": path.relative_to(PROJECT_ROOT).as_posix(),
        "source_evaluation_sha256": sha256_file(path),
        "legacy_status": legacy.get("status", "UNKNOWN"),
        "legacy_auto_precision": legacy.get("auto_precision"),
        "legacy_auto_recall": legacy.get("auto_recall"),
        "legacy_candidate_recall": legacy.get("candidate_recall"),
        "legacy_binding_recall": legacy.get("binding_recall"),
        "legacy_silent_miss": legacy.get("silent_miss"),
        "native_candidate_graph_telemetry_available": False,
        "native_role_graph_telemetry_available": False,
        "review_observability_available": False,
        "native_stage_gold_available": False,
        "certification_eligible": False,
        **staged,
        **{f"gate_{name}": passed for name, passed in gates.items()},
        "all_staged_gates": numeric_gates_pass,
        "all_numeric_gates": numeric_gates_pass,
        "staged_status": _historical_status(numeric_gates_pass),
    }


def discover_evaluations() -> tuple[tuple[int, Path], ...]:
    output = []
    for version, directory in VERSION_OUTPUTS.items():
        root = PROJECT_ROOT / "output" / directory
        output.extend((version, path) for path in sorted(root.glob("*evaluation.csv")))
    return tuple(output)


def main() -> int:
    discovered = discover_evaluations()
    with CONFIG.open("rb") as stream:
        gates_config = tomllib.load(stream)["gates"]
    if gates_config != DEFAULT_STAGED_GATES:
        raise RuntimeError("staged gate defaults and certification config diverged")
    backend = default_spacy_backend()
    if backend is None:
        raise RuntimeError("spaCy semantic backend is required for historical rescoring")
    summary = pd.DataFrame(
        _rescore(path, version, backend, gates_config)
        for version, path in discovered
    )
    gate_columns = [column for column in summary if column.startswith("gate_")]
    gates = summary.melt(
        id_vars=["parser_version", "dataset", "generalization_axis"],
        value_vars=gate_columns,
        var_name="gate",
        value_name="passed",
    )
    write_csv_artifacts(OUTPUT, {
        "historical_staged_rescore": summary,
        "historical_staged_gate_matrix": gates,
    })
    metadata = {
        "criteria_version": "PLATFORM_V2_9_1_STAGED_FAIL_CLOSED_VALIDATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "config_sha256": sha256_file(CONFIG),
        "datasets_rescored": len(discovered),
        "numeric_proxy_passes": int(summary["all_numeric_gates"].sum()),
        "certification_passes": int(summary["certification_eligible"].sum()),
        "historical_artifacts_mutated": False,
        "historical_metric_mode": "retrospective_proxy_from_stored_detail_rows",
        "native_candidate_graph_telemetry_available": False,
        "native_role_graph_telemetry_available": False,
        "accepted_only_precision": True,
        "quantity_precision_is_gate": False,
        "review_observability_available": False,
        "quantity_detection_scope": "gold-positive non-table blocks",
        "cross_clause_source": "stored_legacy_summary_aggregate",
        "silent_miss_semantics": "unmatched frame without stored rejection; legacy review telemetry unavailable",
        "rescore_script_sha256": sha256_file(Path(__file__)),
        "staged_evaluation_sha256": sha256_file(STAGED_EVALUATION),
        "gates": gates_config,
    }
    (OUTPUT / "historical_staged_rescore_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    columns = [
        "parser_version", "dataset", "candidate_recall", "quantity_recall",
        "concept_precision", "binding_precision", "role_precision",
        "frame_precision", "frame_recall", "abstention_coverage",
        "silent_frame_miss", "table_route_accuracy", "staged_status",
    ]
    print(summary[columns].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
