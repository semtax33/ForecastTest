from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v270 import V270_RULES, extract_text_kpis_v270, route_document_blocks_v270


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v270-semantic-laws",
                "V270_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    return extract_text_kpis_v270(_document(text)).extraction.frames


def _signatures(text: str):
    return {
        (frame.concept, frame.frame.value, frame.value, frame.change, frame.lower_value, frame.upper_value)
        for frame in _frames(text)
    }


def test_v270_laws_are_typed_and_issuer_neutral() -> None:
    assert len(V270_RULES) >= 11
    assert all(rule.pattern and rule.rule_id.startswith("v270.") for rule in V270_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V270_RULES)


def test_v270_revenue_higher_and_representing_growth() -> None:
    higher = _signatures(
        "Net revenues in Equities were $7.42 billion, 72% higher than the prior-year quarter."
    )
    assert ("REVENUE", "CHANGE_TO", 7_420_000_000.0, 72.0, None, None) in higher
    representing = _signatures(
        "Subscription revenues of $3,877 million in Q2, representing 24.5% year-over-year "
        "growth, 23% in constant currency."
    )
    assert ("REVENUE", "CHANGE_TO", 3_877_000_000.0, 24.5, None, None) in representing
    assert ("REVENUE", "CHANGE_BY", 23.0, None, None, None) in representing


def test_v270_margin_and_component_growth_ownership() -> None:
    margins = _signatures(
        "Non-GAAP gross margin as a percent of revenue of 52.0%, non-GAAP operating "
        "margin as a percent of revenue of 38.4%, and non-GAAP diluted EPS of $1.82."
    )
    assert ("GROSS_MARGIN", "ABSOLUTE_VALUE", 52.0, None, None, None) in margins
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 38.4, None, None, None) in margins
    assert not any(concept == "REVENUE" for concept, *_ in margins)
    volume = _signatures(
        "Gross dollar volume growth of 8% on a local currency basis to $5.6 trillion."
    )
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 8.0, None, None, None) in volume


def test_v270_forecast_and_secondary_organic_growth() -> None:
    forecast = _signatures(
        "We project an operating margin of 33.2% compared with 28.2% in the year ago quarter."
    )
    assert forecast == {
        ("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 33.2, None, None, None)
    }
    organic = _signatures(
        "Portfolio revenue of $2.388 billion increased 8.0% as reported and 5.1% organic."
    )
    assert ("REVENUE", "CHANGE_TO", 2_388_000_000.0, 8.0, None, None) in organic
    assert ("REVENUE", "CHANGE_BY", 5.1, None, None, None) in organic


def test_v270_guidance_growth_shares_and_fx() -> None:
    guidance = _signatures(
        "Total revenue in the range of $3.345 billion to $3.355 billion, representing "
        "year-over-year growth of 32%."
    )
    assert (
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        3_350_000_000.0,
        None,
        3_345_000_000.0,
        3_355_000_000.0,
    ) in guidance
    assert ("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0, None, None, None) in guidance
    shares = _signatures(
        "Diluted earnings per share in the range of $0.96 to $0.98, using 830 million "
        "to 840 million shares outstanding."
    )
    assert ("SHARES_GUIDANCE", "RANGE_GUIDANCE", 835_000_000.0, None, 830_000_000.0, 840_000_000.0) in shares
    fx = _signatures("Foreign exchange benefit of $308 million on the remaining net sales revenue included.")
    assert ("REVENUE", "CHANGE_BY", 308_000_000.0, None, None, None) in fx


def test_v270_suppresses_submetric_and_comparative_false_positives() -> None:
    compensation = _signatures(
        "GAAP income from operations included share-based compensation expense of "
        "$213 million, compared with $200 million in the prior-year quarter."
    )
    assert not any("OPERATING_INCOME" in concept for concept, *_ in compensation)
    gains = _signatures(
        "Net revenues included mark-to-market gains associated with deferred compensation "
        "of $294 million in the quarter."
    )
    assert not any(concept == "REVENUE" for concept, *_ in gains)
    comparison = _signatures(
        "Income from operations increased to $1.22 billion, compared with $0.95 billion in 2025."
    )
    assert ("OPERATING_INCOME", "COMPARATIVE", 1_220_000_000.0, None, None, None) in comparison
    assert not any(frame == "CHANGE_TO" for _, frame, *_ in comparison)


def test_v270_router_compact_grids_and_footnote_prose() -> None:
    grids = (
        "Non-compensation expenses increased. ($ millions) 2Q 2026 2Q 2025 Net Revenues "
        "$1,646 $1,552 Total Expenses $1,242 $1,229 Compensation $559 $613.",
        "Q2 Key Business Drivers Gross dollar volume Cross-border volume Switched transactions "
        "up 8% up 12% up 9%.",
        "Non-GAAP Net Debt reconciliation: Total debt $14,309 Add costs 49 Less Cash and "
        "cash equivalents (9,099) Net debt $5,244.",
        "GAAP operating margin 37.4% 35.0% Non-GAAP operating margin 38.4% 35.0%.",
    )
    for text in grids:
        assert any(
            route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
            for route in route_document_blocks_v270(_document(text))
        )
    footnote = (
        "The three months ended April 2025 excludes $48 million of revenue adjustments "
        "and $31 million of inorganic revenue. The twelve months ended April 2026 excludes "
        "$998 million of revenue adjustments, including $135 million of inorganic revenue."
    )
    assert all(route.route is BlockRoute.PROSE for route in route_document_blocks_v270(_document(footnote)))
