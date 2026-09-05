from __future__ import annotations

from datetime import datetime, timezone
from importlib.util import find_spec
import json
from pathlib import Path
import shutil
import subprocess

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.llm import (
    DEFAULT_ENCODER_CANDIDATES,
    build_encoder_benchmark_matrix,
)
from equity_platform.text_ie.training import (
    assess_semantic_training_readiness,
    build_semantic_training_dataset,
    load_staged_gold,
)


STAGED_GOLD = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v291_native_abc_stage_gold.jsonl"
)
GOLD_ROOT = PROJECT_ROOT / "data-lake/gold/parser/text_ie"
OUTPUT = PROJECT_ROOT / "output/text_ie_semantic_challenger/readiness.json"


def _gpu_inventory() -> tuple[dict[str, object], ...]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return ()
    completed = subprocess.run(
        [
            executable,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode:
        return ()
    devices = []
    for row in completed.stdout.splitlines():
        parts = tuple(part.strip() for part in row.split(","))
        if len(parts) != 3:
            continue
        devices.append({
            "name": parts[0],
            "memory_mib": int(parts[1]),
            "driver_version": parts[2],
        })
    return tuple(devices)


def _line_count(path: Path) -> int:
    return sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())


def build_readiness_report() -> dict[str, object]:
    examples = load_staged_gold(STAGED_GOLD)
    dataset = build_semantic_training_dataset(examples)
    training = assess_semantic_training_readiness(dataset)
    packages = {
        package: find_spec(package) is not None
        for package in ("torch", "transformers", "accelerate")
    }
    devices = _gpu_inventory()
    legacy_files = tuple(
        path
        for path in GOLD_ROOT.glob("*.jsonl")
        if path != STAGED_GOLD
    )
    blockers = list(training.reasons)
    if not devices:
        blockers.append("NO_NVIDIA_GPU_VISIBLE")
    if not all(packages.values()):
        blockers.append("OPTIONAL_TRANSFORMER_DEPENDENCIES_MISSING")
    blockers.append("NO_FINE_TUNED_TASK_CHECKPOINTS")
    blockers.append("ENCODER_SOURCE_SLICE_BENCHMARK_NOT_RUN")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED_FAIL_CLOSED" if blockers else "READY_RESEARCH_ONLY",
        "production_enabled": False,
        "cuda_policy": "CUDA_REQUIRED_NO_SILENT_CPU_FALLBACK",
        "gpu_inventory": devices,
        "python_packages": packages,
        "staged_training_corpus": {
            "source_examples": dataset.source_example_count,
            "text_contexts": training.text_context_count,
            "concept_examples": training.concept_example_count,
            "binding_pairs": training.relation_pair_count,
            "positive_bindings": training.positive_binding_count,
            "negative_bindings": training.negative_binding_count,
            "role_examples": training.role_example_count,
            "independently_human_adjudicated": training.independently_human_adjudicated,
            "ready": training.ready,
        },
        "legacy_frame_only_corpora": {
            "files": len(legacy_files),
            "examples": sum(_line_count(path) for path in legacy_files),
            "training_status": "EXCLUDED_UNTIL_EXACT_SPANS_AND_RELATIONS_ARE_ADJUDICATED",
        },
        "encoder_candidates": [
            {
                "model_id": candidate.model_id,
                "family": candidate.family,
                "research_hypothesis": candidate.research_hypothesis,
                "runtime_champion": candidate.runtime_champion,
            }
            for candidate in DEFAULT_ENCODER_CANDIDATES
        ],
        "benchmark_matrix": [
            {
                "model_id": cell.model_id,
                "source_slice": cell.source_slice.value,
                "status": cell.status,
            }
            for cell in build_encoder_benchmark_matrix()
        ],
        "blockers": sorted(set(blockers)),
    }


def main() -> int:
    report = build_readiness_report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    corpus = report["staged_training_corpus"]
    gpu = report["gpu_inventory"]
    print(f"STATUS={report['status']} PRODUCTION_ENABLED={report['production_enabled']}")
    print(
        f"GPU={gpu[0]['name'] if gpu else 'NONE'} "
        f"MEMORY_MIB={gpu[0]['memory_mib'] if gpu else 0}"
    )
    print(
        f"TEXT_CONTEXTS={corpus['text_contexts']} CONCEPTS={corpus['concept_examples']} "
        f"BINDING_PAIRS={corpus['binding_pairs']} ROLES={corpus['role_examples']}"
    )
    print(f"BLOCKERS={','.join(report['blockers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
