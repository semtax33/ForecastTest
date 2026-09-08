from equity_platform.text_ie.training import (
    SpanEvaluationExample,
    SpanSafetyGateInput,
    assess_span_safety_gate,
    evaluate_exact_spans,
)


def test_exact_span_evaluation_counts_false_positives_and_false_negatives() -> None:
    metrics = evaluate_exact_spans((
        SpanEvaluationExample(
            example_id="sec-1",
            source_slice="SEC_10Q",
            gold_spans=((0, 7), (20, 26)),
            predicted_spans=((0, 7), (30, 35)),
        ),
        SpanEvaluationExample(
            example_id="ir-1",
            source_slice="IR_QA",
            gold_spans=((4, 10),),
            predicted_spans=((4, 10),),
        ),
    ))

    assert (metrics.true_positive, metrics.false_positive, metrics.false_negative) == (2, 1, 1)
    assert metrics.precision == 2 / 3
    assert metrics.recall == 2 / 3
    assert set(metrics.by_source_slice) == {"SEC_10Q", "IR_QA"}


def test_span_safety_gate_prioritizes_semantics_over_ner_recall() -> None:
    result = assess_span_safety_gate(SpanSafetyGateInput(
        period_accuracy=1.0,
        unit_accuracy=1.0,
        binding_precision=0.995,
        guidance_actual_accuracy=1.0,
        scope_accuracy=1.0,
        span_recall=0.95,
        explicit_abstention_rate=0.30,
        silent_miss_count=0,
    ))

    assert result.passed
    assert result.reasons == ()


def test_span_safety_gate_fails_closed_on_period_binding_or_silent_miss() -> None:
    result = assess_span_safety_gate(SpanSafetyGateInput(
        period_accuracy=0.99,
        unit_accuracy=1.0,
        binding_precision=0.98,
        guidance_actual_accuracy=1.0,
        scope_accuracy=1.0,
        span_recall=0.99,
        explicit_abstention_rate=0.0,
        silent_miss_count=1,
    ))

    assert not result.passed
    assert result.reasons == (
        "PERIOD_ACCURACY_BELOW_100_PERCENT",
        "LOW_BINDING_PRECISION",
        "SILENT_MISS",
    )


def test_low_span_recall_is_reported_only_after_semantic_checks() -> None:
    result = assess_span_safety_gate(SpanSafetyGateInput(
        period_accuracy=1.0,
        unit_accuracy=1.0,
        binding_precision=1.0,
        guidance_actual_accuracy=1.0,
        scope_accuracy=1.0,
        span_recall=0.60,
        explicit_abstention_rate=0.40,
        silent_miss_count=0,
    ))

    assert not result.passed
    assert result.reasons == ("LOW_SPAN_RECALL",)
