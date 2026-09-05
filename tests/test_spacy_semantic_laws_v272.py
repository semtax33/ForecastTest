from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v272 import (
    V272_RULES,
    extract_text_kpis_v272,
    route_document_blocks_v272,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v272-semantic-laws",
                "V272_SEMANTIC_LAW_TEST",
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
        )
        for frame in extract_text_kpis_v272(_document(f"<p>{text}</p>")).extraction.frames
    }


def test_v272_laws_are_spacy_dsl_and_issuer_neutral() -> None:
    assert len(V272_RULES) == 16
    assert all(rule.pattern and rule.rule_id.startswith("v272.") for rule in V272_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V272_RULES)


def test_v272_abbreviated_margin_range_and_nearby_guidance() -> None:
    document = _document(
        "<p>Financial Outlook For the third quarter, we expect:</p>"
        "<p>Revenue of approximately $3.3 billion; •</p>"
        "<p>Non-GAAP operating margin of 48 - 49%; and •</p>"
    )
    frames = {
        (frame.concept, frame.frame.value, frame.value, frame.lower_value, frame.upper_value)
        for frame in extract_text_kpis_v272(document).extraction.frames
    }
    assert ("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 3_300_000_000.0, None, None) in frames
    assert ("OPERATING_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 48.5, 48.0, 49.0) in frames


def test_v272_multi_metric_value_ownership_firewall() -> None:
    signatures = _signatures(
        "Our quarter had revenue up 37.7% and EPS up 39.7%."
    )
    assert ("REVENUE", "CHANGE_BY", 37.7, None, None, None) in signatures
    assert not any(concept == "REVENUE" and value == 39.7 for concept, _, value, *_ in signatures)
    costs = _signatures(
        "The reimbursement is recognized in fees revenue. Technology and facility costs "
        "of $205.9 million increased $10.9 million."
    )
    assert not any(concept == "REVENUE" and value == 205_900_000.0 for concept, _, value, *_ in costs)


def test_v272_revenue_change_ownership_and_split_percent() -> None:
    multi = _signatures(
        "Revenue of $3.036 billion, an increase of 12.1% compared to the first quarter, "
        "and an increase of 37.7% from the prior-year quarter."
    )
    assert ("REVENUE", "CHANGE_TO", 3_036_000_000.0, 12.1, None, None) in multi
    assert ("REVENUE", "CHANGE_BY", 37.7, None, None, None) in multi
    split = _signatures(
        "Global FX net revenue of $27.6 million increased $4.0 million, or 17 perce nt, "
        "from the prior-year quarter."
    )
    assert ("REVENUE", "CHANGE_TO", 27_600_000.0, 17.0, None, None) in split
    assert ("REVENUE", "CHANGE_BY", 4_000_000.0, None, None, None) in split


def test_v272_comparative_current_prior_roles() -> None:
    sales = _signatures(
        "Device sales were $1.1 billion, an increase of 12% compared to $968 million "
        "in the same period last year."
    )
    assert ("REVENUE", "COMPARATIVE", 1_100_000_000.0, None, None, None) in sales
    assert ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 968_000_000.0, None, None, None) in sales
    margins = _signatures("Segment operating margin increased to 15.1% from 13.3% a year ago.")
    assert ("OPERATING_MARGIN", "COMPARATIVE", 15.1, None, None, None) in margins
    assert ("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 13.3, None, None, None) in margins
    compared = _signatures("Enterprise operating margin was 22.3% compared to 19.5% a year ago.")
    assert ("OPERATING_MARGIN", "COMPARATIVE", 22.3, None, None, None) in compared
    assert ("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 19.5, None, None, None) in compared


def test_v272_debt_delivered_and_higher_patterns() -> None:
    debt = _signatures("We improved flexibility by reducing net debt by approximately $170 million.")
    assert ("DEBT", "CHANGE_BY", 170_000_000.0, None, None, None) in debt
    delivered = _signatures("MIS delivered $1.3 billion in revenue, up 25% year-over-year.")
    assert ("REVENUE", "CHANGE_TO", 1_300_000_000.0, 25.0, None, None) in delivered
    higher = _signatures("Net sales of $3,274 million, 24% higher than the prior-year quarter.")
    assert ("REVENUE", "CHANGE_TO", 3_274_000_000.0, 24.0, None, None) in higher


def test_v272_margin_change_to_owns_level_and_delta() -> None:
    expanded = _signatures(
        "Operating margin was 47.9%; Adjusted Operating Margin expanded by 440 bps to 55.3%."
    )
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 47.9, None, None, None) in expanded
    assert ("OPERATING_MARGIN", "CHANGE_TO", 55.3, 440.0, None, None) in expanded
    assert not any(frame == "ABSOLUTE_VALUE" and value == 55.3 for _, frame, value, *_ in expanded)
    up = _signatures("Adjusted operating margin of 22.6%, up 410 basis points year over year.")
    assert ("OPERATING_MARGIN", "CHANGE_TO", 22.6, 410.0, None, None) in up


def test_v272_guidance_and_respectively_alignment() -> None:
    guidance = _signatures(
        "Expects full year net sales of $14,000 million and organic sales growth of 31%, "
        "each at the midpoint of guidance."
    )
    assert ("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 14_000_000_000.0, None, None, None) in guidance
    assert ("REVENUE_GUIDANCE", "CHANGE_BY", 31.0, None, None, None) in guidance
    aligned = _signatures(
        "Operating profit of $638 million increased $196 million and adjusted operating "
        "profit of $738 million increased $249 million, up 44% and 51%, respectively."
    )
    for expected in (
        ("OPERATING_INCOME", "CHANGE_TO", 638_000_000.0, 44.0, None, None),
        ("OPERATING_INCOME", "CHANGE_BY", 196_000_000.0, None, None, None),
        ("OPERATING_INCOME", "CHANGE_TO", 738_000_000.0, 51.0, None, None),
        ("OPERATING_INCOME", "CHANGE_BY", 249_000_000.0, None, None, None),
    ):
        assert expected in aligned


def test_v272_risk_enumerations_are_not_tables() -> None:
    document = _document(
        "<p>Risks and uncertainties include economic conditions; regulatory changes; "
        "risk of supply disruption; political conditions; cybersecurity incidents; "
        "failure to retain personnel; and other future events.</p>"
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v272(document)
    )
