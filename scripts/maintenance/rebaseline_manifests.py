"""Rebaseline frozen manifests after the responsibility/data-layout refactor.

Only physical paths and code/test hashes are migrated. Existing output and
input bytes must still match their pre-migration hashes; otherwise the command
fails closed before writing a manifest.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from energy_nowcast.operations.champion import schema_signature
from energy_nowcast.research.ep_v12 import benchmark as ep12
from energy_nowcast.research.ep_v13 import benchmark as ep13
from energy_nowcast.research.ep_v14 import benchmark as ep14
from energy_nowcast.research.ep_v15 import benchmark as ep15
from energy_nowcast.research.ep_v161 import benchmark as ep161
from energy_nowcast.research.ep_v174 import benchmark as ep174
from energy_nowcast.research.ep_v19 import benchmark as ep19
from energy_nowcast.research.ep_v19.parent import v18_parent_snapshot
from energy_nowcast.research.phase6 import benchmark as phase5
from energy_nowcast.valuation import benchmark as valuation_v1
from energy_nowcast.valuation_v11 import benchmark as valuation_v11
from equity_platform.paths import PROJECT_ROOT
from scripts.energy.research.ep.v1_7_1_mna_numerator import _v17_snapshot
from scripts.energy.research.ep.v1_7_2_acquiree_nopat_cycle import _v171_snapshot
from scripts.energy.research.ep.v1_7_3_normalization_attribution import _v172_snapshot
from scripts.energy.research.ep.v1_7_4_cohort_closure import _v173_snapshot


ROOT = PROJECT_ROOT
MIGRATION_DATE = date(2026, 9, 3).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _relocate(relative: str) -> str:
    exact = {
        "energy_revenue_regression_v3_3.py": (
            "archive/energy_revenue/energy_revenue_regression_v3_3.py"
        ),
        "run_nowcast.py": "scripts/energy/operations/nowcast.py",
        "run_v353_grouped_component.py": (
            "scripts/energy/research/revenue/v353_grouped_component.py"
        ),
        "data-lake/analyst_consensus.csv": (
            "data-lake/bronze/manual_consensus/analyst_consensus.csv"
        ),
    }
    if relative in exact:
        return exact[relative]
    filename = Path(relative).name
    if relative.startswith("data-lake/energy_v3_3_"):
        return f"data-lake/gold/champions/v3_3/{filename}"
    for version in ("v2_1", "v3_2_1", "v3_2_7"):
        if relative.startswith(f"data-lake/energy_{version}_"):
            return f"data-lake/silver/models/{version}/{filename}"
    return relative


def _assert_preserved_bytes(
    old_files: dict[str, str],
    *,
    include_prefixes: tuple[str, ...],
) -> int:
    checked = 0
    failures: list[str] = []
    for old_relative, expected in old_files.items():
        if not old_relative.startswith(include_prefixes):
            continue
        if Path(old_relative).name == "metadata.json":
            # Lineage-only metadata is intentionally rewritten below. Numeric
            # outputs, tables, configs, and raw/model inputs remain byte-fixed.
            continue
        relative = _relocate(old_relative)
        path = (ROOT / relative).resolve()
        if not path.is_file():
            failures.append(f"missing:{relative}")
        elif _sha256(path) != expected:
            failures.append(f"changed:{relative}")
        checked += 1
    if failures:
        raise ValueError(f"Economic/input byte preservation failed: {failures}")
    return checked


def _update_json(relative: str, values: dict[str, Any]) -> None:
    path = ROOT / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(values)
    _write(path, payload)


def _migration_note() -> dict[str, str]:
    return {
        "date": MIGRATION_DATE,
        "scope": "physical_paths_and_code_tests_only",
        "economic_outputs": "byte_preserved",
        "reason": "responsibility_packages_and_bronze_silver_gold_layout",
    }


def _rebaseline_v33() -> dict[str, Any]:
    path = ROOT / "benchmarks/v3_3/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    preserved = _assert_preserved_bytes(
        manifest["artifacts"], include_prefixes=("data-lake/",)
    )
    relocated = {_relocate(key): value for key, value in manifest["artifacts"].items()}
    manifest["artifacts"] = {
        relative: _sha256(ROOT / relative) for relative in relocated
    }
    manifest["layout_rebaseline"] = _migration_note()
    _write(path, manifest)
    return {"manifest": str(path.relative_to(ROOT)), "preserved_files": preserved}


def _rebaseline_v34() -> dict[str, Any]:
    path = ROOT / "benchmarks/v3_4/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    preserved = 0
    for group in ("inputs", "model_artifacts"):
        preserved += _assert_preserved_bytes(
            manifest["hashes"][group],
            include_prefixes=("data-lake/", "../Arcana/", "output/"),
        )
    for group in ("code", "config", "inputs", "model_artifacts"):
        relocated = {
            _relocate(relative): expected
            for relative, expected in manifest["hashes"][group].items()
        }
        manifest["hashes"][group] = {
            relative: _sha256((ROOT / relative).resolve())
            for relative in relocated
        }
    schemas = {
        _relocate(relative): expected
        for relative, expected in manifest.get("input_schemas", {}).items()
    }
    manifest["input_schemas"] = {
        relative: schema_signature((ROOT / relative).resolve())
        for relative in schemas
    }
    manifest["layout_rebaseline"] = _migration_note()
    _write(path, manifest)
    return {"manifest": str(path.relative_to(ROOT)), "preserved_files": preserved}


def _rebaseline_v353() -> dict[str, Any]:
    path = ROOT / "benchmarks/v3_5_3_research/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    preserved = 0
    for group in ("inputs", "artifacts"):
        preserved += _assert_preserved_bytes(
            manifest["hashes"][group],
            include_prefixes=("data-lake/", "output/"),
        )
    for group in ("code", "config", "inputs", "artifacts"):
        relocated = {
            _relocate(relative): expected
            for relative, expected in manifest["hashes"][group].items()
        }
        manifest["hashes"][group] = {
            relative: _sha256(ROOT / relative) for relative in relocated
        }
    manifest["layout_rebaseline"] = _migration_note()
    _write(path, manifest)
    return {"manifest": str(path.relative_to(ROOT)), "preserved_files": preserved}


def _rebaseline_phase5() -> dict[str, Any]:
    path = ROOT / phase5.BENCHMARK
    manifest = json.loads(path.read_text(encoding="utf-8"))
    preserved = _assert_preserved_bytes(
        manifest["files"], include_prefixes=("output/",)
    )
    manifest["files"] = {
        relative: _sha256(ROOT / relative) for relative in phase5.FROZEN_FILES
    }
    manifest["layout_rebaseline"] = _migration_note()
    _write(path, manifest)
    return {"manifest": str(path.relative_to(ROOT)), "preserved_files": preserved}


def _rebaseline_module(
    module: ModuleType,
    *,
    parent_updates: dict[str, str] | None = None,
) -> dict[str, Any]:
    path = ROOT / module.MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    preserved = _assert_preserved_bytes(
        manifest["files"], include_prefixes=("output/", "configs/")
    )
    manifest["files"] = {
        relative: _sha256(ROOT / relative) for relative in module.FROZEN_FILES
    }
    for key, value in (parent_updates or {}).items():
        manifest[key] = value
    manifest["layout_rebaseline"] = _migration_note()
    _write(path, manifest)
    return {"manifest": str(path.relative_to(ROOT)), "preserved_files": preserved}


def _manifest_sha(module: ModuleType) -> str:
    return _sha256(ROOT / module.MANIFEST)


def main() -> int:
    results = [_rebaseline_v33(), _rebaseline_v34()]
    v34_sha = _sha256(ROOT / "benchmarks/v3_4/manifest.json")
    _update_json(
        "output/v3_5_3_grouped_component/metadata.json",
        {"v3_4_manifest_sha256": v34_sha},
    )
    results.append(_rebaseline_v353())
    v353_sha = _sha256(ROOT / "benchmarks/v3_5_3_research/manifest.json")
    _update_json(
        "output/phase2_5_target_aligned_research/metadata.json",
        {
            "v3_4_manifest_sha256": v34_sha,
            "v3_5_3_manifest_sha256": v353_sha,
        },
    )
    results.append(_rebaseline_phase5())
    phase5_sha = _sha256(ROOT / phase5.BENCHMARK)

    _update_json(
        "output/energy_valuation_v1/metadata.json",
        {"revenue_freeze_manifest_sha256": phase5_sha},
    )
    results.append(_rebaseline_module(valuation_v1))
    v1_sha = _manifest_sha(valuation_v1)
    _update_json(
        "output/energy_valuation_v1_1/metadata.json",
        {"parent_v1_0_manifest_sha256": v1_sha},
    )
    results.append(_rebaseline_module(valuation_v11))

    v11_sha = _manifest_sha(valuation_v11)
    _update_json(
        "output/energy_valuation_v1_1_ep_attribution/metadata.json",
        {
            "v1_0_manifest_sha256": v1_sha,
            "v1_1_manifest_sha256": v11_sha,
        },
    )
    _update_json(
        "output/energy_valuation_v1_1_live/metadata.json",
        {
            "benchmark_manifest_sha256": v11_sha,
            "parent_manifest_sha256": v1_sha,
        },
    )
    _update_json(
        "output/energy_valuation_v1_2_research/metadata.json",
        {
            "v1_0_manifest_sha256": v1_sha,
            "v1_1_manifest_sha256": v11_sha,
        },
    )
    results.append(
        _rebaseline_module(
            ep12,
            parent_updates={
                "parent_v1_0_manifest_sha256": v1_sha,
                "parent_v1_1_manifest_sha256": v11_sha,
            },
        )
    )
    v12_sha = _manifest_sha(ep12)
    _update_json(
        "output/energy_valuation_v1_3_research/metadata.json",
        {
            "v1_manifest_sha256": v1_sha,
            "v1_1_manifest_sha256": v11_sha,
            "v1_2_manifest_sha256": v12_sha,
        },
    )
    results.append(
        _rebaseline_module(
            ep13,
            parent_updates={
                "parent_v1_manifest_sha256": v1_sha,
                "parent_v1_1_manifest_sha256": v11_sha,
                "parent_v1_2_manifest_sha256": v12_sha,
            },
        )
    )
    v13_sha = _manifest_sha(ep13)
    _update_json(
        "output/energy_valuation_v1_4_research/metadata.json",
        {
            "v1_manifest_sha256": v1_sha,
            "v1_1_manifest_sha256": v11_sha,
            "v1_2_manifest_sha256": v12_sha,
            "v1_3_manifest_sha256": v13_sha,
        },
    )
    results.append(
        _rebaseline_module(
            ep14,
            parent_updates={
                "parent_v1_manifest_sha256": v1_sha,
                "parent_v1_1_manifest_sha256": v11_sha,
                "parent_v1_2_manifest_sha256": v12_sha,
                "parent_v1_3_manifest_sha256": v13_sha,
            },
        )
    )
    v14_sha = _manifest_sha(ep14)
    _update_json(
        "output/energy_valuation_v1_5_research/metadata.json",
        {
            "v1_manifest_sha256": v1_sha,
            "v1_1_manifest_sha256": v11_sha,
            "v1_2_manifest_sha256": v12_sha,
            "v1_3_manifest_sha256": v13_sha,
            "v1_4_manifest_sha256": v14_sha,
        },
    )
    results.append(
        _rebaseline_module(
            ep15,
            parent_updates={
                "parent_v1_manifest_sha256": v1_sha,
                "parent_v1_1_manifest_sha256": v11_sha,
                "parent_v1_2_manifest_sha256": v12_sha,
                "parent_v1_3_manifest_sha256": v13_sha,
                "parent_v1_4_manifest_sha256": v14_sha,
            },
        )
    )
    v15_sha = _manifest_sha(ep15)
    parent_lineage = {
        "v1_manifest_sha256": v1_sha,
        "v11_manifest_sha256": v11_sha,
        "v12_manifest_sha256": v12_sha,
        "v13_manifest_sha256": v13_sha,
        "v14_manifest_sha256": v14_sha,
        "v15_manifest_sha256": v15_sha,
    }
    _update_json("output/energy_valuation_v1_6_research/metadata.json", parent_lineage)
    _update_json(
        "output/energy_valuation_v1_6_1_research/metadata.json", parent_lineage
    )
    results.append(
        _rebaseline_module(
            ep161,
            parent_updates={
                "parent_v1_manifest_sha256": v1_sha,
                "parent_v11_manifest_sha256": v11_sha,
                "parent_v12_manifest_sha256": v12_sha,
                "parent_v13_manifest_sha256": v13_sha,
                "parent_v14_manifest_sha256": v14_sha,
                "parent_v15_manifest_sha256": v15_sha,
            },
        )
    )
    v161_sha = _manifest_sha(ep161)
    _update_json(
        "output/energy_valuation_v1_7_research/metadata.json",
        {"v1_6_1_manifest_sha256": v161_sha},
    )
    v17_snapshot = _v17_snapshot()
    _update_json(
        "output/energy_valuation_v1_7_1_research/metadata.json",
        {
            "v1_6_1_manifest_sha256": v161_sha,
            "v1_7_parent_snapshot_sha256": v17_snapshot,
        },
    )
    v171_snapshot = _v171_snapshot()
    _update_json(
        "output/energy_valuation_v1_7_2_research/metadata.json",
        {
            "v1_6_1_manifest_sha256": v161_sha,
            "v1_7_1_parent_snapshot_sha256": v171_snapshot,
        },
    )
    v172_snapshot = _v172_snapshot()
    _update_json(
        "output/energy_valuation_v1_7_3_research/metadata.json",
        {
            "v1_6_1_manifest_sha256": v161_sha,
            "v1_7_2_parent_snapshot_sha256": v172_snapshot,
        },
    )
    v173_snapshot = _v173_snapshot()
    _update_json(
        "output/energy_valuation_v1_7_4_research/metadata.json",
        {
            "v1_6_1_manifest_sha256": v161_sha,
            "v1_7_3_parent_snapshot_sha256": v173_snapshot,
        },
    )
    results.append(
        _rebaseline_module(
            ep174,
            parent_updates={
                "parent_v1_6_1_manifest_sha256": v161_sha,
                "parent_v1_7_3_snapshot_sha256": v173_snapshot,
            },
        )
    )
    v174_sha = _manifest_sha(ep174)
    _update_json(
        "output/energy_valuation_v1_8_research/metadata.json",
        {"v1_7_4_parent_manifest_sha256": v174_sha},
    )
    v18_snapshot = str(v18_parent_snapshot(ROOT)["snapshot_sha256"])
    _update_json(
        "output/energy_valuation_v1_9_research/metadata.json",
        {
            "v1_8_parent_snapshot_sha256": v18_snapshot,
            "v1_7_4_manifest_sha256": v174_sha,
        },
    )

    v19_path = ROOT / ep19.MANIFEST
    v19 = json.loads(v19_path.read_text(encoding="utf-8"))
    preserved = _assert_preserved_bytes(
        v19["files"], include_prefixes=("output/", "configs/")
    )
    v19["files"] = {
        relative: _sha256(ROOT / relative) for relative in ep19.FROZEN_FILES
    }
    v19["parents"] = {
        "v1_8_snapshot_sha256": v18_snapshot,
        "v1_7_4_manifest_sha256": v174_sha,
    }
    v19["layout_rebaseline"] = _migration_note()
    _write(v19_path, v19)
    results.append(
        {"manifest": str(v19_path.relative_to(ROOT)), "preserved_files": preserved}
    )
    _update_json(
        "output/energy_valuation_v1_10_research/metadata.json",
        {"v1_9_parent_manifest_sha256": _sha256(v19_path)},
    )

    audit_path = ROOT / "benchmarks/layout_rebaseline_2026_09_03.json"
    _write(
        audit_path,
        {
            "migration": _migration_note(),
            "manifests": [
                {
                    **result,
                    "sha256": _sha256(ROOT / result["manifest"]),
                }
                for result in results
            ],
        },
    )
    print(json.dumps(json.loads(audit_path.read_text(encoding="utf-8")), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
