from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT


SUBMISSION = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_batch_v1/human_submission_v1"
)
CONTEXT_DISPOSITION = SUBMISSION / "context_disposition.csv"
REPORT = SUBMISSION / "quality_report.json"


def _read(name: str, key: str) -> dict[str, dict[str, str]]:
    path = SUBMISSION / name
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(dict(row) for row in csv.DictReader(handle))
    indexed = {row[key]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"{name} has duplicate {key}")
    return indexed


def _complete(row: dict[str, str]) -> bool:
    return row["candidate_graph_complete"].strip().upper() in {"TRUE", "YES"}


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> int:
    contexts_a = _read("annotator_a_context_audit.csv", "context_id")
    contexts_b = _read("annotator_b_context_audit.csv", "context_id")
    pairs_a = _read("annotator_a_pairs.csv", "pair_id")
    pairs_b = _read("annotator_b_pairs.csv", "pair_id")
    adjudication = _read("adjudication_template.csv", "pair_id")
    if set(contexts_a) != set(contexts_b):
        raise ValueError("A/B context sets differ")
    if not (set(pairs_a) == set(pairs_b) == set(adjudication)):
        raise ValueError("A/B/adjudication pair sets differ")
    disposition_rows = []
    for context_id in sorted(contexts_a):
        a = contexts_a[context_id]
        b = contexts_b[context_id]
        a_complete = _complete(a)
        b_complete = _complete(b)
        accepted = a_complete and b_complete
        disposition_rows.append({
            "context_id": context_id,
            "source_slice": a["source_slice"],
            "entity": a["entity"],
            "annotator_a_complete": a_complete,
            "annotator_b_complete": b_complete,
            "gold_a_candidate_graph_accepted": accepted,
            "annotator_a_missing_metric_mentions": a["missing_metric_mentions"],
            "annotator_a_missing_quantity_mentions": a["missing_quantity_mentions"],
            "annotator_a_missing_pairs": a["missing_pairs"],
            "annotator_b_missing_metric_mentions": b["missing_metric_mentions"],
            "annotator_b_missing_quantity_mentions": b["missing_quantity_mentions"],
            "annotator_b_missing_pairs": b["missing_pairs"],
        })
    with CONTEXT_DISPOSITION.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(disposition_rows[0]))
        writer.writeheader()
        writer.writerows(disposition_rows)
    accepted_context_ids = {
        row["context_id"]
        for row in disposition_rows
        if row["gold_a_candidate_graph_accepted"]
    }
    accepted_pair_ids = {
        pair_id
        for pair_id, row in pairs_a.items()
        if row["context_id"] in accepted_context_ids
    }
    exact_fields = (
        "reviewed_metric_start", "reviewed_metric_end", "reviewed_metric_literal",
        "reviewed_quantity_start", "reviewed_quantity_end", "reviewed_quantity_literal",
        "reviewed_concept_label", "reviewed_binding_label", "reviewed_role_label",
        "reviewed_scope", "reviewed_period", "reviewed_quantity_kind",
    )
    agreement = {
        field: sum(pairs_a[pair_id][field] == pairs_b[pair_id][field]
                   for pair_id in accepted_pair_ids)
        for field in exact_fields
    }
    exact = sum(
        all(pairs_a[pair_id][field] == pairs_b[pair_id][field] for field in exact_fields)
        for pair_id in accepted_pair_ids
    )
    source_slices = sorted({row["source_slice"] for row in disposition_rows})
    by_source = {}
    for source_slice in source_slices:
        rows = [row for row in disposition_rows if row["source_slice"] == source_slice]
        accepted = sum(bool(row["gold_a_candidate_graph_accepted"]) for row in rows)
        source_pair_ids = {
            pair_id
            for pair_id in accepted_pair_ids
            if pairs_a[pair_id]["source_slice"] == source_slice
        }
        source_exact = sum(
            all(pairs_a[pair_id][field] == pairs_b[pair_id][field]
                for field in exact_fields)
            for pair_id in source_pair_ids
        )
        by_source[source_slice] = {
            "submitted_contexts": len(rows),
            "jointly_complete_contexts": accepted,
            "candidate_graph_yield": _rate(accepted, len(rows)),
            "quarantined_contexts": len(rows) - accepted,
            "accepted_pairs": len(source_pair_ids),
            "exact_pair_agreement": _rate(source_exact, len(source_pair_ids)),
            "gold_a_context_gap_to_50": max(0, 50 - accepted),
            "gold_a_context_gap_to_75": max(0, 75 - accepted),
        }
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PARTIAL_GOLD_A_ACCEPTED_CANDIDATE_GRAPH_RECOVERY_REQUIRED",
        "production_enabled": False,
        "submitted_contexts": len(disposition_rows),
        "jointly_complete_contexts": len(accepted_context_ids),
        "quarantined_contexts": len(disposition_rows) - len(accepted_context_ids),
        "accepted_pairs": len(accepted_pair_ids),
        "candidate_graph_decisions": dict(sorted(Counter(
            "BOTH_COMPLETE" if row["gold_a_candidate_graph_accepted"]
            else "BOTH_INCOMPLETE" if not row["annotator_a_complete"] and not row["annotator_b_complete"]
            else "A_INCOMPLETE_B_COMPLETE" if not row["annotator_a_complete"]
            else "A_COMPLETE_B_INCOMPLETE"
            for row in disposition_rows
        ).items())),
        "by_source_slice": by_source,
        "accepted_pair_agreement": {
            "exact": _rate(exact, len(accepted_pair_ids)),
            **{
                field.removeprefix("reviewed_"): _rate(count, len(accepted_pair_ids))
                for field, count in agreement.items()
            },
        },
        "adjudication_status": dict(sorted(Counter(
            adjudication[pair_id]["agreement_status"]
            for pair_id in accepted_pair_ids
        ).items())),
        "final_binding_labels": dict(sorted(Counter(
            adjudication[pair_id]["final_binding_label"]
            for pair_id in accepted_pair_ids
        ).items())),
        "context_disposition": CONTEXT_DISPOSITION.relative_to(PROJECT_ROOT).as_posix(),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"STATUS={report['status']} ACCEPTED_CONTEXTS={len(accepted_context_ids)} "
        f"QUARANTINED_CONTEXTS={report['quarantined_contexts']} "
        f"ACCEPTED_PAIRS={len(accepted_pair_ids)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
