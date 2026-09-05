from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v286 import extract_text_kpis_v286, route_document_blocks_v286


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "test://v286", "V286", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v286(_doc(text))
    return {(f.concept, f.frame.value, f.value, f.change, f.lower_value, f.upper_value, f.polarity.positive) for f in result.extraction.frames}, {c.metric.concept for c in result.candidates}


def test_v286_multi_clause_actual_and_outlook_ownership() -> None:
    frames, _ = _frames("Recurring revenue grew 54% year-over-year. We are raising long-term annual revenue outlook to $600 million from $500 million and expect the semiconductor business to reach $200 million in annual revenue.")
    assert {x for x in frames if "REVENUE" in x[0]} == {
        ("REVENUE", "CHANGE_BY", 54.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 600_000_000.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 200_000_000.0, None, None, None, True),
    }


def test_v286_comparative_revenue_without_percent() -> None:
    frames, _ = _frames("Revenue was $96.1 million as compared to $104.8 million in the first quarter.")
    assert {x for x in frames if "REVENUE" in x[0]} == {
        ("REVENUE", "COMPARATIVE", 96_100_000.0, None, None, None, True),
        ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 104_800_000.0, None, None, None, True),
    }


def test_v286_exclusion_loss_and_ebitda_loss() -> None:
    no_fact, _ = _frames("Excluding revenue from an agreement, net loss was $29.5 million.")
    assert not no_fact
    loss, _ = _frames("Excluding revenue from an agreement, Adjusted EBITDA was a loss of $11.1 million.")
    assert {x for x in loss if x[0] in {"REVENUE", "ADJUSTED_EBITDA"}} == {("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 11_100_000.0, None, None, None, False)}


def test_v286_activity_count_and_delta_to_revenue() -> None:
    volume, _ = _frames("Test volume increased 43% to 36,111 tests delivered.")
    assert {x for x in volume if x[0] == "ACTIVITY_VOLUME"} == {("ACTIVITY_VOLUME", "CHANGE_TO", 36_111.0, 43.0, None, None, True)}
    revenue, _ = _frames("Rental revenue increased $9.5 million, or 54.3%, to $27.0 million.")
    assert {x for x in revenue if x[0] == "REVENUE"} == {("REVENUE", "CHANGE_TO", 27_000_000.0, 54.3, None, None, True)}


def test_v286_backlog_cash_and_projected_revenue_roles() -> None:
    facts, _ = _frames("Current effective backlog is $100.6 million. Total cash was $116.5 million compared to $37.1 million.")
    assert facts == {
        ("BACKLOG", "ABSOLUTE_VALUE", 100_600_000.0, None, None, None, True),
        ("CASH", "COMPARATIVE", 116_500_000.0, None, None, None, True),
        ("PRIOR_YEAR_CASH", "COMPARATIVE", 37_100_000.0, None, None, None, True),
    }
    projected, _ = _frames("Record backlog of over $100 million provides visibility into projected fiscal 2027 revenue of $130 million to $150 million, representing expected growth of 160% to 200%.")
    assert projected == {
        ("BACKLOG", "ABSOLUTE_VALUE", 100_000_000.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 140_000_000.0, None, 130_000_000.0, 150_000_000.0, True),
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 180.0, None, 160.0, 200.0, True),
    }


def test_v286_revenue_share_ratio_does_not_become_growth_guidance() -> None:
    ratio, _ = _frames("We expect non-GAAP net income to be 18% to 22% of total revenue.")
    assert not ratio
    composition, _ = _frames("Subscription revenue constituted 91% of total revenue.")
    assert composition == {("REVENUE", "COMPOSITION", 91.0, None, None, None, True)}


def test_v286_margin_and_ebitda_comparisons() -> None:
    margin, _ = _frames("Gross margin was 63.5% compared to 61.7% in the prior-year period.")
    assert margin == {
        ("GROSS_MARGIN", "COMPARATIVE", 63.5, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 61.7, None, None, None, True),
    }
    ebitda, _ = _frames("Adjusted EBITDA was $132.0 million compared to $136.4 million, a decrease of 3.2%.")
    assert ebitda == {("ADJUSTED_EBITDA", "CHANGE_TO", 132_000_000.0, 3.2, None, None, False)}


def test_v286_outlook_and_headline_roles() -> None:
    outlook, _ = _frames("Fiscal 2027 Outlook: subscription revenue growth guidance to at least 32% and total revenue to be $368 million to $373 million.")
    assert outlook == {
        ("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 370_500_000.0, None, 368_000_000.0, 373_000_000.0, True),
    }
    headline = "ANNOUNCES RECORD REVENUE OF $87.7M. Quarter Adjusted EBITDA of 20.8%. Raises Guidance: Total Revenue Range to $368M to $373M and Subscription Revenue Growth to At Least 32%."
    routes = {r.route for r in route_document_blocks_v286(_doc(headline)) if r.char_start is not None}
    assert routes.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    frames, candidates = _frames(headline)
    assert "ADJUSTED_EBITDA_MARGIN" in candidates
    assert frames == {
        ("REVENUE", "ABSOLUTE_VALUE", 87_700_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 20.8, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 370_500_000.0, None, 368_000_000.0, 373_000_000.0, True),
    }


def test_v286_profit_margin_and_expense_guards() -> None:
    no_fact, _ = _frames("Consulting expenses were $9.2 million, including success fees from sales of businesses of $5.1 million and implementation expenses of $2.0 million.")
    assert not no_fact
    gross, _ = _frames("GAAP gross profit was $11.3 million, representing a 22% gross margin.")
    assert gross == {("GROSS_MARGIN", "ABSOLUTE_VALUE", 22.0, None, None, None, True)}


def test_v286_operating_income_and_ebitda_ownership() -> None:
    frames, candidates = _frames("Operating Income of $159.3 million; EBITDA of $177.6 million up 16.1% year-over-year.")
    assert {"OPERATING_INCOME", "ADJUSTED_EBITDA"} <= candidates
    assert frames == {
        ("OPERATING_INCOME", "ABSOLUTE_VALUE", 159_300_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA", "CHANGE_TO", 177_600_000.0, 16.1, None, None, True),
    }


def test_v286_sales_guidance_ignores_eps_and_ebitda_margin_change_wins() -> None:
    guidance, _ = _frames("FY27 Guidance Including Total Sales +4.0% to +6.5% and EPS of $11.65 to $12.15.")
    assert guidance == {("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 5.25, None, 4.0, 6.5, True)}
    margin, candidates = _frames("Gross margin was steady, while EBITDA margins expanded by more than 60 basis points.")
    assert "ADJUSTED_EBITDA_MARGIN" in candidates
    assert margin == {("ADJUSTED_EBITDA_MARGIN", "CHANGE_BY", 60.0, None, None, None, True)}


def test_v286_shares_guidance_and_multi_growth_result() -> None:
    shares, _ = _frames("Outlook: weighted-average diluted shares outstanding of approximately 185 million.")
    assert shares == {("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 185_000_000.0, None, None, None, True)}
    result, _ = _frames("Record revenue of $392.4 million, up 27% sequentially and 104% year-over-year.")
    assert result == {
        ("REVENUE", "CHANGE_TO", 392_400_000.0, 27.0, None, None, True),
        ("REVENUE", "CHANGE_BY", 104.0, None, None, None, True),
    }


def test_v286_fused_release_header_keeps_local_metric_ownership() -> None:
    adea = (
        "FOR IMMEDIATE RELEASE ADEIA ANNOUNCES SECOND QUARTER 2026 FINANCIAL RESULTS "
        "Long-term annual revenue outlook increased to $600 million on the strength of our semiconductor business. "
        "Second quarter revenue of $96 million was in line with our expectations, and we generated $55 million "
        "in operating cash flow with a 59% adjusted EBITDA margin."
    )
    frames, _ = _frames(adea)
    assert frames == {
        ("REVENUE", "ABSOLUTE_VALUE", 96_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 59.0, None, None, None, True),
    }

    agys = (
        "AGILYSYS ANNOUNCES RECORD REVENUE OF $87.7M IN FISCAL 2027 FIRST QUARTER "
        "Quarter Adjusted EBITDA of 20.8% and Adjusted EPS of $0.49 "
        "Raises Full-Year Fiscal 2027 Guidance Levels: Total Revenue Range to $368M to $373M "
        "and Subscription Revenue Growth to At Least 32%."
    )
    frames, _ = _frames(agys)
    assert frames == {
        ("REVENUE", "ABSOLUTE_VALUE", 87_700_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 20.8, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 370_500_000.0, None, 368_000_000.0, 373_000_000.0, True),
    }


def test_v286_operational_scaled_count_and_explicit_current_growth() -> None:
    volume, _ = _frames("Second quarter 2026 proppant product sales volumes were 5.6 million tons.")
    assert volume == {("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 5_600_000.0, None, None, None, True)}

    excluded, _ = _frames(
        "Excluding revenue recognized under the agreement, which did not generate revenue in the quarter, "
        "revenue for the current quarter increased 30% from the prior year."
    )
    assert excluded == {("REVENUE", "CHANGE_BY", 30.0, None, None, None, True)}

    to_record, _ = _frames(
        "Total net revenue increased 14.3% to a record $87.7 million compared to total net revenue of "
        "$76.7 million in the comparable prior-year period."
    )
    assert to_record == {("REVENUE", "CHANGE_TO", 87_700_000.0, 14.3, None, None, True)}

    to_date, _ = _frames(
        "Positive top-line trends have sustained into the first quarter with organic sales up year over year "
        "by an estimated 7% to date."
    )
    assert to_date == {("REVENUE", "CHANGE_BY", 7.0, None, None, None, True)}
