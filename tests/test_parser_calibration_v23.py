from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v23_blind_candidates import (
    CANDIDATES,
    load_blind_config,
    verify_candidate_artifact,
    verify_parser_snapshot,
)


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v23_blind_sentence_annotations.jsonl"
)
OUTPUT = PROJECT_ROOT / "output/platform_v2_3_parser_calibration"


def test_v23_parser_selection_and_candidates_are_hash_frozen() -> None:
    config = load_blind_config()
    verify_parser_snapshot(config)
    verify_candidate_artifact(config)
    assert config["blindness_claim"] == "SENTENCE_BLOCK_OUTCOME_BLIND_NOT_ISSUER_UNSEEN"
    assert config["rule_changes_after_selection"] is False
    assert sha256_file(
        PROJECT_ROOT / "scripts/architecture/v23_blind_candidates.py"
    ) == config["selection_snapshot"]["generator_sha256"]

    candidates = pd.read_csv(CANDIDATES)
    assert len(candidates) == 39
    assert candidates["candidate_id"].is_unique
    assert candidates["ticker"].nunique() == 10
    selected_concepts = {
        reason.removeprefix("CONCEPT:")
        for payload in candidates["selection_reason"]
        for reason in payload.split("|")
        if reason.startswith("CONCEPT:")
    }
    assert selected_concepts == set(config["required_critical_concepts"])


def test_v23_annotations_are_exhaustive_and_blind_scores_are_fail_closed() -> None:
    candidates = pd.read_csv(CANDIDATES)
    annotations = [
        json.loads(line)
        for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(annotations) == 39
    assert {row["candidate_id"] for row in annotations} == set(candidates["candidate_id"])

    detail = pd.read_csv(OUTPUT / "blind_sentence_evaluation.csv")
    summary = pd.read_csv(OUTPUT / "blind_sentence_summary.csv").iloc[0]
    assert len(detail) == 39
    assert summary["annotation_coverage"] == 1.0
    assert summary["critical_opportunities"] == 18
    assert summary["critical_precision"] == 1.0
    assert summary["critical_recall"] == pytest.approx(1 / 6)
    assert summary["narrative_opportunities"] == 4
    assert summary["narrative_precision"] == 1.0
    assert summary["narrative_recall"] == pytest.approx(1 / 4)
    assert summary["table_route_accuracy"] == pytest.approx(18 / 19)
    assert not bool(summary["critical_recall_gate_95pct"])
    assert summary["status"] == "HOLD_RESEARCH_UNFROZEN"


def test_v23_source_lineage_reaches_l0_but_cannot_run_dcf() -> None:
    gate = pd.read_csv(OUTPUT / "platform_v23_gate.csv").iloc[0]
    funnel = pd.read_csv(OUTPUT / "certification_funnel.csv").set_index("level")
    certification = pd.read_csv(OUTPUT / "universe_layer_certification.csv")
    assert gate["registered_tickers"] == 52
    assert gate["selection_concept_coverage"] == 1.0
    assert gate["gold_critical_concept_coverage"] == pytest.approx(0.7)
    assert gate["l0_source_ready"] == 52
    assert gate["l1_parser_ready"] == 0
    assert gate["strict_dcf_runs"] == 0
    assert not bool(gate["forecast_snapshot_changed"])
    assert not bool(gate["dcf_kernel_changed"])
    assert not bool(gate["terminal_input_ready"])
    assert not bool(gate["production_promoted"])
    assert gate["status"] == "HOLD_RESEARCH_UNFROZEN"
    assert funnel.loc["L0_SOURCE_READY", "tickers"] == 52
    assert funnel.loc["L3_VALUATION_READY", "tickers"] == 0
    assert certification["lineage_hash_coverage"].eq(1.0).all()
    assert not certification["narrative_evidence_ready"].any()


def test_v23_blind_evaluation_manifest_is_immutable() -> None:
    manifest = json.loads(
        (
            PROJECT_ROOT
            / "benchmarks/platform_v2_3_parser_calibration/manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["platform_status"] == "HOLD_RESEARCH_UNFROZEN"
    assert manifest["policy"]["future_use"] == "ERROR_ANALYSIS_ONLY_NOT_RETUNING_VALIDATION"
    assert sha256_file(
        PROJECT_ROOT / "configs/certification/platform_v23_blind_set.toml"
    ) == manifest["config_sha256"]
    for relative, expected in manifest["artifact_sha256"].items():
        assert sha256_file(PROJECT_ROOT / relative) == expected
