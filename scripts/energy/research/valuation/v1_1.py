from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tomllib

import pandas as pd

from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import MANIFEST, freeze_v11, verify_v11
from equity_platform.sectors.energy.valuation.v11 import run_valuation_v11
from energy_nowcast.valuation_v11.financial_adjustments import (
    overlay_latest_financials,
    rebuild_semantically_safe_financials,
)
from energy_nowcast.valuation_v11.perimeter import build_adjusted_market
from energy_nowcast.valuation_v11.sanity import (
    parent_boundary_audit,
    run_sanity_audit,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs" / "energy_valuation_v1_1.toml"
PARENT_CONFIG = ROOT / "configs" / "energy_valuation_v1.toml"
PARENT_OUTPUT = ROOT / "output" / "energy_valuation_v1"
OUTPUT = ROOT / "output" / "energy_valuation_v1_1"
COMPANYFACTS = (
    ROOT.parent / "Arcana" / "data-lake" / "bronze" / "sec" / "companyfacts"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Energy Valuation Platform V1.1 sanity-audited candidate"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--rebuild-candidate", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def _subindustry_value_comparison(
    parent_weighted: pd.DataFrame,
    candidate_weighted: pd.DataFrame,
) -> pd.DataFrame:
    parent = (
        parent_weighted.groupby("subindustry", as_index=False)
        .agg(
            v1_0_median_value_gap_pct=(
                "probability_weighted_value_gap_pct", "median"
            )
        )
    )
    candidate = (
        candidate_weighted.groupby("subindustry", as_index=False)
        .agg(
            v1_1_median_value_gap_pct=(
                "probability_weighted_value_gap_pct", "median"
            )
        )
    )
    result = parent.merge(candidate, on="subindustry", how="outer")
    result["median_value_gap_change_pct_points"] = (
        result["v1_1_median_value_gap_pct"] - result["v1_0_median_value_gap_pct"]
    )
    result["absolute_skew_reduction_pct_points"] = (
        result["v1_0_median_value_gap_pct"].abs()
        - result["v1_1_median_value_gap_pct"].abs()
    )
    return result


def _financial_comparison(
    parent_ttm: pd.DataFrame,
    candidate_ttm: pd.DataFrame,
) -> pd.DataFrame:
    def latest_summary(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        latest = (
            frame.loc[frame["ttm_complete"]]
            .sort_values(["ticker", "quarter_ordinal"])
            .groupby("ticker", as_index=False, group_keys=False)
            .tail(1)
        )
        return (
            latest.groupby("subindustry", as_index=False)
            .agg(
                **{
                    f"{prefix}_median_operating_margin_pct": (
                        "operating_margin_pct", "median"
                    ),
                    f"{prefix}_median_fcff_margin_pct": (
                        "fcff_margin_pct", "median"
                    ),
                    f"{prefix}_median_roic_pct": ("roic_pct", "median"),
                }
            )
        )

    result = latest_summary(parent_ttm, "v1_0").merge(
        latest_summary(candidate_ttm, "v1_1"),
        on="subindustry",
        how="outer",
    )
    result["fcff_margin_change_pct_points"] = (
        result["v1_1_median_fcff_margin_pct"]
        - result["v1_0_median_fcff_margin_pct"]
    )
    return result


def main() -> None:
    args = _arguments()
    manifest_path = ROOT / MANIFEST
    if manifest_path.exists() and not args.rebuild_candidate:
        print(json.dumps(verify_v11(ROOT), indent=2, ensure_ascii=False))
        return
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent_config = tomllib.loads(PARENT_CONFIG.read_text(encoding="utf-8"))
    parent_manifest = verify_v1(ROOT)

    frozen_quarterly = pd.read_parquet(
        PARENT_OUTPUT / "quarterly_financial_bridge.parquet"
    )
    parent_ttm = pd.read_parquet(PARENT_OUTPUT / "ttm_financial_bridge.parquet")
    parent_market = pd.read_csv(PARENT_OUTPUT / "market_inputs.csv")
    anchor_growth = pd.read_csv(PARENT_OUTPUT / "anchor_growth_inputs.csv")
    parent_assumptions = pd.read_csv(PARENT_OUTPUT / "scenario_assumptions.csv")
    parent_weighted = pd.read_csv(
        PARENT_OUTPUT / "forward_dcf_probability_weighted.csv"
    )

    quarterly, ttm, capex_semantics = rebuild_semantically_safe_financials(
        frozen_quarterly
    )
    market_with_financials = overlay_latest_financials(parent_market, ttm)
    adjusted_market, capital_claims = build_adjusted_market(
        market_with_financials, COMPANYFACTS
    )
    valuation = run_valuation_v11(ttm, adjusted_market, config, anchor_growth)
    sanity = run_sanity_audit(
        ttm=ttm,
        adjusted_market=adjusted_market,
        assumptions=valuation["scenario_assumptions"],
        projections=valuation["dcf_projections"],
        scenario_values=valuation["forward_dcf_scenario_values"],
        weighted=valuation["forward_dcf_probability_weighted"],
        reverse=valuation["reverse_dcf_expectations"],
        roundtrip=valuation["reverse_dcf_roundtrip"],
        config=config,
    )
    parent_boundary_detail, parent_boundary_summary = parent_boundary_audit(
        parent_assumptions, parent_config, config
    )
    value_comparison = _subindustry_value_comparison(
        parent_weighted, valuation["forward_dcf_probability_weighted"]
    )
    financial_comparison = _financial_comparison(parent_ttm, ttm)
    status = sanity["v1_1_completion_status"]
    research_complete = bool(
        status.loc[status["status_dimension"].eq("V1_1_RESEARCH"), "passed"].iloc[0]
    )

    artifacts = {
        "quarterly_financial_bridge_v1_1.parquet": quarterly,
        "ttm_financial_bridge_v1_1.parquet": ttm,
        "capex_semantics_audit.csv": capex_semantics,
        "adjusted_market_inputs.csv": adjusted_market,
        "capital_claims_reconciliation.csv": capital_claims,
        "scenario_assumptions.csv": valuation["scenario_assumptions"],
        "dcf_projections.csv": valuation["dcf_projections"],
        "forward_dcf_scenario_values.csv": valuation[
            "forward_dcf_scenario_values"
        ],
        "forward_dcf_probability_weighted.csv": valuation[
            "forward_dcf_probability_weighted"
        ],
        "reverse_dcf_expectations.csv": valuation["reverse_dcf_expectations"],
        "reverse_dcf_roundtrip.csv": valuation["reverse_dcf_roundtrip"],
        "expectations_gap.csv": valuation["expectations_gap"],
        "scenario_boundary_detail.csv": sanity["scenario_boundary_detail"],
        "scenario_boundary_summary.csv": sanity["scenario_boundary_summary"],
        "parent_v1_0_boundary_detail.csv": parent_boundary_detail,
        "parent_v1_0_boundary_summary.csv": parent_boundary_summary,
        "terminal_value_audit.csv": sanity["terminal_value_audit"],
        "terminal_value_summary.csv": sanity["terminal_value_summary"],
        "historical_fcff_sanity.csv": sanity["historical_fcff_sanity"],
        "historical_fcff_subindustry_summary.csv": sanity[
            "historical_fcff_subindustry_summary"
        ],
        "forward_fcff_sanity.csv": sanity["forward_fcff_sanity"],
        "reverse_dcf_roundtrip_summary.csv": sanity[
            "reverse_dcf_roundtrip_summary"
        ],
        "expectations_gap_outliers.csv": sanity["expectations_gap_outliers"],
        "subindustry_expectations_skew.csv": sanity[
            "subindustry_expectations_skew"
        ],
        "subindustry_value_comparison.csv": value_comparison,
        "subindustry_financial_comparison.csv": financial_comparison,
        "v1_1_requirement_audit.csv": sanity["v1_1_requirement_audit"],
        "v1_1_completion_status.csv": status,
    }
    for name, frame in artifacts.items():
        path = output / name
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False)

    failed = sanity["v1_1_requirement_audit"].loc[
        ~sanity["v1_1_requirement_audit"]["passed"], "requirement"
    ].tolist()
    metadata = {
        "version": config["version"],
        "parent_version": config["parent_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_v1_0_manifest_verified": True,
        "parent_v1_0_manifest_sha256": parent_manifest["manifest_sha256"],
        "v1_1_code_complete": research_complete,
        "v1_1_research_complete": research_complete,
        "v1_1_production_promoted": False,
        "live_matched_observations": "0/20",
        "freeze_eligible": research_complete,
        "failed_sanity_gates": failed,
        "config_sha256": _sha256(CONFIG),
        "scenario_weight_interpretation": (
            "DEFAULT_SCENARIO_WEIGHT_NOT_EMPIRICAL_PROBABILITY"
        ),
        "roic_semantics": {
            "historical_incremental_roic": (
                "DELTA_TTM_NOPAT_OVER_DELTA_INVESTED_CAPITAL_DIAGNOSTIC"
            ),
            "forecast_normalized_roic": (
                "NORMALIZED_FORWARD_RETURN_USED_FOR_REINVESTMENT_BRIDGE"
            ),
        },
        "valuation_perimeter": (
            "OPERATING_EV_MINUS_ADJUSTED_DEBT_MINUS_NCI_MINUS_PREFERRED_"
            "PLUS_CASH_PLUS_STANDARDIZED_NONOPERATING_ASSETS"
        ),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    report = f"""# Energy Valuation Platform V1.1 RC sanity audit

## Status

{_markdown(status)}

The immutable V1.0 manifest was verified before this run and remains unchanged.
V1.1 can be frozen only when every hard sanity invariant passes. Production
remains not promoted at 0/20 matched live-forward observations.

## Requirement audit

{_markdown(sanity['v1_1_requirement_audit'])}

## Boundary saturation: V1.0 parent

{_markdown(parent_boundary_summary)}

## Boundary saturation: V1.1 candidate

{_markdown(sanity['scenario_boundary_summary'])}

## Value-gap change

{_markdown(value_comparison)}

## Financial bridge change

{_markdown(financial_comparison)}

## Reverse DCF round-trip

{_markdown(sanity['reverse_dcf_roundtrip_summary'])}

## Terminal-value dependence

{_markdown(sanity['terminal_value_summary'])}

## Historical FCFF sanity by subindustry

{_markdown(sanity['historical_fcff_subindustry_summary'])}

## Expectations-gap skew

{_markdown(sanity['subindustry_expectations_skew'])}

## Accounting and solver corrections

- Net `PaymentsForProceedsFromOtherInvestingActivities` is rejected as gross
  cash CapEx and replaced only by a prior-only subindustry distribution.
- Debt concepts that already represent total long-term debt are not added to
  current debt a second time. If a current taxonomy gap reports zero debt while
  an older point-in-time debt fact exists, the last disclosed balance is carried
  forward and its fallback method is exposed in the reconciliation artifact.
- NCI and preferred claims are included in the EV-to-common-equity bridge when
  standardized facts exist. Lease liabilities are disclosed but not added a
  second time without a matching lease-expense adjustment.
- Reverse DCF returns an explicit unbracketed status instead of presenting the
  nearest search boundary as a market-implied assumption.
- Reinvestment is not clipped inside DCF projections, preserving the forward
  growth/reinvestment/normalized-ROIC identity.
- 60/20/20 values are labelled default scenario weights, not empirical
  probabilities. Possible/Plausible/Probable remains a story-validation class.

## Interpretation boundary

Historical incremental ROIC is a backward-looking change ratio. Forecast
normalized ROIC is a separate forward bridge assumption; they are not the same
metric. Terminal dependence and expectations-gap outliers are flags, not
investment recommendations.
"""
    (output / "report.md").write_text(report, encoding="utf-8")

    if args.freeze:
        if not research_complete:
            raise RuntimeError(
                f"V1.1 freeze prohibited by failed sanity gates: {failed}"
            )
        print(json.dumps(freeze_v11(ROOT), indent=2, ensure_ascii=False))
    else:
        print(
            f"Energy Valuation V1.1 candidate written to {output}; "
            f"freeze_eligible={research_complete}; failed={failed}"
        )


if __name__ == "__main__":
    main()
