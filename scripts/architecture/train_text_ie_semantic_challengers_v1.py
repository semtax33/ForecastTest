from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.semantic_challenger import SemanticTask
from equity_platform.text_ie.training.huggingface_fine_tuning import (
    HuggingFaceFineTuningRuntime,
)
from equity_platform.text_ie.training import (
    AnnotationQualityTier,
    EncoderCalibrationRun,
    SemanticTrainingAuthority,
    assess_semantic_training_authority,
    build_semantic_fine_tuning_plan,
    build_semantic_training_dataset_from_review_queue,
    load_annotation_review_queue,
    run_semantic_fine_tuning_plan,
    select_encoder_champion,
)


GOLD_QUEUE = PROJECT_ROOT / "data-lake/gold/parser/text_ie/gold_a_combined_v1.jsonl"
PAIR_GOLD_B_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/pair_gold_b_combined_v1.jsonl"
)
INGESTION_REPORT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_combined_v1_ingestion_report.json"
)
OUTPUT = PROJECT_ROOT / "output/text_ie_semantic_challenger/training_v1"
REPORT = OUTPUT / "report.json"
CHECKPOINT_ROOT = OUTPUT / "checkpoints"


def _write_report(payload: dict[str, object]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run all nine CUDA fine-tuning cells after the corpus gates pass.",
    )
    parser.add_argument(
        "--epochs",
        type=float,
        default=None,
        help="Override epochs; RESEARCH_ONLY defaults to 1 and calibration runs to 3.",
    )
    args = parser.parse_args(argv)
    common = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gold_queue": GOLD_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "production_enabled": False,
        "certification_opened": False,
    }
    if (
        not GOLD_QUEUE.exists()
        or not PAIR_GOLD_B_QUEUE.exists()
        or not INGESTION_REPORT.exists()
    ):
        report = {
            **common,
            "status": "BLOCKED_MISSING_COMBINED_HUMAN_GOLD_A",
            "training_executed": False,
        }
        _write_report(report)
        print(f"STATUS={report['status']}")
        return 1
    ingestion_report = json.loads(INGESTION_REPORT.read_text(encoding="utf-8"))
    authority = assess_semantic_training_authority(
        training_ready=bool(ingestion_report.get("training_ready")),
        all_benchmark_slices_ready=bool(
            ingestion_report.get("all_source_slices_ready")
        ),
    )
    if not authority.training_allowed:
        report = {
            **common,
            "status": "BLOCKED_COMBINED_CORPUS_GATES_NOT_READY",
            "training_executed": False,
            "ingestion_status": ingestion_report.get("status"),
            "training_authority": authority.value,
        }
        _write_report(report)
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
    try:
        plan = build_semantic_fine_tuning_plan(
            dataset,
            output_root=CHECKPOINT_ROOT,
        )
    except ValueError as exc:
        report = {
            **common,
            "status": "BLOCKED_FINE_TUNING_PLAN_GATE",
            "training_executed": False,
            "error": str(exc),
        }
        _write_report(report)
        print(f"STATUS={report['status']} ERROR={exc}")
        return 1
    if not args.execute:
        status = (
            "CUDA_FINE_TUNING_PLAN_READY_CERTIFICATION_SEALED"
            if authority.calibration_champion_allowed
            else "CUDA_RESEARCH_FINE_TUNING_PLAN_READY_CALIBRATION_LOCKED"
        )
        report = {
            **common,
            "status": status,
            "training_executed": False,
            "training_authority": authority.value,
            "plan": asdict(plan),
        }
        _write_report(report)
        print(f"STATUS={report['status']} CELLS={len(plan.cells)}")
        return 0
    epochs = args.epochs
    if epochs is None:
        epochs = 1.0 if authority is SemanticTrainingAuthority.RESEARCH_ONLY else 3.0
    if epochs <= 0:
        parser.error("--epochs must be positive")
    results = run_semantic_fine_tuning_plan(
        plan,
        dataset,
        runtime=HuggingFaceFineTuningRuntime(epochs=epochs),
    )
    if authority is SemanticTrainingAuthority.RESEARCH_ONLY:
        report = {
            **common,
            "status": "RESEARCH_CHALLENGERS_TRAINED_CALIBRATION_LOCKED",
            "training_executed": True,
            "training_authority": authority.value,
            "cuda_required": True,
            "epochs": epochs,
            "plan": asdict(plan),
            "training_results": [asdict(result) for result in results],
            "calibration_selection": None,
        }
        _write_report(report)
        print(
            f"STATUS={report['status']} CELLS={len(results)} "
            "CHAMPION=None CERTIFICATION_OPENED=False"
        )
        return 0
    calibration_runs = tuple(
        EncoderCalibrationRun(
            model_id=result.model_id,
            task=SemanticTask(result.task),
            checkpoint=result.checkpoint,
            predictions=result.predictions,
        )
        for result in results
    )
    selection = select_encoder_champion(calibration_runs)
    report = {
        **common,
        "status": selection.status,
        "training_executed": True,
        "training_authority": authority.value,
        "cuda_required": True,
        "epochs": epochs,
        "plan": asdict(plan),
        "training_results": [asdict(result) for result in results],
        "calibration_selection": asdict(selection),
    }
    _write_report(report)
    print(
        f"STATUS={selection.status} CHAMPION={selection.champion_model_id} "
        f"CERTIFICATION_OPENED=False"
    )
    return 0 if selection.champion_model_id is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
