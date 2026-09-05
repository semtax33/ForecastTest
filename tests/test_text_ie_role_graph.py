from __future__ import annotations

from equity_platform.text_ie.model import QuantityKind, QuantityMention, SemanticFrame
from equity_platform.text_ie.role_graph import (
    SemanticRole,
    build_frame_role_intent,
    materialize_role_intent,
)


def _money(value: float, start: int) -> QuantityMention:
    return QuantityMention(
        QuantityKind.MONEY,
        value,
        "USD",
        str(value),
        start,
        start + 3,
    )


def test_range_role_intent_keeps_only_observed_endpoints() -> None:
    low = _money(285_000_000.0, 0)
    high = _money(300_000_000.0, 10)

    intent = build_frame_role_intent(
        concept="CAPEX_GUIDANCE",
        semantic=SemanticFrame.RANGE_GUIDANCE,
        lower=low,
        upper=high,
    )

    assert [(item.role, item.quantity) for item in intent.assignments] == [
        (SemanticRole.GUIDANCE_LOW, low),
        (SemanticRole.GUIDANCE_HIGH, high),
    ]

    materialized = materialize_role_intent(intent)
    assert materialized.value.value == 292_500_000.0
    assert materialized.value.raw == low.raw
    assert materialized.lower is low
    assert materialized.upper is high


def test_change_to_role_intent_is_independent_of_frame_materialization() -> None:
    current = _money(6_900_000_000.0, 0)
    delta = QuantityMention(
        QuantityKind.PERCENT,
        1.0,
        "PERCENT",
        "1%",
        20,
        22,
    )

    intent = build_frame_role_intent(
        concept="REVENUE",
        semantic=SemanticFrame.CHANGE_TO,
        value=current,
        change=delta,
        positive=False,
    )

    assert [(item.role, item.quantity) for item in intent.assignments] == [
        (SemanticRole.VALUE_CURRENT, current),
        (SemanticRole.DELTA, delta),
    ]
    assert materialize_role_intent(intent).positive is False
