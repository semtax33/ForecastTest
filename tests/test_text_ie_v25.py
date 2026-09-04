from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v25 import extract_text_kpis_v25


def _extract(text: str):
    document = adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "memory://v25-test", "V25_TEST", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "IR", "EARNINGS_RELEASE", "2026-09-01", "2026Q3"),
    )
    return extract_text_kpis_v25(document)


def test_change_to_is_one_canonical_event_not_two_facts() -> None:
    result = _extract("Revenue increased 5% to $10 billion.")
    assert len(result.extraction.frames) == 1
    frame = result.extraction.frames[0]
    assert frame.frame.value == "CHANGE_TO"
    assert frame.value == 10_000_000_000
    assert frame.change == 5
    assert result.suppressed_duplicate_count == 1


def test_cross_clause_binding_is_forbidden() -> None:
    result = _extract("Revenue rose 8%, while operating income declined to $900 million.")
    frames = {frame.concept: frame for frame in result.extraction.frames}
    assert frames["REVENUE"].value == 8
    assert frames["OPERATING_INCOME"].value == 900_000_000
    assert all(frame.concept != "REVENUE" or frame.value != 900_000_000 for frame in frames.values())


def test_ambiguous_top_two_values_go_to_review() -> None:
    result = _extract("Revenue was $10 billion and $11 billion.")
    assert not result.extraction.frames
    assert any(item.rule_id == "v25.binding_margin" for item in result.extraction.reviews)


def test_dense_financial_grid_routes_before_text_ie() -> None:
    text = "Q2 FY27 Q2 FY26 Change Net sales $125.2 $120.9 $4.3 3.5% Operating income $8.1 $6.7 $1.4 20.6%"
    result = _extract(text)
    assert result.table_routes
    assert not result.extraction.frames
    assert any(item.failure_class == "TABLE_TEXT_BOUNDARY" for item in result.extraction.abstentions)
