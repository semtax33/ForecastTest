from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


V52_OUTPUT = Path("output/industrials_v5_2_hii_conditional_valuation_research")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_hii_v521_consensus_overlay(
    *, root: Path, config: dict[str, Any]
) -> dict[str, pd.DataFrame]:
    financial = pd.read_csv(root / V52_OUTPUT / "hii_consensus_vintage_detail.csv")
    market = pd.read_csv(root / V52_OUTPUT / "hii_market_capitalization_bridge.csv").iloc[0]
    valuation = pd.read_csv(root / V52_OUTPUT / "hii_conditional_valuation_summary.csv").iloc[0]

    finn_path = Path(config["finnworlds_ratings"])
    finn = json.loads(finn_path.read_text(encoding="utf-8"))
    consensus = finn["data"]["result"]["output"]["analyst_consensus"]
    yahoo_path = Path(config["yahoo_consensus"])
    yahoo = json.loads(yahoo_path.read_text(encoding="utf-8"))["data"]
    yahoo_targets = yahoo["analyst_price_targets"]

    rows = [
        {
            "provider": "FINNWORLDS",
            "snapshot_date": finn["snapshot_date"],
            "metric_family": "RATING_AND_PRICE_TARGET",
            "reference_stock_price": float(consensus["stock_price"]),
            "target_average": float(consensus["analyst_average"]),
            "target_high": float(consensus["analyst_highest"]),
            "target_low": float(consensus["analyst_lowest"]),
            "analyst_count": int(consensus["analysts_number"]),
            "buy_count": int(consensus["buy"] or 0),
            "hold_count": int(consensus["hold"] or 0),
            "sell_count": int(consensus["sell"] or 0),
            "source_path": str(finn_path),
            "source_sha256": _sha256(finn_path),
        },
        {
            "provider": "YAHOO",
            "snapshot_date": "2026-07-31",
            "metric_family": "PRICE_TARGET",
            "reference_stock_price": float(yahoo_targets["current"]),
            "target_average": float(yahoo_targets["mean"]),
            "target_high": float(yahoo_targets["high"]),
            "target_low": float(yahoo_targets["low"]),
            "analyst_count": 11,
            "buy_count": pd.NA,
            "hold_count": pd.NA,
            "sell_count": pd.NA,
            "source_path": str(yahoo_path),
            "source_sha256": _sha256(yahoo_path),
        },
    ]
    targets = pd.DataFrame(rows)
    targets["reference_price_gap_vs_official_close_pct"] = (
        targets["reference_stock_price"] / float(market["market_price"]) - 1.0
    ) * 100.0
    targets["reference_price_quality_pass"] = targets[
        "reference_price_gap_vs_official_close_pct"
    ].abs().le(5.0)
    targets["reference_price_used_for_valuation"] = False
    targets["target_used_to_fit_dcf"] = False
    targets["use"] = "MODEL_VS_ANALYST_EXPECTATIONS_DIAGNOSTIC_ONLY"

    provider_rows = [
        {
            "provider": provider,
            "metric_family": "REVENUE_AND_EPS_ESTIMATES",
            "rows": len(group),
            "snapshot_dates": "|".join(sorted(group["snapshot_date"].astype(str).unique())),
            "used_to_fit_dcf": False,
        }
        for provider, group in financial.groupby("provider")
    ]
    provider_rows.append(
        {
            "provider": "FINNWORLDS",
            "metric_family": "RATING_AND_PRICE_TARGET",
            "rows": 1,
            "snapshot_dates": str(finn["snapshot_date"]),
            "used_to_fit_dcf": False,
        }
    )
    coverage = pd.DataFrame(provider_rows).sort_values("provider").reset_index(drop=True)
    target_median = float(targets["target_average"].median())
    comparison = pd.DataFrame(
        [
            {
                "valuation_date": config["valuation_date"],
                "official_market_close": float(market["market_price"]),
                "analyst_average_target_median": target_median,
                "analyst_target_upside_vs_close_pct": target_median / float(market["market_price"]) * 100.0 - 100.0,
                "scenario_weighted_conditional_dcf_per_share": float(valuation["scenario_weighted_conditional_value_per_share"]),
                "conditional_dcf_gap_vs_analyst_target_pct": float(valuation["scenario_weighted_conditional_value_per_share"]) / target_median * 100.0 - 100.0,
                "finnworlds_reference_price_quality_pass": bool(
                    targets.loc[targets["provider"].eq("FINNWORLDS"), "reference_price_quality_pass"].iloc[0]
                ),
                "official_close_remains_reverse_dcf_target": True,
                "analyst_target_used_to_fit_dcf": False,
                "terminal_authority": False,
                "production_promoted": False,
                "status": "CONSENSUS_EXPECTATIONS_OVERLAY_DIAGNOSTIC_ONLY",
            }
        ]
    )
    bad_reference_prices = targets.loc[~targets["reference_price_quality_pass"]]
    gate = pd.DataFrame(
        [
            {
                "required_providers": "ALPHA_VANTAGE|FMP|FINNWORLDS",
                "required_providers_present": bool(
                    {"ALPHA_VANTAGE", "FMP", "FINNWORLDS"}.issubset(set(coverage["provider"]))
                ),
                "all_consensus_is_out_of_model_fit": bool(~coverage["used_to_fit_dcf"].any()),
                "bad_reference_price_cannot_replace_official_close": bool(
                    (~bad_reference_prices["reference_price_used_for_valuation"]).all()
                    if len(bad_reference_prices)
                    else True
                ),
                "research_freeze_eligible": True,
                "terminal_input_allowed": False,
                "production_promoted": False,
            }
        ]
    )
    return {
        "hii_analyst_price_target_vintages": targets,
        "hii_consensus_provider_coverage": coverage,
        "hii_model_vs_analyst_expectations": comparison,
        "hii_v521_consensus_gate": gate,
    }
