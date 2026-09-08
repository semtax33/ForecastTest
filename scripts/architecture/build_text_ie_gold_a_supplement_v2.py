from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.build_text_ie_gold_a_supplement_v1 import build_supplement


OUTPUT = PROJECT_ROOT / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2"
SUPPLEMENT_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_gold_a_supplement_v2.jsonl"
)
CONTEXTS_PER_SLICE = 66
SEC_CANDIDATE_CONTEXTS_PER_SLICE = 116


def main() -> int:
    manifest = build_supplement(
        output=OUTPUT,
        supplement_queue=SUPPLEMENT_QUEUE,
        contexts_per_slice=CONTEXTS_PER_SLICE,
        sec_candidate_contexts_per_slice=SEC_CANDIDATE_CONTEXTS_PER_SLICE,
    )
    print(
        f"STATUS={manifest['status']} CONTEXTS={manifest['total_contexts']} "
        f"PAIRS_PER_ANNOTATOR={manifest['total_pairs_per_annotator']}"
    )
    print(f"CONTEXT_COUNTS={manifest['context_counts']}")
    print("THEORETICAL_COMBINED_GOLD_A_CONTEXTS=335")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
