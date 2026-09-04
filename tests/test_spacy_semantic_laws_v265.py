from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v265 import (
    V265_RULES,
    extract_text_kpis_v265,
    route_document_blocks_v265,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v265-semantic-laws",
                "V265_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            entity="TEST",
            source_kind="TEST",
            document_kind="TEXT_IE",
            available_at="2026-09-04",
            report_period="2026Q2",
        ),
    )


def _frames(text: str):
    return extract_text_kpis_v265(_document(text)).extraction.frames


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


def test_v265_uses_typed_issuer_neutral_laws() -> None:
    assert len(V265_RULES) >= 12
    assert all(rule.pattern for rule in V265_RULES)
    assert all(rule.rule_id.startswith("v265.") for rule in V265_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V265_RULES)


def test_operating_income_margin_alias_is_a_margin_anchor() -> None:
    result = extract_text_kpis_v265(
        _document(
            "Adjusted operating income margin of 24.9%, an increase of "
            "40 basis points year-on-year."
        )
    )
    assert any(
        candidate.metric.concept == "OPERATING_MARGIN"
        and candidate.metric.alias.casefold() == "operating income margin"
        for candidate in result.candidates
    )
    assert (
        "OPERATING_MARGIN",
        "CHANGE_TO",
        24.9,
        40.0,
        True,
    ) in _signatures(
        "Adjusted operating income margin of 24.9%, an increase of "
        "40 basis points year-on-year."
    )


def test_margin_range_and_approximate_level_use_labeled_values() -> None:
    ranged = _frames(
        "Adjusted operating income margin expansion 2 of 70 bps to 80 bps."
    )
    assert any(
        frame.concept == "OPERATING_MARGIN_CHANGE_GUIDANCE"
        and frame.frame.value == "RANGE_GUIDANCE"
        and frame.value == 75.0
        and frame.lower_value == 70.0
        and frame.upper_value == 80.0
        for frame in ranged
    )
    assert (
        "OPERATING_MARGIN",
        "ABSOLUTE_VALUE",
        25.0,
        None,
        True,
    ) in _signatures("We delivered robust operating margins of about 25%.")


def test_multi_value_growth_guidance_emits_distinct_semantic_roles() -> None:
    signatures = _signatures(
        "Adjusted total sales growth of >4.5 percent, reflecting adjusted "
        "organic sales growth of >3.5 percent."
    )
    assert (
        "REVENUE_CHANGE_GUIDANCE",
        "ABSOLUTE_VALUE",
        4.5,
        None,
        True,
    ) in signatures
    assert (
        "REVENUE_CHANGE_GUIDANCE",
        "ABSOLUTE_VALUE",
        3.5,
        None,
        True,
    ) in signatures


def test_cash_and_full_year_guidance_bind_each_metric_owner() -> None:
    cash = _signatures(
        "MPC had $7.8 billion of cash and cash equivalents, including "
        "$1.0 billion of cash at MPLX."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 7_800_000_000.0, None, True) in cash
    assert ("CASH", "ABSOLUTE_VALUE", 1_000_000_000.0, None, True) in cash
    guidance = _signatures(
        "The company is raising its guidance for consolidated revenue to "
        "approximately $91.2 billion and consolidated adjusted operating "
        "profit to approximately $8.65 billion."
    )
    assert (
        "REVENUE_GUIDANCE",
        "ABSOLUTE_VALUE",
        91_200_000_000.0,
        None,
        True,
    ) in guidance
    assert (
        "OPERATING_INCOME_GUIDANCE",
        "ABSOLUTE_VALUE",
        8_650_000_000.0,
        None,
        True,
    ) in guidance


def test_comparative_operating_income_and_production_semantics() -> None:
    comparison = _signatures(
        "The segment reported $318 million of operating income for 2026, "
        "compared to $54 million for 2025."
    )
    assert (
        "OPERATING_INCOME",
        "COMPARATIVE",
        318_000_000.0,
        None,
        True,
    ) in comparison
    assert (
        "PRIOR_YEAR_OPERATING_INCOME",
        "COMPARATIVE",
        54_000_000.0,
        None,
        True,
    ) in comparison
    assert (
        "PRODUCTION",
        "ABSOLUTE_VALUE",
        1.8,
        None,
        True,
    ) in _signatures("Record Permian production of more than 1.8 Moebd.")
    assert (
        "PRODUCTION_CHANGE_GUIDANCE",
        "ABSOLUTE_VALUE",
        9.0,
        None,
        True,
    ) in _signatures("Permian production is consistent with planned 9% CAGR through 2030.")


def test_specific_frames_remove_upstream_duplicate_and_wrong_owner() -> None:
    margin = _frames("Operating margin decreased 20 bps to 12.3%.")
    assert len([frame for frame in margin if frame.concept == "OPERATING_MARGIN"]) == 1
    revenue = _frames("Revenue of $5.9 billion, up 8%.")
    assert len([frame for frame in revenue if frame.concept == "REVENUE"]) == 1
    capex = _frames(
        "Free cash flow, which is after capital expenditures, was $1 billion."
    )
    assert not any(frame.concept == "CAPEX" for frame in capex)


def test_organic_secondary_change_is_not_a_second_level_frame() -> None:
    revenue = _frames(
        "Sales of $24.7 billion, up 14 percent versus prior year, and up "
        "16 percent organically."
    )
    assert {
        (frame.frame.value, frame.value, frame.change)
        for frame in revenue
        if frame.concept == "REVENUE"
    } == {
        ("CHANGE_TO", 24_700_000_000.0, 14.0),
        ("CHANGE_BY", 16.0, None),
    }


def test_semantic_table_router_recovers_period_grids_without_numeric_regex() -> None:
    grids = (
        "Second Quarter Year to Date 2026 Guidance ($ millions) 2026 2025 "
        "Change 2026 2025 Change Revenue $2,966 $2,770 7% $5,956 $5,181 15%",
        "GAAP (millions of dollars) Three Months Ended June 30, Six Months "
        "Ended June 30, 2026 2025 2026 2025 Reconciliation of operating income",
        "EARNINGS AND VOLUME SUMMARY BY SEGMENT 2Q26 1Q26 Dollars in millions "
        "YTD 2026 YTD 2025 Earnings/(Loss)",
    )
    for text in grids:
        routes = route_document_blocks_v265(_document(text))
        assert any(route.route is BlockRoute.FLATTENED_TABLE for route in routes)
