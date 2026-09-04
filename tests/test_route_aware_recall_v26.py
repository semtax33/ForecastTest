from __future__ import annotations

from scripts.architecture.v26_route_evaluation import evaluate_route_aware_ladder
from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import (
    BlockRoute,
    extract_text_kpis_v26,
    route_document_blocks,
)


def test_coverage_ladder_cannot_create_final_fact_after_zero_binding() -> None:
    """Every text final must have a measured upstream semantic binding."""

    _, ladder = evaluate_route_aware_ladder()
    hits = ladder.set_index("stage")["hits"]
    assert hits["ALL_BINDING_ROUTES"] >= hits["FINAL_FACT"]


def test_dom_table_is_routed_as_true_table_before_text_ie() -> None:
    document = adapt_html_fragments(
        fragments=(HtmlFragment(
            b"<p>Quarterly results</p><table><tr><th>Revenue</th><th>2026</th><th>2025</th></tr><tr><td>Total</td><td>$10</td><td>$9</td></tr></table>",
            "memory://v26-dom-table",
            "V26_DOM_TABLE",
            numeric_rows_only=False,
        ),),
        metadata=DocumentMetadata("TEST", "10-Q", "FINANCIAL_STATEMENTS_AND_NOTES", "2026-08-01", "2026Q2"),
    )
    routes = route_document_blocks(document)
    assert any(route.route is BlockRoute.TRUE_TABLE for route in routes)


def test_flattened_table_continuation_routes_without_period_header() -> None:
    text = "$172,282 $47,581 $10,527 $74,028 $129,412 $223,753 Restructuring and other — 2 (77) — (75) (75) Adjusted revenues"
    document = adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "memory://v26-flat", "V26_FLAT", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "10-Q", "FINANCIAL_STATEMENT_NOTE", "2026-08-01", "2026Q2"),
    )
    routes = route_document_blocks(document)
    assert any(route.route is BlockRoute.FLATTENED_TABLE for route in routes)


def test_table_with_explanatory_prose_routes_as_mixed() -> None:
    text = (
        "The table below shows revenue changes: 2026 2025 Q2 Q1 "
        "Revenue $10 $9 $8 $7 11% 9% 7% 5%. "
        "Please refer to the notes for methodology."
    )
    document = adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "memory://v26-mixed", "V26_MIXED", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "10-Q", "FINANCIAL_STATEMENT_NOTE", "2026-08-01", "2026Q2"),
    )
    assert any(route.route is BlockRoute.MIXED for route in route_document_blocks(document))


def test_every_unbound_candidate_has_one_candidate_level_root_cause() -> None:
    document = adapt_html_fragments(
        fragments=(HtmlFragment(
            b"<p>Revenue is an important performance measure.</p>",
            "memory://v26-rejection",
            "V26_REJECTION",
            numeric_rows_only=False,
        ),),
        metadata=DocumentMetadata("TEST", "IR", "EARNINGS_RELEASE", "2026-08-01", "2026Q2"),
    )
    result = extract_text_kpis_v26(document)
    rejected_ids = [item.candidate_id for item in result.rejections]
    bound_ids = {item.upstream_candidate_id for item in result.bindings}
    expected = {
        item.candidate_id for item in result.candidates
        if item.candidate_id not in bound_ids
    }
    assert set(rejected_ids) == expected
    assert len(rejected_ids) == len(set(rejected_ids))
    assert all(item.primary_root_cause for item in result.rejections)


def _extract(text: str):
    document = adapt_html_fragments(
        fragments=(HtmlFragment(
            f"<p>{text}</p>".encode(),
            "memory://v26-semantic",
            "V26_SEMANTIC",
            numeric_rows_only=False,
        ),),
        metadata=DocumentMetadata("TEST", "IR", "EARNINGS_RELEASE", "2026-08-01", "2026Q2"),
    )
    return extract_text_kpis_v26(document)


def test_comparison_frame_preserves_current_and_prior_values() -> None:
    result = _extract("Operating income was $155.3 million compared to $165.3 million.")
    assert len(result.comparisons) == 1
    comparison = result.comparisons[0]
    assert [item.value for item in comparison.current_values] == [155_300_000]
    assert [item.value for item in comparison.prior_values] == [165_300_000]
    signatures = {(item.concept, item.frame.value, item.value) for item in result.extraction.frames}
    assert ("OPERATING_INCOME", "COMPARATIVE", 155_300_000) in signatures
    assert ("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 165_300_000) in signatures


def test_change_event_ignores_explanatory_money_after_causal_boundary() -> None:
    result = _extract(
        "Adjusted operating income increased 85.5% compared to the prior year "
        "primarily driven by the absence of a $471 million reserve."
    )
    signatures = {(item.concept, item.frame.value, item.value) for item in result.extraction.frames}
    assert ("OPERATING_INCOME", "CHANGE_BY", 85.5) in signatures
    change = next(item for item in result.changes if item.concept == "OPERATING_INCOME")
    assert change.delta is not None and change.delta.value == 85.5
    assert change.level is None


def test_change_event_merges_delta_and_level_once() -> None:
    result = _extract(
        "Rental revenue increased 6.6% year-over-year to $2.418 billion."
    )
    matches = [
        item for item in result.extraction.frames
        if item.concept == "REVENUE" and item.frame.value == "CHANGE_TO"
    ]
    assert len(matches) == 1
    assert matches[0].value == 2_418_000_000
    assert matches[0].change == 6.6


def test_post_level_parallel_deltas_share_the_same_level() -> None:
    result = _extract(
        "Record FY 2026 Total Revenues $67.4 billion, up 17% USD, "
        "and up 16% constant currency."
    )
    matches = [
        item for item in result.extraction.frames
        if item.concept == "REVENUE" and item.frame.value == "CHANGE_TO"
    ]
    assert {item.change for item in matches} == {17.0, 16.0}
    assert all(abs(item.value - 67_400_000_000) < 0.01 for item in matches)
    assert not any(
        item.concept == "REVENUE" and item.frame.value == "CHANGE_BY"
        for item in result.extraction.frames
    )
