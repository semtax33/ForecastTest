from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table as markdown, write_csv_artifacts
from equity_platform.sectors.industrials import (
    INDUSTRIALS_V1,
    build_annual_financial_bridge,
    build_industrials_research_baseline,
)
from equity_platform.sectors.industrials.market import build_market_inputs


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana/data-lake/bronze"
CONFIG = ROOT / "configs/industrials_v1.toml"
OUTPUT = ROOT / "output/industrials_valuation_v1_research"
COMPANYFACTS = ARCANA / "sec/companyfacts/CIK0000018230.json"
PRICE = ARCANA / "yfinance/price/CAT.csv"
BENCHMARK = ARCANA / "yfinance/benchmark/us_sp500.csv"
RISK_FREE = ARCANA / "fred/rates/us_dgs10.csv"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(config["as_of_date"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    financials = build_annual_financial_bridge(COMPANYFACTS, cutoff)
    market = build_market_inputs(
        companyfacts_path=COMPANYFACTS,
        price_path=PRICE,
        benchmark_path=BENCHMARK,
        risk_free_path=RISK_FREE,
        annual_financials=financials,
        cutoff=cutoff,
        equity_risk_premium_pct=float(config["equity_risk_premium_pct"]),
        fallback_credit_spread_pct=float(config["fallback_credit_spread_pct"]),
        beta_weeks=int(config["beta_weeks"]),
    )
    results = build_industrials_research_baseline(
        financials=financials,
        market=market,
        minimum_training_observations=int(config["minimum_training_observations"]),
        minimum_validation_observations=int(config["minimum_validation_observations"]),
        bridge_history_years=int(config["bridge_history_years"]),
        terminal_growth_pct=float(config["terminal_growth_pct"]),
        horizon_years=int(config["forecast_horizon_years"]),
    )
    artifacts = {"annual_financial_bridge": financials, "market_inputs": market, **results}
    write_csv_artifacts(OUTPUT, artifacts)
    source_hashes = hash_files(
        ROOT,
        (
            "configs/industrials_v1.toml",
            "equity_platform/sec.py",
            "equity_platform/valuation.py",
            "equity_platform/sectors/industrials/definition.py",
            "equity_platform/sectors/industrials/financials.py",
            "equity_platform/sectors/industrials/market.py",
            "equity_platform/sectors/industrials/model.py",
        ),
    )
    gate = results["industrials_v1_gate"].iloc[0]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "sector": INDUSTRIALS_V1.sector,
        "subindustry": INDUSTRIALS_V1.subindustry,
        "tickers": list(INDUSTRIALS_V1.tickers),
        "primary_anchor": INDUSTRIALS_V1.anchors[0].name,
        "anchor_promoted": bool(gate["anchor_promoted"]),
        "research_complete": bool(gate["industrials_v1_research_complete"]),
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "source_hashes": source_hashes,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = f"""# Industrials Valuation Platform V1 — CAT research baseline\n\n## Gate\n\n{markdown(results['industrials_v1_gate'])}\n\n## Anchor validation\n\n{markdown(results['anchor_validation'])}\n\n## Forecast and valuation bridge\n\n{markdown(results['forecast_financial_bridge'])}\n\n## Market inputs\n\n{markdown(market)}\n\nThe primary causal route is Orders/Backlog → Shipments → Revenue → Margin →\nReinvestment → ROIC/FCFF → Valuation. CAT's standardized SEC remaining-\nperformance-obligation history is used only when an expanding-window\nwalk-forward regression has at least the predeclared validation sample and\nstrictly beats the prior-year Revenue baseline on MASE. Otherwise V1 retains\nthe baseline and labels the anchor locked. This is a research platform, not a\nproduction model or investment recommendation.\n"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(results["industrials_v1_gate"].to_string(index=False))
    print(results["forecast_financial_bridge"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
