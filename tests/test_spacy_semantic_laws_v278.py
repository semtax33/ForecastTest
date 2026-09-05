from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v278 import extract_text_kpis_v278, route_document_blocks_v278


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v278-semantic-laws",
                "V278_SEMANTIC_LAW_TEST",
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
        for frame in extract_text_kpis_v278(_document(f"<p>{text}</p>")).extraction.frames
    }


def _route(text: str) -> BlockRoute:
    routes = [
        route
        for route in route_document_blocks_v278(_document(f"<p>{text}</p>"))
        if route.char_start is not None
    ]
    assert len(routes) == 1
    return routes[0].route


def test_v278_semantic_paraphrases_reach_candidates_and_frames() -> None:
    gross = extract_text_kpis_v278(
        _document(
            "<p>Gross profit for the first six months of 2026 increased 9% to "
            "$4.86 billion (or 51.5% of sales) from $4.45 billion (or 51.4% of "
            "sales) for the same period one year ago.</p>"
        )
    )
    assert "GROSS_MARGIN" in {item.metric.concept for item in gross.candidates}
    gross_frames = {
        (frame.concept, frame.frame.value, frame.value)
        for frame in gross.extraction.frames
        if "GROSS_MARGIN" in frame.concept
    }
    assert gross_frames == {
        ("GROSS_MARGIN", "COMPARATIVE", 51.5),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 51.4),
    }

    shares = extract_text_kpis_v278(
        _document(
            "<p>Diluted earnings per common share increased 13% to $1.58 on "
            "836 million shares versus $1.40 on 861 million shares one year ago.</p>"
        )
    )
    assert "SHARES" in {item.metric.concept for item in shares.candidates}
    share_frames = {
        (frame.concept, frame.frame.value, frame.value)
        for frame in shares.extraction.frames
        if "SHARES" in frame.concept
    }
    assert share_frames == {
        ("SHARES", "COMPARATIVE", 836_000_000.0),
        ("PRIOR_YEAR_SHARES", "COMPARATIVE", 861_000_000.0),
    }


def test_v278_routes_semantic_bullets_and_fragments_as_prose() -> None:
    bullet = (
        "Second-Quarter Highlights ➢ Sales $9.3 billion, up 9% YoY, underlying "
        "sales up 4% ➢ Operating profit $2.6 billion, adjusted operating profit "
        "$2.7 billion, up 7% ➢ Operating profit margin 27.5%; adjusted operating "
        "profit margin 29.5% ➢ Project backlog $11 billion"
    )
    assert _route(bullet) not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert _route(
        "S., total revenue increased 11% to $2.06 billion due to continued strong "
        "patient demand and higher realized net prices."
    ) not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert _route(
        "S., increasing the sale of gas backlog to a record $8.1 billion while "
        "customer proposal activity remains robust."
    ) not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def test_v278_routes_financial_grids_as_tables() -> None:
    assert _route(
        "$ 1,699 $ 1,653 $ 3,319 $ 3,263 Losses gains on sales of facilities "
        "8 3 7 2 Net income 1,691 1,656 3,312 3,265 Depreciation and "
        "amortization 944 863 1,874 1,723 Interest expense 599 568 1,183 1,115 "
        "Adjusted EBITDA $4,027 $3,849 $7,829 $7,582"
    ) in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert _route(
        "Supplemental Non-GAAP Disclosures Operating Results Summary Dollars in "
        "millions Second Quarter Six Months Ended June 30 2026 2025 2026 2025 "
        "Revenues $20,230 $18,605 $39,339 $36,926 Net income"
    ) in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert _route("Q2 2025 10.6% 13.2% (19.1)% Operating Income ($ bn) $4.5 reported vs.") in {
        BlockRoute.FLATTENED_TABLE,
        BlockRoute.MIXED,
    }


def test_v278_adjusted_operating_income_and_per_share_guard() -> None:
    frames = _signatures(
        "Adjusted income from operations 1 for the second quarter 2026 was "
        "$2.1 billion, or $7.78 per share."
    )
    assert (
        "OPERATING_INCOME",
        "ABSOLUTE_VALUE",
        2_100_000_000.0,
        None,
        None,
        None,
        True,
    ) in frames
    guarded = _signatures(
        "2026 outlook for adjusted income from operations increased to at least "
        "$30.45 per share."
    )
    assert not any(frame[0] == "OPERATING_INCOME" for frame in guarded)


def test_v278_margin_direction_and_factual_context() -> None:
    lower = _signatures(
        "Operating margin was 60 basis points lower than the previous year as "
        "pricing was offset by inflation."
    )
    assert {
        frame for frame in lower if frame[0] == "OPERATING_MARGIN"
    } == {
        ("OPERATING_MARGIN", "CHANGE_BY", 60.0, None, None, None, False)
    }
    factual = _signatures(
        "Employees delivered another solid quarter, maintaining profitability "
        "with 29.5% operating margin and 23.5% return on capital."
    )
    assert (
        "OPERATING_MARGIN",
        "ABSOLUTE_VALUE",
        29.5,
        None,
        None,
        None,
        True,
    ) in factual
    assert not any(frame[0] == "OPERATING_MARGIN_GUIDANCE" for frame in factual)


def test_v278_component_and_parallel_change_ownership() -> None:
    currency = _signatures(
        "Sales were $9,289 million, up 9% versus prior year including 2% favorable "
        "currency impact."
    )
    assert ("REVENUE", "CHANGE_TO", 9_289_000_000.0, 9.0, None, None, True) in currency
    assert ("REVENUE", "CHANGE_BY", 2.0, None, None, None, True) in currency

    organic = _signatures(
        "Net revenues increased 4.1 percent driven by our underlying Organic Net "
        "Revenue growth of 2.2 percent."
    )
    assert {frame[2] for frame in organic if frame[:2] == ("REVENUE", "CHANGE_BY")} == {
        4.1,
        2.2,
    }

    yield_volume = _signatures(
        "Revenue growth from average yield on related business revenue was 4.0 "
        "percent, and volume decreased related business revenue by 1.9 percent."
    )
    assert ("REVENUE", "CHANGE_BY", 4.0, None, None, None, True) in yield_volume
    assert ("REVENUE", "CHANGE_BY", 1.9, None, None, None, False) in yield_volume


def test_v278_guidance_range_revision_and_growth_component() -> None:
    revised = _signatures(
        "The Company is increasing premium and service revenues guidance range by "
        "$2.0 billion to a range of $173.0 billion to $177.0 billion."
    )
    assert (
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        175_000_000_000.0,
        None,
        173_000_000_000.0,
        177_000_000_000.0,
        True,
    ) in revised
    assert (
        "REVENUE_GUIDANCE",
        "CHANGE_BY",
        2_000_000_000.0,
        None,
        None,
        None,
        True,
    ) in revised

    component = _signatures(
        "Total revenue guidance reflects a year-over-year benefit of approximately "
        "150 basis points in growth from foreign exchange rates."
    )
    assert (
        "REVENUE_CHANGE_GUIDANCE",
        "CHANGE_BY",
        150.0,
        None,
        None,
        None,
        True,
    ) in component


def test_v278_current_guidance_range_owns_values_before_prior_range() -> None:
    frames = _signatures(
        "Vertex raised its full year 2026 total revenue guidance to $13.1 billion "
        "to $13.2 billion from $12.95 billion to $13.1 billion previously."
    )
    guidance = {frame for frame in frames if frame[0] == "REVENUE_GUIDANCE"}
    assert guidance == {
        (
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            13_150_000_000.0,
            None,
            13_100_000_000.0,
            13_200_000_000.0,
            True,
        )
    }


def test_v278_banking_revenue_and_parallel_debt_components() -> None:
    bank = _signatures(
        "Taxable-equivalent net interest income was up $23 million, or 0.6%, "
        "compared to the first quarter."
    )
    assert {frame[2] for frame in bank if frame[:2] == ("REVENUE", "CHANGE_BY")} == {
        23_000_000.0,
        0.6,
    }

    debt = _signatures(
        "Average deposits increased $5.9 billion, or 1.5%, average short-term "
        "borrowings decreased $1.8 billion, or 5.8%, and average long-term debt "
        "increased $3.5 billion, or 9.4%."
    )
    debt_changes = {
        (frame[2], frame[6])
        for frame in debt
        if frame[:2] == ("DEBT", "CHANGE_BY")
    }
    assert debt_changes == {
        (1_800_000_000.0, False),
        (5.8, False),
        (3_500_000_000.0, True),
        (9.4, True),
    }


def test_v278_volume_fact_and_decline_guidance_range() -> None:
    actual = _signatures("Adjusted IMS volumes grew by around 8%.")
    assert (
        "ACTIVITY_VOLUME",
        "CHANGE_BY",
        8.0,
        None,
        None,
        None,
        True,
    ) in actual
    guidance = _signatures("Cigarette shipment volume decline of 2% to 3%.")
    assert (
        "ACTIVITY_VOLUME_CHANGE_GUIDANCE",
        "RANGE_GUIDANCE",
        2.5,
        None,
        2.0,
        3.0,
        False,
    ) in guidance


def test_v278_multiple_growth_rates_share_one_revenue_level() -> None:
    frames = _signatures(
        "CASGEVY revenue of $76 million, representing 78% quarter-over-quarter "
        "sequential growth and 151% growth compared to the prior year."
    )
    revenue = {frame for frame in frames if frame[0] == "REVENUE"}
    assert revenue == {
        ("REVENUE", "CHANGE_TO", 76_000_000.0, 78.0, None, None, True),
        ("REVENUE", "CHANGE_TO", 76_000_000.0, 151.0, None, None, True),
    }


def test_v278_cash_and_marketable_securities_comparison() -> None:
    frames = _signatures(
        "Cash, cash equivalents, and total marketable securities as of June 30, "
        "2026, were $13.6 billion, compared to $12.3 billion as of December 31, 2025."
    )
    cash = {frame for frame in frames if "CASH" in frame[0]}
    assert cash == {
        ("CASH", "COMPARATIVE", 13_600_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 12_300_000_000.0, None, None, None, True),
    }
