from __future__ import annotations

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v262 import extract_text_kpis_v262
import scripts.architecture.v261_fifth_holdout_evaluation as base


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_2_range_and_route_guards"


def evaluate_disclosed_fifth_set():
    prior = base.extract_text_kpis_v261
    base.extract_text_kpis_v261 = extract_text_kpis_v262
    try:
        detail, summary, ladder, rejections = base.evaluate_fifth_holdout()
    finally:
        base.extract_text_kpis_v261 = prior
    summary.loc[:, "version"] = "PLATFORM_V2_6_2_FIFTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND"
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_disclosed_fifth_set()
    write_csv_artifacts(
        OUTPUT,
        {
            "fifth_disclosed_evaluation": detail,
            "fifth_disclosed_summary": summary,
            "fifth_disclosed_ladder": ladder,
            "fifth_disclosed_rejection_taxonomy": rejections,
        },
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
