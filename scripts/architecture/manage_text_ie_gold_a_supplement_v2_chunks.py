from __future__ import annotations

import argparse
import csv
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    merge_annotation_chunk_package,
    hydrate_adjudication_rows,
    split_annotation_batch_into_chunks,
)


BATCH = PROJECT_ROOT / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2"
CHUNKS = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2_chunks"
)
SUBMISSION = BATCH / "human_submission_v2"
STAGING = CHUNKS / "_adjudication_staging"


def _read(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def _write(path: Path, rows: tuple[dict[str, str], ...]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _hydrate_adjudicator_chunks() -> int:
    package = merge_annotation_chunk_package(
        chunks_root=CHUNKS,
        output_root=STAGING,
    )
    for chunk in package.chunks:
        current = _read(CHUNKS / chunk.files["adjudication_template.csv"])
        if any(row.get("adjudicator_id", "").strip() for row in current):
            raise ValueError("refusing to overwrite adjudicator work already in progress")
    hydrated = hydrate_adjudication_rows(
        annotator_a_rows=_read(STAGING / "annotator_a_pairs.csv"),
        annotator_b_rows=_read(STAGING / "annotator_b_pairs.csv"),
        template_rows=_read(BATCH / "adjudication_template.csv"),
    )
    by_pair = {row["pair_id"]: row for row in hydrated}
    for chunk in package.chunks:
        _write(
            CHUNKS / chunk.files["adjudication_template.csv"],
            tuple(by_pair[pair_id] for pair_id in chunk.pair_ids),
        )
    print(
        f"STATUS=ADJUDICATION_CHUNKS_HYDRATED CHUNKS={package.chunk_count} "
        f"PAIRS={package.pair_count}"
    )
    return 0


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--hydrate-adjudication", action="store_true")
    action.add_argument("--merge", action="store_true")
    args = parser.parse_args(argv)
    if args.hydrate_adjudication:
        try:
            return _hydrate_adjudicator_chunks()
        except ValueError as exc:
            print(f"STATUS=ADJUDICATION_HYDRATION_BLOCKED ERROR={exc}")
            return 1
    if args.merge:
        try:
            package = merge_annotation_chunk_package(
                chunks_root=CHUNKS,
                output_root=SUBMISSION,
            )
        except ValueError as exc:
            print(f"STATUS=CHUNK_MERGE_BLOCKED ERROR={exc}")
            return 1
        print(
            f"STATUS=CHUNKS_MERGED_AWAITING_INGESTION CHUNKS={package.chunk_count} "
            f"CONTEXTS={package.context_count} PAIRS={package.pair_count}"
        )
        return 0
    package = split_annotation_batch_into_chunks(
        batch_root=BATCH,
        chunks_root=CHUNKS,
        maximum_pairs_per_chunk=350,
    )
    (CHUNKS / "README.md").write_text(
        "# GOLD_A Supplement V2 chunk workflow\n\n"
        "- Give only `annotator_a/` to annotator A and only `annotator_b/` "
        "to annotator B. Do not share answers.\n"
        "- Every context stays inside one chunk; do not move or delete rows.\n"
        "- Complete every pair and context audit field under the canonical "
        "annotation guideline.\n"
        "- Run this module with `--hydrate-adjudication` after A/B finish. It "
        "copies both answers and prefills only exact agreements.\n"
        "- Then give `adjudicator/` only to the separate adjudicator.\n"
        "- After adjudication is complete, run this module with `--merge`.\n"
        "- Merging verifies every expected pair/context identity exactly once.\n",
        encoding="utf-8",
    )
    print(
        f"STATUS=BLIND_CHUNKS_READY CHUNKS={package.chunk_count} "
        f"CONTEXTS={package.context_count} PAIRS={package.pair_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
