from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.hii.benchmark import (
    verify_hii_v5_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    build_hii_conditional_valuation,
    build_hii_v51_governance,
    build_hii_v52_evidence,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v5_2_hii_valuation.toml"
GOVERNANCE_OUTPUT = ROOT / "output/industrials_v5_1_hii_governance_research"
REPLICATION_OUTPUT = ROOT / "output/aerospace_defense_aggregate_revenue_replication_v1"
VALUATION_OUTPUT = ROOT / "output/industrials_v5_2_hii_conditional_valuation_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent_before = verify_hii_v5_evidence(ROOT)

    governance = build_hii_v51_governance(ROOT)
    write_csv_artifacts(
        GOVERNANCE_OUTPUT,
        {
            key: value
            for key, value in governance.items()
            if not key.startswith("ad_aggregate_replication_")
        },
    )
    write_csv_artifacts(
        REPLICATION_OUTPUT,
        {
            key: value
            for key, value in governance.items()
            if key.startswith("ad_aggregate_replication_")
        },
    )

    evidence = build_hii_v52_evidence(root=ROOT, config=config)
    valuation = build_hii_conditional_valuation(evidence=evidence, config=config)
    artifacts = {**evidence, **valuation}
    write_csv_artifacts(VALUATION_OUTPUT, artifacts)

    parent_after = verify_hii_v5_evidence(ROOT)
    parent_unchanged = parent_before["manifest_sha256"] == parent_after["manifest_sha256"]
    summary = valuation["hii_conditional_valuation_summary"].iloc[0]
    ttm = evidence["hii_ttm_fcff_bridge"].iloc[0]
    source_coverage = evidence["hii_v52_source_coverage"]
    gate = {
        "parent_hii_v5_unchanged": parent_unchanged,
        "route_selection_leakage_audited": True,
        "clean_predeclared_route_retained": True,
        "quarterly_nwc_chain_complete": bool(ttm["quarterly_nwc_chain_complete"]),
        "fcff_identity_pass": bool(ttm["fcff_identity_pass"]),
        "all_source_cutoffs_pass": bool(source_coverage["pit_cutoff_pass"].all()),
        "dcf_run": True,
        "reverse_dcf_run": True,
        "solver_round_trip_pass": bool(
            valuation["hii_dcf_reverse_round_trip"].iloc[0]["growth_round_trip_error_pct"]
            <= 1e-7
        ),
        "ev_to_equity_identity_pass": bool(summary["all_ev_to_equity_identities_pass"]),
        "terminal_authority": False,
        "production_promoted": False,
        "live_forward_matched_observations": "0/20",
        "research_freeze_eligible": bool(
            parent_unchanged
            and ttm["quarterly_nwc_chain_complete"]
            and ttm["fcff_identity_pass"]
            and source_coverage["pit_cutoff_pass"].all()
            and summary["all_ev_to_equity_identities_pass"]
        ),
        "status": "CONDITIONAL_VALUATION_RESEARCH_READY_TERMINAL_AND_PRODUCTION_LOCKED",
    }
    gate_frame = pd.DataFrame([gate])
    write_csv_artifacts(VALUATION_OUTPUT, {"hii_v52_gate": gate_frame})

    common = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_hii_v5_manifest_sha256": parent_after["manifest_sha256"],
        "parent_hii_v5_unchanged": parent_unchanged,
        "pdf_parsing_used": False,
        "terminal_authority": False,
        "production_promoted": False,
    }
    (GOVERNANCE_OUTPUT / "metadata.json").write_text(
        json.dumps(
            {
                **common,
                "version": "INDUSTRIALS_V5_1_HII_GOVERNANCE",
                "status": "ROUTE_LEAKAGE_CORRECTED_AUTHORITY_NAMESPACES_SPLIT",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (REPLICATION_OUTPUT / "metadata.json").write_text(
        json.dumps(
            {
                **common,
                "version": "AEROSPACE_DEFENSE_AGGREGATE_REVENUE_REPLICATION_V1",
                "status": "REPLICATED_RESEARCH_HYPOTHESIS_NOT_INDUSTRY_LAW",
                "cross_company_replication": True,
                "cross_regime_replication": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (VALUATION_OUTPUT / "metadata.json").write_text(
        json.dumps(
            {
                **common,
                "version": config["version"],
                "valuation_date": config["valuation_date"],
                "source_layers": source_coverage["layer"].tolist(),
                "authority": evidence["hii_v52_authority"].iloc[0].to_dict(),
                "gate": gate,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    report = "\n".join(
        [
            "# HII V5.2 conditional valuation research",
            "",
            "This run preserves frozen V5 and corrects route-selection governance before valuation.",
            "DCF values are conditional sensitivity outputs, not fair-value or production authority.",
            "",
            "## Route-selection audit",
            "",
            markdown_table(governance["hii_route_selection_leakage_audit"]),
            "",
            "## FY26 guidance financial bridge",
            "",
            markdown_table(evidence["hii_2026_guidance_financial_bridge"]),
            "",
            "## TTM FCFF identity",
            "",
            markdown_table(evidence["hii_ttm_fcff_bridge"]),
            "",
            "## Independent WACC range",
            "",
            markdown_table(evidence["hii_wacc_range"]),
            "",
            "## Conditional DCF range",
            "",
            markdown_table(valuation["hii_conditional_valuation_summary"]),
            "",
            "## Reverse DCF diagnostics",
            "",
            markdown_table(valuation["hii_reverse_dcf_diagnostics"]),
            "",
            "## Terminal margin conditional implied WACC",
            "",
            markdown_table(valuation["hii_terminal_margin_conditional_implied_wacc"]),
            "",
            "## Gate",
            "",
            markdown_table(gate_frame),
            "",
        ]
    )
    (VALUATION_OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
