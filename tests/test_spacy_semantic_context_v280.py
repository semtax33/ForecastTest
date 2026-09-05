from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v280 import extract_text_kpis_v280, route_document_blocks_v280


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v280-semantic-context",
                "V280_SEMANTIC_CONTEXT_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _signatures(text: str):
    result = extract_text_kpis_v280(_document(f"<p>{text}</p>"))
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
        for frame in result.extraction.frames
    }, {candidate.metric.concept for candidate in result.candidates}


def _route(text: str) -> BlockRoute:
    routes = [
        route
        for route in route_document_blocks_v280(_document(f"<p>{text}</p>"))
        if route.char_start is not None
    ]
    assert len(routes) == 1
    return routes[0].route


def test_v280_parallel_operating_income_and_margin_keep_distinct_owners() -> None:
    frames, _ = _signatures(
        "Operating income increased 89.1% to $1.16 billion and operating income "
        "margin expanded approximately 510 basis points to 11.8%."
    )
    assert {frame for frame in frames if frame[0] in {"OPERATING_INCOME", "OPERATING_MARGIN"}} == {
        ("OPERATING_INCOME", "CHANGE_TO", 1_160_000_000.0, 89.1, None, None, True),
        ("OPERATING_MARGIN", "CHANGE_TO", 11.8, 510.0, None, None, True),
    }
    levels, _ = _signatures(
        "Operating income was $690 million and operating income margin was 14.1%."
    )
    assert {frame for frame in levels if frame[0] in {"OPERATING_INCOME", "OPERATING_MARGIN"}} == {
        ("OPERATING_INCOME", "ABSOLUTE_VALUE", 690_000_000.0, None, None, None, True),
        ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 14.1, None, None, None, True),
    }


def test_v280_margin_headline_and_components_respect_include_boundary() -> None:
    frames, _ = _signatures(
        "Gross profit margin increased 850 basis points to 42.9% and included "
        "680 basis points related to the net impact of tariff refunds."
    )
    assert {frame for frame in frames if frame[0] == "GROSS_MARGIN"} == {
        ("GROSS_MARGIN", "CHANGE_TO", 42.9, 850.0, None, None, True),
        ("GROSS_MARGIN", "CHANGE_BY", 680.0, None, None, None, True),
    }
    change_only, _ = _signatures(
        "Adjusted operating income margin expanded 500 basis points including "
        "a 320 basis point benefit related to tariff refunds."
    )
    assert {frame for frame in change_only if frame[0] == "OPERATING_MARGIN"} == {
        ("OPERATING_MARGIN", "CHANGE_BY", 500.0, None, None, None, True),
        ("OPERATING_MARGIN", "CHANGE_BY", 320.0, None, None, None, True),
    }


def test_v280_retail_ticket_and_traffic_are_driver_candidates_and_frames() -> None:
    frames, candidates = _signatures(
        "Comparable store net sales growth included a 3.3% increase in average "
        "ticket and a 0.4% increase in traffic."
    )
    assert {"PRICE_REALIZATION", "ACTIVITY_VOLUME"} <= candidates
    assert {frame for frame in frames if frame[0] in {"PRICE_REALIZATION", "ACTIVITY_VOLUME"}} == {
        ("PRICE_REALIZATION", "CHANGE_BY", 3.3, None, None, None, True),
        ("ACTIVITY_VOLUME", "CHANGE_BY", 0.4, None, None, None, True),
    }
    assert not {frame for frame in frames if frame[0] == "REVENUE"}


def test_v280_bookings_and_book_to_bill_keep_separate_roles() -> None:
    frames, candidates = _signatures(
        "Second quarter net new bookings were $3.15 billion, an increase of 19% "
        "year-over-year, resulting in a book-to-bill ratio of 1.22x."
    )
    assert "ORDERS" in candidates
    assert {frame for frame in frames if frame[0] in {"ORDERS", "BOOK_TO_BILL"}} == {
        ("ORDERS", "CHANGE_TO", 3_150_000_000.0, 19.0, None, None, True),
        ("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.22, None, None, None, True),
    }


def test_v280_adjusted_ebitda_level_and_change_is_change_to() -> None:
    frames, _ = _signatures("Adjusted EBITDA was $994 million, up 9.2% year-over-year.")
    assert {frame for frame in frames if frame[0] == "ADJUSTED_EBITDA"} == {
        ("ADJUSTED_EBITDA", "CHANGE_TO", 994_000_000.0, 9.2, None, None, True)
    }


def test_v280_guidance_midpoint_components_and_growth_ranges() -> None:
    midpoint, _ = _signatures(
        "The new mid-point of the revenue growth guidance is 6.5% versus the prior "
        "guidance of 5.8%, reflecting approximately 100 basis points higher organic "
        "revenue growth, and approximately 50 basis points higher contribution from "
        "acquisitions, partially offset by approximately 80 basis points of foreign "
        "exchange headwind."
    )
    assert {frame for frame in midpoint if frame[0] == "REVENUE_CHANGE_GUIDANCE"} == {
        ("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 6.5, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 100.0, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 50.0, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 80.0, None, None, None, False),
    }
    ranges, _ = _signatures(
        "Comparable store sales are now expected to increase 6% to 7% in the third "
        "quarter and 4% to 5% in the fourth quarter."
    )
    assert {frame for frame in ranges if frame[0] == "REVENUE_CHANGE_GUIDANCE"} == {
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 6.5, None, 6.0, 7.0, True),
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 4.5, None, 4.0, 5.0, True),
    }


def test_v280_future_language_promotes_metric_to_guidance() -> None:
    revenue, _ = _signatures("Revenue is expected to grow 9% year over year.")
    assert {frame for frame in revenue if "REVENUE" in frame[0]} == {
        ("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 9.0, None, None, None, True)
    }
    margin, _ = _signatures(
        "Adjusted operating margin is anticipated to be approximately 44%."
    )
    assert {frame for frame in margin if "OPERATING_MARGIN" in frame[0]} == {
        ("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 44.0, None, None, None, True)
    }


def test_v280_comparatives_emit_current_and_prior_without_cross_binding() -> None:
    income, _ = _signatures(
        "Operating income was $618 million, compared to $783 million in the prior year quarter."
    )
    assert {frame for frame in income if "OPERATING_INCOME" in frame[0]} == {
        ("OPERATING_INCOME", "COMPARATIVE", 618_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 783_000_000.0, None, None, None, True),
    }
    sales, _ = _signatures(
        "For the first six months, sales increased 17% to $12.3 billion, up from "
        "$10.5 billion in 2025."
    )
    assert {frame for frame in sales if "REVENUE" in frame[0]} == {
        ("REVENUE", "COMPARATIVE", 12_300_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 10_500_000_000.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 17.0, None, None, None, True),
    }


def test_v280_prior_period_changes_and_respectively_are_owned() -> None:
    comparable, _ = _signatures(
        "Comparable store sales rose 10% for the quarter on top of a 2% gain last year."
    )
    assert {frame for frame in comparable if "REVENUE" in frame[0]} == {
        ("REVENUE", "CHANGE_BY", 10.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "CHANGE_BY", 2.0, None, None, None, True),
    }
    respectively, _ = _signatures(
        "Revenue and Adjusted Net Income declined 1% and 2%, respectively, on an "
        "organic operational basis."
    )
    assert {frame for frame in respectively if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_BY", 1.0, None, None, None, False)
    }


def test_v280_cash_debt_and_two_metric_levels_are_recovered() -> None:
    cash, _ = _signatures(
        "Balance Sheet Items Unrestricted cash balances as of June 30, 2026 were $3.38 billion."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 3_380_000_000.0, None, None, None, True) in cash
    debt, candidates = _signatures(
        "Short-term and long-term borrowings, net of debt issuance costs, of $4.6 billion."
    )
    assert "DEBT" in candidates
    assert ("DEBT", "ABSOLUTE_VALUE", 4_600_000_000.0, None, None, None, True) in debt
    metrics, _ = _signatures(
        "The company reported total revenues of $4.8 billion and Adjusted EBITDA "
        "of $1.8 billion."
    )
    assert {frame for frame in metrics if frame[0] in {"REVENUE", "ADJUSTED_EBITDA"}} == {
        ("REVENUE", "ABSOLUTE_VALUE", 4_800_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_800_000_000.0, None, None, None, True),
    }


def test_v280_margin_comparison_and_guidance_range_do_not_collapse() -> None:
    comparison, _ = _signatures(
        "Gross profit margin was 33.4%, up 2.7 percentage points versus last year's 30.7%."
    )
    assert {frame for frame in comparison if frame[0] in {"GROSS_MARGIN", "PRIOR_YEAR_GROSS_MARGIN"}} == {
        ("GROSS_MARGIN", "COMPARATIVE", 33.4, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 30.7, None, None, None, True),
        ("GROSS_MARGIN", "CHANGE_BY", 2.7, None, None, None, True),
    }
    guidance, _ = _signatures(
        "Excluding this benefit, operating margin increased by 205 basis points, "
        "above the Company's plan for an increase of 130 to 150 basis points."
    )
    assert {frame for frame in guidance if "OPERATING_MARGIN" in frame[0]} == {
        ("OPERATING_MARGIN", "CHANGE_BY", 205.0, None, None, None, True),
        ("OPERATING_MARGIN_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 140.0, None, 130.0, 150.0, True),
    }


def test_v280_revenue_driver_owner_precedes_driver_metric() -> None:
    frames, _ = _signatures(
        "Year-to-date organic sales increased 0.5 percent, as volume growth of "
        "0.8 percent was partially offset by price-related investments."
    )
    assert {frame for frame in frames if frame[0] in {"REVENUE", "ACTIVITY_VOLUME"}} == {
        ("REVENUE", "CHANGE_BY", 0.5, None, None, None, True),
        ("ACTIVITY_VOLUME", "CHANGE_BY", 0.8, None, None, None, True),
    }


def test_v280_eps_range_after_sales_projection_is_not_revenue() -> None:
    frames, _ = _signatures(
        "If the second half performs in line with these sales projections, our "
        "earnings per share ranges are projected to be $1.75 to $1.83."
    )
    assert not {frame for frame in frames if "REVENUE" in frame[0]}


def test_v280_numeric_prose_and_debt_maturity_sentence_are_not_tables() -> None:
    assert _route(
        "Total debt was $6.5 billion as of June 30, 2026, down from $7.2 billion "
        "as of December 31, 2025."
    ) not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def test_v280_revenue_level_owns_each_reported_and_operational_rate() -> None:
    frames, _ = _signatures(
        "Research Solutions revenue of $4,972 million increased 7.5% on a reported "
        "basis and 6.4% at constant currency."
    )
    assert {frame for frame in frames if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 4_972_000_000.0, 7.5, None, None, True),
        ("REVENUE", "CHANGE_TO", 4_972_000_000.0, 6.4, None, None, True),
    }
    simple, _ = _signatures("Net sales increased 7.1% to $9.9 billion.")
    assert {frame for frame in simple if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 9_900_000_000.0, 7.1, None, None, True)
    }


def test_v280_long_preamble_does_not_steal_revenue_comparison_values() -> None:
    frames, _ = _signatures(
        "Board Increased Stock Repurchase Authorization to $6.0 billion. The company "
        "reported results for the quarter. Net revenue was $3.15 billion, compared "
        "to $3.18 billion in the prior year quarter."
    )
    assert {frame for frame in frames if "REVENUE" in frame[0]} == {
        ("REVENUE", "COMPARATIVE", 3_150_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 3_180_000_000.0, None, None, None, True),
    }


def test_v280_relative_guidance_owns_basis_points_not_benchmark_percent() -> None:
    frames, _ = _signatures(
        "The Company now expects Organic Sales Growth to be approximately 100 basis "
        "points below its weighted average category growth, currently 2% on a trailing basis."
    )
    assert {frame for frame in frames if "REVENUE" in frame[0]} == {
        ("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 100.0, None, None, None, False)
    }


def test_v280_respectively_aligns_prior_margin_charge_and_portfolio_mix() -> None:
    margins, _ = _signatures(
        "Gross margin was 38.3 percent compared to 35.0 percent in the prior year, "
        "inclusive of approximately 50 basis points and approximately 200 basis "
        "points, respectively, of charges."
    )
    assert {frame for frame in margins if "GROSS_MARGIN" in frame[0]} == {
        ("GROSS_MARGIN", "COMPARATIVE", 38.3, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 35.0, None, None, None, True),
        ("GROSS_MARGIN", "CHANGE_BY", 50.0, None, None, None, False),
        ("PRIOR_YEAR_GROSS_MARGIN", "CHANGE_BY", 200.0, None, None, None, False),
    }
    drivers, _ = _signatures(
        "Organic sales increased 2.5 percent led by volume growth and improved "
        "portfolio mix of 2.2 percent and 1.2 percent, respectively."
    )
    assert {frame for frame in drivers if frame[0] in {"REVENUE", "ACTIVITY_VOLUME"}} == {
        ("REVENUE", "CHANGE_BY", 2.5, None, None, None, True),
        ("ACTIVITY_VOLUME", "CHANGE_BY", 2.2, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 1.2, None, None, None, True),
    }


def test_v280_cash_flow_and_maturity_ladder_are_not_balance_sheet_levels() -> None:
    cash_flow, _ = _signatures("Cash flow from operations was $2.6 billion for the fiscal year.")
    assert not {frame for frame in cash_flow if frame[0] == "CASH"}
    maturity, _ = _signatures(
        "Scheduled debt maturities for 2026 through 2030 were $0.9 billion, $2.7 "
        "billion, $3.4 billion, $1.2 billion, and $1.3 billion respectively."
    )
    assert not {frame for frame in maturity if frame[0] == "DEBT"}


def test_v280_margin_direction_is_change_and_ungrounded_traffic_is_not_bound() -> None:
    margin, _ = _signatures("Gross Margin Yields decreased 5.6% as-reported.")
    assert {frame for frame in margin if frame[0] == "GROSS_MARGIN"} == {
        ("GROSS_MARGIN", "CHANGE_BY", 5.6, None, None, None, False)
    }
    sales, _ = _signatures(
        "Total sales increased 13% versus last year, with comparable store sales "
        "up 10%, primarily driven by customer traffic."
    )
    assert {frame for frame in sales if frame[0] in {"REVENUE", "ACTIVITY_VOLUME"}} == {
        ("REVENUE", "CHANGE_BY", 13.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 10.0, None, None, None, True),
    }


def test_v280_ambiguous_multi_segment_range_remains_abstained() -> None:
    frames, _ = _signatures(
        "While sales at Segment A were below our expectations, Segment B, Segment C, "
        "and Segment D all delivered terrific comp sales increases of 6% to 7%."
    )
    assert not {frame for frame in frames if "REVENUE" in frame[0]}
    assert _route(
        "As of June 30, scheduled debt maturities for 2026, 2027, 2028, 2029 and "
        "2030 were $0.9 billion, $2.7 billion, $3.4 billion, $1.2 billion, and "
        "$1.3 billion respectively."
    ) not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
