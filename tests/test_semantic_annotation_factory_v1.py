from __future__ import annotations

import tomllib

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    build_historical_review_queue,
    write_annotation_review_queue,
)
from scripts.architecture.build_semantic_annotation_factory_v1 import (
    discover_annotation_files,
    discover_candidate_csvs,
    verify_candidate_sources,
)


CONFIG = (
    PROJECT_ROOT / "configs/certification/text_ie_annotation_factory_v1.toml"
)


def test_annotation_factory_freeze_replays_all_historical_candidates(tmp_path) -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    expected = config["historical_replay"]
    candidates = discover_candidate_csvs()
    annotations = discover_annotation_files()

    queue = build_historical_review_queue(
        candidate_csvs=candidates,
        annotation_files=annotations,
    )
    output = tmp_path / "queue.jsonl"
    write_annotation_review_queue(output, queue.items)

    assert config["status"] == "SCHEMA_FROZEN_MODEL_UNTRAINED"
    assert not config["model_training_allowed"]
    assert len(candidates) == expected["candidate_csvs"]
    assert len(annotations) == expected["annotation_files"]
    assert queue.annotation_row_count == expected["annotation_rows"]
    assert queue.unique_candidate_count == expected["unique_contexts"]
    assert queue.superseded_annotation_rows == expected["superseded_rows"]
    assert len(queue.items) == expected["queue_items"]
    assert sum(item.proposal is not None for item in queue.items) == expected["pair_proposals"]
    assert sum(
        item.proposal is None and item.adjudication_status == "PENDING"
        for item in queue.items
    ) == expected["context_recovery_items"]
    assert queue.archived_table_contexts == expected["archived_table_contexts"]
    assert queue.selected_expected_frames == expected["selected_legacy_frames"]
    assert queue.matched_expected_frames == expected["matched_legacy_frames"]
    assert queue.unmatched_expected_frames == expected["unmatched_legacy_frames"]
    assert sha256_file(output) == config["artifacts"]["generated_queue_sha256"]


def test_annotation_factory_freeze_verifies_schema_guideline_and_raw_sources() -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    artifacts = config["artifacts"]

    assert sha256_file(PROJECT_ROOT / artifacts["schema"]) == artifacts["schema_sha256"]
    assert sha256_file(PROJECT_ROOT / artifacts["guideline"]) == artifacts["guideline_sha256"]
    verification = verify_candidate_sources(discover_candidate_csvs())
    assert verification["all_sources_verified"]
    assert verification["existing_source_files"] == config["historical_replay"]["verified_source_files"]
