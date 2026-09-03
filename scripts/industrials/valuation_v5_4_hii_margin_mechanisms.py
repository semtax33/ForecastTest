from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v53 import (
    verify_hii_v53_margin_research,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    build_hii_v54_margin_mechanism_research,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v5_4_hii_margin_mechanisms.toml"
OUTPUT = ROOT / "output/industrials_v5_4_hii_margin_mechanism_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    v52_before = verify_hii_v52_valuation(ROOT)
    v53_before = verify_hii_v53_margin_research(ROOT)
    artifacts = build_hii_v54_margin_mechanism_research(root=ROOT, config=config)
    v52_after = verify_hii_v52_valuation(ROOT)
    v53_after = verify_hii_v53_margin_research(ROOT)
    parents_unchanged = (
        v52_before["manifest_sha256"] == v52_after["manifest_sha256"]
        and v53_before["manifest_sha256"] == v53_after["manifest_sha256"]
    )
    gate = artifacts["hii_v54_gate"].copy()
    gate["frozen_parents_unchanged"] = parents_unchanged
    gate["research_freeze_eligible"] = gate["research_freeze_eligible"] & parents_unchanged
    artifacts["hii_v54_gate"] = gate
    write_csv_artifacts(OUTPUT, artifacts)

    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "parent_hii_v52_manifest_sha256": v52_after["manifest_sha256"],
        "parent_hii_v53_manifest_sha256": v53_after["manifest_sha256"],
        "frozen_parents_unchanged": parents_unchanged,
        "pdf_parsing_used": False,
        "contract_vintage_margin_identified": False,
        "direct_labor_hours_identified": False,
        "price_reset_lag_identified": False,
        "valuation_upgrade_allowed": False,
        "fair_value_claim_allowed": False,
        "terminal_authority": False,
        "production_promoted": False,
        "live_forward_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = "\n".join(
        [
            "# HII V5.4 margin mechanism research benchmark",
            "",
            "This layer asks which contemporaneous operational mechanisms could move HII from",
            "5-7% consolidated margins to 8-10% or more. It is not a valuation upgrade and",
            "does not grant fair-value, terminal-input, or production authority.",
            "",
            "## Summary",
            "",
            markdown_table(artifacts["hii_v54_research_summary"]),
            "",
            "## Guidance realization",
            "",
            markdown_table(artifacts["hii_guidance_realization_audit"]),
            "",
            "## Material guidance shocks",
            "",
            markdown_table(artifacts["hii_material_guidance_shocks"]),
            "",
            "## Cost-recovery mechanisms",
            "",
            markdown_table(artifacts["hii_cost_recovery_mechanism_evidence"]),
            "",
            "## Industry labor and material pressure",
            "",
            markdown_table(artifacts["hii_industry_labor_material_pressure_summary"]),
            "",
            "## Contemporaneous normalized margins",
            "",
            markdown_table(artifacts["hii_contemporaneous_margin_panel"]),
            "",
            "## Operational requirements",
            "",
            markdown_table(artifacts["hii_operational_margin_requirements"]),
            "",
            "## DCF and reverse-DCF cross-check",
            "",
            markdown_table(artifacts["hii_operational_margin_valuation_crosscheck"]),
            "",
            "## Mechanism scorecard",
            "",
            markdown_table(artifacts["hii_margin_mechanism_scorecard"]),
            "",
            "## Gate",
            "",
            markdown_table(gate),
            "",
        ]
    )
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
