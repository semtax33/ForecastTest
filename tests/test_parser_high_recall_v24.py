from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v24_blind_candidates import (
    CANDIDATES,
    load_blind_config,
    verify_candidate_artifact,
    verify_v24_snapshot,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_4_high_recall"
ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v24_unseen_sentence_annotations.jsonl"


def test_v24_is_a_true_issuer_and_document_unseen_snapshot() -> None:
    config = load_blind_config()
    verify_v24_snapshot(config)
    verify_candidate_artifact(config)
    assert config["issuer_unseen"] is True
    assert config["document_unseen"] is True
    assert config["prior_repository_occurrence_count_before_declaration"] == 0
    assert config["rule_changes_after_selection"] is False
    assert len(config["evaluation_tickers"]) == 10
    assert len(config["sources"]) == 10


def test_v24_annotations_are_exhaustive_and_ladder_is_reproducible() -> None:
    candidates = pd.read_csv(CANDIDATES)
    annotations = [json.loads(line) for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines() if line]
    assert len(candidates) == len(annotations) == 54
    assert {row["candidate_id"] for row in annotations} == set(candidates["candidate_id"])
    ladder = pd.read_csv(OUTPUT / "coverage_ladder.csv").set_index("stage")
    assert ladder.loc["MENTION", "recall"] == 1.0
    assert ladder.loc["CANDIDATE", "recall"] == 1.0
    assert ladder.loc["BINDING", "recall"] == pytest.approx(41 / 57)
    assert ladder.loc["FINAL_FACT", "recall"] == pytest.approx(29 / 57)


def test_v24_passes_recall_milestone_but_fails_closed_on_precision() -> None:
    summary = pd.read_csv(OUTPUT / "blind_sentence_summary.csv").iloc[0]
    gate = pd.read_csv(OUTPUT / "platform_v24_gate.csv").iloc[0]
    funnel = pd.read_csv(OUTPUT / "certification_funnel.csv").set_index("level")
    assert summary["candidate_precision"] == pytest.approx(38 / 56)
    assert summary["critical_recall"] == pytest.approx(29 / 56)
    assert summary["critical_precision"] == pytest.approx(29 / 54)
    assert bool(summary["v24_recall_milestone_50pct"])
    assert not bool(summary["precision_gate_99pct"])
    assert summary["status"] == "HOLD_RESEARCH_UNFROZEN"
    assert gate["strict_dcf_runs"] == 0
    assert funnel.loc["L0_SOURCE_READY", "tickers"] == 52
    assert funnel.loc["L1_PARSER_READY", "tickers"] == 0
    assert funnel.loc["L3_VALUATION_READY", "tickers"] == 0


def test_v24_manifest_freezes_diagnostic_use_only() -> None:
    path = PROJECT_ROOT / "benchmarks/platform_v2_4_high_recall/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["platform_status"] == "HOLD_RESEARCH_UNFROZEN"
    assert manifest["policy"]["future_use"] == "ERROR_ANALYSIS_ONLY_NOT_RETUNING_VALIDATION"
    for relative, expected in manifest["artifact_sha256"].items():
        assert sha256_file(PROJECT_ROOT / relative) == expected
