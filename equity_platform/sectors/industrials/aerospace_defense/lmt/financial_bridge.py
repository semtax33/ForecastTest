from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.common.reinvestment import trailing_origin_available_rates


def build_lmt_financial_bridge_forecast(*, walk_forward: pd.DataFrame, quarterly_actuals: pd.DataFrame, annual_actuals: pd.DataFrame, point_summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    company = walk_forward.groupby(["period", "forecast_as_of", "actual_available_at"], as_index=False).agg(
        predicted_revenue_usd=("predicted_sales_usd", "sum"), actual_revenue_usd=("actual_sales_usd", "sum"),
        predicted_operating_profit_usd=("predicted_operating_profit_usd", "sum"), actual_operating_profit_usd=("actual_operating_profit_usd", "sum"),
        all_revenue_claims_allowed=("revenue_performance_claim_allowed", "all"), all_margin_claims_allowed=("margin_performance_claim_allowed", "all"),
    )
    company["predicted_operating_margin_pct"] = company["predicted_operating_profit_usd"] / company["predicted_revenue_usd"] * 100.0
    company["actual_operating_margin_pct"] = company["actual_operating_profit_usd"] / company["actual_revenue_usd"] * 100.0
    q = quarterly_actuals.copy()
    q["filing_date"] = pd.to_datetime(q["filing_date"])
    q["capex_rate"] = q["discrete_capex_usd"] / q["discrete_revenue_usd"]
    q["da_rate"] = q["discrete_depreciation_amortization_usd"] / q["discrete_revenue_usd"]
    q["change_nwc_rate"] = q["change_operating_nwc_usd"] / q["discrete_revenue_usd"]
    q["tax_rate"] = (q["discrete_income_tax_usd"] / q["discrete_pretax_income_usd"]).where(lambda values: values.between(0.0, 0.50))
    annual = annual_actuals.copy()
    annual["filing_date"] = pd.to_datetime(annual["filing_date"])
    annual["rd_rate"] = annual["research_development_usd"] / annual["revenue_usd"]
    rows: list[dict[str, object]] = []
    for _, row in company.iterrows():
        cutoff = pd.Timestamp(row["forecast_as_of"])
        known_annual = annual.loc[annual["filing_date"].le(cutoff)]
        rates = trailing_origin_available_rates(q, cutoff=cutoff)
        if rates is None or known_annual.empty:
            continue
        latest_annual = known_annual.iloc[-1]
        nopat = row["predicted_operating_profit_usd"] * (1.0 - float(rates["tax_rate"]))
        net_capex = row["predicted_revenue_usd"] * (float(rates["capex_rate"]) - float(rates["da_rate"]))
        change_nwc = row["predicted_revenue_usd"] * float(rates["change_nwc_rate"])
        core = net_capex + change_nwc
        innovation = core + row["predicted_revenue_usd"] * float(latest_annual["rd_rate"])
        rows.append({
            **row.to_dict(), "tax_rate_source": "TRAILING_EIGHT_QUARTER_MEDIAN_AS_OF_ORIGIN", "forecast_tax_rate_pct": float(rates["tax_rate"] * 100.0),
            "predicted_nopat_usd": nopat, "predicted_net_capex_usd": net_capex, "predicted_change_operating_nwc_usd": change_nwc,
            "predicted_core_reinvestment_usd": core, "predicted_innovation_adjusted_reinvestment_usd": innovation,
            "predicted_innovation_adjusted_reinvestment_rate_pct": innovation / nopat * 100.0 if nopat else np.nan,
            "invested_capital_source_fiscal_year": int(latest_annual["fiscal_year"]),
            "latest_known_invested_capital_usd": latest_annual["invested_capital_usd"],
            "annualized_quarterly_roic_proxy_pct": nopat * 4.0 / latest_annual["invested_capital_usd"] * 100.0,
            "bridge_claim_allowed": bool(row["all_revenue_claims_allowed"] and row["all_margin_claims_allowed"] and point_summary["joint_champion"].all()),
            "roic_forecast_claim_allowed": False, "terminal_input_allowed": False,
        })
    bridge = pd.DataFrame(rows)
    summary = pd.DataFrame([{
        "forecast_periods": len(bridge), "forecast_first_period": bridge["period"].min(), "forecast_last_period": bridge["period"].max(),
        "revenue_margin_joint_champion_segments": int(point_summary["joint_champion"].sum()),
        "financial_bridge_claim_periods": int(bridge["bridge_claim_allowed"].sum()),
        "mean_revenue_ape_pct": float((bridge["predicted_revenue_usd"] / bridge["actual_revenue_usd"] - 1.0).abs().mean() * 100.0),
        "mean_operating_margin_error_pct_points": float((bridge["predicted_operating_margin_pct"] - bridge["actual_operating_margin_pct"]).abs().mean()),
        "reinvestment_forecast_is_conditional_bridge": True, "roic_forecast_claim_allowed": False, "terminal_input_allowed": False,
    }])
    return {"lmt_company_financial_bridge_forecast": bridge, "lmt_company_financial_bridge_summary": summary}
