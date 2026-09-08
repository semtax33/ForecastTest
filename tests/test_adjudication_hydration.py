from __future__ import annotations

import pytest

from equity_platform.text_ie.training.adjudication_prep import (
    hydrate_adjudication_rows,
)


REVIEW_FIELDS = {
    "metric_start": "0",
    "metric_end": "7",
    "metric_literal": "Revenue",
    "quantity_start": "12",
    "quantity_end": "23",
    "quantity_literal": "$10 million",
    "concept_label": "REVENUE",
    "binding_label": "BELONGS_TO",
    "role_label": "VALUE_CURRENT",
    "scope": "CONSOLIDATED",
    "period": "FY2025",
    "quantity_kind": "MONEY",
    "notes": "",
}


def _pair(channel: str, annotator: str, *, concept: str = "REVENUE") -> dict[str, str]:
    return {
        "annotation_channel": channel,
        "pair_id": "pair-1",
        "context_id": "context-1",
        "source_slice": "SEC_10K",
        "entity": "TEST",
        "source_sha256": "a" * 64,
        "source_path": "D:/source.htm",
        "text": "Revenue was $10 million.",
        **{f"reviewed_{key}": value for key, value in REVIEW_FIELDS.items()},
        "reviewed_concept_label": concept,
        "annotator_id": annotator,
    }


def _template() -> dict[str, str]:
    row = {
        key: value
        for key, value in _pair("A", "a").items()
        if key in {
            "pair_id", "context_id", "source_slice", "entity",
            "source_sha256", "source_path", "text",
        }
    }
    row.update({
        f"annotator_{channel}_{field}": ""
        for channel in ("a", "b")
        for field in ("id", *REVIEW_FIELDS)
    })
    row.update({
        "agreement_status": "",
        "adjudicator_id": "",
        **{f"final_{field}": "" for field in REVIEW_FIELDS if field != "notes"},
        "adjudication_notes": "",
    })
    return row


def test_agreed_independent_answers_are_transcribed_and_prefilled() -> None:
    rows = hydrate_adjudication_rows(
        annotator_a_rows=(_pair("A", "human-a"),),
        annotator_b_rows=(_pair("B", "human-b"),),
        template_rows=(_template(),),
    )

    row = rows[0]
    assert row["annotator_a_id"] == "human-a"
    assert row["annotator_b_id"] == "human-b"
    assert row["agreement_status"] == "AGREED"
    assert row["final_concept_label"] == "REVENUE"
    assert row["adjudicator_id"] == ""


def test_disagreement_is_transcribed_but_final_is_left_for_adjudicator() -> None:
    rows = hydrate_adjudication_rows(
        annotator_a_rows=(_pair("A", "human-a"),),
        annotator_b_rows=(_pair("B", "human-b", concept="SALES"),),
        template_rows=(_template(),),
    )

    row = rows[0]
    assert row["agreement_status"] == "DISAGREEMENT"
    assert row["annotator_a_concept_label"] == "REVENUE"
    assert row["annotator_b_concept_label"] == "SALES"
    assert row["final_concept_label"] == ""


def test_hydration_rejects_source_identity_drift() -> None:
    altered = _pair("B", "human-b")
    altered["source_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="immutable adjudication source changed"):
        hydrate_adjudication_rows(
            annotator_a_rows=(_pair("A", "human-a"),),
            annotator_b_rows=(altered,),
            template_rows=(_template(),),
        )


def test_hydration_rejects_incomplete_annotator_answers() -> None:
    incomplete = _pair("A", "human-a")
    incomplete["reviewed_concept_label"] = ""

    with pytest.raises(ValueError, match="incomplete reviewed annotation"):
        hydrate_adjudication_rows(
            annotator_a_rows=(incomplete,),
            annotator_b_rows=(_pair("B", "human-b"),),
            template_rows=(_template(),),
        )
