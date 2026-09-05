from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v279 import extract_text_kpis_v279, route_document_blocks_v279


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v279-semantic-ownership",
                "V279_SEMANTIC_OWNERSHIP_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _signatures(text: str):
    return {
        (
            frame.concept,
            frame.frame.value,
            frame.value,
            frame.change,
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
        )
        for frame in extract_text_kpis_v279(_document(f"<p>{text}</p>")).extraction.frames
    }


def _route(text: str) -> BlockRoute:
    routes = [
        route
        for route in route_document_blocks_v279(_document(f"<p>{text}</p>"))
        if route.char_start is not None
    ]
    assert len(routes) == 1
    return routes[0].route


def test_v279_each_revenue_clause_owns_its_level_and_parallel_rates() -> None:
    frames = _signatures(
        "Global net revenues from the aesthetics portfolio were $1.282 billion, "
        "an increase of 0.3 percent on a reported basis, or a decrease of 0.9 "
        "percent on an operational basis. ◦ Global Botox Cosmetic net revenues "
        "were $728 million, an increase of 5.2 percent on a reported basis, or "
        "3.4 percent on an operational basis. ◦ Global Juvederm net revenues "
        "were $245 million, a decrease of 6.0 percent on a reported basis, or "
        "6.6 percent on an operational basis."
    )
    assert {frame for frame in frames if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 1_282_000_000.0, 0.3, None, None, True),
        ("REVENUE", "CHANGE_TO", 1_282_000_000.0, 0.9, None, None, False),
        ("REVENUE", "CHANGE_TO", 728_000_000.0, 5.2, None, None, True),
        ("REVENUE", "CHANGE_TO", 728_000_000.0, 3.4, None, None, True),
        ("REVENUE", "CHANGE_TO", 245_000_000.0, 6.0, None, None, False),
        ("REVENUE", "CHANGE_TO", 245_000_000.0, 6.6, None, None, False),
    }


def test_v279_semicolon_revenue_highlights_keep_levels_and_first_item_rates() -> None:
    frames = _signatures(
        "Second-Quarter Global Net Revenues from the Immunology Portfolio Were "
        "$8.786 Billion, an Increase of 15.1 Percent on a Reported Basis, or "
        "14.6 Percent on an Operational Basis; Global Skyrizi Net Revenues Were "
        "$5.505 Billion; Global Rinvoq Net Revenues Were $2.525 Billion; Global "
        "Humira Net Revenues Were $756 Million."
    )
    assert {frame for frame in frames if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 8_786_000_000.0, 15.1, None, None, True),
        ("REVENUE", "CHANGE_TO", 8_786_000_000.0, 14.6, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 5_505_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 2_525_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 756_000_000.0, None, None, None, True),
    }


def test_v279_record_revenue_and_forward_range_have_canonical_frames() -> None:
    actual = _signatures(
        "Record Traditional Servers and Networking revenue: $8.5 billion, up "
        "92% year over year."
    )
    assert {frame for frame in actual if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 8_500_000_000.0, 92.0, None, None, True)
    }

    guidance = _signatures(
        "Full-year FY27 revenue expected between $165.0 billion and $169.0 "
        "billion, up 47% year over year at the midpoint of $167.0 billion."
    )
    assert {frame for frame in guidance if "REVENUE" in frame[0]} == {
        (
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            167_000_000_000.0,
            None,
            165_000_000_000.0,
            169_000_000_000.0,
            True,
        ),
        (
            "REVENUE_CHANGE_GUIDANCE",
            "ABSOLUTE_VALUE",
            47.0,
            None,
            None,
            None,
            True,
        ),
    }


def test_v279_amount_before_metric_ownership_separates_orders_and_revenue() -> None:
    frames = _signatures(
        "We booked $24.4 billion in AI orders and recognized $16.1 billion of "
        "AI server revenue."
    )
    assert {frame for frame in frames if frame[0] in {"ORDERS", "REVENUE"}} == {
        ("ORDERS", "ABSOLUTE_VALUE", 24_400_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 16_100_000_000.0, None, None, None, True),
    }


def test_v279_revenue_bridge_components_retain_their_own_concepts() -> None:
    points = _signatures(
        "Net sales were up 1 percent to $4.6 billion, including a 7-point benefit "
        "from the 53rd week, a 1-point benefit from foreign currency exchange, "
        "and a 7-point headwind from the net impact of divestitures and acquisitions."
    )
    assert {frame for frame in points if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 4_600_000_000.0, 1.0, None, None, True),
        ("REVENUE", "CHANGE_BY", 7.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 1.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 7.0, None, None, None, False),
    }

    drivers = _signatures(
        "Legacy KDP net sales increased 7.3%, driven by favorable net price "
        "realization of 4.2% and volume/mix growth of 3.1%."
    )
    assert {frame for frame in drivers if frame[0] in {"REVENUE", "PRICE_REALIZATION", "ACTIVITY_VOLUME"}} == {
        ("REVENUE", "CHANGE_BY", 7.3, None, None, None, True),
        ("PRICE_REALIZATION", "CHANGE_BY", 4.2, None, None, None, True),
        ("ACTIVITY_VOLUME", "CHANGE_BY", 3.1, None, None, None, True),
    }


def test_v279_operating_profit_and_unchanged_revenue_guidance() -> None:
    profit = _signatures("Operating profit of $886 million was down 73 percent.")
    assert {frame for frame in profit if frame[0] == "OPERATING_INCOME"} == {
        (
            "OPERATING_INCOME",
            "CHANGE_TO",
            886_000_000.0,
            73.0,
            None,
            None,
            False,
        )
    }
    guidance = _signatures(
        "Premium revenue guidance for the full year is unchanged at approximately "
        "$42 billion."
    )
    assert (
        "REVENUE_GUIDANCE",
        "ABSOLUTE_VALUE",
        42_000_000_000.0,
        None,
        None,
        None,
        True,
    ) in guidance

    growth = _signatures(
        "The net impact of divestitures, foreign currency exchange, and the 53rd "
        "week is expected to reduce full-year reported net sales growth by "
        "approximately 2 percent."
    )
    assert {frame for frame in growth if "REVENUE" in frame[0]} == {
        (
            "REVENUE_CHANGE_GUIDANCE",
            "ABSOLUTE_VALUE",
            2.0,
            None,
            None,
            None,
            False,
        )
    }


def test_v279_cash_comparison_and_level_change_exclude_cash_flow_driver() -> None:
    comparison = _signatures(
        "Cash and investments at the parent company were approximately $290 "
        "million as of June 30, 2026, compared to $223 million as of December "
        "31, 2025."
    )
    assert {frame for frame in comparison if "CASH" in frame[0]} == {
        ("CASH", "COMPARATIVE", 290_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 223_000_000.0, None, None, None, True),
    }
    change = _signatures(
        "Cash and equivalents and short-term investments were $9.0 billion, down "
        "approximately $0.1 billion from last year, as cash generated from operations, "
        "which includes approximately $0.3 billion of cash received from tariff "
        "recoveries, was more than offset by dividends and capital expenditures."
    )
    assert {frame for frame in change if frame[0] == "CASH"} == {
        (
            "CASH",
            "CHANGE_TO",
            9_000_000_000.0,
            100_000_000.0,
            None,
            None,
            False,
        )
    }


def test_v279_margin_level_change_and_driver_are_not_cross_bound() -> None:
    gross = _signatures(
        "Gross margin for the fourth quarter increased 890 basis points to 49.2 "
        "percent, including an approximately 900 basis point benefit due to tariff recovery."
    )
    assert {frame for frame in gross if frame[0] == "GROSS_MARGIN"} == {
        ("GROSS_MARGIN", "CHANGE_TO", 49.2, 890.0, None, None, True),
        ("GROSS_MARGIN", "CHANGE_BY", 900.0, None, None, None, True),
    }
    operating = _signatures(
        "Production Systems pretax operating margin was 16%, expanding 138 bps sequentially."
    )
    assert {frame for frame in operating if frame[0] == "OPERATING_MARGIN"} == {
        ("OPERATING_MARGIN", "CHANGE_TO", 16.0, 138.0, None, None, True)
    }


def test_v279_margin_comparison_and_two_highlights_are_canonical() -> None:
    comparison = _signatures(
        "Operating margin of 19.1% expanded from 13.6% in the prior year."
    )
    assert {frame for frame in comparison if "OPERATING_MARGIN" in frame[0]} == {
        ("OPERATING_MARGIN", "COMPARATIVE", 19.1, None, None, None, True),
        ("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 13.6, None, None, None, True),
    }
    highlights = _signatures(
        "GAAP operating margin expanded 60 basis points year-over-year to 10.5%, "
        "primarily driven by sales leverage. Non-GAAP operating margin expanded "
        "430 basis points year-over-year to 14.4%."
    )
    assert {frame for frame in highlights if frame[0] == "OPERATING_MARGIN"} == {
        ("OPERATING_MARGIN", "CHANGE_TO", 10.5, 60.0, None, None, True),
        ("OPERATING_MARGIN", "CHANGE_TO", 14.4, 430.0, None, None, True),
    }


def test_v279_routes_reconciliations_but_not_header_only_fragments() -> None:
    assert _route(
        "The impact of specified items by line item was as follows: Six Months "
        "Ended June 30, 2025 (in millions) Cost of products sold SG&A R&D Other "
        "operating income Other expense, net As reported (GAAP) $8,348 $6,546 "
        "$4,198 $(24) $4,107 Adjusted for specified items: amortization "
        "$(3,722) other $(97) $(27) $(32) $24 $(21) As adjusted $4,529 $6,519 $4,166."
    ) in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert _route(
        "Segment Information (in millions; unaudited) Three Months Ended May 1, "
        "2026 May 2, 2025 Reconciliation to consolidated net revenue: Reportable "
        "segment net revenue $43,618 $22,826 Corporate and other $224 $552 Total "
        "consolidated net revenue $43,842 $23,378 Reconciliation to consolidated "
        "operating income: Reportable segment operating income $4,225 $1,651."
    ) in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert _route(
        "RECONCILIATION OF GAAP TO NON-GAAP INFORMATION CHANGE IN NET SALES AND "
        "OPERATING MARGIN - CONSOLIDATED AND SEGMENTS (UNAUDITED) Reported Impact "
        "of Foreign Currency Constant Currency First Six Months of 2026 Change in net sales U."
    ) not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
