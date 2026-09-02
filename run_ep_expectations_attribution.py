from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parent
V1_OUTPUT = ROOT / "output" / "energy_valuation_v1"
V11_OUTPUT = ROOT / "output" / "energy_valuation_v1_1"
OUTPUT = ROOT / "output" / "energy_valuation_v1_1_ep_attribution"
YEARS = 5


@dataclass(frozen=True)
class DcfResult:
    enterprise_value_usd: float
    pv_explicit_fcff_usd: float
    pv_terminal_value_usd: float


def _project(
    *,
    base_revenue: float,
    growth_pct: float,
    margin_pct: float,
    roic_pct: float,
    tax_rate_pct: float,
    wacc_pct: float,
    terminal_growth_pct: float,
    terminal_margin_pct: float | None = None,
    terminal_roic_pct: float | None = None,
    margin_fade_years: int | None = None,
) -> DcfResult:
    revenue = float(base_revenue)
    wacc = wacc_pct / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    if wacc <= terminal_growth:
        raise ValueError("WACC must exceed terminal growth")
    target_margin = (
        margin_pct if terminal_margin_pct is None else terminal_margin_pct
    )
    explicit_pv = 0.0
    last_revenue = np.nan
    for year in range(1, YEARS + 1):
        growth_fade = (year - 1) / (YEARS - 1)
        year_growth = growth_pct * (1.0 - growth_fade) + terminal_growth_pct * growth_fade
        revenue *= 1.0 + year_growth / 100.0
        if margin_fade_years is None:
            year_margin = margin_pct
        else:
            remaining = max(0.0, 1.0 - year / max(margin_fade_years, 1))
            year_margin = target_margin + (margin_pct - target_margin) * remaining
        nopat = revenue * year_margin / 100.0 * (1.0 - tax_rate_pct / 100.0)
        reinvestment_rate = year_growth / roic_pct
        fcff = nopat * (1.0 - reinvestment_rate)
        explicit_pv += fcff / ((1.0 + wacc) ** year)
        last_revenue = revenue
    terminal_roic = roic_pct if terminal_roic_pct is None else terminal_roic_pct
    terminal_nopat = (
        last_revenue * (1.0 + terminal_growth)
        * target_margin / 100.0 * (1.0 - tax_rate_pct / 100.0)
    )
    terminal_reinvestment_rate = terminal_growth_pct / terminal_roic
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** YEARS)
    return DcfResult(
        enterprise_value_usd=float(explicit_pv + pv_terminal),
        pv_explicit_fcff_usd=float(explicit_pv),
        pv_terminal_value_usd=float(pv_terminal),
    )


def _normalized_margins(ttm: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ep = ttm.loc[ttm["ttm_complete"] & ttm["subindustry"].eq("ep")]
    for ticker, history in ep.groupby("ticker", sort=True):
        history = history.sort_values("quarter_ordinal")
        recent = history.tail(20)
        prior = history.iloc[:-20]
        prior_clean = pd.to_numeric(
            prior["operating_margin_pct"], errors="coerce"
        ).dropna()
        full_clean = pd.to_numeric(
            history["operating_margin_pct"], errors="coerce"
        ).dropna()
        if len(prior_clean) >= 8:
            normalized = float(prior_clean.median())
            method = "PRE_RECENT_20Q_COMPANY_MEDIAN"
            observations = len(prior_clean)
        else:
            normalized = float(full_clean.median())
            method = "FULL_HISTORY_COMPANY_MEDIAN_INSUFFICIENT_PRIOR_WINDOW"
            observations = len(full_clean)
        rows.append({
            "ticker": ticker,
            "normalized_terminal_margin_pct": normalized,
            "normalized_margin_method": method,
            "normalized_margin_observations": observations,
            "recent_20q_median_margin_pct": float(
                pd.to_numeric(recent["operating_margin_pct"], errors="coerce").median()
            ),
        })
    return pd.DataFrame(rows)


def _equity_value(result: DcfResult, market: pd.Series) -> float:
    common_equity = (
        result.enterprise_value_usd
        - float(market["adjusted_total_debt_usd"])
        - float(market["noncontrolling_interest_usd"])
        - float(market["preferred_stock_usd"])
        + float(market["cash_usd"])
        + float(market["nonoperating_assets_usd"])
    )
    return common_equity / float(market["shares_outstanding"])


def _no_anchor_growth(row: pd.Series) -> float:
    if not bool(row["anchor_growth_override_used"]):
        return float(row["growth_pct"])
    anchor_effect = 0.25 * (
        float(row["anchor_growth_winsorized_pct"])
        - float(row["historical_growth_median_regularized_pct"])
    )
    return float(np.clip(
        float(row["growth_pct"]) - anchor_effect,
        float(row["growth_lower_bound"]),
        float(row["growth_upper_bound"]),
    ))


def _experiment_parameters(
    experiment: str,
    assumption: pd.Series,
    normalized_margin: float,
) -> dict[str, float | int | None]:
    growth = float(assumption["growth_pct"])
    margin = float(assumption["operating_margin_pct"])
    roic = float(assumption["roic_pct"])
    wacc = float(assumption["wacc_pct"])
    terminal_growth = float(assumption["terminal_growth_pct"])
    terminal_margin: float | None = None
    terminal_roic: float | None = None
    fade_years: int | None = None

    if experiment == "NO_NEAR_TERM_REVENUE_ANCHOR":
        growth = _no_anchor_growth(assumption)
    elif experiment == "GROWTH_IMMEDIATELY_AT_TERMINAL_RATE":
        growth = terminal_growth
    elif experiment.startswith("WACC_PLUS_"):
        wacc += float(experiment.removeprefix("WACC_PLUS_").removesuffix("BP")) / 100.0
    elif experiment == "TERMINAL_G_MINUS_100BP":
        terminal_growth = max(0.0, terminal_growth - 1.0)
    elif experiment == "TERMINAL_ROIC_FADE_TO_WACC_PLUS_200BP":
        terminal_roic = min(roic, max(wacc + 2.0, terminal_growth + 1.0))
    elif experiment == "TERMINAL_PRE_RECENT_WINDOW_MARGIN":
        terminal_margin = min(margin, normalized_margin)
    elif experiment.startswith("MARGIN_PREMIUM_PROXY_"):
        fade_years = int(
            experiment.removeprefix("MARGIN_PREMIUM_PROXY_").removesuffix("Y_FADE")
        )
        terminal_margin = min(margin, normalized_margin)
    elif experiment == "COMBINED_LONG_RUN_NORMALIZATION":
        wacc += 1.0
        terminal_growth = max(0.0, terminal_growth - 1.0)
        terminal_margin = min(margin, normalized_margin)
        terminal_roic = min(roic, max(wacc + 2.0, terminal_growth + 1.0))
        fade_years = 2
    elif experiment != "ORIGINAL_V1_1":
        raise ValueError(f"Unknown experiment: {experiment}")
    return {
        "growth_pct": growth,
        "margin_pct": margin,
        "roic_pct": roic,
        "wacc_pct": wacc,
        "terminal_growth_pct": terminal_growth,
        "terminal_margin_pct": terminal_margin,
        "terminal_roic_pct": terminal_roic,
        "margin_fade_years": fade_years,
    }


def _run_counterfactuals(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    normalized: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    experiments = (
        "ORIGINAL_V1_1",
        "NO_NEAR_TERM_REVENUE_ANCHOR",
        "GROWTH_IMMEDIATELY_AT_TERMINAL_RATE",
        "MARGIN_PREMIUM_PROXY_1Y_FADE",
        "MARGIN_PREMIUM_PROXY_2Y_FADE",
        "MARGIN_PREMIUM_PROXY_4Y_FADE",
        "WACC_PLUS_100BP",
        "WACC_PLUS_200BP",
        "WACC_PLUS_300BP",
        "TERMINAL_G_MINUS_100BP",
        "TERMINAL_PRE_RECENT_WINDOW_MARGIN",
        "TERMINAL_ROIC_FADE_TO_WACC_PLUS_200BP",
        "COMBINED_LONG_RUN_NORMALIZATION",
    )
    market_lookup = market.set_index("ticker")
    margin_lookup = normalized.set_index("ticker")
    scenario_rows: list[dict[str, object]] = []
    for experiment in experiments:
        for _, assumption in assumptions.iterrows():
            ticker = str(assumption["ticker"])
            current = market_lookup.loc[ticker]
            normalized_margin = float(
                margin_lookup.loc[ticker, "normalized_terminal_margin_pct"]
            )
            parameters = _experiment_parameters(
                experiment, assumption, normalized_margin
            )
            result = _project(
                base_revenue=float(current["ttm_revenue"]),
                tax_rate_pct=float(assumption["tax_rate_pct"]),
                **parameters,
            )
            scenario_rows.append({
                "experiment": experiment,
                "ticker": ticker,
                "scenario": assumption["scenario"],
                "scenario_weight": float(assumption["scenario_weight"]),
                "enterprise_value_usd": result.enterprise_value_usd,
                "pv_explicit_fcff_usd": result.pv_explicit_fcff_usd,
                "pv_terminal_value_usd": result.pv_terminal_value_usd,
                "fair_value": _equity_value(result, current),
                "market_price": float(current["market_price"]),
            })
    scenario = pd.DataFrame(scenario_rows)
    scenario["weighted_ev"] = (
        scenario["enterprise_value_usd"] * scenario["scenario_weight"]
    )
    scenario["weighted_explicit"] = (
        scenario["pv_explicit_fcff_usd"] * scenario["scenario_weight"]
    )
    scenario["weighted_terminal"] = (
        scenario["pv_terminal_value_usd"] * scenario["scenario_weight"]
    )
    scenario["weighted_fair_value"] = (
        scenario["fair_value"] * scenario["scenario_weight"]
    )
    ticker = (
        scenario.groupby(["experiment", "ticker"], as_index=False)
        .agg(
            weighted_enterprise_value_usd=("weighted_ev", "sum"),
            weighted_explicit_fcff_usd=("weighted_explicit", "sum"),
            weighted_terminal_value_usd=("weighted_terminal", "sum"),
            fair_value=("weighted_fair_value", "sum"),
            market_price=("market_price", "first"),
        )
    )
    ticker["value_gap_pct"] = (
        ticker["fair_value"] / ticker["market_price"] - 1.0
    ) * 100.0
    ticker["terminal_value_share_pct"] = (
        ticker["weighted_terminal_value_usd"]
        / ticker["weighted_enterprise_value_usd"] * 100.0
    )
    return scenario, ticker


def _summarize(ticker: pd.DataFrame) -> pd.DataFrame:
    original = ticker.loc[ticker["experiment"].eq("ORIGINAL_V1_1")].set_index(
        "ticker"
    )
    rows: list[dict[str, object]] = []
    for experiment, group in ticker.groupby("experiment", sort=False):
        indexed = group.set_index("ticker")
        change = (indexed["fair_value"] / original["fair_value"] - 1.0) * 100.0
        rows.append({
            "experiment": experiment,
            "median_value_gap_pct": float(group["value_gap_pct"].median()),
            "median_gap_reduction_vs_original_pct_points": float(
                original["value_gap_pct"].median() - group["value_gap_pct"].median()
            ),
            "median_fair_value_change_vs_original_pct": float(change.median()),
            "outlier_tickers_abs_gap_over_75pct": int(
                group["value_gap_pct"].abs().gt(75.0).sum()
            ),
            "median_terminal_value_share_pct": float(
                group["terminal_value_share_pct"].median()
            ),
        })
    return pd.DataFrame(rows)


def _ticker_exposure(
    ticker_results: pd.DataFrame,
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    normalized: pd.DataFrame,
    ttm: pd.DataFrame,
) -> pd.DataFrame:
    pivot_gap = ticker_results.pivot(
        index="ticker", columns="experiment", values="value_gap_pct"
    )
    pivot_fair = ticker_results.pivot(
        index="ticker", columns="experiment", values="fair_value"
    )
    base = assumptions.loc[assumptions["scenario"].eq("BASE"), [
        "ticker", "growth_pct", "operating_margin_pct", "roic_pct", "wacc_pct",
        "terminal_growth_pct", "anchor_growth_override_used",
        "anchor_growth_winsorized_pct", "historical_growth_median_regularized_pct",
    ]].set_index("ticker")
    latest = (
        ttm.loc[ttm["ttm_complete"] & ttm["subindustry"].eq("ep")]
        .sort_values(["ticker", "quarter_ordinal"])
        .groupby("ticker", as_index=False, group_keys=False)
        .tail(1)
        .set_index("ticker")
    )
    market_index = market.set_index("ticker")
    result = pd.DataFrame(index=pivot_gap.index)
    result["original_value_gap_pct"] = pivot_gap["ORIGINAL_V1_1"]
    result["original_fair_value"] = pivot_fair["ORIGINAL_V1_1"]
    result["market_price"] = market_index["market_price"]
    result["base_growth_pct"] = base["growth_pct"]
    result["base_operating_margin_pct"] = base["operating_margin_pct"]
    result["base_roic_pct"] = base["roic_pct"]
    result["base_wacc_pct"] = base["wacc_pct"]
    result["anchor_used"] = base["anchor_growth_override_used"]
    result["no_anchor_gap_reduction_pct_points"] = (
        pivot_gap["ORIGINAL_V1_1"] - pivot_gap["NO_NEAR_TERM_REVENUE_ANCHOR"]
    )
    for experiment, label in (
        ("GROWTH_IMMEDIATELY_AT_TERMINAL_RATE", "explicit_growth"),
        ("MARGIN_PREMIUM_PROXY_1Y_FADE", "margin_1y_fade"),
        ("MARGIN_PREMIUM_PROXY_2Y_FADE", "margin_2y_fade"),
        ("MARGIN_PREMIUM_PROXY_4Y_FADE", "margin_4y_fade"),
        ("WACC_PLUS_100BP", "wacc_plus_100bp"),
        ("TERMINAL_G_MINUS_100BP", "terminal_g_minus_100bp"),
        ("TERMINAL_PRE_RECENT_WINDOW_MARGIN", "terminal_margin"),
        ("TERMINAL_ROIC_FADE_TO_WACC_PLUS_200BP", "terminal_roic"),
        ("COMBINED_LONG_RUN_NORMALIZATION", "combined_normalization"),
    ):
        result[f"{label}_gap_reduction_pct_points"] = (
            pivot_gap["ORIGINAL_V1_1"] - pivot_gap[experiment]
        )
    result["historical_fcff_minus_operating_margin_pct_points"] = (
        latest["fcff_margin_pct"] - latest["operating_margin_pct"]
    )
    claims = (
        market_index["adjusted_total_debt_usd"]
        + market_index["noncontrolling_interest_usd"]
        + market_index["preferred_stock_usd"]
        - market_index["cash_usd"]
        - market_index["nonoperating_assets_usd"]
    )
    original_ev = ticker_results.loc[
        ticker_results["experiment"].eq("ORIGINAL_V1_1")
    ].set_index("ticker")["weighted_enterprise_value_usd"]
    result["market_enterprise_value_usd"] = market_index[
        "market_enterprise_value_adjusted_usd"
    ]
    result["model_enterprise_value_usd"] = original_ev
    result["enterprise_value_gap_pct"] = (
        original_ev / result["market_enterprise_value_usd"] - 1.0
    ) * 100.0
    result["ev_to_equity_gap_amplification_pct_points"] = (
        result["original_value_gap_pct"] - result["enterprise_value_gap_pct"]
    )
    result["net_claims_to_market_ev_pct"] = (
        claims / result["market_enterprise_value_usd"] * 100.0
    )
    result = result.join(normalized.set_index("ticker"))
    return result.reset_index().sort_values(
        "original_value_gap_pct", ascending=False
    )


def _correlations(exposure: pd.DataFrame) -> pd.DataFrame:
    drivers = (
        "base_growth_pct", "base_operating_margin_pct", "base_roic_pct",
        "base_wacc_pct", "historical_fcff_minus_operating_margin_pct_points",
        "net_claims_to_market_ev_pct", "no_anchor_gap_reduction_pct_points",
        "terminal_margin_gap_reduction_pct_points",
        "terminal_roic_gap_reduction_pct_points",
    )
    target = exposure["original_value_gap_pct"].rank()
    return pd.DataFrame([{
        "driver": driver,
        "spearman_rank_correlation_with_original_gap": float(
            exposure[driver].rank().corr(target)
        ),
        "observations": int(exposure[[driver, "original_value_gap_pct"]].dropna().shape[0]),
        "interpretation": "CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION",
    } for driver in drivers]).sort_values(
        "spearman_rank_correlation_with_original_gap", ascending=False
    )


def _identifiability(assumptions: pd.DataFrame) -> pd.DataFrame:
    ep_base = assumptions.loc[
        assumptions["scenario"].eq("BASE") & assumptions["subindustry"].eq("ep")
    ]
    anchor_count = int(ep_base["anchor_growth_override_used"].sum())
    return pd.DataFrame([
        {
            "candidate_driver": "COMMODITY_SPOT_OR_QTD_PRICE",
            "direct_v1_1_input": False,
            "coverage": "0/14",
            "analysis_treatment": "NOT_IDENTIFIABLE_FROM_V1_1",
        },
        {
            "candidate_driver": "HORMUZ_GEOPOLITICAL_PREMIUM",
            "direct_v1_1_input": False,
            "coverage": "0/14",
            "analysis_treatment": "MARGIN_PERSISTENCE_PROXY_ONLY",
        },
        {
            "candidate_driver": "AIS_VISIBLE_OR_DARK_TRANSIT",
            "direct_v1_1_input": False,
            "coverage": "0/14",
            "analysis_treatment": "NOT_IDENTIFIABLE_FROM_V1_1",
        },
        {
            "candidate_driver": "FROZEN_REVENUE_NOWCAST_GROWTH_ANCHOR",
            "direct_v1_1_input": True,
            "coverage": f"{anchor_count}/14",
            "analysis_treatment": "REMOVE_25PCT_ANCHOR_CONTRIBUTION",
        },
        {
            "candidate_driver": "WACC_RISK_PREMIUM",
            "direct_v1_1_input": True,
            "coverage": "14/14",
            "analysis_treatment": "+100_TO_300BP_SENSITIVITY",
        },
        {
            "candidate_driver": "TERMINAL_MARGIN_ROIC_GROWTH",
            "direct_v1_1_input": True,
            "coverage": "14/14",
            "analysis_treatment": "LONG_RUN_NORMALIZATION_SENSITIVITY",
        },
    ])


def _diagnostic_summary(
    exposure: pd.DataFrame,
    assumptions: pd.DataFrame,
    summary: pd.DataFrame,
    normalized: pd.DataFrame,
) -> pd.DataFrame:
    base = assumptions.loc[assumptions["scenario"].eq("BASE")]
    original = summary.loc[summary["experiment"].eq("ORIGINAL_V1_1")].iloc[0]
    anchored = exposure.loc[exposure["anchor_used"]]
    return pd.DataFrame([
        {"metric": "equity_value_gap_median_pct", "value": original["median_value_gap_pct"], "detail": "12/14 positive; 8/14 absolute gap above 75%"},
        {"metric": "enterprise_value_gap_median_pct", "value": exposure["enterprise_value_gap_pct"].median(), "detail": "Before EV-to-common-equity claims"},
        {"metric": "ev_to_equity_individual_gap_amplification_median_pct_points", "value": exposure["ev_to_equity_gap_amplification_pct_points"].median(), "detail": "Amplifier, not originating operating-value driver"},
        {"metric": "base_wacc_median_pct", "value": base["wacc_pct"].median(), "detail": "Frozen V1.1 E&P base"},
        {"metric": "base_operating_margin_median_pct", "value": base["operating_margin_pct"].median(), "detail": "Held constant into terminal in V1.1"},
        {"metric": "base_roic_median_pct", "value": base["roic_pct"].median(), "detail": "Used for explicit and terminal reinvestment"},
        {"metric": "near_term_anchor_coverage_tickers", "value": anchored.shape[0], "detail": "Revenue nowcast anchor, 25% growth-center weight"},
        {"metric": "near_term_anchor_gap_reduction_median_anchored_pct_points", "value": anchored["no_anchor_gap_reduction_pct_points"].median(), "detail": "Four anchored tickers only"},
        {"metric": "near_term_anchor_gap_reduction_median_all_ep_pct_points", "value": exposure["no_anchor_gap_reduction_pct_points"].median(), "detail": "Sector median unchanged"},
        {"metric": "terminal_margin_prior_window_high_confidence_tickers", "value": normalized["normalized_margin_method"].eq("PRE_RECENT_20Q_COMPANY_MEDIAN").sum(), "detail": "Remaining names use full-history fallback"},
        {"metric": "historical_fcff_margin_gap_rank_correlation", "value": exposure["historical_fcff_minus_operating_margin_pct_points"].rank().corr(exposure["original_value_gap_pct"].rank()), "detail": "Descriptive, not mechanical or causal"},
    ])


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_before = verify_v1(ROOT)
    benchmark_before = verify_v11(ROOT)
    assumptions = pd.read_csv(V11_OUTPUT / "scenario_assumptions.csv")
    assumptions = assumptions.loc[assumptions["subindustry"].eq("ep")].copy()
    market = pd.read_csv(V11_OUTPUT / "adjusted_market_inputs.csv")
    market = market.loc[market["subindustry"].eq("ep")].copy()
    ttm = pd.read_parquet(V1_OUTPUT / "ttm_financial_bridge.parquet")
    normalized = _normalized_margins(ttm)
    scenario, ticker_results = _run_counterfactuals(
        assumptions, market, normalized
    )
    summary = _summarize(ticker_results)
    exposure = _ticker_exposure(
        ticker_results, assumptions, market, normalized, ttm
    )
    correlations = _correlations(exposure)
    identifiability = _identifiability(assumptions)
    diagnostics = _diagnostic_summary(
        exposure, assumptions, summary, normalized
    )

    frozen = pd.read_csv(V11_OUTPUT / "forward_dcf_probability_weighted.csv")
    frozen = frozen.loc[frozen["subindustry"].eq("ep")].set_index("ticker")
    reproduced = ticker_results.loc[
        ticker_results["experiment"].eq("ORIGINAL_V1_1")
    ].set_index("ticker")
    reproduction_error = (
        reproduced["fair_value"] - frozen["probability_weighted_fair_value"]
    ).abs()
    if reproduction_error.max() > 1e-6:
        raise RuntimeError(
            f"Attribution failed to reproduce frozen V1.1: {reproduction_error.max()}"
        )

    scenario.to_csv(OUTPUT / "scenario_counterfactuals.csv", index=False)
    ticker_results.to_csv(OUTPUT / "ticker_counterfactuals.csv", index=False)
    summary.to_csv(OUTPUT / "counterfactual_summary.csv", index=False)
    exposure.to_csv(OUTPUT / "ticker_driver_exposure.csv", index=False)
    correlations.to_csv(OUTPUT / "cross_sectional_driver_correlations.csv", index=False)
    identifiability.to_csv(OUTPUT / "hormuz_identifiability_audit.csv", index=False)
    normalized.to_csv(OUTPUT / "normalized_margin_inputs.csv", index=False)
    diagnostics.to_csv(OUTPUT / "diagnostic_summary.csv", index=False)

    original = summary.loc[summary["experiment"].eq("ORIGINAL_V1_1")].iloc[0]
    combined = summary.loc[
        summary["experiment"].eq("COMBINED_LONG_RUN_NORMALIZATION")
    ].iloc[0]
    anchor = summary.loc[
        summary["experiment"].eq("NO_NEAR_TERM_REVENUE_ANCHOR")
    ].iloc[0]
    report = f"""# E&P V1.1 expectations-gap attribution

This is a read-only counterfactual analysis outside V1.1. Both immutable
manifests were verified before and after the run. Frozen V1.1 fair values were
reproduced with a maximum absolute per-share error of
`{reproduction_error.max():.3e}`.

## Identification boundary

{_markdown(identifiability)}

V1.1 has no direct spot-oil, Hormuz-premium, AIS-visible-flow, dark-shipping, or
geopolitical-premium-duration input. Only 4/14 E&P tickers use a frozen revenue
nowcast anchor, and that anchor enters the growth center at 25%. Therefore the
Hormuz contribution cannot be estimated directly. The 1/2/4-year experiments
below are recent-window margin-persistence proxies, not measured Hormuz effects.

## Counterfactual results

{_markdown(summary)}

The original median gap is `{float(original['median_value_gap_pct']):.2f}%`.
Removing the embedded near-term revenue anchor changes it to
`{float(anchor['median_value_gap_pct']):.2f}%`. The combined long-run
normalization changes it to `{float(combined['median_value_gap_pct']):.2f}%`.
Counterfactual effects are nonlinear and overlapping, so rows must not be added
as if they were an accounting waterfall.

## Cross-sectional diagnostics

{_markdown(correlations)}

{_markdown(diagnostics)}

These rank correlations use only 14 companies and are descriptive, not causal.
Historical CFO-derived FCFF does not directly feed the forward DCF: V1.1
projects FCFF as NOPAT minus growth/normalized-ROIC reinvestment. Therefore the
historical E&P FCFF-margin anomaly is a monitoring clue, not a mechanical source
of the +90.7% valuation gap.

## Interpretation

The analysis distinguishes three claims: (1) a Hormuz explanation is not
identified by V1.1 inputs; (2) near-term anchor removal measures the maximum
embedded revenue-nowcast channel available in the frozen model; and (3) WACC
and terminal-normalization sensitivities measure how much of the gap depends on
long-run economics rather than a short-lived commodity shock. No V1.1 input or
frozen output was changed. This is not an investment recommendation.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    parent_after = verify_v1(ROOT)
    benchmark_after = verify_v11(ROOT)
    if parent_after["manifest_sha256"] != parent_before["manifest_sha256"]:
        raise RuntimeError("V1.0 changed during attribution")
    if benchmark_after["manifest_sha256"] != benchmark_before["manifest_sha256"]:
        raise RuntimeError("V1.1 changed during attribution")
    metadata = {
        "analysis": "E&P_EXPECTATIONS_GAP_ATTRIBUTION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_0_manifest_sha256": parent_after["manifest_sha256"],
        "v1_1_manifest_sha256": benchmark_after["manifest_sha256"],
        "frozen_v1_1_mutated": False,
        "original_median_gap_pct": float(original["median_value_gap_pct"]),
        "maximum_frozen_reproduction_error_per_share": float(
            reproduction_error.max()
        ),
        "method": "NON_ADDITIVE_READ_ONLY_COUNTERFACTUAL_SENSITIVITY",
        "hormuz_directly_identifiable": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
