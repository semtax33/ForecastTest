from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v262 import (
    BlockRoute,
    extract_text_kpis_v262,
    route_document_blocks_v262,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<p>{text}</p>".encode(),
                "memory://v262",
                "V262",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            "TEST",
            "IR",
            "EARNINGS_RELEASE",
            "2026-09-04",
            "2026Q3",
        ),
    )


def _frames(text: str):
    return extract_text_kpis_v262(_document(text)).extraction.frames


def _signatures(text: str):
    return {
        (
            frame.concept,
            frame.frame.value,
            round(float(frame.value or 0), 3),
            frame.change,
            frame.lower_value,
            frame.upper_value,
        )
        for frame in _frames(text)
    }


def test_growth_and_margin_guidance_ranges_are_semantic_frames() -> None:
    signatures = _signatures(
        "Fiscal 2027 consolidated outlook includes revenue growth of 5% to 6%, "
        "adjusted EBIT margin expansion of 70 to 90 basis points."
    )
    assert ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 5.5, None, 5.0, 6.0) in signatures
    assert (
        "OPERATING_MARGIN_GUIDANCE",
        "RANGE_GUIDANCE",
        80.0,
        None,
        70.0,
        90.0,
    ) in signatures
    result = extract_text_kpis_v262(_document(
        "Adjusted EBIT margin expansion of 70 to 90 basis points."
    ))
    assert any(candidate.metric.concept == "OPERATING_MARGIN" for candidate in result.candidates)


def test_money_guidance_range_preserves_scaled_endpoints() -> None:
    assert (
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        5_900_000_000.0,
        None,
        5_650_000_000.0,
        6_150_000_000.0,
    ) in _signatures(
        "Third quarter outlook is for revenue in the range of $5.65 billion to $6.15 billion."
    )


def test_absolute_revenue_capex_and_cash_reduction_are_bound() -> None:
    assert ("REVENUE", "ABSOLUTE_VALUE", 5_460_000_000.0, None, None, None) in _signatures(
        "TI reported second quarter revenue of $5.46 billion."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 138_700_000.0, None, None, None) in _signatures(
        "Capital investments of $138.7 million and R&D expenses of $114.3 million."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 3_300_000_000.0, None, None, None) in _signatures(
        "We invested $3.9 billion in R&D and invested $3.3 billion in capital expenditures."
    )
    assert ("CASH", "CHANGE_BY", 250_000_000.0, None, None, None) in _signatures(
        "$250 million in fees are reflected as a reduction to cash and cash equivalents."
    )


def test_metric_ownership_blocks_headline_revenue_from_pretax_income_values() -> None:
    frames = _frames(
        "PACCAR Parts Achieves Record Quarterly Revenues. PACCAR Parts earned "
        "pre-tax income of $417.0 million compared to $416.5 million last year."
    )
    assert not any(frame.concept.endswith("REVENUE") for frame in frames)


def test_adjacent_ebit_and_margin_clauses_do_not_cross_bind() -> None:
    signatures = _signatures(
        "Adjusted EBIT increased 10% to $5.9 billion for the year, and adjusted "
        "EBIT margin increased 80 basis points to 26.8%."
    )
    assert ("EBIT", "CHANGE_TO", 5_900_000_000.0, 10.0, None, None) in signatures
    assert (
        "OPERATING_MARGIN",
        "CHANGE_TO",
        26.8,
        80.0,
        None,
        None,
    ) in signatures
    assert not any(
        concept == "EBIT" and change in {80.0, 26.8}
        for concept, _, _, change, _, _ in signatures
    )


def test_table_fragments_and_dense_narrative_are_separated() -> None:
    table_text = (
        "Quarter Ended June 30, 2025 2026 Reported Underlying Sales "
        "Control Systems $1,120 $1,199 7% 7% Total $4,553 $4,873 7% 6% "
        "Page 7 Table 4 cont."
    )
    assert any(
        route.route is BlockRoute.FLATTENED_TABLE
        for route in route_document_blocks_v262(_document(table_text))
    )
    prose_text = (
        "Second-quarter revenues totaled $15.0 billion, an increase of "
        "$381 million, or 3%, compared to the prior-year quarter."
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v262(_document(prose_text))
    )
    assert ("REVENUE", "CHANGE_TO", 15_000_000_000.0, 3.0, None, None) in _signatures(prose_text)


def test_negative_basis_point_change_needs_no_verb() -> None:
    assert (
        "GROSS_MARGIN",
        "CHANGE_BY",
        77.0,
        None,
        None,
        None,
    ) in _signatures("GROSS MARGIN -77 basis points vs. last year")
    frame = next(frame for frame in _frames("GROSS MARGIN -77 basis points vs. last year"))
    assert frame.polarity.positive is False


def test_second_organic_growth_rate_does_not_inherit_revenue_level() -> None:
    signatures = _signatures(
        "Revenues increased 7% to $21.9 billion and 6% on an organic constant currency basis."
    )
    assert ("REVENUE", "CHANGE_TO", 21_900_000_000.0, 7.0, None, None) in signatures
    assert ("REVENUE", "CHANGE_BY", 6.0, None, None, None) in signatures
    assert ("REVENUE", "CHANGE_TO", 21_900_000_000.0, 6.0, None, None) not in signatures


def test_comparison_does_not_also_emit_current_value_as_absolute() -> None:
    signatures = _signatures(
        "PFS revenues were $1.09 billion compared to $1.08 billion last year."
    )
    assert ("REVENUE", "COMPARATIVE", 1_090_000_000.0, None, None, None) in signatures
    assert ("REVENUE", "ABSOLUTE_VALUE", 1_090_000_000.0, None, None, None) not in signatures


def test_eps_range_does_not_bind_to_earlier_ebit_anchor() -> None:
    frames = _frames(
        "Outlook includes adjusted EBIT margin expansion of 70 to 90 basis points, "
        "and adjusted diluted EPS growth of 9% to 11%."
    )
    assert not any(frame.concept == "EBIT_GUIDANCE" for frame in frames)


def test_long_non_gaap_definition_is_not_a_table_but_reconciliation_is() -> None:
    prose = (
        "We delivered results at the high end of guidance for revenue growth and margin expansion. "
        "Adjusted EBIT, adjusted EBIT margin, adjusted net earnings, adjusted diluted earnings per "
        "share, adjusted effective tax rate and organic constant currency are all non-GAAP measures."
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v262(_document(prose))
    )
    table = (
        "As reported (GAAP) $916 $198 $718 $0 $718 $1.28 Amortization 253 1 59 194 0 194 0.35 "
        "Adjusted (non-GAAP) $1,218 $258 $960 $0 $960 $1.71"
    )
    assert any(
        route.route is BlockRoute.FLATTENED_TABLE
        for route in route_document_blocks_v262(_document(table))
    )
