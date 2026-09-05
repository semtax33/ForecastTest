from __future__ import annotations

import pandas as pd

from scripts.architecture.v291_native_abc_candidates import (
    note_context_flags,
    select_predeclared_blocks,
)


def test_note_context_uses_document_region_not_heading_aliases() -> None:
    texts = (
        "PART I. FINANCIAL INFORMATION",
        "NOTES TO THE CONDENSED CONSOLIDATED FINANCIAL STATEMENTS",
        "Revenue recognition disclosures were as follows.",
        "ITEM 2. MANAGEMENT'S DISCUSSION AND ANALYSIS",
    )

    assert note_context_flags(texts) == (False, True, True, False)


def test_native_abc_selection_is_deterministic_and_preserves_note_coverage() -> None:
    pool = pd.DataFrame([
        {
            "candidate_id": f"{source_id}-{rank}",
            "source_id": source_id,
            "sampling_key": f"{rank:02d}",
            "sampling_stratum": "NUMERIC" if rank % 2 else "DENSE_NUMERIC",
            "note_context": rank in {4, 5},
            "text": "x" * 50 if rank == 0 else "short",
        }
        for source_id in ("AAL_10Q", "AAME_10K")
        for rank in range(6)
    ])

    selected = select_predeclared_blocks(
        pool,
        source_ids=("AAL_10Q", "AAME_10K"),
        blocks_per_source=3,
        note_blocks_per_filing_source=1,
        filing_source_ids={"AAL_10Q", "AAME_10K"},
        max_block_chars=20,
    )

    assert len(selected) == 6
    assert selected.groupby("source_id").size().to_dict() == {
        "AAL_10Q": 3,
        "AAME_10K": 3,
    }
    assert selected.groupby("source_id")["note_context"].sum().to_dict() == {
        "AAL_10Q": 1,
        "AAME_10K": 1,
    }
    assert selected["text"].str.len().max() <= 20
    assert selected["sampling_key"].tolist() == sorted(
        selected["sampling_key"].tolist()
    )
