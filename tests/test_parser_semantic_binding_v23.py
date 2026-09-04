from __future__ import annotations

import ast
from pathlib import Path

import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import calibration_metrics, evaluate_gold_corpus


DEV = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v23_semantic_binding_dev.jsonl"
CORE = (
    PROJECT_ROOT / "equity_platform/text_ie/semantic_binding.py",
    PROJECT_ROOT / "equity_platform/text_ie/context_validation.py",
    PROJECT_ROOT / "equity_platform/text_ie/runtime.py",
)


def test_v23_generic_binding_development_corpus_is_exact() -> None:
    rows = evaluate_gold_corpus(DEV)
    metrics = calibration_metrics(rows)
    assert len(rows) == 15
    assert all(row["passed"] for row in rows)
    assert metrics["expected_frames"] == 16
    assert metrics["auto_precision"] == 1.0
    assert metrics["auto_recall"] == 1.0
    assert metrics["review_plus_abstention_capture"] == 1.0


def test_v23_core_contains_no_issuer_specific_branch() -> None:
    forbidden = {
        "AR", "CNX", "COP", "DVN", "EOG", "EQT", "FANG", "MGY", "MTDR",
        "NOG", "OVV", "PR", "RRC", "SM", "XOM", "CVX", "EPD", "ET", "KMI",
        "WMB", "MPC", "PSX", "VLO", "BKR", "HAL", "SLB", "CAT", "ACCO",
        "ODFL", "UBER", "KEX",
    }
    for path in CORE:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert not literals & forbidden


def test_v23_development_metrics_do_not_claim_blind_certification() -> None:
    metrics = calibration_metrics(evaluate_gold_corpus(DEV))
    assert metrics["critical_precision"] == pytest.approx(1.0)
    assert metrics["critical_recall"] == pytest.approx(1.0)
    assert "blind" not in DEV.name.casefold()
