from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v282 import extract_text_kpis_v282, route_document_blocks_v282


def _document(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<html><body><p>{text}</p></body></html>".encode(), "test://v282", "V282", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v282(_document(text))
    return {
        (frame.concept, frame.frame.value, frame.value, frame.change, frame.lower_value, frame.upper_value, frame.polarity.positive)
        for frame in result.extraction.frames
    }, {candidate.metric.concept for candidate in result.candidates}


def _routes(text: str):
    return {
        route.route
        for route in route_document_blocks_v282(_document(text))
        if route.char_start is not None
    }


def test_v282_margin_units_guidance_and_negative_polarity() -> None:
    actual, _ = _frames("GAAP operating margin was 7%, down 8 percentage points from last year.")
    assert {item for item in actual if item[0] == "OPERATING_MARGIN"} == {
        ("OPERATING_MARGIN", "CHANGE_TO", 7.0, 800.0, None, None, False)
    }
    compact, _ = _frames("Gross profit increased by $8 million and gross margin decreased by 0.3pp.")
    assert {item for item in compact if item[0] == "GROSS_MARGIN"} == {
        ("GROSS_MARGIN", "CHANGE_BY", 30.0, None, None, None, False)
    }
    guidance, _ = _frames("Guidance includes adjusted operating margin of around 10.5-11%.")
    assert {item for item in guidance if "OPERATING_MARGIN" in item[0]} == {
        ("OPERATING_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 10.75, None, 10.5, 11.0, True)
    }


def test_v282_adjusted_ebit_margin_and_ebit_component_pairs() -> None:
    margin, candidates = _frames("Adjusted EBIT margins of 11.0% were 220 basis points higher than the prior year.")
    assert "OPERATING_MARGIN" in candidates
    assert ("OPERATING_MARGIN", "CHANGE_TO", 11.0, 220.0, None, None, True) in margin
    ebit, _ = _frames(
        "Adjusted EBIT of $2,813 million was 63% higher than last year, including "
        "$842 million of acquired EBIT, which represents growth of 49%."
    )
    assert {item for item in ebit if item[0] == "EBIT"} == {
        ("EBIT", "CHANGE_TO", 2_813_000_000.0, 63.0, None, None, True),
        ("EBIT", "CHANGE_TO", 842_000_000.0, 49.0, None, None, True),
    }


def test_v282_respectively_and_client_flow_ownership() -> None:
    ebitda, _ = _frames("Adjusted EBITDA and Economic EPS grew 44% and 54%, respectively.")
    assert {item for item in ebitda if item[0] == "ADJUSTED_EBITDA"} == {
        ("ADJUSTED_EBITDA", "CHANGE_BY", 44.0, None, None, None, True)
    }
    flows, candidates = _frames(
        "Net client cash flows were $13 billion in the quarter and $35 billion year to date, "
        "while alternative strategies generated net inflows of $29 billion and $58 billion."
    )
    assert "ACTIVITY_VOLUME" in candidates
    assert {item for item in flows if item[0] == "ACTIVITY_VOLUME"} == {
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 13_000_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 35_000_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 29_000_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 58_000_000_000.0, None, None, None, True),
    }


def test_v282_revenue_roles_ranges_and_composition() -> None:
    decline, _ = _frames("Americas Revenue was $2.6 billion, a 20% decrease from the prior year.")
    assert {item for item in decline if item[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 2_600_000_000.0, 20.0, None, None, False)
    }
    guidance, _ = _frames("The company expects annual revenue between $200 million to $225 million.")
    assert {item for item in guidance if "REVENUE" in item[0]} == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 212_500_000.0, None, 200_000_000.0, 225_000_000.0, True)
    }
    composition, _ = _frames(
        "Revenues were $327 million, comprised of $272 million from Gathering and "
        "$79 million from Water Handling, net of $23 million of amortization."
    )
    assert {item for item in composition if item[0] == "REVENUE"} == {
        ("REVENUE", "ABSOLUTE_VALUE", 327_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 272_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 79_000_000.0, None, None, None, True),
    }
    delta, _ = _frames("Net product revenues increased $106 million compared with the prior quarter.")
    assert {item for item in delta if item[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_BY", 106_000_000.0, None, None, None, True)
    }


def test_v282_revenue_driver_boundaries_and_respectively() -> None:
    rent, candidates = _frames(
        "Core revenues increased 2.4% to $735.8 million, driven by a 2.8% increase "
        "in Average Monthly Realized Rent per property and a 50 basis point decrease in occupancy."
    )
    assert "PRICE_REALIZATION" in candidates
    assert {item for item in rent if item[0] in {"REVENUE", "PRICE_REALIZATION"}} == {
        ("REVENUE", "CHANGE_TO", 735_800_000.0, 2.4, None, None, True),
        ("PRICE_REALIZATION", "CHANGE_BY", 2.8, None, None, None, True),
    }
    preposed, _ = _frames("Growth was driven by a 2.7% increase in core revenues and a 0.7% decrease in expenses.")
    assert {item for item in preposed if item[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_BY", 2.7, None, None, None, True)
    }


def test_v282_product_revenue_respectively_and_share_scaling() -> None:
    revenue, _ = _frames(
        "Product revenues for A and B were $90 million and $52 million, respectively, "
        "together representing $142 million in total product revenues and 11% growth."
    )
    assert {item for item in revenue if item[0] == "REVENUE"} == {
        ("REVENUE", "ABSOLUTE_VALUE", 90_000_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 52_000_000.0, None, None, None, True),
        ("REVENUE", "CHANGE_TO", 142_000_000.0, 11.0, None, None, True),
    }
    shares, _ = _frames(
        "Dilutive weighted-average common shares outstanding for the three months ended June 30, 2026 and 2025 "
        "would be 138,281 and 137,089 thousand shares, respectively."
    )
    assert {item for item in shares if "SHARES" in item[0]} == {
        ("SHARES", "COMPARATIVE", 138_281_000.0, None, None, None, True),
        ("PRIOR_YEAR_SHARES", "COMPARATIVE", 137_089_000.0, None, None, None, True),
    }


def test_v282_cash_and_revenue_false_ownership_guards() -> None:
    cash, _ = _frames("Unencumbered cash and Agency MBS totaled $7.5 billion, representing 62% of equity.")
    assert not {item for item in cash if item[0] == "CASH"}
    margin, _ = _frames("Adjusted operating margin on net service revenue was 14.3%, an increase of 240 basis points.")
    assert not {item for item in margin if item[0] == "REVENUE"}
    guidance, _ = _frames(
        "Guidance calls for unchanged sales growth and adjusted operating margin around 10.5-11%."
    )
    assert not {item for item in guidance if "REVENUE" in item[0]}


def test_v282_highlights_composite_supersedes_standalone_ebitda_change() -> None:
    frames, _ = _frames(
        "Highlights: Gathering and compression volumes increased 19% and 17%, respectively; "
        "Adjusted EBITDA was $289 million, a 2% increase; Capital expenditures were $47 million."
    )
    assert {item for item in frames if item[0] == "ADJUSTED_EBITDA"} == {
        ("ADJUSTED_EBITDA", "CHANGE_TO", 289_000_000.0, 2.0, None, None, True)
    }


def test_v282_explicit_prior_revenue_is_retained_with_change_to() -> None:
    frames, _ = _frames(
        "Core revenues increased 2.4% to $735.8 million, compared to $718.5 million in the prior year."
    )
    assert {item for item in frames if "REVENUE" in item[0]} == {
        ("REVENUE", "CHANGE_TO", 735_800_000.0, 2.4, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 718_500_000.0, None, None, None, True),
    }


def test_v282_table_and_highlights_upper_context_routes() -> None:
    pipeline = _routes(
        "Development Pipeline Summary Lots for Future Delivery Market Number of Properties "
        "Phoenix 163 $394,000 $2,280 Tampa 145 $398,000 $2,630 Total 308 $396,000 $2,450"
    )
    assert BlockRoute.FLATTENED_TABLE in pipeline or BlockRoute.MIXED in pipeline
    net_debt = _routes(
        "Reconciliation of net debt ($ million) June 30 2025 June 30 2026 Cash and cash equivalents "
        "827 1115 Short-term debt 116 135 Long-term debt 13841 13862 Net debt 13271 12897"
    )
    assert BlockRoute.FLATTENED_TABLE in net_debt or BlockRoute.MIXED in net_debt
    highlights = _routes(
        "Highlights: Gathering and compression volumes increased 19% and 17%, respectively; "
        "Adjusted EBITDA was $289 million, a 2% increase; Capital expenditures were $47 million."
    )
    assert highlights.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
