from pathlib import Path

from equity_platform.sectors.industrials.aerospace_defense.gd_v6.benchmark import (
    verify_gd_v6_research,
)


ROOT = Path(__file__).resolve().parents[1]


def test_gd_v6_research_manifest_is_intact():
    result = verify_gd_v6_research(ROOT)
    assert result["verified_files"] > 0
