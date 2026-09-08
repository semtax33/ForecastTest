from __future__ import annotations

import argparse
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    build_context_recovery_cases,
    write_context_recovery_package,
)


SUBMISSION = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_batch_v1/human_submission_v1"
)
OUTPUT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_batch_v1/context_recovery_v1"
)


def build_package(
    *,
    submission: Path = SUBMISSION,
    output: Path = OUTPUT,
) -> dict[str, object]:
    cases = build_context_recovery_cases(
        submission / "annotator_a_context_audit.csv",
        submission / "annotator_b_context_audit.csv",
    )
    return write_context_recovery_package(output, cases)


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission", type=Path, default=SUBMISSION)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    summary = build_package(submission=args.submission, output=args.output)
    print(
        f"STATUS={summary['status']} CONTEXTS={summary['contexts']} "
        f"EXPLICIT_METRIC_HINTS={summary['explicit_metric_hints']} "
        f"EXPLICIT_QUANTITY_HINTS={summary['explicit_quantity_hints']} "
        f"SOURCE_REREAD={summary['contexts_requiring_source_reread']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
