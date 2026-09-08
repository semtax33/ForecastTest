from __future__ import annotations

import argparse
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import import_annotation_chunk_submission


CHUNKS = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2_chunks"
)
STAGING = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2/incoming_submission_v2"
)
SUBMISSION = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2/human_submission_v2"
)


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotator-a-zip", type=Path, required=True)
    parser.add_argument("--annotator-b-zip", type=Path, required=True)
    parser.add_argument("--adjudication-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    adjudications = tuple(sorted(
        args.adjudication_dir.glob("chunk_*__adjudication.csv")
    ))
    try:
        report = import_annotation_chunk_submission(
            chunks_root=CHUNKS,
            annotator_a_zip=args.annotator_a_zip,
            annotator_b_zip=args.annotator_b_zip,
            adjudication_files=adjudications,
            staging_root=STAGING,
            output_root=SUBMISSION,
        )
    except (OSError, ValueError) as exc:
        print(f"STATUS=CHUNK_SUBMISSION_IMPORT_BLOCKED ERROR={exc}")
        return 1
    print(
        f"STATUS={report['status']} CHUNKS={report['chunks']} "
        f"CONTEXTS={report['contexts']} PAIRS={report['pairs']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
