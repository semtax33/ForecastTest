from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from scripts.architecture import v25_blind_candidates as v25
from scripts.architecture import v251_blind_candidates as v251


def _annotation_ids(path):
    return {json.loads(line)["candidate_id"] for line in path.read_text(encoding="utf-8").splitlines() if line}


def test_v25_candidate_generator_is_frozen_and_annotations_are_exhaustive() -> None:
    config = v25.load_blind_config()
    v25.verify_v25_snapshot(config)
    v25.verify_candidate_artifact(config)
    assert config["candidate_generator_frozen"] is True
    assert sha256_file(PROJECT_ROOT / "scripts/architecture/v25_blind_candidates.py") == config["selection_snapshot"]["generator_sha256"]
    candidates = pd.read_csv(v25.CANDIDATES)
    annotations = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v25_unseen_sentence_annotations.jsonl"
    assert len(candidates) == 51
    assert set(candidates["candidate_id"]) == _annotation_ids(annotations)


def test_v25_first_unseen_is_frozen_as_failed_diagnostic() -> None:
    summary = pd.read_csv(PROJECT_ROOT / "output/platform_v2_5_binding_precision/blind_sentence_summary.csv").iloc[0]
    assert summary["candidate_recall"] == 1.0
    assert summary["critical_precision"] == pytest.approx(4 / 7)
    assert summary["critical_recall"] == pytest.approx(12 / 56)
    assert summary["duplicate_auto_emission"] == 0
    assert summary["illegal_cross_clause_auto_binding"] == 0
    assert summary["status"] == "HOLD_RESEARCH_UNFROZEN"


def test_v251_second_unseen_recovers_precision_without_reusing_validation() -> None:
    config = v251.load_blind_config()
    v251.verify_candidate_artifact(config)
    assert config["blindness_claim"] == "SECOND_ISSUER_AND_DOCUMENT_UNSEEN_AFTER_V25_DIAGNOSTIC"
    candidates = pd.read_csv(v251.CANDIDATES)
    annotations = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v251_unseen_sentence_annotations.jsonl"
    assert len(candidates) == 50
    assert candidates["ticker"].nunique() == 10
    assert set(candidates["candidate_id"]) == _annotation_ids(annotations)
    summary = pd.read_csv(PROJECT_ROOT / "output/platform_v2_5_1_precision_adjudication/blind_sentence_summary.csv").iloc[0]
    assert summary["candidate_recall"] == 1.0
    assert summary["critical_precision"] == 1.0
    assert summary["critical_recall"] == pytest.approx(7 / 43)
    assert summary["duplicate_auto_emission"] == 0
    assert summary["illegal_cross_clause_auto_binding"] == 0
    assert summary["silent_miss"] == 0
    assert not bool(summary["recall_gate"])
    assert not bool(summary["table_gate"])


def test_v251_certification_stays_fail_closed_and_does_not_run_dcf() -> None:
    output = PROJECT_ROOT / "output/platform_v2_5_1_precision_adjudication"
    gate = pd.read_csv(output / "platform_v251_gate.csv").iloc[0]
    funnel = pd.read_csv(output / "certification_funnel.csv").set_index("level")
    assert bool(gate["precision_recovery_achieved"])
    assert not bool(gate["all_v25_gates_passed"])
    assert gate["strict_dcf_runs"] == 0
    assert not bool(gate["forecast_snapshot_changed"])
    assert not bool(gate["dcf_kernel_changed"])
    assert funnel.loc["L0_SOURCE_READY", "tickers"] == 52
    assert funnel.loc["L1_PARSER_READY", "tickers"] == 0
    assert funnel.loc["L3_VALUATION_READY", "tickers"] == 0


@pytest.mark.parametrize("name", ["platform_v2_5_binding_precision", "platform_v2_5_1_precision_adjudication"])
def test_v25_manifests_are_immutable(name: str) -> None:
    manifest = json.loads((PROJECT_ROOT / f"benchmarks/{name}/manifest.json").read_text(encoding="utf-8"))
    assert manifest["platform_status"] == "HOLD_RESEARCH_UNFROZEN"
    for relative, expected in manifest["artifact_sha256"].items():
        assert sha256_file(PROJECT_ROOT / relative) == expected
