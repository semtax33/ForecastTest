from __future__ import annotations

from contextlib import contextmanager

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v267 import extract_text_kpis_v267
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v266_ninth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v266_ninth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_7_spacy_semantic_firewall"


@contextmanager
def _development_inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": lambda config: None,
        "extract_text_kpis_v261": extract_text_kpis_v267,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def main() -> int:
    with _development_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    summary.loc[:, "version"] = "PLATFORM_V2_6_7_NINTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND"
    write_csv_artifacts(
        OUTPUT,
        {
            "ninth_disclosed_evaluation": detail,
            "ninth_disclosed_summary": summary,
            "ninth_disclosed_ladder": ladder,
            "ninth_disclosed_rejection_taxonomy": rejections,
        },
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
