from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v290 import extract_text_kpis_v290, route_document_blocks_v290
from equity_platform.text_ie.v290.semantics import semantic_concepts_v290


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "test://v290", "V290", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v290(_doc(text))
    return {
        (f.concept, f.frame.value, f.value, f.change, f.lower_value, f.upper_value, f.polarity.positive)
        for f in result.extraction.frames
    }


def _concepts(text: str) -> set[str]:
    return {mention.concept for mention in semantic_concepts_v290(text)}


def test_v290_red_candidate_aliases_cover_industry_activity_and_margin() -> None:
    assert {"REVENUE", "ACTIVITY_VOLUME"} <= _concepts(
        "These acquisitions represent $600 million in annual revenue and 9,700 retail vehicle annual unit sales."
    )
    assert "SHARES" in _concepts("A 6% reduction of shares was completed.")
    assert "OPERATING_MARGIN" in _concepts("The company is delivering an EBIT margin greater than 95%.")
    assert "ACTIVITY_VOLUME" in _concepts("Paying memberships grew 99.2% year over year.")
    assert "ACTIVITY_VOLUME" in _concepts("The company owned 216 hotels with 29,459 guest rooms.")


def test_v290_red_excludes_non_cash_expense_and_sales_price_homonyms() -> None:
    assert _frames("R&D non-cash stock-based compensation expense was $4.6 million compared to $4.4 million.") == set()
    assert _frames("Sales and marketing expense was $61.1 million compared to $61.5 million last year.") == set()
    assert _frames("The company generated $17.5 million of cash from operations.") == set()
    assert _frames("The company sold a hotel for a gross sales price of $8.7 million.") == set()
    assert _frames("Based in Italy and with annual sales of approximately $150 million, El operates globally.") == set()


def test_v290_red_postpositive_cash_and_liquidity_ownership() -> None:
    assert _frames(
        "The company had $1.0 billion of liquidity, including $53 million in cash and $0.9 billion of availability under its revolving credit facility."
    ) == {
        ("CASH", "ABSOLUTE_VALUE", 53_000_000.0, None, None, None, True),
    }


def test_v290_red_compatible_quantity_kind_and_metric_scope_beat_distance() -> None:
    assert _frames(
        "These acquisitions represent $600 million in annual revenue and 9,700 retail new and used vehicle annual unit sales."
    ) == {
        ("REVENUE", "ABSOLUTE_VALUE", 600_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 9_700.0, None, None, None, True),
    }
    assert _frames(
        "First half share repurchases of $457 million, 6% reduction of shares. The company reported revenue of $6.9 billion, a decrease of 1% compared to last year."
    ) == {
        ("SHARES", "CHANGE_BY", 6.0, None, None, None, False),
        ("REVENUE", "CHANGE_TO", 6_900_000_000.0, 1.0, None, None, False),
    }
    assert _frames(
        "The company had $360.2 million in cash, $274.5 million in accounts receivable and $620.9 million in principal value of outstanding debt."
    ) == {
        ("CASH", "ABSOLUTE_VALUE", 360_200_000.0, None, None, None, True),
        ("DEBT", "ABSOLUTE_VALUE", 620_900_000.0, None, None, None, True),
    }


def test_v290_red_change_to_precedes_comparison_when_change_is_explicit() -> None:
    cases = {
        "Revenue was $6.9 billion, a decrease of 1% compared to last year.": (
            "REVENUE", "CHANGE_TO", 6_900_000_000.0, 1.0, None, None, False
        ),
        "Revenue was $217.7 million, up 23.7% from $176.0 million in the prior-year quarter.": (
            "REVENUE", "CHANGE_TO", 217_700_000.0, 23.7, None, None, True
        ),
        "Net sales were $150.0 million, an 18.4% increase from $126.7 million in the prior year.": (
            "REVENUE", "CHANGE_TO", 150_000_000.0, 18.4, None, None, True
        ),
        "Sales of $8.8 billion were up 55% year over year.": (
            "REVENUE", "CHANGE_TO", 8_800_000_000.0, 55.0, None, None, True
        ),
    }
    for text, expected in cases.items():
        assert _frames(text) == {expected}


def test_v290_red_from_to_order_and_dollar_change_roles() -> None:
    assert _frames("Royalties increased 44% from $17.2 million to $24.7 million.") == {
        ("REVENUE", "CHANGE_TO", 24_700_000.0, 44.0, None, None, True),
    }
    assert _frames(
        "Cash and investments totaled $286.5 million, compared to $311.6 million, for a decrease of $25.1 million."
    ) == {
        ("CASH", "CHANGE_TO", 286_500_000.0, 25_100_000.0, None, None, False),
    }
    assert _frames("The midpoint of anticipated capital expenditures increased by $5.0 million.") == {
        ("CAPEX", "CHANGE_BY", 5_000_000.0, None, None, None, True),
    }


def test_v290_red_adjusted_ebitda_and_multi_period_comparisons() -> None:
    assert _frames("Adjusted EBITDA was $53 million, compared to $46 million in 2025.") == {
        ("ADJUSTED_EBITDA", "COMPARATIVE", 53_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 46_000_000.0, None, None, None, True),
    }
    assert _frames("Adjusted EBITDA loss was $7.7 million, compared to a loss of $46.2 million last year.") == {
        ("ADJUSTED_EBITDA", "COMPARATIVE", 7_700_000.0, None, None, None, False),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 46_200_000.0, None, None, None, False),
    }
    assert _frames("Cash was $48.0 million, compared to $44.1 million and $28.0 million at the dated prior periods.") == {
        ("CASH", "COMPARATIVE", 48_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 44_100_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 28_000_000.0, None, None, None, True),
    }


def test_v290_red_basis_point_change_and_multi_value_revenue_roles() -> None:
    assert _frames("Gross margin was 54.0%, 130 basis points higher than last year.") == {
        ("GROSS_MARGIN", "CHANGE_TO", 54.0, 130.0, None, None, True),
    }
    assert _frames(
        "NanoKnife sales were $11.8 million, an increase of 64.5%, including 47.0% growth in probes and 132.5% growth in capital sales."
    ) == {
        ("REVENUE", "CHANGE_TO", 11_800_000.0, 64.5, None, None, True),
        ("REVENUE", "CHANGE_BY", 47.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 132.5, None, None, None, True),
    }
    assert _frames("Net revenues include $8.0 million of milestones and royalties of $9.7 million.") == {
        ("REVENUE", "ABSOLUTE_VALUE", 8_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 9_700_000.0, None, None, None, True),
    }


def test_v290_red_composition_and_parenthesized_percent() -> None:
    assert _frames("Med Tech represented 47% of total revenue, up approximately 22% from 2020.") == {
        ("REVENUE", "COMPOSITION", 47.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 22.0, None, None, None, True),
    }
    assert _frames("Revenue decreased (11)% year over year.") == {
        ("REVENUE", "CHANGE_BY", 11.0, None, None, None, False),
    }


def test_v290_red_guidance_ranges_are_owned_per_metric() -> None:
    assert _frames("We reaffirm full year revenue guidance of $1,080 - $1,140 million and adjusted non-GAAP EBITDA of $285 - $300 million.") == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 1_110_000_000.0, None, 1_080_000_000.0, 1_140_000_000.0, True),
        ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 292_500_000.0, None, 285_000_000.0, 300_000_000.0, True),
    }
    assert _frames("We expect more than $390 million of annualized royalties payable to us at a partner's peak sales guidance of $2.7 billion.") == {
        ("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 390_000_000.0, None, None, None, True),
    }


def test_v290_red_activity_counts_and_changes() -> None:
    assert _frames("Paying memberships grew 99.2% year over year.") == {
        ("ACTIVITY_VOLUME", "CHANGE_BY", 99.2, None, None, None, True),
    }
    assert _frames("Revenue growth was driven by 99.2% year-over-year growth in paying memberships.") == {
        ("ACTIVITY_VOLUME", "CHANGE_BY", 99.2, None, None, None, True),
    }
    assert _frames("Guild membership grew to 390,000 from 230,000 members, a 69.6% increase.") == {
        ("ACTIVITY_VOLUME", "CHANGE_TO", 390_000.0, 69.6, None, None, True),
    }
    assert _frames("The company owned 216 hotels with an aggregate of 29,459 guest rooms.") == {
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 216.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 29_459.0, None, None, None, True),
    }
    assert _frames("As of June 30, 2026, the company owned 216 hotels with 29,459 guest rooms in 83 markets across 37 states.") == {
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 216.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 29_459.0, None, None, None, True),
    }
    mixed = (
        "Membership grew to 390,000 from 230,000 members, a 69.6% increase. ● "
        "Selling and marketing expense was 52.8% of revenue compared to 71.6%, reflecting efficiency in retaining members."
    )
    assert _frames(mixed) == {
        ("ACTIVITY_VOLUME", "CHANGE_TO", 390_000.0, 69.6, None, None, True),
    }


def test_v290_red_excluded_share_counts_and_expense_revenue_are_suppressed() -> None:
    assert _frames("Therefore 340,000 shares and 345,000 shares have been excluded from the calculation of adjusted weighted-average shares outstanding.") == set()
    assert _frames("Total operating expenses, excluding cost of revenues, were $78.5 million compared to $81.7 million.") == set()
    assert _frames("Sales and marketing was $61.1 million compared to $61.5 million on a higher revenue base.") == set()
    assert _frames(
        "Guild selling and marketing expense was 52.8% of Guild revenue in Q2 2026, compared to 71.6% in Q2 2025, "
        "reflecting improved efficiency in acquiring and retaining members as the Guild scales."
    ) == set()


def test_v290_red_revpar_is_a_revenue_driver() -> None:
    assert _frames("Comparable Hotels RevPAR growth was more than 5% for the second quarter.") == {
        ("REVENUE", "CHANGE_BY", 5.0, None, None, None, True),
    }


def test_v290_red_router_distinguishes_narrative_and_flattened_tables() -> None:
    narrative = (
        "Capital Allocation, Liquidity, and Leverage For the first six months ended June 30, 2026, cash used in operating activities was "
        "$48.9 million, auto loans receivable, net, increased $493.6 million, capital expenditures were $126.0 million, "
        "and adjusted free cash flow was $439.2 million, or 125% of adjusted net income."
    )
    routes = {route.route for route in route_document_blocks_v290(_doc(narrative)) if route.char_start is not None}
    assert routes.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})

    statements = (
        "CONSOLIDATED STATEMENT OF OPERATIONS (Unaudited) Three Months Ended June 30, 2026 2025 (In thousands) "
        "Revenue $248,003 $278,221 Cost of revenue 11,669 13,142 Gross profit 236,334 265,079 Operating expenses "
        "142,256 139,453 Operating income (233,749) 17,673 Net income (230,667) 10,897"
    )
    routes = {route.route for route in route_document_blocks_v290(_doc(statements)) if route.char_start is not None}
    assert routes & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}

    header = "GAAP financial measures for the periods presented: NET SALES Percentage Growth relative to prior period Net sales Foreign Constant Currency Organic Acquisition Net Sales"
    routes = {route.route for route in route_document_blocks_v290(_doc(header)) if route.char_start is not None}
    assert routes & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def test_v290_regression_role_graph_preserves_prior_disclosed_semantics() -> None:
    assert _frames("First half gross profit margin expanded to 55.8% from 54.9%.") == {
        ("GROSS_MARGIN", "COMPARATIVE", 55.8, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 54.9, None, None, None, True),
    }
    assert _frames(
        "We raised approximately $285 million through equity offerings, and eliminated approximately $282 million of debt."
    ) == {
        ("DEBT", "CHANGE_BY", 282_000_000.0, None, None, None, False),
    }
    assert _frames("Cash was $778.4 million, excluding restricted cash of $41.1 million.") == {
        ("CASH", "ABSOLUTE_VALUE", 778_400_000.0, None, None, None, True),
    }
    assert _frames(
        "Cash, cash equivalents and restricted cash increased to $6.8 million, compared with $3.7 million last year."
    ) == {
        ("CASH", "COMPARATIVE", 6_800_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 3_700_000.0, None, None, None, True),
    }
    assert _frames(
        "Cash and investments totaled $286.5 million, compared to $311.6 million, for a decrease of $25.1 million "
        "due primarily to operating activities offset by $14.0 million received from stock option exercises."
    ) == {
        ("CASH", "CHANGE_TO", 286_500_000.0, 25_100_000.0, None, None, False),
    }
    assert _frames(
        "Net revenues from Brand royalties and other revenues include $8.0 million of revenue recognized toward "
        "milestones and royalties of approximately $9.7 million, related to the agreement."
    ) == {
        ("REVENUE", "ABSOLUTE_VALUE", 8_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 9_700_000.0, None, None, None, True),
    }
    assert _frames("Attendance was up 17.9%, and Adjusted EBITDA climbed by 336.7%.") == {
        ("ADJUSTED_EBITDA", "CHANGE_BY", 336.7, None, None, None, True),
    }
    assert _frames(
        "COGS increased $4.8 million, or 22%, reflecting increased product volumes on which revenue was recognized."
    ) == set()
    assert _frames(
        "Revenues from the leasing segment increased by $3,000 to $6,565,000 compared to $6,562,000 in the prior year."
    ) == {
        ("REVENUE", "CHANGE_TO", 6_565_000.0, 3_000.0, None, None, True),
    }
    assert _frames("International revenue increased 56% during the period to $2.7 million as treatment volumes increased.") == {
        ("REVENUE", "CHANGE_TO", 2_700_000.0, 56.0, None, None, True),
    }
    assert _frames(
        "Free Cash Flow of $135 million; Backlog of $48.2 billion; Book-to-Bill of 1.1x, Last Twelve Months 1.3x."
    ) == {
        ("BACKLOG", "ABSOLUTE_VALUE", 48_200_000_000.0, None, None, None, True),
        ("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.1, None, None, None, True),
        ("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.3, None, None, None, True),
    }
    assert _frames("Operating loss was $0.6 million for the first half of 2026 compared to $26.2 million last year.") == {
        ("OPERATING_INCOME", "COMPARATIVE", 600_000.0, None, None, None, False),
        ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 26_200_000.0, None, None, None, False),
    }
    assert _frames("Q3 revenue in the range of $46 million to $48 million.") == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 47_000_000.0, None, 46_000_000.0, 48_000_000.0, True),
    }
    assert _frames(
        "Adjusted EBITDA in the range between ($9) million to ($7) million increased from ($16) million to ($12) million."
    ) == {
        ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 8_000_000.0, None, 7_000_000.0, 9_000_000.0, False),
    }
