from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v263 import (
    BlockRoute,
    extract_text_kpis_v263,
    route_document_blocks_v263,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "memory://v263", "V263", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "IR", "EARNINGS_RELEASE", "2026-09-04", "2026Q3"),
    )


def _frames(text: str):
    return extract_text_kpis_v263(_document(text)).extraction.frames


def _signatures(text: str):
    return {
        (frame.concept, frame.frame.value, frame.value, frame.change, frame.polarity.positive)
        for frame in _frames(text)
    }


def test_debt_reduced_by_is_negative_delta_not_level() -> None:
    signatures = _signatures("Total debt was reduced by a record $8.4 billion in the quarter.")
    assert ("DEBT", "CHANGE_BY", 8_400_000_000.0, None, False) in signatures
    assert not any(concept == "DEBT" and frame == "ABSOLUTE_VALUE" for concept, frame, *_ in signatures)


def test_expense_subject_does_not_let_sales_and_marketing_own_values() -> None:
    frames = _frames(
        "Selling, general and administrative costs increased $68 million to $344 million "
        "from $276 million due to higher sales and marketing costs."
    )
    assert not any(frame.concept == "REVENUE" for frame in frames)


def test_causal_revenue_phrase_does_not_steal_operating_income_change() -> None:
    signatures = _signatures(
        "Operating income grew 12%, primarily driven by organic revenue growth and lower expenses."
    )
    assert ("OPERATING_INCOME", "CHANGE_BY", 12.0, None, True) in signatures
    assert not any(concept == "REVENUE" for concept, *_ in signatures)


def test_revenue_attribution_keeps_each_local_direction_without_duplicate_emission() -> None:
    signatures = _signatures(
        "The decrease in advertising revenue was attributable to a decrease of 4% from lower rates, "
        "partially offset by increases of 1% from impressions and 1% from a transaction."
    )
    frames = [frame for frame in _frames(
        "The decrease in advertising revenue was attributable to a decrease of 4% from lower rates, "
        "partially offset by increases of 1% from impressions and 1% from a transaction."
    ) if frame.concept == "REVENUE"]
    assert sum(frame.value == 4.0 and not frame.polarity.positive for frame in frames) == 1
    assert sum(frame.value == 1.0 and frame.polarity.positive for frame in frames) == 1


def test_parenthesized_margin_order_count_and_order_composition() -> None:
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", -0.2, None, False) in _signatures(
        "Operating margin was (0.2) percent in the quarter."
    )
    assert ("ORDERS", "ABSOLUTE_VALUE", 246.0, None, True) in _signatures(
        "Commercial Airplanes booked 246 net orders."
    )
    assert ("ORDERS", "COMPOSITION", 27.0, None, True) in _signatures(
        "Backlog was $85 billion, with 27 percent representing orders from outside the U.S."
    )


def test_guidance_and_respectively_bind_the_right_metric() -> None:
    assert ("OPERATING_INCOME_GUIDANCE", "ABSOLUTE_VALUE", 4_900_000_000.0, None, True) in _signatures(
        "We expect Q4 total segment operating income of approximately $4.9 billion."
    )
    signatures = _signatures(
        "Full-year guidance for cash provided by operations and capital expenditures of at least "
        "$19 billion and approximately $9 billion, respectively."
    )
    assert ("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 9_000_000_000.0, None, True) in signatures


def test_compact_kpi_pairs_bind_level_and_change() -> None:
    assert ("ORDERS", "CHANGE_TO", 16_500_000_000.0, 17.0, True) in _signatures(
        "Total orders of $16.5B, +17%."
    )
    assert ("OPERATING_INCOME", "CHANGE_TO", 2_700_000_000.0, 18.0, True) in _signatures(
        "Profit (GAAP) of $2.8B, +17%; operating profit $2.7B, +18%."
    )


def test_versus_margin_comparisons_emit_each_pair() -> None:
    frames = [frame for frame in _frames(
        "Operating margin was 34.9% versus 34.1% in the prior year, and comparable operating "
        "margin was 35.6% versus 34.7% in the prior year."
    ) if "OPERATING_MARGIN" in frame.concept]
    assert {(frame.concept, frame.value) for frame in frames} == {
        ("OPERATING_MARGIN", 34.9),
        ("PRIOR_YEAR_OPERATING_MARGIN", 34.1),
        ("OPERATING_MARGIN", 35.6),
        ("PRIOR_YEAR_OPERATING_MARGIN", 34.7),
    }


def test_run_on_headline_recovers_revenue_and_operating_income_changes() -> None:
    signatures = _signatures(
        "Net Revenues Grew 7%; Organic Revenues Grew 6% Operating Income Grew 9%; "
        "Comparable Currency Neutral Operating Income Grew 6%."
    )
    assert {item[2] for item in signatures if item[0] == "REVENUE"} == {7.0, 6.0}
    assert {item[2] for item in signatures if item[0] == "OPERATING_INCOME"} == {9.0, 6.0}


def test_table_reconciliation_and_disclaimer_routes_are_distinct() -> None:
    grid = (
        "The following table reconciles expected net income to expected EBIT-adjusted "
        "(dollars in billions): Updated Previous Net income $8.4-9.8 $9.9-11.4 "
        "EBIT-adjusted $14.0-16.0 $13.5-15.5"
    )
    assert any(route.route is BlockRoute.FLATTENED_TABLE for route in route_document_blocks_v263(_document(grid)))
    disclaimer = (
        "The company is not able to reconcile projected organic revenues to projected reported "
        "net revenues without unreasonable efforts because exact timing cannot be predicted."
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v263(_document(disclaimer))
    )
