from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v268 import (
    V268_RULES,
    extract_text_kpis_v268,
    route_document_blocks_v268,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v268-semantic-laws",
                "V268_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            "TEST", "TEST", "TEXT_IE", "2026-09-04", "2026Q2"
        ),
    )


def _frames(text: str):
    return extract_text_kpis_v268(_document(text)).extraction.frames


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


def test_v268_laws_are_typed_and_issuer_neutral() -> None:
    assert len(V268_RULES) >= 30
    assert all(rule.pattern for rule in V268_RULES)
    assert all(rule.rule_id.startswith("v268.") for rule in V268_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V268_RULES)


def test_v268_emits_each_order_and_book_to_bill_value() -> None:
    orders = _signatures(
        "Orders received in the quarter totaled $14.7 billion in defense and "
        "$5.3 billion in aerospace, for a total of $20 billion."
    )
    assert {
        value
        for concept, frame, value, _, _ in orders
        if concept == "ORDERS" and frame == "ABSOLUTE_VALUE"
    } == {14_700_000_000.0, 5_300_000_000.0, 20_000_000_000.0}
    ratios = _signatures(
        "Book-to-bill ratio was 1.4-to-1 for defense, 1.5-to-1 for aerospace, "
        "and 1.4-to-1 company-wide."
    )
    assert {
        value
        for concept, frame, value, _, _ in ratios
        if concept == "BOOK_TO_BILL" and frame == "ABSOLUTE_VALUE"
    } == {1.4, 1.5}


def test_v268_delta_amount_and_percent_are_changes_not_levels() -> None:
    signatures = _signatures(
        "Operating income decreased $97 million, or 38 percent, due to a lower "
        "operating margin rate and higher sales."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_BY",
        97_000_000.0,
        None,
        False,
    ) in signatures
    assert ("OPERATING_INCOME", "CHANGE_BY", 38.0, None, False) in signatures
    assert not any(
        concept in {"REVENUE", "OPERATING_MARGIN"}
        for concept, _, _, _, _ in signatures
    )
    revenue = _signatures(
        "Railway operating revenues of $3.0 billion, down $50 million, or 2%, "
        "on a volume decline of 4% year-over-year."
    )
    assert (
        "REVENUE",
        "CHANGE_TO",
        3_000_000_000.0,
        2.0,
        False,
    ) in revenue
    assert ("REVENUE", "CHANGE_BY", 50_000_000.0, None, False) in revenue
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 4.0, None, False) in revenue


def test_v268_railway_operating_income_alias_owns_its_values() -> None:
    signatures = _signatures(
        "Income from railway operations was $937 million, a decrease of $194 "
        "million, or 17%, compared to fourth quarter 2024 which included railway "
        "line sales of $53 million."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        937_000_000.0,
        17.0,
        False,
    ) in signatures
    assert (
        "OPERATING_INCOME",
        "CHANGE_BY",
        194_000_000.0,
        None,
        False,
    ) in signatures
    assert not any(concept == "REVENUE" for concept, _, _, _, _ in signatures)


def test_v268_guidance_cash_and_volume_roles_are_local() -> None:
    cash = _signatures(
        "Total available liquidity was $2.02 billion, which includes $0.66 billion "
        "in cash and cash equivalents plus $1.36 billion under credit facilities."
    )
    assert cash == {("CASH", "ABSOLUTE_VALUE", 660_000_000.0, None, True)}
    guidance = _frames(
        "Mobility service revenue growth for 2026 to be 2.5 to 3.0 percent."
    )
    assert any(
        frame.concept == "REVENUE_CHANGE_GUIDANCE"
        and frame.lower_value == 2.5
        and frame.upper_value == 3.0
        for frame in guidance
    )
    volume = _signatures("Revenue declined on a volume decline of 4% year-over-year.")
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 4.0, None, False) in volume


def test_v268_eps_firewall_does_not_bind_railway_line_sales() -> None:
    signatures = _signatures(
        "Diluted earnings per share were $2.87, down $0.36, or 11%, compared to "
        "2024 which included railway line sales."
    )
    assert not any(concept == "REVENUE" for concept, _, _, _, _ in signatures)


def test_v268_router_recovers_fragments_and_releases_causal_prose() -> None:
    tables = (
        "S. 52.5 6.0 n/a (14.1) International 6.4 6.1 n/a 2.4 Total reported 24.7 6.1",
        "Organic revenue growth Three months ended June 27, 2026 Revenue growth "
        "10% Acquisitions 5% Currency translation 1% Organic revenue growth 5%",
        "Ended 12/31/25 Consolidated Net Income $16,599 $17,608 Interest expense "
        "7,348 6,694 Depreciation 19,037 18,349 Consolidated Adjusted EBITDA "
        "$51,753 $49,997 Other 3,720 2,282",
    )
    for text in tables:
        assert any(
            route.route is BlockRoute.FLATTENED_TABLE
            for route in route_document_blocks_v268(_document(text))
        )
    prose = (
        "The increase was primarily due to higher sales of $475 million on one "
        "program, and $360 million due to the sales impact of another contract."
    )
    assert all(
        route.route is BlockRoute.PROSE
        for route in route_document_blocks_v268(_document(prose))
    )
