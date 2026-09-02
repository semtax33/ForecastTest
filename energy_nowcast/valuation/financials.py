from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..research.phase6.financial_targets import (
    EP_TICKERS,
    INTEGRATED_TICKERS,
    REFINING_TICKERS,
    SERVICES_TICKERS,
)
from ..research.v351.revenue import CIKS, load_companyfacts_quarterly_revenue


MIDSTREAM_TICKERS = ("KMI", "WMB", "ET", "EPD")
ENERGY_TICKERS = (
    *EP_TICKERS,
    *INTEGRATED_TICKERS,
    *REFINING_TICKERS,
    *MIDSTREAM_TICKERS,
    *SERVICES_TICKERS,
)

SUBINDUSTRY = {
    **{ticker: "ep" for ticker in EP_TICKERS},
    **{ticker: "integrated" for ticker in INTEGRATED_TICKERS},
    **{ticker: "refining" for ticker in REFINING_TICKERS},
    **{ticker: "midstream" for ticker in MIDSTREAM_TICKERS},
    **{ticker: "services" for ticker in SERVICES_TICKERS},
}

ANCHOR = {
    "ep": "PRODUCTION_PLUS_REALIZED_PRICE",
    "integrated": "SEGMENT_EARNINGS",
    "refining": "THROUGHPUT_PLUS_REFINING_MARGIN",
    "midstream": "VOLUME_PLUS_FEE_PLUS_ADJUSTED_EBITDA",
    "services": "ACTIVITY_PLUS_PRICING_PLUS_OPERATING_MARGIN",
}

ANCHOR_ROUTE = {
    "ep": "V3.5.3_GROUPED_REVENUE_PLUS_CONDITIONAL_COST_REINVESTMENT",
    "integrated": "SEGMENT_EARNINGS_DOWNSTREAM_CANDIDATE_OTHER_BASELINE",
    "refining": "P2.1_REVENUE_PLUS_THROUGHPUT_CRACK_CAPTURE_BRIDGE",
    "midstream": "LAG_ADJUSTED_EBITDA_PLUS_VOLUME_FEE_BRIDGE",
    "services": "STRUCTURAL_REVENUE_PLUS_ACTIVITY_MARGIN_BRIDGE",
}


CAPEX_COMPONENTS: dict[str, tuple[str, ...]] = {
    "AR": (
        "PaymentsToAcquireOilAndGasProperty",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ),
    "CNX": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "COP": (
        "PaymentsForProceedsFromProductiveAssets",
        "PaymentsToAcquireProductiveAssets",
    ),
    "DVN": ("PaymentsToAcquireProductiveAssets",),
    "EOG": (
        "PaymentsToAcquireOilAndGasPropertyAndEquipment",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ),
    "EQT": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "FANG": (
        "PaymentsToAcquireOilAndGasProperty",
        "PaymentsToAcquireOilAndGasEquipment",
    ),
    "MGY": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "MTDR": ("PaymentsToAcquireOtherPropertyPlantAndEquipment",),
    "NOG": (
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
        "PaymentsToAcquireOilAndGasPropertyAndEquipment",
    ),
    "OVV": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "PR": (
        "PaymentsToAcquireOilAndGasProperty",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ),
    "RRC": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "SM": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "XOM": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "CVX": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "VLO": (
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ),
    "MPC": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    # PSX maps its disclosed capital expenditures and investments to this
    # generic cash-flow concept. It remains explicitly ticker-specific.
    "PSX": ("PaymentsForProceedsFromOtherInvestingActivities",),
    "KMI": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "WMB": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "ET": ("PaymentsToAcquireProductiveAssets",),
    "EPD": (
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ),
    "SLB": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "HAL": ("PaymentsToAcquireProductiveAssets",),
    "BKR": ("PaymentsToAcquireProductiveAssets",),
}

CAPEX_ADDITIVE_TICKERS = {"AR", "EOG", "PR"}

OPERATING_INCOME_OPTIONS = ("OperatingIncomeLoss",)
NET_INCOME_OPTIONS = ("ProfitLoss", "NetIncomeLoss")
TAX_OPTIONS = ("IncomeTaxExpenseBenefit",)
INTEREST_OPTIONS = (
    "InterestExpense",
    "InterestAndDebtExpense",
    "InterestExpenseDebt",
    "InterestExpenseNonoperating",
    "InterestIncomeExpenseNet",
    "InterestIncomeExpenseNonoperatingNet",
)
CFO_OPTIONS = ("NetCashProvidedByUsedInOperatingActivities",)

CASH_OPTIONS = (
    "Cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
CURRENT_DEBT_OPTIONS = (
    "DebtCurrent",
    "LongTermDebtCurrent",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "ShortTermBorrowings",
)
NONCURRENT_DEBT_OPTIONS = (
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtNoncurrent",
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    "LongTermDebt",
)
EQUITY_OPTIONS = (
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest",
    "StockholdersEquity",
    "PartnersCapital",
)


def _quarter(value: pd.Timestamp) -> str:
    return str(value.to_period("Q"))


def _ordinal(value: str) -> int:
    return int(pd.Period(value, freq="Q").ordinal)


@lru_cache(maxsize=64)
def _companyfacts(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fact_frame(
    companyfacts_root: Path,
    ticker: str,
    tag: str,
    unit: str = "USD",
) -> pd.DataFrame:
    path = companyfacts_root / f"CIK{CIKS[ticker]:010d}.json"
    payload = _companyfacts(str(path))
    fact = payload.get("facts", {}).get("us-gaap", {}).get(tag, {})
    values = fact.get("units", {}).get(unit, [])
    frame = pd.DataFrame(values)
    if frame.empty:
        return frame
    for column in ("start", "end", "filed"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
    frame["source_tag"] = f"us-gaap:{tag}"
    frame["source_path"] = str(path)
    return frame


def _original_duration(
    facts: pd.DataFrame,
    form: str,
    minimum_days: int,
    maximum_days: int,
) -> pd.DataFrame:
    if facts.empty or "start" not in facts:
        return pd.DataFrame()
    selected = facts.loc[facts["form"].eq(form)].copy()
    selected["duration_days"] = (selected["end"] - selected["start"]).dt.days + 1
    selected = selected.loc[selected["duration_days"].between(minimum_days, maximum_days)]
    selected = selected.loc[
        selected["filed"].ge(selected["end"])
        & selected["filed"].le(selected["end"] + pd.Timedelta(days=150))
    ]
    return (
        selected.sort_values(["end", "filed"])
        .groupby("end", as_index=False)
        .head(1)
    )


def quarterly_duration_fact(
    companyfacts_root: Path,
    ticker: str,
    tag: str,
    value_name: str,
) -> pd.DataFrame:
    facts = _fact_frame(companyfacts_root, ticker, tag)
    if facts.empty:
        return pd.DataFrame()
    direct = _original_duration(facts, "10-Q", 75, 105)
    direct = direct.loc[direct["end"].dt.quarter.isin([1, 2, 3])]
    annual = _original_duration(facts, "10-K", 330, 380)
    annual = annual.loc[annual["end"].dt.quarter.eq(4)]
    rows: dict[str, dict[str, object]] = {}
    for fact in direct.itertuples(index=False):
        quarter = _quarter(fact.end)
        rows[quarter] = {
            "ticker": ticker,
            "quarter": quarter,
            value_name: float(fact.val),
            f"{value_name}_available_at": pd.Timestamp(fact.filed),
            f"{value_name}_source_tag": fact.source_tag,
            f"{value_name}_source_path": fact.source_path,
            f"{value_name}_method": "DIRECT_10Q_QUARTER",
        }
    for fact in annual.itertuples(index=False):
        year = int(fact.end.year)
        components = [f"{year}Q{quarter}" for quarter in (1, 2, 3)]
        if not all(quarter in rows for quarter in components):
            continue
        quarter = f"{year}Q4"
        rows[quarter] = {
            "ticker": ticker,
            "quarter": quarter,
            value_name: float(fact.val) - sum(float(rows[q][value_name]) for q in components),
            f"{value_name}_available_at": pd.Timestamp(fact.filed),
            f"{value_name}_source_tag": fact.source_tag,
            f"{value_name}_source_path": fact.source_path,
            f"{value_name}_method": "Q4_FY_MINUS_Q1_Q2_Q3",
        }
    result = pd.DataFrame(rows.values())
    if not result.empty:
        result["quarter_ordinal"] = result["quarter"].map(_ordinal)
    return result.sort_values("quarter_ordinal") if len(result) else result


def quarterly_cash_flow_fact(
    companyfacts_root: Path,
    ticker: str,
    tag: str,
    value_name: str,
) -> pd.DataFrame:
    facts = _fact_frame(companyfacts_root, ticker, tag)
    if facts.empty:
        return pd.DataFrame()
    specifications = (
        ("10-Q", 75, 105, 1),
        ("10-Q", 165, 200, 2),
        ("10-Q", 255, 295, 3),
        ("10-K", 330, 380, 4),
    )
    cumulative: dict[str, pd.Series] = {}
    for form, low, high, quarter_number in specifications:
        selected = _original_duration(facts, form, low, high)
        selected = selected.loc[selected["end"].dt.quarter.eq(quarter_number)]
        for _, fact in selected.iterrows():
            cumulative[_quarter(fact["end"])] = fact
    rows: list[dict[str, object]] = []
    for year in sorted({pd.Period(q, freq="Q").year for q in cumulative}):
        prior = 0.0
        for quarter_number in (1, 2, 3, 4):
            quarter = f"{year}Q{quarter_number}"
            fact = cumulative.get(quarter)
            if fact is None:
                break
            cumulative_value = float(fact["val"])
            value = cumulative_value - prior
            prior = cumulative_value
            rows.append({
                "ticker": ticker,
                "quarter": quarter,
                value_name: value,
                f"{value_name}_available_at": pd.Timestamp(fact["filed"]),
                f"{value_name}_source_tag": fact["source_tag"],
                f"{value_name}_source_path": fact["source_path"],
                f"{value_name}_method": (
                    "DIRECT_Q1_CASH_FLOW" if quarter_number == 1
                    else "YTD_MINUS_PRIOR_YTD_CASH_FLOW"
                ),
            })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["quarter_ordinal"] = result["quarter"].map(_ordinal)
    return result


def _coalesce_duration(
    companyfacts_root: Path,
    ticker: str,
    options: Iterable[str],
    value_name: str,
) -> pd.DataFrame:
    result = pd.DataFrame()
    for tag in options:
        candidate = quarterly_duration_fact(
            companyfacts_root, ticker, tag, value_name
        )
        if candidate.empty:
            continue
        if result.empty:
            result = candidate
        else:
            missing = candidate.loc[
                ~candidate["quarter"].isin(set(result["quarter"]))
            ]
            result = pd.concat([result, missing], ignore_index=True, sort=False)
    return result.sort_values("quarter_ordinal") if len(result) else result


def _coalesce_cash_flow(
    companyfacts_root: Path,
    ticker: str,
    options: Iterable[str],
    value_name: str,
) -> pd.DataFrame:
    result = pd.DataFrame()
    for tag in options:
        candidate = quarterly_cash_flow_fact(
            companyfacts_root, ticker, tag, value_name
        )
        if candidate.empty:
            continue
        if result.empty:
            result = candidate
        else:
            missing = candidate.loc[
                ~candidate["quarter"].isin(set(result["quarter"]))
            ]
            result = pd.concat([result, missing], ignore_index=True, sort=False)
    return result.sort_values("quarter_ordinal") if len(result) else result


def _instant_fact(
    companyfacts_root: Path,
    ticker: str,
    tag: str,
    value_name: str,
) -> pd.DataFrame:
    facts = _fact_frame(companyfacts_root, ticker, tag)
    if facts.empty:
        return pd.DataFrame()
    selected = facts.loc[
        facts["form"].isin(["10-Q", "10-K"])
        & facts["filed"].ge(facts["end"])
        & facts["filed"].le(facts["end"] + pd.Timedelta(days=150))
    ].copy()
    selected = (
        selected.sort_values(["end", "filed"])
        .groupby("end", as_index=False)
        .head(1)
    )
    if selected.empty:
        return selected
    result = pd.DataFrame({
        "ticker": ticker,
        "quarter": selected["end"].map(_quarter),
        value_name: selected["val"].astype(float),
        f"{value_name}_available_at": selected["filed"],
        f"{value_name}_source_tag": selected["source_tag"],
        f"{value_name}_source_path": selected["source_path"],
        f"{value_name}_method": "ORIGINAL_QUARTER_END_INSTANT_FACT",
    })
    result["quarter_ordinal"] = result["quarter"].map(_ordinal)
    return result.drop_duplicates(["ticker", "quarter"], keep="first")


def _coalesce_instant(
    companyfacts_root: Path,
    ticker: str,
    options: Iterable[str],
    value_name: str,
) -> pd.DataFrame:
    result = pd.DataFrame()
    for tag in options:
        candidate = _instant_fact(companyfacts_root, ticker, tag, value_name)
        if candidate.empty:
            continue
        if result.empty:
            result = candidate
        else:
            missing = candidate.loc[
                ~candidate["quarter"].isin(set(result["quarter"]))
            ]
            result = pd.concat([result, missing], ignore_index=True, sort=False)
    return result.sort_values("quarter_ordinal") if len(result) else result


def _capex(companyfacts_root: Path, ticker: str) -> pd.DataFrame:
    components: list[pd.DataFrame] = []
    for tag in CAPEX_COMPONENTS[ticker]:
        frame = quarterly_cash_flow_fact(
            companyfacts_root, ticker, tag, "cash_capex_usd"
        )
        if not frame.empty:
            components.append(frame)
    if not components:
        return pd.DataFrame()
    if ticker not in CAPEX_ADDITIVE_TICKERS:
        result = components[0].copy()
        for component in components[1:]:
            missing = component.loc[
                ~component["quarter"].isin(set(result["quarter"]))
            ]
            result = pd.concat([result, missing], ignore_index=True, sort=False)
        result["cash_capex_usd"] = result["cash_capex_usd"].abs()
        result["quarter_ordinal"] = result["quarter"].map(_ordinal)
        return result.sort_values("quarter_ordinal")
    combined = pd.concat(components, ignore_index=True, sort=False)
    result = (
        combined.groupby(["ticker", "quarter"], as_index=False)
        .agg(
            cash_capex_usd=("cash_capex_usd", lambda values: float(np.abs(values).sum())),
            cash_capex_usd_available_at=("cash_capex_usd_available_at", "max"),
            cash_capex_usd_source_tag=("cash_capex_usd_source_tag", lambda values: ";".join(sorted(set(values)))),
            cash_capex_usd_source_path=("cash_capex_usd_source_path", lambda values: ";".join(sorted(set(values)))),
            cash_capex_usd_method=("cash_capex_usd_method", lambda values: ";".join(sorted(set(values)))),
        )
    )
    result["quarter_ordinal"] = result["quarter"].map(_ordinal)
    return result


def _merge_metrics(parts: list[pd.DataFrame]) -> pd.DataFrame:
    result = pd.DataFrame()
    for part in parts:
        if part.empty:
            continue
        view = part.drop(columns=["quarter_ordinal"], errors="ignore")
        result = view if result.empty else result.merge(
            view, on=["ticker", "quarter"], how="outer"
        )
    return result


def _fill_conditional_capex(
    frame: pd.DataFrame,
    *,
    trailing_observations: int = 12,
    minimum_observations: int = 4,
) -> pd.DataFrame:
    """Fill taxonomy gaps from prior-only capex-intensity distributions."""
    result = frame.sort_values("quarter").copy()
    result["cash_capex_imputed"] = False
    observed = result.loc[
        result["cash_capex_usd"].gt(0) & result["revenue"].gt(0)
    ].copy()
    observed["capex_intensity"] = observed["cash_capex_usd"] / observed["revenue"]
    observed["quarter_ordinal"] = observed["quarter"].map(_ordinal)
    for index, row in result.loc[
        result["cash_capex_usd"].isna() & result["revenue"].gt(0)
    ].iterrows():
        target_ordinal = _ordinal(str(row["quarter"]))
        eligible = observed.loc[
            observed["quarter_ordinal"].lt(target_ordinal)
        ].sort_values("quarter_ordinal").tail(trailing_observations)
        if len(eligible) < minimum_observations:
            continue
        intensity = float(eligible["capex_intensity"].median())
        result.at[index, "cash_capex_usd"] = float(row["revenue"]) * intensity
        result.at[index, "cash_capex_usd_available_at"] = eligible[
            "cash_capex_usd_available_at"
        ].max()
        result.at[index, "cash_capex_usd_source_tag"] = (
            "CONDITIONAL:PIT_TRAILING_CAPEX_INTENSITY_DISTRIBUTION"
        )
        result.at[index, "cash_capex_usd_source_path"] = ";".join(
            sorted(set(eligible["cash_capex_usd_source_path"].dropna().astype(str)))
        )
        result.at[index, "cash_capex_usd_method"] = (
            f"PRIOR_ONLY_MEDIAN_{len(eligible)}Q_CAPEX_TO_REVENUE"
        )
        result.at[index, "cash_capex_imputed"] = True
    return result


def _fill_hierarchical_capex(
    quarterly: pd.DataFrame,
    *,
    trailing_quarters: int = 12,
    minimum_peer_observations: int = 8,
) -> pd.DataFrame:
    """Fill residual gaps with a prior-only same-subindustry distribution.

    This is a disclosed hierarchical shrinkage fallback: company history is
    used first by ``_fill_conditional_capex``; only remaining taxonomy gaps
    use peer capex intensity that was available before the target filing.
    """
    result = quarterly.sort_values(["ticker", "quarter_ordinal"]).copy()
    observed = result.loc[
        result["cash_capex_usd"].gt(0)
        & result["revenue"].gt(0)
        & result["cash_capex_usd_available_at"].notna()
    ].copy()
    observed["capex_intensity"] = (
        observed["cash_capex_usd"] / observed["revenue"]
    )
    missing = result.loc[
        result["cash_capex_usd"].isna() & result["revenue"].gt(0)
    ]
    for index, row in missing.iterrows():
        target_ordinal = int(row["quarter_ordinal"])
        target_available_at = pd.Timestamp(row["revenue_available_at"])
        eligible = observed.loc[
            observed["subindustry"].eq(row["subindustry"])
            & observed["quarter_ordinal"].lt(target_ordinal)
            & observed["quarter_ordinal"].ge(target_ordinal - trailing_quarters)
            & observed["cash_capex_usd_available_at"].le(target_available_at)
        ].copy()
        if len(eligible) < minimum_peer_observations:
            continue
        intensity = float(eligible["capex_intensity"].median())
        result.at[index, "cash_capex_usd"] = float(row["revenue"]) * intensity
        result.at[index, "cash_capex_usd_available_at"] = eligible[
            "cash_capex_usd_available_at"
        ].max()
        result.at[index, "cash_capex_usd_source_tag"] = (
            "CONDITIONAL:PIT_SUBINDUSTRY_CAPEX_INTENSITY_DISTRIBUTION"
        )
        result.at[index, "cash_capex_usd_source_path"] = ";".join(
            sorted(set(eligible["cash_capex_usd_source_path"].dropna().astype(str)))
        )
        result.at[index, "cash_capex_usd_method"] = (
            f"PRIOR_ONLY_{row['subindustry'].upper()}_PEER_MEDIAN_"
            f"{len(eligible)}_OBS_CAPEX_TO_REVENUE"
        )
        result.at[index, "cash_capex_imputed"] = True
    return result


def build_balance_sheet(
    companyfacts_root: Path,
    tickers: Iterable[str] = ENERGY_TICKERS,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for ticker in tickers:
        frame = _merge_metrics([
            _coalesce_instant(companyfacts_root, ticker, CASH_OPTIONS, "cash_usd"),
            _coalesce_instant(companyfacts_root, ticker, CURRENT_DEBT_OPTIONS, "current_debt_usd"),
            _coalesce_instant(companyfacts_root, ticker, NONCURRENT_DEBT_OPTIONS, "noncurrent_debt_usd"),
            _coalesce_instant(companyfacts_root, ticker, EQUITY_OPTIONS, "equity_including_nci_usd"),
        ])
        if frame.empty:
            continue
        for column in (
            "cash_usd", "current_debt_usd", "noncurrent_debt_usd",
            "equity_including_nci_usd",
        ):
            if column not in frame:
                frame[column] = np.nan
        frame["current_debt_usd"] = frame["current_debt_usd"].fillna(0.0)
        frame["noncurrent_debt_usd"] = frame["noncurrent_debt_usd"].fillna(0.0)
        frame["total_debt_usd"] = (
            frame["current_debt_usd"] + frame["noncurrent_debt_usd"]
        )
        frame["invested_capital_usd"] = (
            frame["total_debt_usd"]
            + frame["equity_including_nci_usd"]
            - frame["cash_usd"]
        )
        availability_columns = [
            column for column in frame if column.endswith("_available_at")
        ]
        frame["balance_available_at"] = frame[availability_columns].max(axis=1)
        frame["quarter_ordinal"] = frame["quarter"].map(_ordinal)
        rows.append(frame)
    return pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame()


def build_quarterly_financials(
    companyfacts_root: Path,
    tickers: Iterable[str] = ENERGY_TICKERS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = tuple(tickers)
    revenue = load_companyfacts_quarterly_revenue(companyfacts_root, tickers)
    revenue = revenue.rename(columns={
        "filing_date": "revenue_available_at",
        "source_fact": "revenue_source_tag",
        "source_path": "revenue_source_path",
        "revenue_method": "revenue_method",
    })
    wanted_revenue = [
        "ticker", "quarter", "revenue", "revenue_available_at",
        "revenue_source_tag", "revenue_source_path", "revenue_method",
    ]
    all_rows: list[pd.DataFrame] = []
    for ticker in tickers:
        frame = _merge_metrics([
            revenue.loc[revenue["ticker"].eq(ticker), wanted_revenue],
            _coalesce_duration(companyfacts_root, ticker, OPERATING_INCOME_OPTIONS, "operating_income_usd"),
            _coalesce_duration(companyfacts_root, ticker, NET_INCOME_OPTIONS, "net_income_usd"),
            _coalesce_duration(companyfacts_root, ticker, TAX_OPTIONS, "income_tax_usd"),
            _coalesce_duration(companyfacts_root, ticker, INTEREST_OPTIONS, "interest_expense_usd"),
            _coalesce_cash_flow(companyfacts_root, ticker, CFO_OPTIONS, "cfo_usd"),
            _capex(companyfacts_root, ticker),
        ])
        if frame.empty:
            continue
        for column in (
            "operating_income_usd", "net_income_usd", "income_tax_usd",
            "interest_expense_usd", "cfo_usd", "cash_capex_usd",
        ):
            if column not in frame:
                frame[column] = np.nan
        frame = _fill_conditional_capex(frame)
        frame["interest_expense_usd"] = frame["interest_expense_usd"].abs()
        inferred_pretax = frame["net_income_usd"] + frame["income_tax_usd"]
        valid_tax = inferred_pretax.gt(0) & frame["income_tax_usd"].ge(0)
        frame["effective_tax_rate"] = 0.21
        frame.loc[valid_tax, "effective_tax_rate"] = (
            frame.loc[valid_tax, "income_tax_usd"] / inferred_pretax[valid_tax]
        ).clip(0.0, 0.35)
        frame["tax_rate_method"] = np.where(
            valid_tax, "INFERRED_FROM_NET_INCOME_PLUS_TAX", "US_STATUTORY_21PCT_FALLBACK"
        )
        direct_ebit = frame["operating_income_usd"].notna()
        frame["ebit_usd"] = frame["operating_income_usd"]
        frame.loc[~direct_ebit, "ebit_usd"] = (
            frame.loc[~direct_ebit, "net_income_usd"]
            + frame.loc[~direct_ebit, "income_tax_usd"]
            + frame.loc[~direct_ebit, "interest_expense_usd"]
        )
        frame["ebit_method"] = np.where(
            direct_ebit,
            "DIRECT_GAAP_OPERATING_INCOME",
            "DERIVED_NET_INCOME_PLUS_TAX_PLUS_INTEREST",
        )
        frame["nopat_usd"] = frame["ebit_usd"] * (1.0 - frame["effective_tax_rate"])
        frame["fcff_usd"] = (
            frame["cfo_usd"]
            + frame["interest_expense_usd"] * (1.0 - frame["effective_tax_rate"])
            - frame["cash_capex_usd"]
        )
        frame["reinvestment_usd"] = frame["nopat_usd"] - frame["fcff_usd"]
        frame["subindustry"] = SUBINDUSTRY[ticker]
        frame["primary_anchor"] = frame["subindustry"].map(ANCHOR)
        frame["anchor_route"] = frame["subindustry"].map(ANCHOR_ROUTE)
        availability_columns = [
            column for column in frame if column.endswith("_available_at")
        ]
        frame["financial_available_at"] = frame[availability_columns].max(axis=1)
        frame["quarter_ordinal"] = frame["quarter"].map(_ordinal)
        frame["core_financial_complete"] = frame[[
            "revenue", "ebit_usd", "nopat_usd", "cfo_usd",
            "cash_capex_usd", "fcff_usd",
        ]].notna().all(axis=1)
        all_rows.append(frame)
    quarterly = pd.concat(all_rows, ignore_index=True, sort=False)
    quarterly = _fill_hierarchical_capex(quarterly)
    quarterly["fcff_usd"] = (
        quarterly["cfo_usd"]
        + quarterly["interest_expense_usd"]
        * (1.0 - quarterly["effective_tax_rate"])
        - quarterly["cash_capex_usd"]
    )
    quarterly["reinvestment_usd"] = quarterly["nopat_usd"] - quarterly["fcff_usd"]
    quarterly["core_financial_complete"] = quarterly[[
        "revenue", "ebit_usd", "nopat_usd", "cfo_usd",
        "cash_capex_usd", "fcff_usd",
    ]].notna().all(axis=1)
    availability_columns = [
        column for column in quarterly if column.endswith("_available_at")
    ]
    quarterly["financial_available_at"] = quarterly[
        availability_columns
    ].max(axis=1)
    balance = build_balance_sheet(companyfacts_root, tickers)
    quarterly = quarterly.merge(
        balance,
        on=["ticker", "quarter", "quarter_ordinal"],
        how="left",
        suffixes=("", "_balance"),
    )
    quarterly["valuation_source_complete"] = (
        quarterly["core_financial_complete"]
        & quarterly["invested_capital_usd"].gt(0)
    )
    coverage_rows = []
    for ticker, group in quarterly.groupby("ticker", sort=True):
        complete = group.loc[group["valuation_source_complete"]]
        latest = complete.sort_values("quarter_ordinal").tail(1)
        conditional_rows = int(complete["cash_capex_imputed"].fillna(False).sum())
        coverage_rows.append({
            "ticker": ticker,
            "subindustry": SUBINDUSTRY[ticker],
            "quarterly_rows": len(group),
            "complete_quarterly_rows": len(complete),
            "conditional_capex_rows": conditional_rows,
            "latest_complete_quarter": (
                latest["quarter"].iloc[0] if len(latest) else pd.NA
            ),
            "capex_source_tags": ";".join(CAPEX_COMPONENTS[ticker]),
            "source_status": (
                (
                    "CONDITIONAL_PIT_COMPLETE"
                    if conditional_rows
                    else "STANDARDIZED_COMPLETE"
                )
                if len(complete) >= 8
                else "INSUFFICIENT_STANDARDIZED_OR_CONDITIONAL_HISTORY"
            ),
        })
    return quarterly.sort_values(["ticker", "quarter_ordinal"]), pd.DataFrame(coverage_rows)


def build_ttm_financials(quarterly: pd.DataFrame) -> pd.DataFrame:
    frame = quarterly.sort_values(["ticker", "quarter_ordinal"]).copy()
    flow_columns = [
        "revenue", "ebit_usd", "nopat_usd", "cfo_usd", "cash_capex_usd",
        "fcff_usd", "reinvestment_usd", "interest_expense_usd", "income_tax_usd",
    ]
    for column in flow_columns:
        frame[f"ttm_{column}"] = (
            frame.groupby("ticker")[column]
            .rolling(4, min_periods=4)
            .sum()
            .reset_index(level=0, drop=True)
        )
    grouped = frame.groupby("ticker", sort=False)
    frame["prior_year_ttm_revenue"] = grouped["ttm_revenue"].shift(4)
    frame["prior_year_ttm_nopat"] = grouped["ttm_nopat_usd"].shift(4)
    frame["prior_year_invested_capital_usd"] = grouped["invested_capital_usd"].shift(4)
    frame["average_invested_capital_usd"] = (
        frame["invested_capital_usd"] + frame["prior_year_invested_capital_usd"]
    ) / 2.0
    frame["revenue_growth_pct"] = (
        frame["ttm_revenue"] / frame["prior_year_ttm_revenue"] - 1.0
    ) * 100.0
    frame["operating_margin_pct"] = frame["ttm_ebit_usd"] / frame["ttm_revenue"] * 100.0
    frame["fcff_margin_pct"] = frame["ttm_fcff_usd"] / frame["ttm_revenue"] * 100.0
    frame["roic_pct"] = (
        frame["ttm_nopat_usd"] / frame["average_invested_capital_usd"] * 100.0
    )
    delta_capital = (
        frame["invested_capital_usd"] - frame["prior_year_invested_capital_usd"]
    )
    frame["incremental_roic_pct"] = np.where(
        delta_capital.abs().gt(1e6),
        (frame["ttm_nopat_usd"] - frame["prior_year_ttm_nopat"])
        / delta_capital * 100.0,
        np.nan,
    )
    frame["reinvestment_rate_pct"] = np.where(
        frame["ttm_nopat_usd"].abs().gt(1e6),
        frame["ttm_reinvestment_usd"] / frame["ttm_nopat_usd"] * 100.0,
        np.nan,
    )
    frame["ttm_complete"] = frame[[
        "ttm_revenue", "ttm_nopat_usd", "ttm_fcff_usd",
        "average_invested_capital_usd", "roic_pct",
    ]].notna().all(axis=1)
    return frame.sort_values(["ticker", "quarter_ordinal"])
