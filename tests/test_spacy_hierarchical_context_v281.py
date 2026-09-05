from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v281 import extract_text_kpis_v281, route_document_blocks_v281


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v281-hierarchical-context",
                "V281_HIERARCHICAL_CONTEXT_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _signatures(text: str):
    result = extract_text_kpis_v281(_document(f"<p>{text}</p>"))
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


def _routes(text: str) -> tuple[BlockRoute, ...]:
    return tuple(
        route.route
        for route in route_document_blocks_v281(_document(f"<p>{text}</p>"))
        if route.char_start is not None
    )


def test_v281_distant_outlook_does_not_promote_actual_segment_revenue() -> None:
    frames, _ = _signatures(
        "This gives us confidence in our increased outlook. Financial Highlights. "
        "The group reported revenue of $746 million, growth of 11% reported and "
        "10% core year-over-year."
    )
    assert {frame for frame in frames if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 746_000_000.0, 11.0, None, None, True),
        ("REVENUE", "CHANGE_TO", 746_000_000.0, 10.0, None, None, True),
    }


def test_v281_reported_and_core_growth_are_actual_not_guidance() -> None:
    frames, _ = _signatures(
        "Applied Markets Group reported third-quarter revenue of $346 million, "
        "growth of 7% reported and 7% core year-over-year."
    )
    assert {frame for frame in frames if "REVENUE" in frame[0]} == {
        ("REVENUE", "CHANGE_TO", 346_000_000.0, 7.0, None, None, True)
    }


def test_v281_margin_parenthetical_component_and_parallel_changes() -> None:
    frames, _ = _signatures(
        "Non-GAAP operating margin of 28.3% (including an approximately 110 basis "
        "point net benefit from tariff refunds), expanded by 320 basis points "
        "year-over-year and 190 basis points sequentially."
    )
    assert {frame for frame in frames if frame[0] == "OPERATING_MARGIN"} == {
        ("OPERATING_MARGIN", "CHANGE_TO", 28.3, 320.0, None, None, True),
        ("OPERATING_MARGIN", "CHANGE_BY", 110.0, None, None, None, True),
        ("OPERATING_MARGIN", "CHANGE_BY", 190.0, None, None, None, True),
    }


def test_v281_shipments_and_passenger_unit_revenue_are_typed_candidates() -> None:
    shipments, shipment_candidates = _signatures(
        "Total shipments increased 18 percent sequentially due to inventory repositioning."
    )
    assert "ACTIVITY_VOLUME" in shipment_candidates
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 18.0, None, None, None, True) in shipments
    unit_revenue, price_candidates = _signatures(
        "Passenger unit revenue for Atlantic was up 8.9%, Pacific up 15.1%, and "
        "Latin America up 6.6%."
    )
    assert "PRICE_REALIZATION" in price_candidates
    assert {frame for frame in unit_revenue if frame[0] == "PRICE_REALIZATION"} == {
        ("PRICE_REALIZATION", "CHANGE_BY", 8.9, None, None, None, True),
        ("PRICE_REALIZATION", "CHANGE_BY", 15.1, None, None, None, True),
        ("PRICE_REALIZATION", "CHANGE_BY", 6.6, None, None, None, True),
    }
    assert not {frame for frame in unit_revenue if frame[0] == "REVENUE"}


def test_v281_physical_production_and_shipment_guidance_ranges_are_aligned() -> None:
    frames, candidates = _signatures(
        "The company expects production and shipments to range between 2.4 and "
        "2.6 million metric tons, and between 2.6 and 2.8 million metric tons, respectively."
    )
    assert {"PRODUCTION", "ACTIVITY_VOLUME"} <= candidates
    assert {frame for frame in frames if frame[0] in {"PRODUCTION_GUIDANCE", "ACTIVITY_VOLUME_GUIDANCE"}} == {
        ("PRODUCTION_GUIDANCE", "RANGE_GUIDANCE", 2_500_000.0, None, 2_400_000.0, 2_600_000.0, True),
        ("ACTIVITY_VOLUME_GUIDANCE", "RANGE_GUIDANCE", 2_700_000.0, None, 2_600_000.0, 2_800_000.0, True),
    }


def test_v281_causal_volume_does_not_inherit_revenue_change() -> None:
    frames, _ = _signatures(
        "Third-party revenue decreased 3 percent on lower volumes and price from supply agreements."
    )
    assert {frame for frame in frames if frame[0] in {"REVENUE", "ACTIVITY_VOLUME", "PRICE_REALIZATION"}} == {
        ("REVENUE", "CHANGE_BY", 3.0, None, None, None, False)
    }


def test_v281_cash_use_dividend_and_shareholder_returns_are_not_cash_balance() -> None:
    for text in (
        "Cash used for investing activities was $203 million, primarily related to capital expenditures of $186 million.",
        "The company declared a quarterly cash dividend of $1.63 per share.",
        "Capital generation supported strong cash returns to shareholders of $3.5 billion.",
    ):
        frames, _ = _signatures(text)
        assert not {frame for frame in frames if frame[0] == "CASH"}
    capex, _ = _signatures(
        "Cash used for investing activities was $203 million, primarily related to capital expenditures of $186 million."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 186_000_000.0, None, None, None, True) in capex


def test_v281_cash_use_with_capex_is_prose_not_a_financial_grid() -> None:
    text = (
        "Cash used for investing activities was $203 million, primarily related to "
        "capital expenditures of $186 million and equity investment contributions of $40 million."
    )
    assert all(route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED} for route in _routes(text))


def test_v281_growth_ranges_and_multiple_actual_rates_keep_semantics() -> None:
    guidance, _ = _signatures(
        "In the third quarter, the company expects year-over-year revenue growth "
        "to be between 16.0% and 19.0%."
    )
    assert {frame for frame in guidance if "REVENUE" in frame[0]} == {
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 17.5, None, 16.0, 19.0, True)
    }
    actual, _ = _signatures(
        "Sales increased 13.0 percent on a reported basis and 4.8 percent on a comparable basis."
    )
    assert {frame for frame in actual if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_BY", 13.0, None, None, None, True),
        ("REVENUE", "CHANGE_BY", 4.8, None, None, None, True),
    }


def test_v281_adjusted_ebitda_comparison_and_booking_growth() -> None:
    ebitda, _ = _signatures(
        "Adjusted EBITDA in Q2 of $1.3 billion increased 21% compared to $1.0 billion last year."
    )
    assert {frame for frame in ebitda if "ADJUSTED_EBITDA" in frame[0]} == {
        ("ADJUSTED_EBITDA", "COMPARATIVE", 1_300_000_000.0, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 1_000_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "CHANGE_BY", 21.0, None, None, None, True),
    }
    bookings, _ = _signatures(
        "Nights and Seats Booked grew 10% year-over-year, while Bedroom Nights Booked grew over 12%."
    )
    assert {frame for frame in bookings if frame[0] == "ORDERS"} == {
        ("ORDERS", "CHANGE_BY", 10.0, None, None, None, True),
        ("ORDERS", "CHANGE_BY", 12.0, None, None, None, True),
    }


def test_v281_quantified_supply_is_activity_but_repositioning_sales_are_not_revenue() -> None:
    supply, candidates = _signatures("The company increased Experiences supply by nearly 80% year-over-year.")
    assert "ACTIVITY_VOLUME" in candidates
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 80.0, None, None, None, True) in supply
    securities, _ = _signatures(
        "Results reflected valuation increases on public equity securities, partially "
        "offset by losses on repositioning sales. Total return was 2.6%."
    )
    assert not {frame for frame in securities if "REVENUE" in frame[0]}


def test_v281_money_delta_is_not_prior_level_and_is_retained() -> None:
    frames, _ = _signatures(
        "Revenue of $615 million increased $52 million, or 9.2%, compared to the prior year quarter."
    )
    assert {frame for frame in frames if "REVENUE" in frame[0]} == {
        ("REVENUE", "CHANGE_TO", 615_000_000.0, 9.2, None, None, True),
        ("REVENUE", "CHANGE_BY", 52_000_000.0, None, None, None, True),
    }

    sequential, _ = _signatures(
        "Nutrition sales increased $127 million on a sequential basis compared to the first quarter of 2026."
    )
    assert {frame for frame in sequential if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_BY", 127_000_000.0, None, None, None, True)
    }


def test_v281_orders_level_and_change_are_bound_as_one_actual_frame() -> None:
    frames, _ = _signatures(
        "New bookings for the third quarter of fiscal 2026 were $19.32 billion, a decrease of 2%."
    )
    assert {frame for frame in frames if frame[0] == "ORDERS"} == {
        ("ORDERS", "CHANGE_TO", 19_320_000_000.0, 2.0, None, None, False)
    }


def test_v281_expects_growth_to_be_is_a_single_range() -> None:
    frames, _ = _signatures(
        "The company now expects revenue growth to be 4% to 5% in local currency."
    )
    assert {frame for frame in frames if "REVENUE" in frame[0]} == {
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 4.5, None, 4.0, 5.0, True)
    }


def test_v281_revenue_comparison_keeps_level_percentage_and_money_delta() -> None:
    frames, _ = _signatures(
        "Total revenues of $18.6 billion were $2.0 billion or 11.8% higher than the prior year quarter."
    )
    assert {frame for frame in frames if frame[0] == "REVENUE"} == {
        ("REVENUE", "CHANGE_TO", 18_600_000_000.0, 11.8, None, None, True),
        ("REVENUE", "CHANGE_BY", 2_000_000_000.0, None, None, None, True),
    }


def test_v281_revenue_after_unrelated_amount_owns_its_local_level() -> None:
    frames, _ = _signatures(
        "Adjusted net income of $13 million was $2 million higher. Dealer Services "
        "generated revenue of $147 million, relatively flat compared to the prior year."
    )
    assert {frame for frame in frames if "REVENUE" in frame[0]} == {
        ("REVENUE", "ABSOLUTE_VALUE", 147_000_000.0, None, None, None, True)
    }


def test_v281_bare_outlook_ranges_parallel_rates_and_margin_changes() -> None:
    revenue, _ = _signatures("Revenue growth of 5% to 6%.")
    assert {frame for frame in revenue if "REVENUE" in frame[0]} == {
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 5.5, None, 5.0, 6.0, True)
    }
    orders, _ = _signatures("Employer Services new business bookings growth of 4% to 7%.")
    assert {frame for frame in orders if "ORDERS" in frame[0]} == {
        ("ORDERS_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 5.5, None, 4.0, 7.0, True)
    }
    margins, _ = _signatures(
        "Segment margin decreased 100 basis points for the quarter and decreased "
        "110 basis points for the fiscal year."
    )
    assert {frame for frame in margins if frame[0] == "OPERATING_MARGIN"} == {
        ("OPERATING_MARGIN", "CHANGE_BY", 100.0, None, None, None, False),
        ("OPERATING_MARGIN", "CHANGE_BY", 110.0, None, None, None, False),
    }


def test_v281_ebitda_growth_and_capex_plan_are_guidance() -> None:
    ebitda, _ = _signatures(
        "The company is reaffirming its expectation for annualized growth in "
        "Adjusted EBITDA of 5% to 7% through 2027, from a prior base of $2.6 billion."
    )
    assert {frame for frame in ebitda if "ADJUSTED_EBITDA" in frame[0]} == {
        ("ADJUSTED_EBITDA_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 6.0, None, 5.0, 7.0, True)
    }
    capex, _ = _signatures("We are on track with our $1.4 billion capex plan at our utilities.")
    assert {frame for frame in capex if "CAPEX" in frame[0]} == {
        ("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 1_400_000_000.0, None, None, None, True)
    }


def test_v281_capex_plan_does_not_steal_later_net_income_change() -> None:
    frames, _ = _signatures(
        'We are on track with our $1.4 billion 2025 capex plan at our US utilities, '
        'which will deliver important upgrades to our customers." Q3 2025 Financial Results '
        "Third quarter 2025 Net Income was $517 million, an increase of $302 million "
        "compared to third quarter 2024."
    )
    assert {frame for frame in frames if "CAPEX" in frame[0]} == {
        ("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 1_400_000_000.0, None, None, None, True)
    }


def test_v281_router_distinguishes_numeric_sentences_and_grids() -> None:
    for prose in (
        "Non-GAAP operating margin of 28.3%, expanded by 320 basis points year-over-year.",
        "Adjusted EBITDA of $1.3 billion increased 21% compared to $1.0 billion last year.",
        "The company expects revenue growth to be 4% to 5% in local currency.",
    ):
        assert all(route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED} for route in _routes(prose))
    for grid in (
        "Net Debt and Adjusted Net Debt June 30 2026 December 31 2025 Short-term borrowings $0 $9 Long-term debt 2224 2438 Total debt 2225 2448 Cash 1352 1597 Net debt 873 851 Adjusted net debt 1446 1464",
        "Other Corporate FY 2026E Capital expenditures $500 million Depreciation and amortization $660 - $680 million Adjusted effective tax rate (50)% - 30% Corporate adjusted EBITDA",
    ):
        assert any(route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED} for route in _routes(grid))
