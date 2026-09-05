from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v289 import extract_text_kpis_v289, route_document_blocks_v289
from equity_platform.text_ie.v289.semantics import V289_RULES


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "test://v289", "V289", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v289(_doc(text))
    return {
        (f.concept, f.frame.value, f.value, f.change, f.lower_value, f.upper_value, f.polarity.positive)
        for f in result.extraction.frames
    }


def test_v289_dsl_operations_compile_as_issuer_neutral_pure_steps() -> None:
    operations = {operation for rule in V289_RULES for operation in rule.operations}
    assert {"bind_labeled_roles", "require_same_clause", "derive_relative_range", "emit_each_value"} <= operations
    assert all("issuer" not in operation for operation in operations)


def test_v289_to_value_wins_over_from_comparator() -> None:
    assert _frames("Net revenues decreased by 14.3% to $2.4 million from $2.8 million.") == {
        ("REVENUE", "CHANGE_TO", 2_400_000.0, 14.3, None, None, False),
    }
    assert _frames("Net revenues increased by 2.0% to $5.2 million from $5.1 million.") == {
        ("REVENUE", "CHANGE_TO", 5_200_000.0, 2.0, None, None, True),
    }


def test_v289_comparative_margin_and_operating_income() -> None:
    assert _frames("Gross profit margin was 50.0%, compared with 53.6% last year.") == {
        ("GROSS_MARGIN", "COMPARATIVE", 50.0, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 53.6, None, None, None, True),
    }
    assert _frames("Operating loss was $0.6 million compared to $26.2 million last year.") == {
        ("OPERATING_INCOME", "COMPARATIVE", 600_000.0, None, None, None, False),
        ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 26_200_000.0, None, None, None, False),
    }
    assert _frames("Gross profit margin expanded to 55.8% from 54.9%.") == {
        ("GROSS_MARGIN", "COMPARATIVE", 55.8, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 54.9, None, None, None, True),
    }


def test_v289_nearest_metric_prevents_cogs_revenue_false_positive() -> None:
    assert _frames("COGS increased $4.8 million, or 22%, reflecting product volumes on which revenue was recognized.") == set()
    assert _frames("The Company generated $4.4 million of cash from operating activities during the period.") == set()


def test_v289_local_absolute_and_change_roles() -> None:
    assert _frames("We eliminated approximately $282 million of debt.") == {
        ("DEBT", "CHANGE_BY", 282_000_000.0, None, None, None, False),
    }
    assert _frames("Cash at June 30, 2026 was $778.4 million, excluding restricted cash of $41.1 million.") == {
        ("CASH", "ABSOLUTE_VALUE", 778_400_000.0, None, None, None, True),
    }
    assert _frames("Attendance rose 17.9%, and Adjusted EBITDA climbed by 336.7%.") == {
        ("ADJUSTED_EBITDA", "CHANGE_BY", 336.7, None, None, None, True),
    }
    assert _frames("The Company expects cash to grow by approximately 10% as of December 31, 2026 compared to December 31, 2025.") == {
        ("CASH", "CHANGE_BY", 10.0, None, None, None, True),
    }


def test_v289_change_amount_and_current_principal_are_separate_roles() -> None:
    assert _frames("Revenues increased by $3,000 to $6,565,000 compared to $6,562,000 last year.") == {
        ("REVENUE", "CHANGE_TO", 6_565_000.0, 3_000.0, None, None, True),
    }
    assert _frames("Cash and cash equivalents were $301.1 million, up by $112.4 million, or 59.6%, compared to $188.7 million.") == {
        ("CASH", "CHANGE_TO", 301_100_000.0, 59.6, None, None, True),
    }


def test_v289_parallel_ratio_metrics_bind_to_their_own_values() -> None:
    assert _frames("Net leverage consisted of $3,875 million of total debt less $459 million of cash and cash equivalents, divided by Adjusted EBITDA of $1,128 million.") == {
        ("DEBT", "ABSOLUTE_VALUE", 3_875_000_000.0, None, None, None, True),
        ("CASH", "ABSOLUTE_VALUE", 459_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_128_000_000.0, None, None, None, True),
    }


def test_v289_bullets_are_independent_semantic_clauses() -> None:
    text = (
        "Highlights ● Revenue increased 19% to $8.4 million, compared with $7.1 million. "
        "● Services revenue increased 40% to $4.9 million. "
        "● Cash and cash equivalents increased to $6.8 million, compared with $3.7 million."
    )
    assert _frames(text) == {
        ("REVENUE", "CHANGE_TO", 8_400_000.0, 19.0, None, None, True),
        ("REVENUE", "CHANGE_TO", 4_900_000.0, 40.0, None, None, True),
        ("CASH", "COMPARATIVE", 6_800_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 3_700_000.0, None, None, None, True),
    }
    assert _frames("Cash, cash equivalents and restricted cash increased to $6.8 million, compared with $3.7 million.") == {
        ("CASH", "COMPARATIVE", 6_800_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 3_700_000.0, None, None, None, True),
    }


def test_v289_orders_falling_sales_and_segment_growth() -> None:
    assert _frames("Reported total orders above $130 million.") == {
        ("ORDERS", "ABSOLUTE_VALUE", 130_000_000.0, None, None, None, True),
    }
    assert _frames("Biodiesel sales fell to $2.5 million during the quarter.") == {
        ("REVENUE", "ABSOLUTE_VALUE", 2_500_000.0, None, None, None, False),
    }
    assert _frames("Global Engineering Solutions revenues decreased 5% year-over-year.") == {
        ("REVENUE", "CHANGE_BY", 5.0, None, None, None, False),
    }


def test_v289_forward_ranges_require_local_metric_ownership() -> None:
    assert _frames("Q3 revenue in the range of $46 million to $48 million.") == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 47_000_000.0, None, 46_000_000.0, 48_000_000.0, True),
    }
    assert _frames("Adjusted EBITDA in the range between ($9) million to ($7) million.") == {
        ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 8_000_000.0, None, 7_000_000.0, 9_000_000.0, False),
    }


def test_v289_headline_is_prose_but_numeric_header_fragment_is_table() -> None:
    headline = "Document Exhibit 99.1 Company Reports Results Revenues of $3.5 billion; Adjusted EBITDA of $290 million; Backlog of $48.2 billion; Book-to-Bill of 1.1x, LTM 1.3x."
    routes = {route.route for route in route_document_blocks_v289(_doc(headline)) if route.char_start is not None}
    assert routes.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    assert _frames(headline) == {
        ("REVENUE", "ABSOLUTE_VALUE", 3_500_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 290_000_000.0, None, None, None, True),
        ("BACKLOG", "ABSOLUTE_VALUE", 48_200_000_000.0, None, None, None, True),
        ("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.1, None, None, None, True),
        ("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.3, None, None, None, True),
    }

    header = "Financial Performance Comparisons Revenues ($ in millions) Q2 2026 Q2 2025 % Change 1H 2026 1H 2025 % Change Product Revenue, net"
    routes = {route.route for route in route_document_blocks_v289(_doc(header)) if route.char_start is not None}
    assert routes & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
