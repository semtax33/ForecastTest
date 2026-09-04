from __future__ import annotations

import json
import pandas as pd
import pytest

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import calibration_metrics, evaluate_gold_corpus
from scripts.architecture.v22_blind_candidates import load_blind_config


DEV = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v22_generalization_dev.jsonl"
TAXONOMY = PROJECT_ROOT / "configs/certification/platform_v22_error_taxonomy.csv"


def test_v22_dev_corpus_generalizes_failure_modes_without_issuer_rules() -> None:
    rows = evaluate_gold_corpus(DEV)
    metrics = calibration_metrics(rows)
    assert len(rows) == 16
    assert all(row["passed"] for row in rows)
    assert metrics["expected_frames"] == 14
    assert metrics["auto_precision"] == 1.0
    assert metrics["auto_recall"] == 1.0
    assert metrics["auto_coverage"] == pytest.approx(14 / 19)
    assert metrics["abstention_rate"] == pytest.approx(4 / 19)

    taxonomy = pd.read_csv(TAXONOMY)
    assert len(taxonomy) == 10
    assert set(taxonomy["failure_class"]) == {
        "RELATION_ERROR",
        "ONTOLOGY_ERROR",
        "DOCUMENT_CONTEXT_ERROR",
    }
    assert not taxonomy["repair_layer"].str.contains("ISSUER", case=False).any()


def test_v22_historical_blind_snapshot_and_artifacts_are_immutable() -> None:
    config = load_blind_config()
    manifest = json.loads(
        (PROJECT_ROOT / "benchmarks/platform_v2_2_parser_generalization/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["parser_snapshot_sha256"] == config["parser_snapshot_sha256"]
    assert manifest["policy"]["old_blind_use"] == "ERROR_ANALYSIS_ONLY_NOT_RETUNING_VALIDATION"
    for relative, expected in manifest["artifact_sha256"].items():
        assert sha256_file(PROJECT_ROOT / relative) == expected
    candidates = pd.read_csv(
        PROJECT_ROOT / "output/platform_v2_2_parser_generalization/blind_sentence_candidates.csv"
    )
    assert candidates["ticker"].nunique() == 8
    assert len(candidates) == 31
    assert candidates["candidate_id"].is_unique


def test_v22_second_blind_set_measures_precision_recall_and_abstention() -> None:
    detail = pd.read_csv(
        PROJECT_ROOT / "output/platform_v2_2_parser_generalization/blind_sentence_evaluation.csv"
    )
    summary = pd.read_csv(
        PROJECT_ROOT / "output/platform_v2_2_parser_generalization/blind_sentence_summary.csv"
    )
    result = summary.iloc[0]
    assert len(detail) == 31
    assert result["annotation_coverage"] == 1.0
    assert result["critical_opportunities"] == 12
    assert result["critical_precision"] == 1.0
    assert result["critical_recall"] == pytest.approx(1 / 12)
    assert result["auto_coverage"] == pytest.approx(1 / 31)
    assert result["review_rate"] == pytest.approx(3 / 31)
    assert result["abstention_rate"] == pytest.approx(27 / 31)
    assert result["review_plus_abstention_miss_capture"] == 1.0
    assert result["table_route_accuracy"] == pytest.approx(8 / 9)
    assert result["narrative_status"] == "NOT_MEASURED_NO_OPPORTUNITIES"
    assert not bool(result["critical_recall_gate_95pct"])
    assert result["status"] == "HOLD_RESEARCH_UNFROZEN"
