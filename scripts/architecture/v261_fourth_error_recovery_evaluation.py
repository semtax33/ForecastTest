from __future__ import annotations

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v261 import extract_text_kpis_v261
import scripts.architecture.v26_fourth_holdout_evaluation as base


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_1_segment_domain_guards"


def evaluate_disclosed_fourth_set():
    prior = base.extract_text_kpis_v26
    base.extract_text_kpis_v26 = extract_text_kpis_v261
    try:
        detail, summary, ladder, rejections, evidence = base.evaluate_fourth_holdout()
    finally:
        base.extract_text_kpis_v26 = prior
    summary.loc[:, "version"] = "PLATFORM_V2_6_1_FOURTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND"
    return detail, summary, ladder, rejections, evidence


def main() -> int:
    detail, summary, ladder, rejections, evidence = evaluate_disclosed_fourth_set()
    write_csv_artifacts(OUTPUT, {
        "fourth_disclosed_evaluation": detail,
        "fourth_disclosed_summary": summary,
        "fourth_disclosed_ladder": ladder,
        "rejection_taxonomy": rejections,
        "evidence_source_coverage": evidence,
    })
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
