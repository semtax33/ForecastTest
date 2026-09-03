from __future__ import annotations

import numpy as np
import pandas as pd

from ...data.cutoff import quarter_cutoff_date
from equity_platform.sectors.energy.research.revenue.v35.adapters import StandardizedKPIBundle


def _period_shift(value: str, quarters: int) -> str:
    return str(pd.Period(value, freq="Q") + quarters)


def _log_yoy(current: object, prior: object) -> float:
    current_value = pd.to_numeric(current, errors="coerce")
    prior_value = pd.to_numeric(prior, errors="coerce")
    if not np.isfinite(current_value) or not np.isfinite(prior_value) or current_value <= 0 or prior_value <= 0:
        return np.nan
    return float(100.0 * np.log(current_value / prior_value))


def _direction(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if not np.isfinite(numeric):
        return "UNKNOWN"
    if numeric > 0:
        return "UP"
    if numeric < 0:
        return "DOWN"
    return "FLAT"


def audit_quarter_alignment(
    predictions: pd.DataFrame,
    panel: pd.DataFrame,
    bundle: StandardizedKPIBundle,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    panel_keys = set(zip(panel["ticker"].astype(str), panel["quarter"].astype(str)))
    price_quarters = set(prices["quarter"].astype(str))
    guidance = bundle.production_guidance.copy()
    guidance["filing_date"] = pd.to_datetime(guidance["filing_date"], errors="coerce")
    rows = []
    for _, prediction in predictions.iterrows():
        ticker = str(prediction["ticker"])
        target = str(prediction["quarter"])
        cutoff = quarter_cutoff_date(target, 61)
        eligible_guidance = guidance.loc[
            guidance["ticker"].eq(ticker)
            & guidance["target_quarter"].astype(str).eq(target)
            & guidance["filing_date"].le(cutoff)
            & guidance["period_semantics"].astype(str).str.startswith("QUARTERLY")
        ].sort_values("filing_date")
        guidance_target = (
            str(eligible_guidance.iloc[-1]["target_quarter"])
            if prediction.get("volume_source") == "POINT_IN_TIME_GUIDANCE" and len(eligible_guidance)
            else None
        )
        revenue_quarter = target if (ticker, target) in panel_keys else None
        price_quarter = target if target in price_quarters else None
        prior_year = _period_shift(target, -4)
        fields = [target, revenue_quarter, price_quarter]
        if guidance_target is not None:
            fields.append(guidance_target)
        rows.append({
            "ticker": ticker,
            "target_quarter": target,
            "revenue_quarter": revenue_quarter,
            "guidance_target_quarter": guidance_target,
            "price_quarter": price_quarter,
            "prior_year_quarter": prior_year,
            "expected_prior_year_quarter": _period_shift(target, -4),
            "forecast_cutoff_date": cutoff,
            "candidate_status": prediction.get("candidate_status"),
            "volume_source": prediction.get("volume_source"),
            "quarter_alignment_ok": all(value == target for value in fields)
            and prior_year == _period_shift(target, -4),
        })
    return pd.DataFrame(rows).sort_values(["target_quarter", "ticker"]).reset_index(drop=True)


def audit_production_units(bundle: StandardizedKPIBundle) -> pd.DataFrame:
    actuals = bundle.production_actuals.copy()
    result = pd.DataFrame({
        "ticker": actuals["ticker"],
        "quarter": actuals["quarter"],
        "metric": "total_production",
        "raw_value": actuals["raw_total_value"],
        "raw_unit": actuals["raw_total_unit"],
        "normalized_value": actuals["total_mboed"],
        "normalized_unit": actuals["normalized_total_unit"],
        "conversion_rule": actuals["conversion_rule"],
        "filing_date": actuals["filing_date"],
        "source_url": actuals["source_url"],
        "source_path": actuals["source_path"],
        "quality_score": actuals["quality_score"],
        "adapter": actuals["adapter"],
    })
    result["unit_status"] = np.where(
        result["raw_unit"].astype(str).isin(["UNRESOLVED", "nan"]),
        "REVIEW_UNRESOLVED_RAW_UNIT",
        "TRACEABLE",
    )
    return result.sort_values(["ticker", "quarter"]).reset_index(drop=True)


def audit_guidance_semantics(bundle: StandardizedKPIBundle) -> pd.DataFrame:
    guidance = bundle.production_guidance.copy()
    guidance["filing_date"] = pd.to_datetime(guidance["filing_date"], errors="coerce")
    result = pd.DataFrame({
        "ticker": guidance["ticker"],
        "target_quarter": guidance["target_quarter"],
        "filing_date": guidance["filing_date"],
        "raw_value": guidance["raw_total_mid"],
        "raw_unit": guidance["raw_total_unit"],
        "normalized_value": guidance["total_mboed_mid"],
        "normalized_unit": guidance["normalized_total_unit"],
        "conversion_rule": guidance["conversion_rule"],
        "period_semantics": guidance["period_semantics"],
        "source_url": guidance["source_url"],
        "source_path": guidance["source_path"],
        "quality_score": guidance["quality_score"],
        "adapter": guidance["adapter"],
    })
    result["release_before_cutoff"] = [
        filing <= quarter_cutoff_date(str(target), 61)
        for filing, target in zip(result["filing_date"], result["target_quarter"])
    ]
    result["model_eligible"] = (
        result["period_semantics"].astype(str).str.startswith("QUARTERLY")
        & result["release_before_cutoff"]
        & result["normalized_value"].notna()
    )
    result["semantic_status"] = np.where(
        result["period_semantics"].astype(str).str.startswith("QUARTERLY"),
        "QUARTERLY_CONFIRMED",
        "EXCLUDED_NON_QUARTERLY_OR_AMBIGUOUS",
    )
    return result.sort_values(["ticker", "target_quarter", "filing_date"]).reset_index(drop=True)


def audit_direction_errors(
    predictions: pd.DataFrame,
    panel: pd.DataFrame,
    bundle: StandardizedKPIBundle,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    actuals = bundle.production_actuals.copy()
    actual_lookup = {
        (str(row["ticker"]), str(row["quarter"])): row
        for _, row in actuals.iterrows()
    }
    guidance = bundle.production_guidance.copy()
    guidance["filing_date"] = pd.to_datetime(guidance["filing_date"], errors="coerce")
    price_lookup = prices.set_index(prices["quarter"].astype(str)).to_dict(orient="index")
    panel_lookup = {
        (str(row["ticker"]), str(row["quarter"])): row
        for _, row in panel.iterrows()
    }
    rows = []
    valid = predictions.loc[predictions["candidate_status"].eq("AVAILABLE")]
    for _, prediction in valid.iterrows():
        ticker = str(prediction["ticker"])
        quarter = str(prediction["quarter"])
        prior_quarter = _period_shift(quarter, -4)
        target_actual = actual_lookup.get((ticker, quarter))
        prior_actual = actual_lookup.get((ticker, prior_quarter))
        current_price = price_lookup.get(quarter, {})
        prior_price = price_lookup.get(prior_quarter, {})
        revenue_row = panel_lookup[(ticker, quarter)]
        cutoff = quarter_cutoff_date(quarter, 61)
        eligible_guidance = guidance.loc[
            guidance["ticker"].eq(ticker)
            & guidance["target_quarter"].astype(str).eq(quarter)
            & guidance["filing_date"].le(cutoff)
            & guidance["period_semantics"].astype(str).str.startswith("QUARTERLY")
        ].sort_values("filing_date")
        guidance_release = eligible_guidance.iloc[-1]["filing_date"] if len(eligible_guidance) else pd.NaT
        actual_log_yoy = float(prediction["actual_log_yoy"])
        predicted_log_yoy = float(prediction["candidate_prediction"])
        correct = np.sign(actual_log_yoy) == np.sign(predicted_log_yoy)
        production_source = target_actual.get("source_path") if target_actual is not None else None
        rows.append({
            "ticker": ticker,
            "quarter": quarter,
            "actual_revenue": revenue_row.get("revenue"),
            "prior_year_revenue": revenue_row.get("prior_year_revenue"),
            "actual_log_yoy": actual_log_yoy,
            "predicted_log_yoy": predicted_log_yoy,
            "actual_direction": _direction(actual_log_yoy),
            "predicted_direction": _direction(predicted_log_yoy),
            "direction_correct": bool(correct),
            "oil_volume_yoy": _log_yoy(
                target_actual.get("oil_mbpd") if target_actual is not None else np.nan,
                prior_actual.get("oil_mbpd") if prior_actual is not None else np.nan,
            ),
            "ngl_volume_yoy": _log_yoy(
                target_actual.get("ngl_mbpd") if target_actual is not None else np.nan,
                prior_actual.get("ngl_mbpd") if prior_actual is not None else np.nan,
            ),
            "gas_volume_yoy": _log_yoy(
                target_actual.get("gas_mmcfd") if target_actual is not None else np.nan,
                prior_actual.get("gas_mmcfd") if prior_actual is not None else np.nan,
            ),
            "total_volume_yoy": _log_yoy(
                target_actual.get("total_mboed") if target_actual is not None else np.nan,
                prior_actual.get("total_mboed") if prior_actual is not None else np.nan,
            ),
            "oil_price_yoy": _log_yoy(current_price.get("wti_price"), prior_price.get("wti_price")),
            "ngl_price_yoy": _log_yoy(
                current_price.get("propane_price_bbl"), prior_price.get("propane_price_bbl")
            ),
            "gas_price_yoy": _log_yoy(current_price.get("henry_price"), prior_price.get("henry_price")),
            "component_growth_log_points": prediction.get("component_growth_log_points"),
            "basis_adjustment_log_points": prediction.get("basis_adjustment_log_points"),
            "volume_source": prediction.get("volume_source"),
            "guidance_release_date": guidance_release,
            "revenue_source": revenue_row.get("source_url"),
            "revenue_source_fact": revenue_row.get("source_fact"),
            "revenue_method": revenue_row.get("revenue_method"),
            "production_source": production_source,
            "mna_flag": target_actual.get("mna_flag") if target_actual is not None else np.nan,
            "likely_missing_driver": (
                "HEDGE_DERIVATIVE_OR_REVENUE_ACCOUNTING_SHOCK"
                if not correct and abs(float(revenue_row.get("revenue"))) < 0.25 * abs(float(revenue_row.get("prior_year_revenue")))
                else "MNA_OR_ASSET_PORTFOLIO_CHANGE"
                if not correct and target_actual is not None and bool(target_actual.get("mna_flag", False))
                else "BASIS_HEDGE_MARKETING_OR_MIX"
                if not correct
                else "NONE_DIRECTION_CORRECT"
            ),
            "diagnostic_priority": "DIRECTION_ERROR" if not correct else "CORRECT_DIRECTION_CONTROL",
        })
    return pd.DataFrame(rows).sort_values(
        ["direction_correct", "ticker", "quarter"]
    ).reset_index(drop=True)


def audit_basis_adjustment(
    time_predictions: pd.DataFrame,
    loco_predictions: pd.DataFrame,
) -> pd.DataFrame:
    time = time_predictions.loc[time_predictions["candidate_status"].eq("AVAILABLE")].copy()
    loco = loco_predictions.loc[loco_predictions["candidate_status"].eq("AVAILABLE")].copy()
    merged = time.merge(
        loco[["ticker", "quarter", "component_growth_log_points", "candidate_prediction"]],
        on=["ticker", "quarter"],
        suffixes=("_time", "_loco"),
    )
    result = pd.DataFrame({
        "ticker": merged["ticker"],
        "quarter": merged["quarter"],
        "actual_log_yoy": merged["actual_log_yoy"],
        "component_prediction": merged["component_growth_log_points_time"],
        "time_prediction_with_company_basis": merged["candidate_prediction_time"],
        "loco_component_prediction": merged["candidate_prediction_loco"],
        "basis_adjustment_log_points": merged["basis_adjustment_log_points"],
    })
    result["component_abs_error"] = (
        result["actual_log_yoy"] - result["component_prediction"]
    ).abs()
    result["basis_adjusted_abs_error"] = (
        result["actual_log_yoy"] - result["time_prediction_with_company_basis"]
    ).abs()
    result["basis_error_delta"] = (
        result["basis_adjusted_abs_error"] - result["component_abs_error"]
    )
    result["basis_worsened_error"] = result["basis_error_delta"].gt(0)
    result["component_prediction_matches_loco"] = np.isclose(
        result["component_prediction"], result["loco_component_prediction"], atol=1e-12
    )
    return result.sort_values(["ticker", "quarter"]).reset_index(drop=True)
