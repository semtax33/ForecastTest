from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_V35 = ROOT / "energy_nowcast/research/v35"
LEGACY_V11_ENGINE = ROOT / "energy_nowcast/valuation_v11/engine.py"
LEGACY_VALIDATION_FACADES = tuple(
    ROOT / "energy_nowcast/validation" / name
    for name in (
        "baselines.py",
        "cross_section_metrics.py",
        "intervals.py",
        "leave_one_company_out.py",
        "metrics.py",
        "promotion_gate.py",
    )
)


def test_removed_energy_v35_facade_is_not_reintroduced() -> None:
    assert not LEGACY_V35.exists()


def test_removed_energy_v11_engine_facade_is_not_reintroduced() -> None:
    assert not LEGACY_V11_ENGINE.exists()


def test_removed_validation_facades_are_not_reintroduced() -> None:
    assert [path for path in LEGACY_VALIDATION_FACADES if path.exists()] == []


def test_python_sources_use_canonical_energy_v35_package() -> None:
    forbidden = "energy_nowcast.research.v35."
    offenders = []
    for root in (ROOT / "energy_nowcast", ROOT / "equity_platform", ROOT / "scripts", ROOT / "tests"):
        for path in root.rglob("*.py"):
            if path == Path(__file__):
                continue
            if forbidden in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_v11_package_uses_canonical_engine_import() -> None:
    forbidden = "from .engine import"
    offenders = []
    package = ROOT / "energy_nowcast/valuation_v11"
    for path in package.rglob("*.py"):
        if forbidden in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_python_sources_use_canonical_shared_validation_package() -> None:
    moved_modules = (
        "baselines",
        "cross_section_metrics",
        "intervals",
        "leave_one_company_out",
        "metrics",
        "promotion_gate",
    )
    offenders = []
    for root in (
        ROOT / "energy_nowcast",
        ROOT / "equity_platform",
        ROOT / "scripts",
        ROOT / "tests",
    ):
        for path in root.rglob("*.py"):
            if path == Path(__file__):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                parts = node.module.split(".")
                if (
                    parts[:2] == ["energy_nowcast", "validation"]
                    and len(parts) > 2
                    and parts[2] in moved_modules
                ) or (
                    node.level > 0
                    and parts[:1] == ["validation"]
                    and len(parts) > 1
                    and parts[1] in moved_modules
                ):
                    offenders.append(path.relative_to(ROOT).as_posix())
                    break
    assert offenders == []
