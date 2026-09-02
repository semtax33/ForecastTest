from __future__ import annotations

from datetime import date
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from ..operations.champion import sha256_file


MODEL_VERSION = "ENERGY_VALUATION_V1_1"


def _target_quarter(base_quarter: str, quarters_forward: int = 4) -> str:
    return str(pd.Period(base_quarter, freq="Q") + quarters_forward)


def _load_market_observation(
    root: Path,
    as_of_date: date,
    overrides_path: Path | None,
) -> pd.DataFrame:
    weighted = pd.read_csv(
        root / "output" / "energy_valuation_v1_1"
        / "forward_dcf_probability_weighted.csv"
    )[["ticker", "market_price"]]
    market_dates = pd.read_csv(
        root / "output" / "energy_valuation_v1" / "market_inputs.csv"
    )[["ticker", "market_date"]]
    result = weighted.merge(market_dates, on="ticker", how="left")
    result["market_price_source"] = "FROZEN_V1_1_WEIGHTED_ARTIFACT"
    if overrides_path is None:
        return result
    override = pd.read_csv(overrides_path)
    required = {"ticker", "market_date", "market_price"}
    missing = required.difference(override.columns)
    if missing:
        raise ValueError(f"Market override is missing columns: {sorted(missing)}")
    override = override.copy()
    override["ticker"] = override["ticker"].astype(str).str.upper()
    override["market_date"] = pd.to_datetime(
        override["market_date"], errors="raise"
    ).dt.date
    if override["ticker"].duplicated().any():
        raise ValueError("Market override has duplicate tickers")
    if override["market_date"].gt(as_of_date).any():
        raise ValueError("Market override contains observations after as-of date")
    lookup = override.set_index("ticker")
    result = result.set_index("ticker")
    common = result.index.intersection(lookup.index)
    result.loc[common, "market_price"] = lookup.loc[common, "market_price"]
    result.loc[common, "market_date"] = lookup.loc[common, "market_date"]
    result.loc[common, "market_price_source"] = (
        f"LIVE_OVERRIDE:{overrides_path.resolve()}:{sha256_file(overrides_path)}"
    )
    return result.reset_index()


def build_valuation_snapshots(
    root: Path,
    as_of_date: date,
    benchmark_manifest_sha256: str,
    market_overrides_path: Path | None = None,
) -> pd.DataFrame:
    output = root / "output" / "energy_valuation_v1_1"
    weighted_path = output / "forward_dcf_probability_weighted.csv"
    weighted = pd.read_csv(weighted_path)
    projections = pd.read_csv(output / "dcf_projections.csv")
    year_one = projections.loc[
        projections["scenario"].eq("BASE")
        & projections["forecast_year"].eq(1)
    ][[
        "ticker", "revenue_usd", "nopat_usd", "reinvestment_usd", "fcff_usd"
    ]].rename(columns={
        "revenue_usd": "base_year1_revenue_usd",
        "nopat_usd": "base_year1_nopat_usd",
        "reinvestment_usd": "base_year1_reinvestment_usd",
        "fcff_usd": "base_year1_fcff_usd",
    })
    assumptions = pd.read_csv(output / "scenario_assumptions.csv")
    base_quarter = assumptions.loc[
        assumptions["scenario"].eq("BASE"),
        ["ticker", "base_financial_quarter"],
    ]
    terminal = pd.read_csv(output / "terminal_value_audit.csv")
    terminal = terminal.loc[terminal["scenario"].eq("BASE"), [
        "ticker", "terminal_value_share_pct", "terminal_dependence_status"
    ]].rename(columns={
        "terminal_value_share_pct": "base_terminal_value_share_pct"
    })
    market = _load_market_observation(root, as_of_date, market_overrides_path)
    result = (
        weighted.drop(columns=["market_price"])
        .merge(year_one, on="ticker", validate="one_to_one")
        .merge(base_quarter, on="ticker", validate="one_to_one")
        .merge(terminal, on="ticker", validate="one_to_one")
        .merge(market, on="ticker", validate="one_to_one")
    )
    config = tomllib.loads(
        (root / "configs" / "energy_valuation_v1_1.toml").read_text(
            encoding="utf-8"
        )
    )
    outlier = float(config["sanity_gates"]["expectations_gap_outlier_abs_pct"])
    result["value_gap_pct"] = (
        result["probability_weighted_fair_value"] / result["market_price"] - 1.0
    ) * 100.0
    result["expectations_monitor_status"] = np.select(
        [
            result["subindustry"].eq("ep"),
            result["value_gap_pct"].abs().gt(outlier),
        ],
        ["E&P_SYSTEMATIC_SKEW_MONITOR", "COMPANY_OUTLIER_MONITOR"],
        default="STANDARD_MONITOR",
    )
    result["as_of_date"] = as_of_date.isoformat()
    result["target_quarter"] = result["base_financial_quarter"].map(
        _target_quarter
    )
    result["model_version"] = MODEL_VERSION
    result["fair_value"] = result["probability_weighted_fair_value"]
    result["market_data_date"] = pd.to_datetime(
        result["market_date"], errors="raise"
    ).dt.date.astype(str)
    result["benchmark_manifest_sha256"] = benchmark_manifest_sha256
    result["valuation_artifact_sha256"] = sha256_file(weighted_path)
    result["production_eligible"] = False
    columns = [
        "as_of_date", "ticker", "target_quarter", "model_version",
        "subindustry", "fair_value", "market_price", "market_data_date",
        "market_price_source", "value_gap_pct", "base_year1_revenue_usd",
        "base_year1_nopat_usd", "base_year1_reinvestment_usd",
        "base_year1_fcff_usd", "base_terminal_value_share_pct",
        "terminal_dependence_status", "expectations_monitor_status",
        "benchmark_manifest_sha256", "valuation_artifact_sha256",
        "production_eligible",
    ]
    return result[columns].sort_values("ticker").reset_index(drop=True)


def build_hypothesis_monitors(root: Path) -> pd.DataFrame:
    output = root / "output" / "energy_valuation_v1_1"
    weighted = pd.read_csv(output / "forward_dcf_probability_weighted.csv")
    config = tomllib.loads(
        (root / "configs" / "energy_valuation_v1_1.toml").read_text(
            encoding="utf-8"
        )
    )
    threshold = float(
        config["sanity_gates"]["expectations_gap_outlier_abs_pct"]
    )
    ep = weighted.loc[weighted["subindustry"].eq("ep")].copy()
    rows: list[dict[str, object]] = [{
        "hypothesis": "E&P_SYSTEMATIC_SKEW",
        "scope": "ep",
        "status": "MONITOR_DO_NOT_RETUNE",
        "metric": "median_probability_weighted_value_gap_pct",
        "value": float(ep["probability_weighted_value_gap_pct"].median()),
        "secondary_metric": "outliers_over_total",
        "secondary_value": (
            f"{int(ep['probability_weighted_value_gap_pct'].abs().gt(threshold).sum())}"
            f"/{len(ep)}"
        ),
    }]
    terminal = pd.read_csv(output / "terminal_value_audit.csv")
    base = terminal.loc[terminal["scenario"].eq("BASE")]
    for subindustry, group in base.groupby("subindustry", sort=True):
        rows.append({
            "hypothesis": "HIGH_TERMINAL_DEPENDENCE",
            "scope": subindustry,
            "status": "MONITOR_LONG_RUN_ECONOMICS",
            "metric": "median_base_terminal_value_share_pct",
            "value": float(group["terminal_value_share_pct"].median()),
            "secondary_metric": "high_or_unstable_tickers",
            "secondary_value": str(int(group["terminal_dependence_status"].isin([
                "HIGH_TERMINAL_DEPENDENCE",
                "UNSTABLE_OR_NONPOSITIVE_ENTERPRISE_VALUE",
            ]).sum())),
        })
    ttm = pd.read_parquet(
        root / "output" / "energy_valuation_v1" / "ttm_financial_bridge.parquet"
    )
    latest = (
        ttm.loc[ttm["ttm_complete"] & ttm["subindustry"].eq("ep")]
        .sort_values(["ticker", "quarter_ordinal"])
        .groupby("ticker", as_index=False, group_keys=False)
        .tail(1)
    )
    difference = latest["fcff_margin_pct"] - latest["operating_margin_pct"]
    rows.append({
        "hypothesis": "E&P_FCFF_MARGIN_ABOVE_OPERATING_MARGIN",
        "scope": "ep",
        "status": "MONITOR_CASH_CONVERSION_AND_CAPEX_FALLBACK",
        "metric": "median_fcff_minus_operating_margin_pct_points",
        "value": float(difference.median()),
        "secondary_metric": "tickers_above_over_total",
        "secondary_value": f"{int(difference.gt(0).sum())}/{len(difference)}",
    })
    return pd.DataFrame(rows)


def model_change_policy() -> pd.DataFrame:
    allowed = (
        "NEW_MARKET_PRICE", "ACTUAL_RELEASE", "CONSENSUS_VINTAGE",
        "LIVE_FORECAST_SNAPSHOT", "SETTLEMENT", "FCFF_ATTRIBUTION",
        "MONITORING_REPORT",
    )
    prohibited = (
        "WACC_FORMULA", "SCENARIO_BOUNDS", "TERMINAL_GROWTH",
        "FINANCIAL_BRIDGE", "PARSER_SEMANTICS", "E&P_MANUAL_OVERRIDE",
        "SCENARIO_WEIGHT_RETUNING",
    )
    rows = [
        {
            "change": change,
            "policy": "ALLOWED_APPEND_ONLY_OBSERVATION",
            "required_version_route": "ENERGY_VALUATION_V1_1_READ_ONLY",
        }
        for change in allowed
    ]
    rows.extend({
        "change": change,
        "policy": "PROHIBITED_IN_FROZEN_V1_1",
        "required_version_route": (
            "V1.1.1_BUGFIX_IF_PROVEN_BUG_ELSE_V1.2_RESEARCH"
        ),
    } for change in prohibited)
    return pd.DataFrame(rows)
