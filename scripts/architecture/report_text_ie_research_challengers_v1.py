from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.llm.encoder_registry import DEFAULT_ENCODER_CANDIDATES
from equity_platform.text_ie.semantic_challenger import SemanticTask
from equity_platform.text_ie.training.research_evaluation import (
    build_research_diagnostics,
)


TRAINING_ROOT = PROJECT_ROOT / "output/text_ie_semantic_challenger/training_v1"
DEFAULT_RECEIPT_ROOT = TRAINING_ROOT / "checkpoints"
DEFAULT_TRAINING_REPORT = TRAINING_ROOT / "report.json"
DEFAULT_INGESTION_REPORT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_combined_v1_ingestion_report.json"
)
DEFAULT_OUTPUT = TRAINING_ROOT / "research_diagnostics.json"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report raw research diagnostics without model selection."
    )
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument(
        "--training-report", type=Path, default=DEFAULT_TRAINING_REPORT
    )
    parser.add_argument(
        "--ingestion-report", type=Path, default=DEFAULT_INGESTION_REPORT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    training_report = _read_json(args.training_report)
    if training_report.get("status") != (
        "RESEARCH_CHALLENGERS_TRAINED_CALIBRATION_LOCKED"
    ):
        raise ValueError("research diagnostics require a completed locked run")
    ingestion_report = _read_json(args.ingestion_report)
    if ingestion_report.get("all_source_slices_ready") is not False:
        raise ValueError("this report is only for a source-coverage-locked run")

    receipts = tuple(
        _read_json(path)
        for path in sorted(args.receipt_root.rglob("result-*.json"))
    )
    expected_matrix = tuple(
        (candidate.model_id, task.value)
        for candidate in DEFAULT_ENCODER_CANDIDATES
        for task in SemanticTask
    )
    report = build_research_diagnostics(
        receipts,
        expected_matrix=expected_matrix,
    )
    report.update({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "training_status": training_report["status"],
        "training_epochs": training_report["epochs"],
        "gold_a_context_counts": ingestion_report.get("context_counts", {}),
        "gold_a_gaps_to_50": ingestion_report.get("context_gaps_to_50", {}),
        "gold_a_gaps_to_75": ingestion_report.get("context_gaps_to_75", {}),
    })
    _atomic_write_json(args.output, report)
    print(
        f"STATUS={report['status']} CELLS={len(report['cells'])} "
        "CHAMPION=None CERTIFICATION_OPENED=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
