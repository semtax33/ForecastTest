from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from ..valuation.financials import (
    CASH_OPTIONS,
    CURRENT_DEBT_OPTIONS,
    ENERGY_TICKERS,
    SUBINDUSTRY,
    _coalesce_cash_flow,
    _coalesce_instant,
    build_quarterly_financials,
)
from ..valuation_v11.financial_adjustments import (
    rebuild_semantically_safe_financials,
)


DEPRECIATION_AMORTIZATION_OPTIONS = (
    "DepreciationDepletionAndAmortization",
    "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    "DepreciationDepletionAndAmortizationPropertyPlantAndEquipmentIncludingOilAndGasProperty",
)
CURRENT_ASSET_OPTIONS = ("AssetsCurrent",)
CURRENT_LIABILITY_OPTIONS = ("LiabilitiesCurrent",)


def _flow_d_and_a(
    companyfacts_root: Path,
    tickers: Iterable[str],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for ticker in tickers:
        frame = _coalesce_cash_flow(
            companyfacts_root,
            ticker,
            DEPRECIATION_AMORTIZATION_OPTIONS,
            "depreciation_amortization_usd",
        )
        if not frame.empty:
            rows.append(frame)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True, sort=False)


def _operating_nwc(
    companyfacts_root: Path,
    tickers: Iterable[str],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    specifications = (
        (CURRENT_ASSET_OPTIONS, "current_assets_usd"),
        (CASH_OPTIONS, "cash_for_nwc_usd"),
        (CURRENT_LIABILITY_OPTIONS, "current_liabilities_usd"),
        (CURRENT_DEBT_OPTIONS, "current_debt_for_nwc_usd"),
    )
    for ticker in tickers:
        merged: pd.DataFrame | None = None
        for options, value_name in specifications:
            metric = _coalesce_instant(
                companyfacts_root,
                ticker,
                options,
                value_name,
            )
            if metric.empty:
                continue
            wanted = [
                "ticker", "quarter", value_name,
                f"{value_name}_available_at", f"{value_name}_source_tag",
            ]
            merged = (
                metric[wanted]
                if merged is None
                else merged.merge(
                    metric[wanted], on=["ticker", "quarter"], how="outer"
                )
            )
        if merged is None or merged.empty:
            continue
        for column in (
            "current_assets_usd", "cash_for_nwc_usd",
            "current_liabilities_usd", "current_debt_for_nwc_usd",
        ):
            if column not in merged:
                merged[column] = np.nan
        merged["current_debt_for_nwc_usd"] = merged[
            "current_debt_for_nwc_usd"
        ].fillna(0.0)
        required = merged[[
            "current_assets_usd", "cash_for_nwc_usd",
            "current_liabilities_usd",
        ]].notna().all(axis=1)
        merged["operating_nwc_usd"] = np.where(
            required,
            merged["current_assets_usd"]
            - merged["cash_for_nwc_usd"]
            - merged["current_liabilities_usd"]
            + merged["current_debt_for_nwc_usd"],
            np.nan,
        )
        availability = [
            column for column in merged if column.endswith("_available_at")
        ]
        merged["operating_nwc_available_at"] = merged[availability].max(axis=1)
        merged["quarter_ordinal"] = merged["quarter"].map(
            lambda value: int(pd.Period(value, freq="Q").ordinal)
        )
        merged = merged.sort_values("quarter_ordinal")
        merged["delta_operating_nwc_usd"] = merged["operating_nwc_usd"].diff()
        merged["operating_nwc_method"] = np.where(
            required,
            "DELTA_CURRENT_ASSETS_MINUS_CASH_MINUS_CURRENT_LIABILITIES_PLUS_CURRENT_DEBT",
            "UNAVAILABLE_STANDARDIZED_CURRENT_BALANCE_COMPONENTS",
        )
        rows.append(merged)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True, sort=False)


def build_fcff_attribution(
    companyfacts_root: Path,
    as_of_date: pd.Timestamp,
    tickers: Iterable[str] = ENERGY_TICKERS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build diagnostic FCFF attribution without changing V1.1 valuation inputs.

    Detailed attribution keeps D&A and operating-NWC change separate. Any
    remaining cash conversion is explicitly stored as `other_cash_conversion`
    rather than being mislabeled as working capital. The combined CFO bridge is
    always retained as the fail-closed accounting identity.
    """
    tickers = tuple(tickers)
    cutoff = pd.Timestamp(as_of_date).normalize()
    raw, _ = build_quarterly_financials(companyfacts_root, tickers)
    quarterly, _, capex_audit = rebuild_semantically_safe_financials(raw)
    quarterly["financial_available_at"] = pd.to_datetime(
        quarterly["financial_available_at"], errors="coerce"
    )
    eligible = quarterly.loc[
        quarterly["core_financial_complete"]
        & quarterly["financial_available_at"].notna()
        & quarterly["financial_available_at"].le(cutoff)
    ].copy()
    latest = (
        eligible.sort_values(["ticker", "quarter_ordinal"])
        .groupby("ticker", as_index=False, group_keys=False)
        .tail(1)
    )

    d_and_a = _flow_d_and_a(companyfacts_root, tickers)
    if not d_and_a.empty:
        d_and_a["depreciation_amortization_usd_available_at"] = pd.to_datetime(
            d_and_a["depreciation_amortization_usd_available_at"], errors="coerce"
        )
        d_and_a = d_and_a.loc[
            d_and_a["depreciation_amortization_usd_available_at"].le(cutoff)
        ]
    nwc = _operating_nwc(companyfacts_root, tickers)
    if not nwc.empty:
        nwc["operating_nwc_available_at"] = pd.to_datetime(
            nwc["operating_nwc_available_at"], errors="coerce"
        )
        nwc = nwc.loc[nwc["operating_nwc_available_at"].le(cutoff)]

    columns = [
        "ticker", "quarter", "depreciation_amortization_usd",
        "depreciation_amortization_usd_method",
    ]
    if d_and_a.empty:
        d_and_a = pd.DataFrame(columns=columns)
    result = latest.merge(d_and_a[columns], on=["ticker", "quarter"], how="left")
    nwc_columns = [
        "ticker", "quarter", "delta_operating_nwc_usd", "operating_nwc_method",
    ]
    if nwc.empty:
        nwc = pd.DataFrame(columns=nwc_columns)
    result = result.merge(nwc[nwc_columns], on=["ticker", "quarter"], how="left")

    result["depreciation_amortization_method"] = result[
        "depreciation_amortization_usd_method"
    ].fillna("UNAVAILABLE_STANDARDIZED_D_AND_A_FACT")
    result["operating_nwc_method"] = result["operating_nwc_method"].fillna(
        "UNAVAILABLE_STANDARDIZED_CURRENT_BALANCE_COMPONENTS"
    )
    result["after_tax_interest_usd"] = result["interest_expense_usd"] * (
        1.0 - result["effective_tax_rate"]
    )
    result["combined_cash_conversion_adjustment_usd"] = (
        result["cfo_usd"] + result["after_tax_interest_usd"]
        - result["nopat_usd"]
    )
    detailed = result[[
        "depreciation_amortization_usd", "delta_operating_nwc_usd"
    ]].notna().all(axis=1)
    result["other_cash_conversion_usd"] = np.where(
        detailed,
        result["combined_cash_conversion_adjustment_usd"]
        - result["depreciation_amortization_usd"]
        + result["delta_operating_nwc_usd"],
        np.nan,
    )
    result["reconstructed_fcff_usd"] = np.where(
        detailed,
        result["nopat_usd"]
        + result["depreciation_amortization_usd"]
        - result["delta_operating_nwc_usd"]
        + result["other_cash_conversion_usd"]
        - result["cash_capex_usd"],
        np.nan,
    )
    result["combined_reconstructed_fcff_usd"] = (
        result["nopat_usd"]
        + result["combined_cash_conversion_adjustment_usd"]
        - result["cash_capex_usd"]
    )
    result["detailed_identity_error_usd"] = (
        result["reconstructed_fcff_usd"] - result["fcff_usd"]
    )
    result["combined_identity_error_usd"] = (
        result["combined_reconstructed_fcff_usd"] - result["fcff_usd"]
    )
    result["capex_imputed"] = result["cash_capex_imputed"].fillna(False)
    result["capex_monitor_status"] = np.where(
        result["capex_imputed"],
        "IMPUTED_CAPEX_REQUIRES_ATTRIBUTION_REVIEW",
        "DIRECT_CASH_CAPEX_DISCLOSURE",
    )
    result["attribution_status"] = np.where(
        detailed,
        "COMPLETE_D_AND_A_NWC_OTHER_SEPARATED",
        "PARTIAL_COMBINED_CASH_CONVERSION_ONLY",
    )
    result["diagnostic_only"] = True
    result["as_of_date"] = cutoff.date().isoformat()
    result["model_version"] = "ENERGY_VALUATION_V1_1"
    result["reported_fcff_usd"] = result["fcff_usd"]
    result["cash_capex_usd"] = result["cash_capex_usd"].abs()
    result["capex_method"] = result["cash_capex_usd_method"].fillna(
        "UNAVAILABLE"
    )
    result["subindustry"] = result["ticker"].map(SUBINDUSTRY)

    output_columns = [
        "as_of_date", "ticker", "quarter", "model_version", "subindustry",
        "financial_available_at", "nopat_usd", "depreciation_amortization_usd",
        "depreciation_amortization_method", "delta_operating_nwc_usd",
        "operating_nwc_method", "other_cash_conversion_usd",
        "combined_cash_conversion_adjustment_usd", "cash_capex_usd",
        "reported_fcff_usd", "reconstructed_fcff_usd",
        "combined_reconstructed_fcff_usd", "detailed_identity_error_usd",
        "combined_identity_error_usd", "capex_imputed", "capex_method",
        "capex_monitor_status", "attribution_status", "diagnostic_only",
    ]
    return result[output_columns].sort_values("ticker"), capex_audit
