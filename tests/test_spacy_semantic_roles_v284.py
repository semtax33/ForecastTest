from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v284 import extract_text_kpis_v284, route_document_blocks_v284


def _document(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<html><body><p>{text}</p></body></html>".encode(), "test://v284", "V284", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v284(_document(text))
    return {
        (frame.concept, frame.frame.value, frame.value, frame.change, frame.lower_value, frame.upper_value, frame.polarity.positive)
        for frame in result.extraction.frames
    }, {candidate.metric.concept for candidate in result.candidates}


def _routes(text: str):
    return {
        route.route
        for route in route_document_blocks_v284(_document(text))
        if route.char_start is not None
    }


def test_v284_segment_revenue_ebitda_and_implied_margin_roles() -> None:
    frames, candidates = _frames(
        "The Production segment generated revenues of $121 million, which resulted in $6 million "
        "of Adjusted EBITDA and a margin of 5%."
    )
    assert "ADJUSTED_EBITDA_MARGIN" in candidates
    assert {item for item in frames if item[0] in {"REVENUE", "ADJUSTED_EBITDA", "ADJUSTED_EBITDA_MARGIN"}} == {
        ("REVENUE", "ABSOLUTE_VALUE", 121_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 6_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 5.0, None, None, None, True),
    }


def test_v284_patient_day_volume_and_realization_roles() -> None:
    frames, candidates = _frames(
        "Same-facility patient days increased 0.8%, and same-facility revenue per patient day decreased 0.8%."
    )
    assert {"ACTIVITY_VOLUME", "PRICE_REALIZATION"} <= candidates
    assert {item for item in frames if item[0] in {"ACTIVITY_VOLUME", "PRICE_REALIZATION", "REVENUE"}} == {
        ("ACTIVITY_VOLUME", "CHANGE_BY", 0.8, None, None, None, True),
        ("PRICE_REALIZATION", "CHANGE_BY", 0.8, None, None, None, False),
    }


def test_v284_plus_minus_revenue_guidance() -> None:
    frames, candidates = _frames(
        "Third Quarter Guidance is within the following ranges: Q3 Revenue $640 million +/- $20 million."
    )
    assert "REVENUE" in candidates
    assert {item for item in frames if "REVENUE" in item[0]} == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 640_000_000.0, None, 620_000_000.0, 660_000_000.0, True)
    }


def test_v284_three_way_revenue_comparison() -> None:
    frames, _ = _frames(
        "Revenue was $574 million in the second quarter, compared with $511 million in the first quarter "
        "and $442 million in the prior-year quarter."
    )
    assert {item for item in frames if "REVENUE" in item[0]} == {
        ("REVENUE", "COMPARATIVE", 574_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 511_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 442_000_000.0, None, None, None, True),
    }


def test_v284_press_release_highlights_are_prose_and_extract_roles() -> None:
    text = (
        "Financial News Release Advanced Energy Reports Second Quarter Results ● Revenue was $574 million, "
        "up 30% year-over-year ● Semiconductor revenue grew 33% year-over-year ● GAAP gross margin was 41.1%; "
        "non-GAAP gross margin was 41.9% ● Cash flow from continuing operations was $86 million. "
        "The company announced financial results."
    )
    assert _routes(text).isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    frames, candidates = _frames(text)
    assert {"REVENUE", "GROSS_MARGIN"} <= candidates
    assert {item for item in frames if item[0] in {"REVENUE", "GROSS_MARGIN", "CASH"}} == {
        ("REVENUE", "CHANGE_TO", 574_000_000.0, 30.0, None, None, True),
        ("REVENUE", "CHANGE_BY", 33.0, None, None, None, True),
        ("GROSS_MARGIN", "ABSOLUTE_VALUE", 41.1, None, None, None, True),
        ("GROSS_MARGIN", "ABSOLUTE_VALUE", 41.9, None, None, None, True),
    }


def test_v284_cash_flow_is_not_cash_balance_and_contract_is_orders() -> None:
    cash_flow, _ = _frames("Adjusted cash from operations was $58 million and $94 million for the full year.")
    assert not {item for item in cash_flow if item[0] == "CASH"}
    orders, candidates = _frames("Awarded a $305 million follow-on contract to provide contractor logistics support.")
    assert "ORDERS" in candidates
    assert {item for item in orders if item[0] == "ORDERS"} == {
        ("ORDERS", "ABSOLUTE_VALUE", 305_000_000.0, None, None, None, True)
    }


def test_v284_unit_revenue_and_solutions_sales_use_economic_roles() -> None:
    realization, candidates = _frames(
        "Adjusted operating net revenue per advisor reached $1.2 million, up 12 percent."
    )
    assert "PRICE_REALIZATION" in candidates
    assert {item for item in realization if item[0] in {"PRICE_REALIZATION", "REVENUE"}} == {
        ("PRICE_REALIZATION", "CHANGE_TO", 1_200_000.0, 12.0, None, None, True)
    }
    activity, candidates = _frames(
        "Retirement Solutions sales increased 20 percent to $1.6 billion, with strong client demand."
    )
    assert "ACTIVITY_VOLUME" in candidates
    assert {item for item in activity if item[0] in {"ACTIVITY_VOLUME", "REVENUE"}} == {
        ("ACTIVITY_VOLUME", "CHANGE_TO", 1_600_000_000.0, 20.0, None, None, True)
    }


def test_v284_share_and_margin_comparisons() -> None:
    shares, _ = _frames(
        "Weighted average diluted shares outstanding decreased to 213.9 million compared to 217.3 million in the prior year."
    )
    assert {item for item in shares if "SHARES" in item[0]} == {
        ("SHARES", "COMPARATIVE", 213_900_000.0, None, None, None, False),
        ("PRIOR_YEAR_SHARES", "COMPARATIVE", 217_300_000.0, None, None, None, False),
    }
    margin, _ = _frames("Adjusted operating margin increased to 10.2% from 9.6% in the prior year.")
    assert {item for item in margin if "OPERATING_MARGIN" in item[0]} == {
        ("OPERATING_MARGIN", "COMPARATIVE", 10.2, None, None, None, True),
        ("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 9.6, None, None, None, True),
    }


def test_v284_revenue_level_change_and_component_ownership() -> None:
    frames, _ = _frames(
        "Sales increased 5% to $820.5 million, including a $16 million sales contribution from an acquisition."
    )
    assert {item for item in frames if item[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 820_500_000.0, 5.0, None, None, True),
        ("REVENUE", "CHANGE_BY", 16_000_000.0, None, None, None, True),
    }


def test_v284_debt_and_production_unit_roles() -> None:
    debt, _ = _frames("The company reduced total debt by $2.3 billion since year-end.")
    assert {item for item in debt if item[0] == "DEBT"} == {
        ("DEBT", "CHANGE_BY", 2_300_000_000.0, None, None, None, False)
    }
    production, _ = _frames("Gross gas production increased to 539 million cubic feet per day.")
    assert {item for item in production if item[0] == "PRODUCTION"} == {
        ("PRODUCTION", "CHANGE_TO", 539_000_000.0, None, None, None, True)
    }


def test_v284_multiple_production_levels_remain_actual() -> None:
    frames, _ = _frames(
        "Reported production was 410,000 BOE per day; adjusted production was 347,000 BOE per day and exceeded guidance."
    )
    assert {item for item in frames if "PRODUCTION" in item[0]} == {
        ("PRODUCTION", "ABSOLUTE_VALUE", 410_000.0, None, None, None, True),
        ("PRODUCTION", "ABSOLUTE_VALUE", 347_000.0, None, None, None, True),
    }


def test_v284_reported_organic_and_respectively_margin_roles() -> None:
    revenue, _ = _frames("Reported net revenues increased by 8.8% (4.7% organic).")
    assert {item for item in revenue if "REVENUE" in item[0]} == {
        ("REVENUE", "CHANGE_BY", 8.8, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 4.7, None, None, None, True),
    }
    gross, _ = _frames(
        "Reported and adjusted gross margin increased by 60 and 20 basis points, respectively."
    )
    assert {item for item in gross if item[0] == "GROSS_MARGIN"} == {
        ("GROSS_MARGIN", "CHANGE_BY", 60.0, None, None, None, True),
        ("GROSS_MARGIN", "CHANGE_BY", 20.0, None, None, None, True),
    }
    operating, candidates = _frames(
        "Segment earnings margin was 11.9%, representing a 60 basis point increase."
    )
    assert "OPERATING_MARGIN" in candidates
    assert {item for item in operating if item[0] in {"OPERATING_MARGIN", "GROSS_MARGIN"}} == {
        ("OPERATING_MARGIN", "CHANGE_TO", 11.9, 60.0, None, None, True)
    }


def test_v284_financial_statement_grid_is_table() -> None:
    routes = _routes(
        "Condensed Consolidated Statements of Income Unaudited Three Months Ended Six Months Ended Revenue "
        "$4,246 $4,155 2% $9,280 $8,884 4% Operating income 915 859 7% 2,630 2,320 13% "
        "Operating margin 30.5% 30.1% 13.4% 9.1%."
    )
    assert routes & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def test_v284_results_bullet_uses_concepts_when_footnotes_touch_metric_names() -> None:
    frames, _ = _frames(
        "Second Quarter Results · Total revenue was $498 million compared to first quarter revenue of $450 million "
        "· Net loss was $75 million compared to $81 million · Adjusted EBITDA¹ was $69 million compared to "
        "$54 million; 14% of revenue compared to 12% of revenue · Net cash provided by operating activities was "
        "$23 million compared to $9 million · Capital expenditures totaled $32 million compared to $41 million "
        "· Free cash flow² was negative $8 million compared to negative $25 million."
    )
    assert {item for item in frames if item[0] in {
        "REVENUE", "PRIOR_YEAR_REVENUE", "ADJUSTED_EBITDA", "PRIOR_YEAR_ADJUSTED_EBITDA",
        "ADJUSTED_EBITDA_MARGIN", "PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", "CAPEX", "PRIOR_YEAR_CAPEX",
    }} == {
        ("REVENUE", "COMPARATIVE", 498_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 450_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "COMPARATIVE", 69_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 54_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 14.0, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 12.0, None, None, None, True),
        ("CAPEX", "COMPARATIVE", 32_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_CAPEX", "COMPARATIVE", 41_000_000.0, None, None, None, True),
    }
