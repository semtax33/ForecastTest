from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v283 import extract_text_kpis_v283, route_document_blocks_v283


def _document(*paragraphs: str):
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<html><body>{body}</body></html>".encode(), "test://v283", "V283", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(*paragraphs: str):
    result = extract_text_kpis_v283(_document(*paragraphs))
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


def _routes(text: str):
    return {
        route.route
        for route in route_document_blocks_v283(_document(text))
        if route.char_start is not None
    }


def test_v283_range_roles_with_local_and_bounded_upper_guidance() -> None:
    frames, _ = _frames(
        "Business Outlook",
        "The following information presents the company's guidance for the third quarter.",
        "Net sales of $1.95 billion to $2.05 billion",
        "Gross margin of 18.5% to 19.5%",
        "Full year 2026 capital expenditures of approximately $2.5 billion to $3.0 billion",
    )
    assert ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 2_000_000_000.0, None, 1_950_000_000.0, 2_050_000_000.0, True) in frames
    assert ("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 19.0, None, 18.5, 19.5, True) in frames
    assert ("CAPEX_GUIDANCE", "RANGE_GUIDANCE", 2_750_000_000.0, None, 2_500_000_000.0, 3_000_000_000.0, True) in frames

    local, _ = _frames("FY2026 Adjusted EBITDA expected to be $265 million to $300 million")
    assert {item for item in local if item[0] == "ADJUSTED_EBITDA_GUIDANCE"} == {
        ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 282_500_000.0, None, 265_000_000.0, 300_000_000.0, True)
    }


def test_v283_adjusted_ebitda_and_margin_comparison_roles() -> None:
    frames, candidates = _frames(
        "Adjusted EBITDA was $1,013.2 million, or 4.1% of Net sales and other revenue, "
        "during the first quarter compared to $1,111.0 million, or 4.5% of Net sales "
        "and other revenue, during the prior-year quarter."
    )
    assert "ADJUSTED_EBITDA_MARGIN" in candidates
    assert {item for item in frames if "ADJUSTED_EBITDA" in item[0]} == {
        ("ADJUSTED_EBITDA", "COMPARATIVE", 1_013_200_000.0, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 1_111_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 4.1, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 4.5, None, None, None, True),
    }
    assert not {item for item in frames if item[0] == "REVENUE"}


def test_v283_segment_operating_earnings_and_sales_comparison_roles() -> None:
    frames, candidates = _frames(
        "Beverage Packaging, EMEA, segment comparable operating earnings for the quarter "
        "were $162 million on sales of $1.24 billion compared to $152 million on sales of "
        "$1.12 billion during the same period last year."
    )
    assert "OPERATING_INCOME" in candidates
    assert {item for item in frames if item[0] in {"OPERATING_INCOME", "PRIOR_YEAR_OPERATING_INCOME", "REVENUE", "PRIOR_YEAR_REVENUE"}} == {
        ("OPERATING_INCOME", "COMPARATIVE", 162_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 152_000_000.0, None, None, None, True),
        ("REVENUE", "COMPARATIVE", 1_240_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 1_120_000_000.0, None, None, None, True),
    }


def test_v283_sales_and_operating_margin_ranges_keep_separate_ownership() -> None:
    frames, candidates = _frames(
        "Capital expenditures of approximately $750 million, which is unchanged. "
        "The company expects comparable sales to be in the range of 1.0% to 3.0% and "
        "adjusted operating income rate to be in the range of 4.1% to 4.2%."
    )
    assert {"CAPEX", "REVENUE", "OPERATING_MARGIN"} <= candidates
    assert {item for item in frames if item[0] in {"CAPEX_GUIDANCE", "REVENUE_CHANGE_GUIDANCE", "OPERATING_MARGIN_GUIDANCE"}} == {
        ("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 750_000_000.0, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 2.0, None, 1.0, 3.0, True),
        ("OPERATING_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 4.15, None, 4.1, 4.2, True),
    }


def test_v283_current_guidance_range_precedes_prior_guidance_range() -> None:
    frames, _ = _frames(
        "Comparable sales % change of 1.9% to 3.0%, compared to prior guidance of (1.0%) to 1.0%."
    )
    assert {item for item in frames if item[0] == "REVENUE_CHANGE_GUIDANCE"} == {
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 2.45, None, 1.9, 3.0, True)
    }


def test_v283_single_percent_recovery_does_not_replace_revenue_level() -> None:
    frames, _ = _frames("International revenue of $709 million decreased 4.2% versus last year.")
    assert {item for item in frames if item[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 709_000_000.0, 4.2, None, None, False)
    }


def test_v283_three_way_operating_income_comparison() -> None:
    frames, _ = _frames(
        "Operating income was $215.8 million for the quarter, as compared to $323.3 million "
        "for the previous quarter and $154.1 million for the prior year."
    )
    assert {item for item in frames if "OPERATING_INCOME" in item[0]} == {
        ("OPERATING_INCOME", "COMPARATIVE", 215_800_000.0, None, None, None, True),
        ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 323_300_000.0, None, None, None, True),
        ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 154_100_000.0, None, None, None, True),
    }


def test_v283_non_cash_expense_ratio_and_per_share_guards() -> None:
    non_cash, _ = _frames(
        "Adjusted net income excludes $3 million related to non-cash asset impairments and "
        "$2 million of weather-related losses."
    )
    assert not {item for item in non_cash if item[0] == "CASH"}
    expense, _ = _frames(
        "Selling and administrative expenses as a percentage of Net sales and other revenue increased 42 basis points."
    )
    assert not {item for item in expense if item[0] == "REVENUE"}
    per_share, _ = _frames(
        "EPS was lower due to a $0.10 per diluted share non-cash impairment charge, partially offset by "
        "$0.08 per diluted share of higher revenues."
    )
    assert not {item for item in per_share if item[0] in {"CASH", "REVENUE"}}


def test_v283_press_release_leads_are_prose() -> None:
    best_buy = _routes(
        "Document Exhibit 99 Best Buy Reports Second Quarter Results Comparable Sales Increased 4.1% "
        "Raises FY27 Comparable Sales Guidance to 1.9% to 3.0% MINNEAPOLIS, August 27, 2026 -- "
        "Best Buy today announced results for the quarter."
    )
    assert best_buy.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    best_buy_frames, _ = _frames(
        "Best Buy Reports Second Quarter Results Comparable Sales Increased 4.1% Diluted EPS "
        "Increased 70% to $1.48 Adjusted Diluted EPS Increased 15% to $1.47 Raises FY27 "
        "Comparable Sales Guidance to 1.9% to 3.0% Best Buy today announced results."
    )
    assert {item for item in best_buy_frames if item[0] in {"REVENUE", "REVENUE_CHANGE_GUIDANCE"}} == {
        ("REVENUE", "CHANGE_BY", 4.1, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 2.45, None, 1.9, 3.0, True),
    }
    carrier = _routes(
        "PALM BEACH GARDENS, July 28, 2026 – Carrier today reported better than expected financial results. "
        "Organic sales returned to growth earlier than expected, up 3%, driven by strong performance."
    )
    assert carrier.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    carrier_frames, _ = _frames(
        "Carrier today reported better than expected financial results. Organic sales returned "
        "to growth earlier than expected, up 3%, driven by strong performance."
    )
    assert {item for item in carrier_frames if item[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_BY", 3.0, None, None, None, True)
    }


def test_v283_income_share_and_projected_ffo_grids_are_tables() -> None:
    share_grid = _routes(
        "Net income $0.43 $0.56 $1.07 $0.95 Weighted average number of common shares outstanding "
        "159,167 158,312 158,863 158,257 Diluted earnings per common share attributable to the company."
    )
    assert share_grid & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    isolated_share_grid = _routes(
        "Net income $0.43 $0.56 $1.07 $0.95 Weighted average number of common and common "
        "equivalent shares outstanding 159,629 158,795 159,344 158,713 BXP, INC."
    )
    assert isolated_share_grid & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    ffo_grid = _routes(
        "Third Quarter 2026 Full Year 2026 Low High Low High Projected EPS diluted $0.50 $0.52 $2.14 $2.24 "
        "Projected Company share of depreciation 1.30 1.30 5.10 5.10 Projected FFO per share diluted $1.80 $1.82 $6.99 $7.05."
    )
    assert ffo_grid & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
