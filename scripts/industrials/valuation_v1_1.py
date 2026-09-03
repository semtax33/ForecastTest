from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table as markdown, write_csv_artifacts
from equity_platform.sectors.industrials import (
    build_annual_financial_bridge,
    build_backlog_semantic_audit,
    build_cat_backlog_history,
    build_cat_segment_history,
    build_cat_sotp_research,
    build_next_year_backlog_bridge,
    build_segment_claim_reconciliation,
    load_cat_10k_sources,
)
from equity_platform.sectors.industrials.market import build_market_inputs


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana/data-lake/bronze"
CONFIG = ROOT / "configs/industrials_v1_1.toml"
OUTPUT = ROOT / "output/industrials_valuation_v1_1_research"
COMPANYFACTS = ARCANA / "sec/companyfacts/CIK0000018230.json"
PRICE = ARCANA / "yfinance/price/CAT.csv"
BENCHMARK = ARCANA / "yfinance/benchmark/us_sp500.csv"
RISK_FREE = ARCANA / "fred/rates/us_dgs10.csv"
V1_FORECAST = ROOT / "output/industrials_valuation_v1_research/forecast_financial_bridge.csv"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(config["as_of_date"])
    catalog_path = ROOT / str(config["source_catalog"])
    sources = load_cat_10k_sources(ROOT, catalog_path, cutoff, fetch_missing=True)
    consolidated = build_annual_financial_bridge(COMPANYFACTS, cutoff)
    segment_history = build_cat_segment_history(sources)
    backlog = build_cat_backlog_history(sources)
    semantic_audit = build_backlog_semantic_audit(backlog, consolidated)
    backlog_results = build_next_year_backlog_bridge(
        backlog,
        segment_history.rename(columns={"mpe_total_revenue_usd": "mpe_revenue_usd"}),
        minimum_history_observations=int(config["minimum_anchor_history_observations"]),
        minimum_validation_observations=int(
            config["minimum_anchor_validation_observations"]
        ),
    )
    market = build_market_inputs(
        companyfacts_path=COMPANYFACTS,
        price_path=PRICE,
        benchmark_path=BENCHMARK,
        risk_free_path=RISK_FREE,
        annual_financials=consolidated,
        cutoff=cutoff,
        equity_risk_premium_pct=float(config["equity_risk_premium_pct"]),
        fallback_credit_spread_pct=float(config["fallback_credit_spread_pct"]),
        beta_weeks=int(config["beta_weeks"]),
    )
    v1_forecast = pd.read_csv(V1_FORECAST) if V1_FORECAST.is_file() else None
    valuation = build_cat_sotp_research(
        segment_history=segment_history,
        market=market,
        backlog_results=backlog_results,
        bridge_history_years=int(config["bridge_history_years"]),
        terminal_growth_pct=float(config["terminal_growth_pct"]),
        horizon_years=int(config["forecast_horizon_years"]),
        finance_cost_of_equity_sensitivity_pct=float(
            config["finance_cost_of_equity_sensitivity_pct"]
        ),
        reverse_growth_lower_pct=float(config["reverse_growth_lower_pct"]),
        reverse_growth_upper_pct=float(config["reverse_growth_upper_pct"]),
        v1_forecast=v1_forecast,
    )
    claim_reconciliation = build_segment_claim_reconciliation(segment_history)
    artifacts = {
        "cat_10k_source_catalog": sources.drop(columns=["resolved_path"]),
        "cat_firm_order_backlog_history": backlog,
        "backlog_semantic_audit": semantic_audit,
        "cat_segment_history": segment_history,
        "segment_claim_reconciliation": claim_reconciliation,
        "market_inputs": market,
        **backlog_results,
        **valuation,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    source_hashes = hash_files(
        ROOT,
        (
            "configs/industrials_v1_1.toml",
            "configs/industrials_v1_1_cat_10k_sources.csv",
            "equity_platform/valuation.py",
            "equity_platform/sectors/industrials/backlog.py",
            "equity_platform/sectors/industrials/financials.py",
            "equity_platform/sectors/industrials/market.py",
            "equity_platform/sectors/industrials/segments.py",
            "equity_platform/sectors/industrials/sources.py",
            "equity_platform/sectors/industrials/sotp.py",
            "scripts/industrials/valuation_v1_1.py",
        ),
    )
    gate = valuation["industrials_v1_1_gate"].iloc[0]
    sotp = valuation["sotp_valuation"].iloc[0]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "research_layer": "SEMANTIC_BACKLOG_AND_SEGMENT_SOTP_AUDIT",
        "research_complete": bool(gate["research_audit_complete"]),
        "direct_backlog_anchor_promoted": bool(gate["direct_backlog_anchor_promoted"]),
        "terminal_input_allowed": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "sotp_value_per_share": float(sotp["sotp_value_per_share"]),
        "market_price": float(sotp["market_price"]),
        "valuation_interpretation": "RESEARCH_ONLY_NOT_A_MISPRICING_SIGNAL",
        "source_hashes": source_hashes,
        "sec_10k_source_hashes": {
            str(row.fiscal_year): row.source_sha256
            for row in sources.itertuples(index=False)
        },
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = f"""# Industrials Valuation V1.1 — CAT semantic and SOTP audit

## Research gate

{markdown(valuation['industrials_v1_1_gate'])}

## Backlog semantic result

{markdown(backlog_results['backlog_anchor_gate'])}

The retired V1 `RevenueRemainingPerformanceObligation` field is not treated as
CAT's firm order backlog. V1.1 directly parses firm backlog and the disclosed
amount not expected to be filled in the next year from each official 10-K.
Although the conditional bridge beats the naive baseline on the currently
available MASE sample, only two walk-forward validations exist versus the
predeclared minimum of three, so it remains locked and is not used in value.

## MP&E financial bridge

{markdown(valuation['mpe_forecast_financial_bridge'])}

## Financial Products standalone value

{markdown(valuation['financial_products_valuation'])}

Financial Products is valued from disclosed book equity, normalized ROE and a
stable-growth residual-income model. Funding debt stays inside the finance
business economics and is not subtracted again from MP&E equity value.

## SOTP result

{markdown(valuation['sotp_valuation'])}

## Reverse DCF

{markdown(valuation['sotp_reverse_dcf'])}

## V1 comparison

{markdown(valuation['v1_vs_v1_1_comparison'])}

This is a research-only semantic/accounting audit. The displayed gap is not a
mispricing conclusion. Terminal replacement, model freeze, and production
promotion remain prohibited; production stays locked at 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(valuation["industrials_v1_1_gate"].to_string(index=False))
    print(valuation["sotp_valuation"].to_string(index=False))
    print(valuation["sotp_reverse_dcf"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
