from __future__ import annotations

from pathlib import Path

from scripts.architecture.universe_certification_v21 import _ir_document_score


def test_ir_source_score_prefers_earnings_release_over_later_event(tmp_path: Path) -> None:
    event = tmp_path / "2026-08-28_EX-99.1_director.htm"
    event.write_text("director appointment", encoding="utf-8")
    earnings = tmp_path / "2026-07-31_EX-99.1_q2_earnings_results.htm"
    earnings.write_text("earnings release financial results quarter ended", encoding="utf-8")
    assert _ir_document_score(earnings) > _ir_document_score(event)
