from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.semantic_challenger import SemanticTask
from equity_platform.text_ie.training import (
    AnnotationQualityTier,
    EncoderCertificationRun,
    build_semantic_fine_tuning_plan,
    build_semantic_training_dataset_from_review_queue,
    encoder_champion_selection_from_dict,
    evaluate_champion_certification,
    load_annotation_review_queue,
)
from equity_platform.text_ie.training.huggingface_fine_tuning import (
    HuggingFaceFineTuningRuntime,
)


GOLD_QUEUE = PROJECT_ROOT / "data-lake/gold/parser/text_ie/gold_a_combined_v1.jsonl"
PAIR_GOLD_B_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/pair_gold_b_combined_v1.jsonl"
)
TRAINING_ROOT = PROJECT_ROOT / "output/text_ie_semantic_challenger/training_v1"
TRAINING_REPORT = TRAINING_ROOT / "report.json"
REPORT = TRAINING_ROOT / "certification_report.json"


def _write(payload: dict[str, object]) -> None:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )


def main() -> int:
    common = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_enabled": False,
    }
    if (
        not TRAINING_REPORT.exists()
        or not GOLD_QUEUE.exists()
        or not PAIR_GOLD_B_QUEUE.exists()
    ):
        report = {**common, "status": "BLOCKED_MISSING_TRAINING_OR_GOLD_A"}
        _write(report)
        print(f"STATUS={report['status']}")
        return 1
    training_report = json.loads(TRAINING_REPORT.read_text(encoding="utf-8"))
    raw_selection = training_report.get("calibration_selection")
    if not raw_selection:
        report = {**common, "status": "BLOCKED_NO_FROZEN_CALIBRATION_CHAMPION"}
        _write(report)
        print(f"STATUS={report['status']}")
        return 1
    selection = encoder_champion_selection_from_dict(raw_selection)
    if selection.champion_model_id is None:
        report = {**common, "status": "BLOCKED_NO_FROZEN_CALIBRATION_CHAMPION"}
        _write(report)
        print(f"STATUS={report['status']}")
        return 1
    items = (
        *load_annotation_review_queue(GOLD_QUEUE),
        *load_annotation_review_queue(PAIR_GOLD_B_QUEUE),
    )
    dataset = build_semantic_training_dataset_from_review_queue(
        items,
        minimum_quality=AnnotationQualityTier.GOLD_B,
    )
    plan = build_semantic_fine_tuning_plan(
        dataset,
        output_root=TRAINING_ROOT / "checkpoints",
    )
    rows_by_task = {
        SemanticTask.CONCEPT: dataset.concepts,
        SemanticTask.BINDING: dataset.relations,
        SemanticTask.ROLE: dataset.roles,
    }
    plan_cells = {
        cell.task: cell
        for cell in plan.cells
        if cell.model_id == selection.champion_model_id
    }
    selection_cells = {
        cell.task: cell
        for cell in selection.cells
        if cell.model_id == selection.champion_model_id
    }
    runtime = HuggingFaceFineTuningRuntime()
    runs = []
    for task in SemanticTask:
        certification_rows = tuple(
            row
            for row in rows_by_task[task]
            if row.holdout_axis == "CERTIFICATION"
        )
        calibration_cell = selection_cells[task]
        predictions = runtime.predict(
            plan_cells[task],
            certification_rows,
            checkpoint=calibration_cell.checkpoint,
        )
        runs.append(EncoderCertificationRun(
            model_id=selection.champion_model_id,
            task=task,
            predictions=predictions,
        ))
    certification = evaluate_champion_certification(selection, tuple(runs))
    report = {
        **common,
        "status": certification.status,
        "champion_model_id": certification.model_id,
        "task_certification_passed": certification.passed,
        "end_to_end_frame_gate_required": True,
        "certification": asdict(certification),
    }
    _write(report)
    print(
        f"STATUS={report['status']} CHAMPION={certification.model_id} "
        f"TASK_CERTIFICATION_PASS={certification.passed} PRODUCTION=False"
    )
    return 0 if certification.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
