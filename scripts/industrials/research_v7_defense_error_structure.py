from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.cross_company_v7 import (
    build_defense_cross_company_error_audit,
)
from equity_platform.sectors.industrials.aerospace_defense.gd_v6 import (
    verify_gd_v6_research,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    verify_hii_v54_margin_mechanism_research,
)


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/industrials_v7_defense_cross_company_error_audit"


def main() -> int:
    gd_before = verify_gd_v6_research(ROOT)
    hii_before = verify_hii_v54_margin_mechanism_research(ROOT)
    evidence = build_defense_cross_company_error_audit(ROOT)
    summary = evidence["defense_error_decomposition_summary"]
    period = evidence["defense_period_error_decomposition"]
    anchor = evidence["defense_anchor_portability_matrix"]
    gate = pd.DataFrame(
        [
            {
                "version": "INDUSTRIALS_V7_DEFENSE_CROSS_COMPANY_ERROR_STRUCTURE",
                "companies": summary["company"].nunique(),
                "company_periods": len(period),
                "decomposition_identity_pass": bool(
                    period["decomposition_identity_error_usd"].le(1.0).all()
                ),
                "frozen_routes_only": True,
                "anchor_rows": len(anchor),
                "outcome_blind_anchor_rows": int(
                    anchor["anchor_selection_outcome_blind"].sum()
                ),
                "positive_signal_before_cancellation_companies": int(
                    summary["aggregate_signal_positive_before_cancellation"].sum()
                ),
                "cancellation_dependent_companies": int(
                    summary["aggregate_outperformance_depends_on_cancellation"].sum()
                ),
                "universal_industry_law_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
                "research_freeze_eligible": bool(
                    summary["company"].nunique() == 4
                    and period["decomposition_identity_error_usd"].le(1.0).all()
                    and anchor["anchor_selection_outcome_blind"].all()
                ),
                "status": "CROSS_COMPANY_HYPOTHESIS_RESEARCH_NOT_UNIVERSAL_LAW",
            }
        ]
    )
    artifacts = {**evidence, "industrials_v7_defense_gate": gate}
    write_csv_artifacts(OUTPUT, artifacts)
    gd_after = verify_gd_v6_research(ROOT)
    hii_after = verify_hii_v54_margin_mechanism_research(ROOT)
    if gd_before["manifest_sha256"] != gd_after["manifest_sha256"]:
        raise RuntimeError("GD V6 frozen parent changed")
    if hii_before["manifest_sha256"] != hii_after["manifest_sha256"]:
        raise RuntimeError("HII V5.4 frozen parent changed")
    metadata = {
        "version": "INDUSTRIALS_V7_DEFENSE_CROSS_COMPANY_ERROR_STRUCTURE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gd_v6_manifest_sha256": gd_before["manifest_sha256"],
        "hii_v54_manifest_sha256": hii_before["manifest_sha256"],
        "frozen_inputs_only": True,
        "universal_industry_law_claim_allowed": False,
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Industrials V7 — Defense cross-company error structure audit

## Gate

{markdown_table(gate)}

## Aggregate skill versus error cancellation

{markdown_table(summary)}

The decomposition is an exact identity. A positive pre-cancellation skill means
the segment forecasts collectively beat the aggregate naive forecast before any
offsetting errors. Cancellation benefit is reported separately and never relabeled
as forecasting signal.

## Direct company model versus sum of segment models

{markdown_table(evidence['defense_direct_vs_segment_sum_model'])}

## Anchor portability

{markdown_table(anchor)}

All routes are read from frozen experiments. No anchor is reselected after this
cross-company outcome is observed. Four companies support hypothesis generation,
not a universal Aerospace & Defense law.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(summary.to_string(index=False))
    print(evidence["defense_direct_vs_segment_sum_model"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
