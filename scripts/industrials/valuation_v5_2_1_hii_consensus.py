from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.hii_v521 import (
    build_hii_v521_consensus_overlay,
    freeze_hii_v521_consensus,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v5_2_hii_valuation.toml"
OUTPUT = ROOT / "output/industrials_v5_2_1_hii_consensus_overlay_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent = verify_hii_v52_valuation(ROOT)
    artifacts = build_hii_v521_consensus_overlay(root=ROOT, config=config)
    write_csv_artifacts(OUTPUT, artifacts)
    metadata = {
        "version": "INDUSTRIALS_V5_2_1_HII_CONSENSUS_EXPECTATIONS_OVERLAY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_hii_v52_manifest_sha256": parent["manifest_sha256"],
        "required_providers": ["ALPHA_VANTAGE", "FMP", "FINNWORLDS"],
        "additional_provider": "YAHOO",
        "consensus_used_to_fit_dcf": False,
        "terminal_authority": False,
        "production_promoted": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = "\n".join(
        [
            "# HII V5.2.1 consensus expectations overlay",
            "",
            "Finnworlds ratings and targets are added without changing frozen V5.2 DCF inputs.",
            "A provider reference price that disagrees with the official close is rejected as a valuation target.",
            "",
            "## Provider coverage",
            "",
            markdown_table(artifacts["hii_consensus_provider_coverage"]),
            "",
            "## Price-target vintages",
            "",
            markdown_table(artifacts["hii_analyst_price_target_vintages"]),
            "",
            "## Model versus analyst expectations",
            "",
            markdown_table(artifacts["hii_model_vs_analyst_expectations"]),
            "",
        ]
    )
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(report)
    frozen = freeze_hii_v521_consensus(ROOT)
    print(frozen["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
