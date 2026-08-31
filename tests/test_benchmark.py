from pathlib import Path

from energy_nowcast.benchmark import verify_frozen_benchmark
from energy_nowcast.config import ProjectPaths


ROOT = Path(__file__).resolve().parents[1]


def test_v33_benchmark_is_byte_for_byte_frozen():
    manifest = verify_frozen_benchmark(ProjectPaths(root=ROOT))
    assert manifest["version"] == "3.3"
    assert manifest["immutable"] is True
    assert manifest["expected_metrics"]["overall_mae_log_points"] < 9.08
