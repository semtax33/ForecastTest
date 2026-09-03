from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v521 import (
    verify_hii_v521_consensus,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v53 import (
    build_hii_v53_margin_research,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v5_3_hii_margin.toml"
OUTPUT = ROOT / "output/industrials_v5_3_hii_through_cycle_margin_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    v52_before = verify_hii_v52_valuation(ROOT)
    v521_before = verify_hii_v521_consensus(ROOT)

    artifacts = build_hii_v53_margin_research(root=ROOT, config=config)
    v52_after = verify_hii_v52_valuation(ROOT)
    v521_after = verify_hii_v521_consensus(ROOT)
    parents_unchanged = (
        v52_before["manifest_sha256"] == v52_after["manifest_sha256"]
        and v521_before["manifest_sha256"] == v521_after["manifest_sha256"]
    )
    gate = artifacts["hii_v53_gate"].copy()
    gate["frozen_parents_unchanged"] = parents_unchanged
    gate["research_freeze_eligible"] = gate["research_freeze_eligible"] & parents_unchanged
    artifacts["hii_v53_gate"] = gate
    write_csv_artifacts(OUTPUT, artifacts)

    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "parent_hii_v52_manifest_sha256": v52_after["manifest_sha256"],
        "parent_hii_v521_manifest_sha256": v521_after["manifest_sha256"],
        "frozen_parents_unchanged": parents_unchanged,
        "source_layers": artifacts["hii_v53_source_coverage"]["layer"].tolist(),
        "pdf_parsing_used": False,
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
            "# HII V5.3 through-cycle margin research benchmark",
            "",
            "This layer tests whether 8-12% long-run consolidated operating margins are supported by",
            "10-K, 10-Q, Arcana IR HTML, and PIT BLS industry evidence. It does not replace frozen V5.2",
            "DCF assumptions and grants no fair-value, terminal-input, or production authority.",
            "",
            "## Research summary",
            "",
            markdown_table(artifacts["hii_v53_research_summary"]),
            "",
            "## Catch-up-neutral margin distributions",
            "",
            markdown_table(artifacts["hii_margin_distribution"]),
            "",
            "## Terminal-margin feasibility",
            "",
            markdown_table(artifacts["hii_terminal_margin_feasibility"]),
            "",
            "## DCF and reverse-DCF cross-check",
            "",
            markdown_table(artifacts["hii_margin_dcf_reverse_crosscheck"]),
            "",
            "## Latest contract mix",
            "",
            markdown_table(
                artifacts["hii_contract_type_mix_history"].loc[
                    artifacts["hii_contract_type_mix_history"]["period"].eq("2026Q2")
                ]
            ),
            "",
            "## PIT industry cost-recovery context",
            "",
            markdown_table(artifacts["hii_industry_cost_recovery_diagnostic"]),
            "",
            "## Consensus and governance corrections",
            "",
            markdown_table(artifacts["hii_immutable_correction_record"]),
            "",
            markdown_table(artifacts["hii_consensus_semantics_corrected_summary"]),
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
