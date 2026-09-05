from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v274 import (
    V274_RULES,
    extract_text_kpis_v274,
    route_document_blocks_v274,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v274-semantic-laws",
                "V274_SEMANTIC_LAW_TEST",
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
            frame.polarity.positive,
        )
        for frame in extract_text_kpis_v274(_document(f"<p>{text}</p>")).extraction.frames
    }


def test_v274_rules_are_spacy_dsl_and_issuer_neutral() -> None:
    assert V274_RULES
    assert all(rule.pattern and rule.rule_id.startswith("v274.") for rule in V274_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V274_RULES)


def test_v274_levels_with_parentheticals_and_including_pairs() -> None:
    ebitda = _signatures(
        "Adjusted EBITDA (a non-GAAP financial measure) for the second quarter was "
        "$1,231 million, which excludes adjustments totaling $60 million."
    )
    assert ("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_231_000_000.0, None, None, None, True) in ebitda
    assert not any(value == 60_000_000.0 for _, _, value, *_ in ebitda)

    orders = _signatures("Orders of $10.5 billion, including $7.1 billion of IET orders.")
    assert ("ORDERS", "ABSOLUTE_VALUE", 10_500_000_000.0, None, None, None, True) in orders
    assert ("ORDERS", "ABSOLUTE_VALUE", 7_100_000_000.0, None, None, None, True) in orders


def test_v274_word_percent_range_and_reported_organic_revenue() -> None:
    guidance = _signatures(
        "The company estimates net sales growth for the third quarter to be approximately "
        "3 to 5 percent on a reported and organic basis."
    )
    assert ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 4.0, None, 3.0, 5.0, True) in guidance

    actual = _signatures(
        "Reported net sales of $5.442 billion, representing an increase of 7.5 percent "
        "on a reported basis; and 7.0 percent on an operational and organic basis."
    )
    assert ("REVENUE", "CHANGE_TO", 5_442_000_000.0, 7.5, None, None, True) in actual
    assert ("REVENUE", "CHANGE_BY", 7.0, None, None, None, True) in actual


def test_v274_income_and_margin_sentence_preserves_metric_ownership() -> None:
    frames = _signatures(
        "GAAP operating income was $15.4 billion, up 31%, with GAAP operating margin of 24.3%."
    )
    assert ("OPERATING_INCOME", "CHANGE_TO", 15_400_000_000.0, 31.0, None, None, True) in frames
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 24.3, None, None, None, True) in frames
    assert not any(concept == "OPERATING_MARGIN" and frame == "CHANGE_BY" and value == 31.0 for concept, frame, value, *_ in frames)


def test_v274_comparatives_and_reverse_revenue_level() -> None:
    income = _signatures("Operating income was $155.3 million compared to $165.3 million.")
    assert ("OPERATING_INCOME", "COMPARATIVE", 155_300_000.0, None, None, None, True) in income
    assert ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 165_300_000.0, None, None, None, True) in income

    cash = _signatures("Cash and cash equivalents were $1.603 billion compared to $1.720 billion.")
    assert ("CASH", "COMPARATIVE", 1_603_000_000.0, None, None, None, True) in cash
    assert ("PRIOR_YEAR_CASH", "COMPARATIVE", 1_720_000_000.0, None, None, None, True) in cash

    revenue = _signatures("We delivered a solid quarter, surpassing $1 billion of first quarter revenue.")
    assert ("REVENUE", "ABSOLUTE_VALUE", 1_000_000_000.0, None, None, None, True) in revenue


def test_v274_revenue_current_prior_comparison_owns_levels() -> None:
    frames = _signatures("Net sales increased 5.7% to $1.020 billion compared to $964.5 million.")
    assert ("REVENUE", "COMPARATIVE", 1_020_000_000.0, None, None, None, True) in frames
    assert ("PRIOR_YEAR_REVENUE", "COMPARATIVE", 964_500_000.0, None, None, None, True) in frames
    assert not any(frame == "CHANGE_TO" and value == 1_020_000_000.0 for _, frame, value, *_ in frames)


def test_v274_activity_and_ebit_money_changes() -> None:
    volume = _signatures("Volume decreased 1% year-over-year.")
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 1.0, None, None, None, False) in volume

    down = _signatures("EBIT was $133 million, a decrease of $19 million versus the year-ago period.")
    assert ("EBIT", "CHANGE_TO", 133_000_000.0, 19_000_000.0, None, None, False) in down

    up = _signatures("EBIT 1 was $1.6 billion, up $1.7 billion year-over-year.")
    assert ("EBIT", "CHANGE_TO", 1_600_000_000.0, 1_700_000_000.0, None, None, True) in up
    assert not any(frame == "CHANGE_BY" and value == 1_700_000_000.0 for _, frame, value, *_ in up)


def test_v274_delivered_revenue_reported_and_fx_neutral() -> None:
    frames = _signatures(
        "Advertising products delivered $570 million of revenue, up 25% on an "
        "as-reported basis and up 24% on an FX-Neutral basis."
    )
    assert ("REVENUE", "CHANGE_TO", 570_000_000.0, 25.0, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 24.0, None, None, None, True) in frames


def test_v274_router_recovers_compact_result_and_guidance_bullets_as_prose() -> None:
    document = _document(
        "<p>Non-GAAP operating income was $22.0 billion, up 13%, with non-GAAP "
        "operating margin at 34.8%.</p>"
        "<p>Q1 FY 2027 Guidance: ◦ Revenue: $18.0 billion to $18.2 billion ◦ "
        "Earnings per Share: GAAP: $1.08 to $1.10; Non-GAAP: $1.32 to $1.34.</p>"
        "<p>Management provides non-GAAP financial measures because it believes such "
        "measures help investors analyze adjusted EBITDA and free cash flow.</p>"
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v274(document)
    )


def test_v274_router_recognizes_balance_guidance_and_milestone_grids() -> None:
    document = _document(
        "<p>1Q'26 2Q'26 Cash and cash equivalents $3,553 $3,412 Investments, net "
        "3,569 3,467 Debt (6,260) (5,762) Net Balance Sheet Value $2,163 $2,533 "
        "Shares Outstanding 624 624 Supplemental Details.</p>"
        "<p>Updated Guidance as of August 6, 2026 Prior Guidance as of May 7, 2026 "
        "GAAP Revenue Growth Low single-digit Revenue Growth FXN Low single-digit "
        "Adjusted Diluted EPS $12.62 to $12.72 $12.52 to $12.72.</p>"
        "<p>Q3 2026 Guidance Revenue $3.07 - $3.12 FX-Neutral Y/Y Growth 8% - 10% "
        "Gross Merchandise Volume $22.0 - $22.4 FX-Neutral Y/Y Growth 10% - 12% "
        "Diluted GAAP EPS $0.94 - $0.99.</p>"
        "<p>Expected production capacity milestones: ~65% in 2H26 ~80% by mid-27 "
        "Near Full Capacity by YE27 Installation milestones and target pumping in 2027.</p>"
    )
    assert all(
        route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v274(document)
    )


def test_v274_bounded_parent_context_promotes_but_does_not_lend_numbers() -> None:
    document = _document(
        "<h2>Full Year Fiscal 2027 Guidance</h2>"
        "<p>Net consolidated sales: $5.86 billion "
        "to $5.91 billion.</p>"
        "<h2>Historical Results</h2>"
        "<p>Operating income was $155.3 million.</p>"
    )
    signatures = {
        (frame.concept, frame.frame.value, frame.value, frame.lower_value, frame.upper_value)
        for frame in extract_text_kpis_v274(document).extraction.frames
    }
    assert ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 5_885_000_000.0, 5_860_000_000.0, 5_910_000_000.0) in signatures
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 155_300_000.0, None, None) in signatures
    assert not any(concept == "OPERATING_INCOME_GUIDANCE" for concept, *_ in signatures)


def test_v274_handles_long_period_modifier_before_word_percent_range() -> None:
    frames = _signatures(
        "The company estimates net sales growth for the third quarter of 2026, "
        "versus the prior year period, to be approximately 3 to 5 percent on a "
        "reported and organic basis."
    )
    assert (
        "REVENUE_CHANGE_GUIDANCE",
        "RANGE_GUIDANCE",
        4.0,
        None,
        3.0,
        5.0,
        True,
    ) in frames


def test_v274_reprocesses_blocks_reclassified_from_table_to_prose() -> None:
    frames = _signatures(
        "Non-GAAP operating income was $22.0 billion, up 13%, with non-GAAP "
        "operating margin at 34.8%."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        22_000_000_000.0,
        13.0,
        None,
        None,
        True,
    ) in frames
    assert (
        "OPERATING_MARGIN",
        "ABSOLUTE_VALUE",
        34.8,
        None,
        None,
        None,
        True,
    ) in frames


def test_v274_local_guidance_label_and_expected_range_are_supported() -> None:
    bullet = _signatures(
        "Q1 FY 2027 Guidance: Revenue: $18.0 billion to $18.2 billion; "
        "Earnings per Share: GAAP: $1.08 to $1.10."
    )
    assert (
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        18_100_000_000.0,
        None,
        18_000_000_000.0,
        18_200_000_000.0,
        True,
    ) in bullet

    expected = _signatures(
        "Net consolidated sales are still expected to be in the range of "
        "$5.86 billion to $5.91 billion."
    )
    assert (
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        5_885_000_000.0,
        None,
        5_860_000_000.0,
        5_910_000_000.0,
        True,
    ) in expected


def test_v274_same_block_outlook_does_not_relabel_later_historical_fact() -> None:
    frames = _signatures(
        "The Company provided an update to its financial outlook for fiscal 2027. "
        "Deckers delivered a solid start, surpassing $1 billion of first quarter revenue."
    )
    assert (
        "REVENUE",
        "ABSOLUTE_VALUE",
        1_000_000_000.0,
        None,
        None,
        None,
        True,
    ) in frames
    assert not any(concept == "REVENUE_GUIDANCE" for concept, *_ in frames)

    long_block = _signatures(
        "The Company also provided an update to its financial outlook for the full "
        "fiscal year ending March 31, 2027. Deckers delivered a solid start to the "
        "fiscal year, surpassing $1 billion of first quarter revenue for the first time, "
        "said the Chief Executive Officer."
    )
    assert (
        "REVENUE",
        "ABSOLUTE_VALUE",
        1_000_000_000.0,
        None,
        None,
        None,
        True,
    ) in long_block
    assert not any(concept == "REVENUE_GUIDANCE" for concept, *_ in long_block)


def test_v274_reported_organic_result_ignores_comparison_to_guidance_range() -> None:
    frames = _signatures(
        "Reported net sales of $5.442 billion, representing an increase of 7.5 percent "
        "on a reported basis, compared to the company's guidance range of 5.5 to 7.5 "
        "percent; and 7.0 percent on an operational and organic basis, compared to the "
        "company's guidance range of 5 to 7 percent, all compared to the prior year period."
    )
    assert (
        "REVENUE",
        "CHANGE_TO",
        5_442_000_000.0,
        7.5,
        None,
        None,
        True,
    ) in frames
    assert (
        "REVENUE",
        "CHANGE_BY",
        7.0,
        None,
        None,
        None,
        True,
    ) in frames
    assert not any(concept == "REVENUE_GUIDANCE" for concept, *_ in frames)


def test_v274_activity_volume_is_a_critical_anchor() -> None:
    result = extract_text_kpis_v274(_document("<p>Volume decreased 1% year-over-year.</p>"))
    frame = next(
        item
        for item in result.extraction.frames
        if item.concept == "ACTIVITY_VOLUME" and item.frame.value == "CHANGE_BY"
    )
    assert frame.tier.value == "CRITICAL"
