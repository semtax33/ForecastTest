from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v285 import extract_text_kpis_v285, route_document_blocks_v285


def _document(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<html><body><p>{text}</p></body></html>".encode(), "test://v285", "V285", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v285(_document(text))
    return {(f.concept, f.frame.value, f.value, f.change, f.lower_value, f.upper_value, f.polarity.positive) for f in result.extraction.frames}, {c.metric.concept for c in result.candidates}


def test_v285_monetary_revenue_growth_is_change() -> None:
    frames, _ = _frames("Revenue growth in defense systems of $35.9 million was attributable to higher program revenue.")
    assert {x for x in frames if x[0] == "REVENUE"} == {("REVENUE", "CHANGE_BY", 35_900_000.0, None, None, None, True)}


def test_v285_growth_components_are_distinct_revenue_facts() -> None:
    frames, _ = _frames("Revenue increased 8.4% to $2.3 billion, including organic growth of 6.1% and acquisition growth of 2.3%.")
    assert {x for x in frames if x[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 2_300_000_000.0, 8.4, None, None, True),
        ("REVENUE", "CHANGE_BY", 6.1, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 2.3, None, None, None, True),
    }


def test_v285_debt_actions_override_cash_surface_role() -> None:
    prepaid, candidates = _frames("The company used $83 million of cash proceeds to prepay the outstanding term loan balance.")
    assert "DEBT" in candidates
    assert {x for x in prepaid if x[0] in {"CASH", "DEBT"}} == {("DEBT", "CHANGE_BY", 83_000_000.0, None, None, None, False)}
    borrowed, _ = _frames("The company secured an additional $100 million of incremental borrowings under its term loan.")
    assert {x for x in borrowed if x[0] == "DEBT"} == {("DEBT", "CHANGE_BY", 100_000_000.0, None, None, None, True)}


def test_v285_segment_ebitda_highlight_is_prose_with_two_roles() -> None:
    text = "Adjusted Segment EBITDA increased 13% to $61.4 million and margin expanded 180 basis points to 20.4% driven by growth."
    routes = {r.route for r in route_document_blocks_v285(_document(text)) if r.char_start is not None}
    assert routes.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    frames, candidates = _frames(text)
    assert {"ADJUSTED_EBITDA", "ADJUSTED_EBITDA_MARGIN"} <= candidates
    assert {x for x in frames if "ADJUSTED_EBITDA" in x[0]} == {
        ("ADJUSTED_EBITDA", "CHANGE_TO", 61_400_000.0, 13.0, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "CHANGE_TO", 20.4, 180.0, None, None, True),
    }


def test_v285_all_cash_per_share_is_not_cash_balance() -> None:
    frames, _ = _frames("The buyer will acquire 100% of the company in an all-cash transaction for $150 per share.")
    assert not {x for x in frames if x[0] == "CASH"}


def test_v285_two_value_growth_keeps_change_to_without_prior_emission() -> None:
    frames, _ = _frames("Net product sales were $125 million, an increase of 30% compared to $96 million last year.")
    assert {x for x in frames if "REVENUE" in x[0]} == {("REVENUE", "CHANGE_TO", 125_000_000.0, 30.0, None, None, True)}


def test_v285_three_value_two_basis_comparison() -> None:
    frames, _ = _frames("GAAP net product sales were $183 million, up 9% compared to GAAP net product sales of $168 million, and up 10% compared to adjusted net product sales of $166 million.")
    assert {x for x in frames if "REVENUE" in x[0]} == {
        ("REVENUE", "COMPARATIVE", 183_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 168_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 166_000_000.0, None, None, None, True),
    }


def test_v285_long_term_ambition_is_revenue_guidance() -> None:
    frames, _ = _frames("Both franchises are on track to achieve our long-term ambition of approximately $1.7 billion in annual net sales in 2028.")
    assert {x for x in frames if "REVENUE" in x[0]} == {("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 1_700_000_000.0, None, None, None, True)}


def test_v285_highlight_list_binds_revenue_and_both_margin_families() -> None:
    frames, _ = _frames("Q2 Highlights: Revenue of $215.2 million · GAAP Gross Margin of 42.4%, and Non-GAAP Gross Margin of 42.7% · GAAP Operating Margin of 9.4% and Non-GAAP Operating Margin of 14.7%.")
    assert {x for x in frames if x[0] in {"REVENUE", "GROSS_MARGIN", "OPERATING_MARGIN"}} == {
        ("REVENUE", "ABSOLUTE_VALUE", 215_200_000.0, None, None, None, True),
        ("GROSS_MARGIN", "ABSOLUTE_VALUE", 42.4, None, None, None, True),
        ("GROSS_MARGIN", "ABSOLUTE_VALUE", 42.7, None, None, None, True),
        ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 9.4, None, None, None, True),
        ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 14.7, None, None, None, True),
    }


def test_v285_gross_margin_range_is_guidance() -> None:
    frames, _ = _frames("We expect overall gross margin to remain in the range of 42% to 48% depending on product mix.")
    assert {x for x in frames if "GROSS_MARGIN" in x[0]} == {("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 45.0, None, 42.0, 48.0, True)}


def test_v285_compact_target_ranges_bind_revenue_and_ebitda() -> None:
    frames, candidates = _frames("Targeting $5-150M revenue and $0-$25M EBITDA adjusted.")
    assert {"REVENUE", "ADJUSTED_EBITDA"} <= candidates
    assert {x for x in frames if "GUIDANCE" in x[0]} == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 77_500_000.0, None, 5_000_000.0, 150_000_000.0, True),
        ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 12_500_000.0, None, 0.0, 25_000_000.0, True),
    }


def test_v285_absolute_operating_metrics_do_not_become_changes_or_revenue() -> None:
    otif, _ = _frames("Achieved 100% OTIF performance while restoring predictable supply.")
    assert {x for x in otif if x[0] == "ACTIVITY_VOLUME"} == {("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 100.0, None, None, None, True)}
    margin, _ = _frames("EBITDA Margin 14% Accretive earnings and record sales.")
    assert {x for x in margin if x[0] in {"ADJUSTED_EBITDA_MARGIN", "REVENUE"}} == {("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 14.0, None, None, None, True)}


def test_v285_layout_damaged_ttm_fragment_abstains() -> None:
    frames, _ = _frames("EBITDA TTM Increase / $8.2M100.2% Performance Q32025 9.2 Increase in TTM Revenue TTM Increase / $7.0M Performance Q22026 vs Q12026 6 Increase in TTM Adj.")
    assert not {x for x in frames if x[0] in {"REVENUE", "ADJUSTED_EBITDA"}}
