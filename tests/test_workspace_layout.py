from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from energy_nowcast.benchmark import verify_frozen_benchmark
from energy_nowcast.config import ProjectPaths
from energy_nowcast.operations.champion import verify_champion
from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v174.benchmark import verify_v174
from energy_nowcast.research.ep_v19.benchmark import verify_v19
from energy_nowcast.research.phase6.benchmark import (
    verify_revenue_research_benchmark,
)
from energy_nowcast.research.v36.benchmark import verify_research_champion
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11
from equity_platform.data_catalog import DATA


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_root_has_no_loose_python_or_csv_files() -> None:
    assert list(ROOT.glob("*.py")) == []
    assert list(ROOT.glob("*.csv")) == []


def test_data_lake_uses_medallion_layout_and_catalog_paths() -> None:
    lake = ROOT / "data-lake"
    assert {path.name for path in lake.iterdir() if path.is_dir()} == {
        "bronze",
        "silver",
        "gold",
    }
    assert {path.name for path in lake.iterdir() if path.is_file()} == {"README.md"}
    assert DATA.manual_consensus.is_file()
    assert DATA.company_kpi_snapshot.is_dir()
    assert DATA.rig_snapshot.is_dir()
    assert DATA.steo_snapshot.is_dir()
    assert DATA.macro_snapshot.is_dir()
    assert (DATA.v21 / "energy_v2_1_panel.csv").is_file()
    assert (DATA.v33 / "energy_v3_3_validation.csv").is_file()


def test_responsibility_entrypoints_are_importable_modules() -> None:
    modules = (
        "scripts.energy.operations.nowcast",
        "scripts.energy.operations.live_forward_v2",
        "scripts.energy.research.valuation.v1",
        "scripts.energy.research.valuation.v1_1",
        "scripts.energy.research.ep.v1_7_4_cohort_closure",
        "scripts.energy.research.ep.v1_9_sample_stability",
        "scripts.energy.research.ep.v1_10_project_to_company_roic",
        "scripts.industrials.valuation_v1",
    )
    assert all(importlib.util.find_spec(module) is not None for module in modules)


def test_all_rebaselined_freezes_verify_together() -> None:
    checks = (
        verify_frozen_benchmark(ProjectPaths(root=ROOT)),
        verify_champion(ROOT),
        verify_research_champion(ROOT),
        verify_revenue_research_benchmark(ROOT),
        verify_v1(ROOT),
        verify_v11(ROOT),
        verify_v12(ROOT),
        verify_v13(ROOT),
        verify_v14(ROOT),
        verify_v15(ROOT),
        verify_v161(ROOT),
        verify_v174(ROOT),
        verify_v19(ROOT),
    )
    assert len(checks) == 13
    audit = json.loads(
        (ROOT / "benchmarks/layout_rebaseline_2026_09_03.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["migration"]["economic_outputs"] == "byte_preserved"
    assert sum(item["preserved_files"] for item in audit["manifests"]) >= 150
