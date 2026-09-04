from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v267 import (
    V267_RULES,
    extract_text_kpis_v267,
    route_document_blocks_v267,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v267-semantic-laws",
                "V267_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            "TEST", "TEST", "TEXT_IE", "2026-09-04", "2026Q2"
        ),
    )


def _frames(text: str):
    return extract_text_kpis_v267(_document(text)).extraction.frames


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


def test_v267_laws_are_typed_and_issuer_neutral() -> None:
    assert len(V267_RULES) >= 16
    assert all(rule.pattern for rule in V267_RULES)
    assert all(rule.rule_id.startswith("v267.") for rule in V267_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V267_RULES)


def test_level_change_topologies_and_metric_ownership() -> None:
    assert (
        "REVENUE",
        "CHANGE_TO",
        145_000_000.0,
        38.0,
        True,
    ) in _signatures("Sales - $145 million, up 38%.")
    assert (
        "REVENUE",
        "CHANGE_TO",
        3_940_000_000.0,
        10.0,
        True,
    ) in _signatures("Revenue totaled $3.94 billion, increasing 10% year-over-year.")
    capex = _signatures(
        "Operating cash flow was $1.7 billion, with gross capital expenditures "
        "of $1.4 billion and free cash flow of $209 million."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 1_400_000_000.0, None, True) in capex


def test_coordinated_growth_and_headwind_keep_local_roles() -> None:
    growth = _signatures(
        "Alphabet revenues growing 24% year-over-year and Google Cloud revenues "
        "accelerating to 82% growth."
    )
    assert ("REVENUE", "CHANGE_BY", 24.0, None, True) in growth
    assert ("REVENUE", "CHANGE_BY", 82.0, None, True) in growth
    headwind = _signatures(
        "Our guidance assumes foreign currency is an approximately 1% headwind "
        "to year-over-year total revenue growth."
    )
    assert (
        "REVENUE_CHANGE_GUIDANCE",
        "ABSOLUTE_VALUE",
        1.0,
        None,
        False,
    ) in headwind


def test_cash_balance_and_capex_range_are_not_cash_flow() -> None:
    cash = _signatures(
        "Cash, cash equivalents, and marketable securities were $90.26 billion "
        "as of June 30, 2026."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 90_260_000_000.0, None, True) in cash
    capex = _frames(
        "We anticipate 2026 capital expenditures, including principal payments "
        "on finance leases, to be in the range of $130-145 billion."
    )
    assert any(
        frame.concept == "CAPEX_GUIDANCE"
        and frame.value == 137_500_000_000.0
        and frame.lower_value == 130_000_000_000.0
        and frame.upper_value == 145_000_000_000.0
        for frame in capex
    )


def test_single_and_multi_period_comparatives_preserve_each_value() -> None:
    single = _signatures(
        "Sales of products were $359 million and $335 million in the current "
        "and prior-year quarters, respectively."
    )
    assert ("REVENUE", "COMPARATIVE", 359_000_000.0, None, True) in single
    assert (
        "PRIOR_YEAR_REVENUE",
        "COMPARATIVE",
        335_000_000.0,
        None,
        True,
    ) in single
    multi = _signatures(
        "Total alliance revenue for Product of $161 million and $10 million in "
        "the first and second quarter of 2026, respectively, and $44 million "
        "and $43 million in the first and second quarter of 2025, respectively."
    )
    assert {value for concept, frame, value, _, _ in multi if concept == "REVENUE"} == {
        161_000_000.0,
        10_000_000.0,
    }
    assert {
        value
        for concept, frame, value, _, _ in multi
        if concept == "PRIOR_YEAR_REVENUE"
    } == {44_000_000.0, 43_000_000.0}


def test_word_and_adjusted_ebitda_ranges_are_typed_guidance() -> None:
    words = _frames(
        "The Company expects organic sales growth in the range of one to three "
        "percent versus prior year."
    )
    assert any(
        frame.concept == "REVENUE_CHANGE_GUIDANCE"
        and frame.value == 2.0
        and frame.lower_value == 1.0
        and frame.upper_value == 3.0
        for frame in words
    )
    ebitda = _frames(
        "The company expects EBITDA to range between $3.20 billion and $3.36 "
        "billion and adjusted EBITDA to range between $3.49 billion and $3.65 billion."
    )
    assert any(
        frame.concept == "ADJUSTED_EBITDA_GUIDANCE"
        and frame.value == 3_570_000_000.0
        and frame.lower_value == 3_490_000_000.0
        and frame.upper_value == 3_650_000_000.0
        for frame in ebitda
    )


def test_resulting_margins_do_not_cross_bind_to_income() -> None:
    signatures = _signatures(
        "Quarterly operating income decreased 57% YoY to $0.4B, resulting in "
        "a 1.4% operating margin."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        400_000_000.0,
        57.0,
        False,
    ) in signatures
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 1.4, None, True) in signatures
    assert not any(
        concept == "OPERATING_INCOME" and change == 1.4
        for concept, _, _, change, _ in signatures
    )


def test_v267_router_recovers_row_grids_and_releases_narrative_notes() -> None:
    tables = (
        "Basic $6.76 $6.46 $11.48 $12.45 Diluted $6.73 $6.43 $11.44 "
        "$12.38 WEIGHTED-AVERAGE COMMON SHARES OUTSTANDING Basic 137.9 137.8 "
        "138.1 137.7 Diluted 138.5 138.5 138.6 138.4",
        "Quarters Ended Six Months Ended Jun. 30, 2026 Jun. 30, 2025 Change "
        "Jun. 30, 2026 Jun. 30, 2025 Change 10.0 10.2 2% 19.3 19.4 1%",
        "KEY PRODUCT 8,366 7,956 5% 4% Growth primarily driven by strong demand",
        "Tax Rate -95.9% 160.3% Cost of sales 8,590 2,081 421 2,502 "
        "Net Loss 5,580 1,715 665 291 2,089 3,491 2026 2025 2024 2023 "
        "1,363 421 135 80 476 1,839",
    )
    for text in tables:
        assert any(
            route.route is BlockRoute.FLATTENED_TABLE
            for route in route_document_blocks_v267(_document(text))
        )
    note = (
        "See reconciliation table below for information. The company defines "
        "performance margin in this note. Guidance does not include later charges."
    )
    assert all(
        route.route is BlockRoute.PROSE
        for route in route_document_blocks_v267(_document(note))
    )
