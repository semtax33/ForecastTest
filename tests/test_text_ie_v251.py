from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v251 import extract_text_kpis_v251


def _extract(text: str):
    return extract_text_kpis_v251(adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "memory://v251", "V251", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "IR", "EARNINGS_RELEASE", "2026-09-04", "2026Q3"),
    ))


def test_simple_change_to_remains_one_fact() -> None:
    result = _extract("Revenue increased 5% to $10 billion.")
    assert len(result.extraction.frames) == 1
    assert result.extraction.frames[0].frame.value == "CHANGE_TO"


def test_multiple_deltas_are_fail_closed() -> None:
    result = _extract("Revenue increased 5%, or 4% in constant currency, to $10 billion.")
    assert not result.extraction.frames
    assert result.extraction.abstentions or result.extraction.reviews


def test_unique_guidance_range_is_emitted() -> None:
    result = _extract("We expect capital expenditures to be $125 million to $150 million.")
    assert len(result.extraction.frames) == 1
    frame = result.extraction.frames[0]
    assert frame.concept == "CAPEX_GUIDANCE"
    assert frame.lower_value == 125_000_000
    assert frame.upper_value == 150_000_000
