from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool


def evaluate_gate_checks(checks: list[GateCheck]) -> tuple[bool, str]:
    failed = [check.name for check in checks if not check.passed]
    return not failed, "|".join(failed)
