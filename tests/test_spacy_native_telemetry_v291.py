from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.staged_evaluation import summarize_staged_validation
from equity_platform.text_ie.training.staged_gold import (
    ConceptGoldNode,
    HoldoutAxis,
    QuantityGoldNode,
    RoleGoldEdge,
    StageEdge,
    StagedGoldExample,
)
from equity_platform.text_ie.v291 import (
    DocumentSemanticTelemetry,
    extract_text_kpis_v291,
    native_stage_gold_row,
    native_staged_row,
)


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<p>{text}</p>".encode(),
                "test://v291-native-telemetry",
                "V291",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def test_v291_native_trace_exposes_role_abstention_after_valid_binding() -> None:
    text = (
        "This sales mix is compared to approximately 90% for disposable protective "
        "garments, 6% for face masks and 4% for face shields for the three months "
        "ended June 30, 2025."
    )

    result = extract_text_kpis_v291(_doc(text))

    assert result.extraction.frames == ()
    trace = result.telemetry.clauses[0]
    assert trace.candidate_ids
    assert {mention.concept for mention in trace.concepts} == {"REVENUE"}
    assert [quantity.value for quantity in trace.quantities] == [90.0, 6.0, 4.0]
    assert [edge.concept for edge in trace.bindings] == ["REVENUE"] * 3
    assert trace.roles == ()
    assert trace.primary_root_cause == "UNRESOLVED_SEMANTIC_ROLE"


def test_v291_native_trace_preserves_emission_and_labels_quantity_roles() -> None:
    result = extract_text_kpis_v291(
        _doc("Revenue was $6.9 billion, a decrease of 1% compared to last year.")
    )

    assert {
        (
            frame.concept,
            frame.frame.value,
            frame.value,
            frame.change,
            frame.polarity.positive,
        )
        for frame in result.extraction.frames
    } == {("REVENUE", "CHANGE_TO", 6_900_000_000.0, 1.0, False)}
    trace = next(item for item in result.telemetry.clauses if item.reduced_frames)
    assert {
        (edge.concept, edge.role, edge.quantity.value)
        for edge in trace.roles
    } == {
        ("REVENUE", "VALUE_CURRENT", 6_900_000_000.0),
        ("REVENUE", "DELTA", 1.0),
    }
    assert trace.primary_root_cause == "EMITTED"
    assert result.telemetry.role_inference_stage == "PRE_REDUCER"


def test_v291_native_evaluation_counts_role_abstention_as_observable() -> None:
    text = (
        "This sales mix is compared to approximately 90% for disposable protective "
        "garments, 6% for face masks and 4% for face shields."
    )
    result = extract_text_kpis_v291(_doc(text))
    expected = [
        {"concept": "REVENUE", "frame": "COMPOSITION", "value": value}
        for value in (90.0, 6.0, 4.0)
    ]
    block = result.base.candidates[0].block

    row = native_staged_row(
        result,
        block_char_start=block.char_start,
        block_char_end=block.char_end,
        expected_frames=expected,
        candidate_hits=3,
        gold_route="TEXT_IE",
        predicted_table=False,
    )
    summary = summarize_staged_validation([row])

    assert summary["quantity_recall"] == 1.0
    assert summary["binding_recall"] == 1.0
    assert summary["role_recall"] == 0.0
    assert summary["silent_frame_miss"] == 0
    assert summary["abstention_coverage"] == 1.0


def test_v291_candidate_without_recovery_trace_is_an_observable_rejection() -> None:
    result = extract_text_kpis_v291(_doc("Revenue was $10 million."))
    block = result.candidates[0].block
    result_without_trace = replace(
        result,
        telemetry=DocumentSemanticTelemetry(clauses=()),
    )

    row = native_staged_row(
        result_without_trace,
        block_char_start=block.char_start,
        block_char_end=block.char_end,
        expected_frames=[
            {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 10_000_000.0}
        ],
        candidate_hits=1,
        gold_route="TEXT_IE",
        predicted_table=False,
    )

    assert row["rejection_count"] == 1
    assert row["detected_quantities"] == (10_000_000.0,)
    assert row["detected_concepts"] == ("REVENUE",)
    assert row["trace_root_causes"] == ("NO_RECOVERY_TRACE_FOR_CANDIDATE",)


def test_v291_emission_does_not_hide_an_unresolved_binding() -> None:
    result = extract_text_kpis_v291(
        _doc("Revenue was $10 million, up 10% from $9 million last year.")
    )

    trace = next(item for item in result.telemetry.clauses if item.reduced_frames)
    assert len(trace.bindings) == 3
    assert len(trace.roles) == 2
    assert len(trace.unresolved_bindings) == 1
    assert trace.unresolved_bindings[0].quantity.value == 9_000_000.0
    assert trace.primary_root_cause == "PARTIAL_UNRESOLVED_BINDING"


def test_v291_binding_graph_preserves_the_exact_concept_source_span() -> None:
    result = extract_text_kpis_v291(
        _doc("Revenue was $10 million and cash was $10 million.")
    )

    trace = next(item for item in result.telemetry.clauses if item.bindings)
    assert {
        (
            edge.concept,
            edge.concept_char_start,
            edge.concept_char_end,
            edge.quantity.char_start,
            edge.quantity.char_end,
        )
        for edge in trace.bindings
    } == {
        ("REVENUE", 0, 7, 12, 23),
        ("CASH", 28, 32, 37, 48),
    }
    assert {
        (
            edge.concept,
            edge.concept_char_start,
            edge.concept_char_end,
            edge.quantity.char_start,
            edge.quantity.char_end,
        )
        for edge in trace.roles
    } == {
        ("REVENUE", 0, 7, 12, 23),
        ("CASH", 28, 32, 37, 48),
    }


def test_v291_native_stage_gold_scores_repeated_values_by_source_span() -> None:
    text = "Revenue was $10 million and cash was $10 million."
    result = extract_text_kpis_v291(_doc(text))
    block = result.candidates[0].block
    example = StagedGoldExample(
        example_id="B-REPEATED-VALUE-001",
        entity="TEST",
        holdout_axis=HoldoutAxis.ISSUER,
        source_kind="IR",
        source_sha256="a" * 64,
        available_at="2026-09-05",
        document_period="2026Q2",
        text=text,
        gold_route="TEXT_IE",
        quantities=(
            QuantityGoldNode("q1", "MONEY", 10_000_000.0, 12, 23),
            QuantityGoldNode("q2", "MONEY", 10_000_000.0, 37, 48),
        ),
        concepts=(
            ConceptGoldNode("c1", "REVENUE", 0, 7),
            ConceptGoldNode("c2", "CASH", 28, 32),
        ),
        candidate_edges=(StageEdge("c1", "q1"), StageEdge("c2", "q2")),
        binding_edges=(StageEdge("c1", "q1"), StageEdge("c2", "q2")),
        role_edges=(
            RoleGoldEdge("c1", "q1", "VALUE_CURRENT"),
            RoleGoldEdge("c2", "q2", "VALUE_CURRENT"),
        ),
        expected_frames=(
            {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 10_000_000.0},
            {"concept": "CASH", "frame": "ABSOLUTE_VALUE", "value": 10_000_000.0},
        ),
        annotation_source="DOUBLE_REVIEWED_HUMAN",
    )

    row = native_stage_gold_row(
        result,
        example,
        block_char_start=block.char_start,
        block_char_end=block.char_end,
        predicted_table=False,
    )
    summary = summarize_staged_validation([row])

    assert summary["expected_candidates"] == 2
    assert summary["candidate_recall"] == 1.0
    assert summary["quantity_precision"] == 1.0
    assert summary["concept_precision"] == 1.0
    assert summary["binding_precision"] == 1.0
    assert summary["role_precision"] == 1.0
