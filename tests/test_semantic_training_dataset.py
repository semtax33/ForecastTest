from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    assess_semantic_training_readiness,
    build_semantic_training_dataset,
    load_staged_gold,
)


GOLD = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v291_native_abc_stage_gold.jsonl"


def test_training_dataset_builds_pair_tasks_without_leaking_table_examples() -> None:
    dataset = build_semantic_training_dataset(load_staged_gold(GOLD))

    assert len(dataset.relations) == 6
    assert len(dataset.roles) == 4
    assert sum(item.binding_label == "BELONGS_TO" for item in dataset.relations) == 4
    assert sum(item.binding_label == "NOT_RELATED" for item in dataset.relations) == 2
    assert {item.role_label for item in dataset.roles} == {
        "VALUE_CURRENT",
        "DELTA",
    }
    assert not any(item.gold_route == "TABLE_DSL" for item in dataset.relations)

    served = next(
        item
        for item in dataset.relations
        if item.metric_literal == "served" and item.quantity_literal == "20,000"
    )
    assert served.concept_label == "ACTIVITY_VOLUME"
    assert served.binding_label == "BELONGS_TO"
    assert "[METRIC]served[/METRIC]" in served.marked_context
    assert "[QTY]20,000[/QTY]" in served.marked_context
    served_role = next(
        item
        for item in dataset.roles
        if item.metric_literal == "served" and item.quantity_literal == "20,000"
    )
    assert served_role.role_label == "VALUE_CURRENT"


def test_native_abc_text_gold_fails_closed_for_transformer_training() -> None:
    dataset = build_semantic_training_dataset(load_staged_gold(GOLD))

    readiness = assess_semantic_training_readiness(dataset)

    assert readiness.relation_pair_count == 6
    assert readiness.role_example_count == 4
    assert readiness.positive_binding_count == 4
    assert not readiness.independently_human_adjudicated
    assert not readiness.ready
    assert "INSUFFICIENT_TEXT_CONTEXTS" in readiness.reasons
    assert "INSUFFICIENT_RELATION_PAIRS" in readiness.reasons
    assert "NO_INDEPENDENT_HUMAN_ADJUDICATION" in readiness.reasons
