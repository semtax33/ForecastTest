from __future__ import annotations

import json

from scripts.architecture.semantic_challenger_readiness import (
    _gpu_compatibility_status,
)


def test_gpu_compatibility_status_accepts_only_non_performance_pass(tmp_path) -> None:
    path = tmp_path / "compatibility.json"
    path.write_text(json.dumps({
        "status": "PASS",
        "evaluation_scope": "GPU_COMPATIBILITY_ONLY_NOT_PERFORMANCE",
        "performance_benchmark_eligible": False,
        "champion_selected": False,
        "models": [{"model_id": "a", "status": "PASS"}],
    }), encoding="utf-8")

    result = _gpu_compatibility_status(path)

    assert result["passed"] is True
    assert result["performance_evaluated"] is False


def test_gpu_compatibility_status_fails_closed_on_missing_or_mis_scoped_file(
    tmp_path,
) -> None:
    assert _gpu_compatibility_status(tmp_path / "missing.json")["passed"] is False
    path = tmp_path / "compatibility.json"
    path.write_text(json.dumps({
        "status": "PASS",
        "evaluation_scope": "PERFORMANCE",
        "performance_benchmark_eligible": True,
        "champion_selected": True,
        "models": [],
    }), encoding="utf-8")

    assert _gpu_compatibility_status(path)["passed"] is False
