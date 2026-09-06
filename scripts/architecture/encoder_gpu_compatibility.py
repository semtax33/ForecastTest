from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.llm.encoder_compatibility import (
    COMPATIBILITY_STATUS,
    preprocess_encoder_text,
)
from equity_platform.text_ie.llm.encoder_registry import DEFAULT_ENCODER_CANDIDATES
from equity_platform.text_ie.training import load_annotation_review_queue


QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_active.jsonl"
)
OUTPUT = (
    PROJECT_ROOT
    / "output/text_ie_semantic_challenger/encoder_gpu_compatibility.json"
)


def _source_slice_samples() -> dict[str, str]:
    samples: dict[str, str] = {}
    for item in load_annotation_review_queue(QUEUE):
        samples.setdefault(item.source_slice.value, item.text)
    required = {"SEC_10K", "SEC_10Q", "IR_PREPARED_REMARKS", "IR_QA"}
    missing = required - set(samples)
    if missing:
        raise RuntimeError(f"missing compatibility source slices: {sorted(missing)}")
    return {source_slice: samples[source_slice] for source_slice in sorted(required)}


def build_gpu_compatibility_report() -> dict[str, object]:
    import accelerate
    import spacy
    import torch
    import transformers

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; CPU compatibility fallback is disabled")
    nlp = spacy.blank("en")
    samples = _source_slice_samples()
    results = []
    for candidate in DEFAULT_ENCODER_CANDIDATES:
        started = time.perf_counter()
        tokenizer = None
        model = None
        try:
            tokenizer = transformers.AutoTokenizer.from_pretrained(
                candidate.model_id,
                trust_remote_code=False,
            )
            texts = [
                preprocess_encoder_text(
                    text,
                    model_id=candidate.model_id,
                    tokenizer=tokenizer,
                    nlp=nlp,
                )
                for text in samples.values()
            ]
            encoded = tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            model = transformers.AutoModel.from_pretrained(
                candidate.model_id,
                trust_remote_code=False,
            )
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            model.to("cuda")
            model.eval()
            encoded = {key: value.to("cuda") for key, value in encoded.items()}
            with torch.inference_mode(), torch.autocast(
                device_type="cuda", dtype=torch.float16
            ):
                output = model(**encoded)
            torch.cuda.synchronize()
            hidden = output.last_hidden_state
            results.append({
                "model_id": candidate.model_id,
                "family": candidate.family,
                "status": "PASS",
                "performance_evaluated": False,
                "source_slices": list(samples),
                "batch_size": int(hidden.shape[0]),
                "sequence_length": int(hidden.shape[1]),
                "hidden_size": int(hidden.shape[2]),
                "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
                "model_revision": getattr(model.config, "_commit_hash", None),
                "tokenizer_revision": tokenizer.init_kwargs.get("_commit_hash"),
                "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / (1 << 20), 2),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            })
        except Exception as exc:  # compatibility report must retain all candidates
            results.append({
                "model_id": candidate.model_id,
                "family": candidate.family,
                "status": "FAIL",
                "performance_evaluated": False,
                "source_slices": list(samples),
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            })
        finally:
            if model is not None:
                model.to("cpu")
            del model
            del tokenizer
            torch.cuda.empty_cache()
    all_passed = all(result["status"] == "PASS" for result in results)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all_passed else "FAIL",
        "evaluation_scope": COMPATIBILITY_STATUS,
        "performance_benchmark_eligible": False,
        "champion_selected": False,
        "device_policy": "CUDA_REQUIRED_NO_SILENT_CPU_FALLBACK",
        "device": {
            "name": torch.cuda.get_device_name(0),
            "total_memory_mib": round(
                torch.cuda.get_device_properties(0).total_memory / (1 << 20), 2
            ),
            "cuda_runtime": torch.version.cuda,
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "accelerate": accelerate.__version__,
            "spacy": spacy.__version__,
        },
        "models": results,
    }


def main() -> int:
    report = build_gpu_compatibility_report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"STATUS={report['status']} SCOPE={report['evaluation_scope']} "
        f"GPU={report['device']['name']}"
    )
    for model in report["models"]:
        print(
            f"MODEL={model['model_id']} STATUS={model['status']} "
            f"PEAK_MIB={model.get('peak_allocated_mib', 0)} "
            f"SECONDS={model['elapsed_seconds']}"
        )
        if model["error"]:
            print(f"ERROR={model['error']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
