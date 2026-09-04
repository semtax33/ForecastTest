from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v266 import (
    V266_RULES,
    extract_text_kpis_v266,
    route_document_blocks_v266,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v266-semantic-laws",
                "V266_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            entity="TEST",
            source_kind="TEST",
            document_kind="TEXT_IE",
            available_at="2026-09-04",
            report_period="2026Q2",
        ),
    )


def _frames(text: str):
    return extract_text_kpis_v266(_document(text)).extraction.frames


def _signatures(text: str):
    return {
        (
            frame.concept,
            frame.frame.value,
            frame.value,
            frame.change,
            frame.polarity.positive,
        )
        for frame in _frames(text)
    }


def test_v266_rules_are_typed_and_issuer_neutral() -> None:
    assert len(V266_RULES) >= 16
    assert all(rule.pattern for rule in V266_RULES)
    assert all(rule.rule_id.startswith("v266.") for rule in V266_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V266_RULES)


def test_margin_comparatives_preserve_current_and_prior_roles() -> None:
    simple = _signatures(
        "Operating profit margin was 20.9% for the second quarter of 2026, "
        "compared with 17.3% for the second quarter of 2025."
    )
    assert ("OPERATING_MARGIN", "COMPARATIVE", 20.9, None, True) in simple
    assert (
        "PRIOR_YEAR_OPERATING_MARGIN",
        "COMPARATIVE",
        17.3,
        None,
        True,
    ) in simple
    interrupted = _signatures(
        "Operating income margin rate of 9.6 percent, which included 3.7 "
        "percentage points of benefit, increased from the prior-year "
        "operating income margin rate of 5.2 percent."
    )
    assert ("OPERATING_MARGIN", "COMPARATIVE", 9.6, None, True) in interrupted
    assert (
        "PRIOR_YEAR_OPERATING_MARGIN",
        "COMPARATIVE",
        5.2,
        None,
        True,
    ) in interrupted


def test_cash_and_two_metric_level_changes_have_explicit_owners() -> None:
    cash = _signatures(
        "Enterprise operating cash flow was $4.4 billion, and the company "
        "ended the quarter with $6.7 billion of enterprise cash."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 6_700_000_000.0, None, True) in cash
    operating = _signatures(
        "Operating profits were a record $1.1 billion, up 10%, and operating "
        "margins in the quarter were 27.5%, up 190 basis points sequentially."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        1_100_000_000.0,
        10.0,
        True,
    ) in operating
    assert ("OPERATING_MARGIN", "CHANGE_TO", 27.5, 190.0, True) in operating


def test_reported_sales_are_not_guidance_and_growth_roles_do_not_cross() -> None:
    signatures = _signatures(
        "2026 Second-Quarter reported sales growth of 6.6% to $25.3 Billion "
        "with operational growth of 5.6% and adjusted operational growth of 5.7%."
    )
    assert signatures == {
        ("REVENUE", "CHANGE_TO", 25_300_000_000.0, 6.6, True),
        ("REVENUE", "CHANGE_BY", 5.6, None, True),
        ("REVENUE", "CHANGE_BY", 5.7, None, True),
    }


def test_guidance_midpoint_and_relative_tolerance_are_distinct_frames() -> None:
    midpoint = _signatures(
        "The company increased 2026 guidance with estimated reported sales "
        "of $101.1 Billion or 7.3% at the midpoint."
    )
    assert (
        "REVENUE_GUIDANCE",
        "CHANGE_TO",
        101_100_000_000.0,
        7.3,
        True,
    ) in midpoint
    ranged = _frames("Revenue is expected to be $108.0 billion, plus or minus 2%.")
    assert any(
        frame.concept == "REVENUE_GUIDANCE"
        and frame.frame.value == "RANGE_GUIDANCE"
        and frame.value == 108_000_000_000.0
        and frame.lower_value == 105_840_000_000.0
        and frame.upper_value == 110_160_000_000.0
        for frame in ranged
    )


def test_negative_impact_uses_trigger_local_polarity() -> None:
    signatures = _signatures(
        "Worldwide operational sales grew 3.6%, with net acquisitions and "
        "divestitures negatively impacting growth by 10 basis points."
    )
    assert ("REVENUE", "CHANGE_BY", 3.6, None, True) in signatures
    assert ("REVENUE", "CHANGE_BY", 10.0, None, False) in signatures


def test_record_segment_sales_and_net_sales_level_change() -> None:
    segment = _signatures(
        "Business Segment Results Sales for the Electrical segment were a "
        "record $4.0 billion, up 18% organically."
    )
    assert ("REVENUE", "CHANGE_TO", 4_000_000_000.0, 18.0, True) in segment
    total = _signatures(
        "Net Sales of $26.5 billion in the second quarter were 5.3 percent "
        "higher than last year."
    )
    assert ("REVENUE", "CHANGE_TO", 26_500_000_000.0, 5.3, True) in total


def test_router_handles_financial_grids_without_regex_templates() -> None:
    tables = (
        "$ in millions 2026 2025 % Change Net sales $3,998 $4,273 -6% "
        "Operating profit $527 $580 -9% Operating margin 13.2% 13.6%",
        "Reconciliation of Net Income to Adjusted EBITDA Three Months Ended "
        "June 30, 2026 Six Months Ended June 30, 2026",
        "Prior Year / Mid-point $100.3B – $100.9B / $100.6B 6.5% – 7.1% / "
        "6.8% $99.7B – $100.7B / $100.2B 5.9% – 6.9% / 6.4% Mid-point",
        "NVIDIA RECONCILIATION OF GAAP TO NON-GAAP OUTLOOK Q3 FY2027 Outlook "
        "GAAP gross margin 74.0% Non-GAAP gross margin 74.0%",
    )
    for text in tables:
        assert any(
            route.route is BlockRoute.FLATTENED_TABLE
            for route in route_document_blocks_v266(_document(text))
        )
    narrative = (
        "Adjusted earnings per share between $3.46 and $3.56 Business Segment "
        "Results Sales for the Electrical segment were a record $4.0 billion, "
        "up 18% organically."
    )
    assert all(
        route.route is BlockRoute.PROSE
        for route in route_document_blocks_v266(_document(narrative))
    )
