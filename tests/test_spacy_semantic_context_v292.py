from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v292 import extract_text_kpis_v292


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<p>{text}</p>".encode(),
                "test://v292-semantic-context",
                "V292",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-06", "2026Q2"),
    )


def test_v292_does_not_treat_share_repurchase_event_as_shares_outstanding() -> None:
    text = (
        "Common Stock Repurchase Program During the quarter ended June 30, 2026, "
        "the Company repurchased 793,077 shares of its common stock and 237,618 "
        "limited partnership units at an average price of $205.10 per share/unit, "
        "for a total investment of $211.4 million."
    )

    result = extract_text_kpis_v292(_doc(text))

    assert not [frame for frame in result.extraction.frames if frame.concept == "SHARES"]
    assert any(
        trace.primary_root_cause == "SUPPRESSED_EVENT_SCOPE"
        for trace in result.telemetry.clauses
    )


def test_v292_recovers_activity_counts_from_predicate_argument_structure() -> None:
    text = (
        "In 2025, we served over 20,000 unique origin and destination pairs, "
        "transporting approximately 1.0 billion pounds of time-sensitive freight "
        "and mail throughout our network."
    )

    result = extract_text_kpis_v292(_doc(text))

    assert {
        (frame.concept, frame.frame.value, frame.value)
        for frame in result.extraction.frames
    } == {
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 20_000.0),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 1_000_000_000.0),
    }
    assert {
        (candidate.metric.alias, quantity.value)
        for candidate in result.candidates
        if candidate.metric.concept == "ACTIVITY_VOLUME"
        for quantity in candidate.quantities
    } == {
        ("served", 20_000.0),
        ("transporting", 1_000_000_000.0),
    }


def test_v292_maps_impact_on_metric_percentages_to_delta_roles() -> None:
    text = (
        "Please refer to “Non-GAAP Financial Measures” later in this release for "
        "definitions of non-GAAP financial measures and to “Table 6 - Geographic "
        "Sales Analysis Percentage Changes” included with this release for a "
        "reconciliation of these non-GAAP financial measures to the related GAAP "
        "measures. **The impact of the acquisition of the Prime100 pet food business "
        "on as reported volume was 0.6% and 0.1% for Hill's Pet Nutrition and Total "
        "Company, respectively."
    )

    result = extract_text_kpis_v292(_doc(text))

    assert {
        (frame.concept, frame.frame.value, frame.value)
        for frame in result.extraction.frames
        if frame.concept == "ACTIVITY_VOLUME"
    } == {
        ("ACTIVITY_VOLUME", "CHANGE_BY", 0.6),
        ("ACTIVITY_VOLUME", "CHANGE_BY", 0.1),
    }
    assert {
        (edge.concept, edge.role, edge.quantity.value)
        for trace in result.telemetry.clauses
        for edge in trace.roles
        if edge.concept == "ACTIVITY_VOLUME"
    } == {
        ("ACTIVITY_VOLUME", "DELTA", 0.6),
        ("ACTIVITY_VOLUME", "DELTA", 0.1),
    }
