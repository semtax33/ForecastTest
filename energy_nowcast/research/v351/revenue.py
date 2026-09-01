from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


CIKS = {
    "AR": 1433270,
    "CNX": 1070412,
    "COP": 1163165,
    "DVN": 1090012,
    "EOG": 821189,
    "EQT": 33213,
    "FANG": 1539838,
    "MGY": 1698990,
    "MTDR": 1520006,
    "NOG": 1104485,
    "OVV": 1792580,
    "PR": 1658566,
    "RRC": 315852,
    "SM": 893538,
}


# These tags match the canonical REVENUE concept chosen in Arcana's normalized
# statement files. The audit changes fact selection, not the accounting concept.
REVENUE_FACT_TAGS = {
    "AR": "RevenueFromContractWithCustomerIncludingAssessedTax",
    "CNX": "Revenues",
    "COP": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "DVN": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "EOG": "Revenues",
    "EQT": "Revenues",
    "FANG": "Revenues",
    "MGY": "Revenues",
    "MTDR": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NOG": "Revenues",
    "OVV": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "PR": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RRC": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SM": "RevenueFromContractWithCustomerIncludingAssessedTax",
}


def _ordinal(value: str) -> int:
    return int(pd.Period(value, freq="Q").ordinal)


def _cutoff_date(value: str, day_of_quarter: int = 61) -> pd.Timestamp:
    return pd.Period(value, freq="Q").start_time + pd.Timedelta(days=day_of_quarter - 1)


def _source_url(cik: int, accession: str) -> str:
    compact = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{compact}/"


def _fact_frame(companyfacts_path: Path, tag: str) -> pd.DataFrame:
    payload = json.loads(companyfacts_path.read_text(encoding="utf-8"))
    fact = payload.get("facts", {}).get("us-gaap", {}).get(tag)
    if not fact:
        return pd.DataFrame()
    rows = fact.get("units", {}).get("USD", [])
    frame = pd.DataFrame(rows)
    if frame.empty or not {"start", "end", "filed", "val"}.issubset(frame):
        return pd.DataFrame()
    for column in ("start", "end", "filed"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["duration_days"] = (frame["end"] - frame["start"]).dt.days + 1
    frame["fy"] = pd.to_numeric(frame.get("fy"), errors="coerce")
    frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
    return frame.dropna(subset=["start", "end", "filed", "val"])


def _original_filing_facts(frame: pd.DataFrame, form: str, min_days: int, max_days: int) -> pd.DataFrame:
    eligible = frame.loc[
        frame["form"].astype(str).eq(form)
        & frame["duration_days"].between(min_days, max_days)
        & frame["fy"].eq(frame["end"].dt.year)
        & frame["filed"].sub(frame["end"]).dt.days.between(0, 180)
    ].copy()
    eligible["quarter"] = eligible["end"].dt.to_period("Q").astype(str)
    return (
        eligible.sort_values(["quarter", "filed", "accn"])
        .drop_duplicates("quarter", keep="first")
        .reset_index(drop=True)
    )


def load_companyfacts_quarterly_revenue(
    companyfacts_root: Path,
    tickers: Iterable[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        cik = CIKS[ticker]
        tag = REVENUE_FACT_TAGS[ticker]
        path = companyfacts_root / f"CIK{cik:010d}.json"
        facts = _fact_frame(path, tag)
        if facts.empty:
            continue
        direct = _original_filing_facts(facts, "10-Q", 75, 105)
        direct = direct.loc[direct["end"].dt.quarter.isin([1, 2, 3])]
        annual = _original_filing_facts(facts, "10-K", 330, 380)
        annual = annual.loc[annual["end"].dt.quarter.eq(4)]
        company_rows: dict[str, dict[str, object]] = {}
        for _, fact in direct.iterrows():
            quarter = str(fact["quarter"])
            company_rows[quarter] = {
                "ticker": ticker,
                "quarter": quarter,
                "revenue": float(fact["val"]),
                "raw_source_value": float(fact["val"]),
                "duration_days": int(fact["duration_days"]),
                "source_duration_days": int(fact["duration_days"]),
                "filing_date": pd.Timestamp(fact["filed"]),
                "form": str(fact["form"]),
                "source_fact": f"us-gaap:{tag}",
                "accession": str(fact["accn"]),
                "source_url": _source_url(cik, str(fact["accn"])),
                "source_path": str(path),
                "revenue_method": "DIRECT_10Q_75_105_DAY_FACT",
                "annual_value": np.nan,
                "q1_q3_sum": np.nan,
            }
        for _, fact in annual.iterrows():
            year = int(fact["end"].year)
            component_quarters = [f"{year}Q{quarter}" for quarter in (1, 2, 3)]
            if not all(quarter in company_rows for quarter in component_quarters):
                continue
            q1_q3_sum = float(sum(company_rows[quarter]["revenue"] for quarter in component_quarters))
            revenue = float(fact["val"] - q1_q3_sum)
            quarter = f"{year}Q4"
            normalized_days = int((pd.Period(quarter, freq="Q").end_time.normalize() - pd.Period(quarter, freq="Q").start_time.normalize()).days + 1)
            company_rows[quarter] = {
                "ticker": ticker,
                "quarter": quarter,
                "revenue": revenue,
                "raw_source_value": float(fact["val"]),
                "duration_days": normalized_days,
                "source_duration_days": int(fact["duration_days"]),
                "filing_date": pd.Timestamp(fact["filed"]),
                "form": str(fact["form"]),
                "source_fact": f"us-gaap:{tag}",
                "accession": str(fact["accn"]),
                "source_url": _source_url(cik, str(fact["accn"])),
                "source_path": str(path),
                "revenue_method": "DERIVED_Q4_FY_MINUS_Q1_Q2_Q3",
                "annual_value": float(fact["val"]),
                "q1_q3_sum": q1_q3_sum,
            }
        rows.extend(company_rows.values())
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["quarter_ordinal"] = result["quarter"].map(_ordinal)
    return result.sort_values(["ticker", "quarter_ordinal"]).reset_index(drop=True)


def build_audited_revenue_panel(
    companyfacts_root: Path,
    price_path: Path,
    tickers: Iterable[str],
    cutoff_day: int = 61,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    audit = load_companyfacts_quarterly_revenue(companyfacts_root, tickers)
    panel = audit.rename(columns={"filing_date": "report_date"}).copy()
    prices = pd.read_csv(price_path)
    prices["quarter"] = prices["quarter"].astype(str)
    panel = panel.merge(
        prices[["quarter", "wti_price", "henry_price", "propane_price_bbl"]],
        on="quarter",
        how="left",
    )
    revenue_lookup = {
        (str(row["ticker"]), str(row["quarter"])): float(row["revenue"])
        for _, row in panel.iterrows()
    }
    report_lookup = {
        (str(row["ticker"]), str(row["quarter"])): pd.Timestamp(row["report_date"])
        for _, row in panel.iterrows()
    }
    price_lookup = prices.set_index("quarter").to_dict(orient="index")
    panel["prior_year_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 4)
    )
    panel["previous_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 1)
    )
    panel["prior_year_revenue"] = [
        revenue_lookup.get((str(row["ticker"]), str(row["prior_year_quarter"])), np.nan)
        for _, row in panel.iterrows()
    ]
    positive_revenue = panel["revenue"].gt(0) & panel["prior_year_revenue"].gt(0)
    panel["actual_log_yoy"] = np.nan
    panel.loc[positive_revenue, "actual_log_yoy"] = 100.0 * np.log(
        panel.loc[positive_revenue, "revenue"]
        / panel.loc[positive_revenue, "prior_year_revenue"]
    )
    actual_yoy_lookup = {
        (str(row["ticker"]), str(row["quarter"])): float(row["actual_log_yoy"])
        for _, row in panel.dropna(subset=["actual_log_yoy"]).iterrows()
    }
    panel["lag_revenue_log_yoy"] = [
        actual_yoy_lookup.get((str(row["ticker"]), str(row["previous_quarter"])), np.nan)
        for _, row in panel.iterrows()
    ]
    panel["lag_report_date"] = [
        report_lookup.get((str(row["ticker"]), str(row["previous_quarter"])), pd.NaT)
        for _, row in panel.iterrows()
    ]
    for price_column, output in (
        ("wti_price", "wti_log_yoy"),
        ("henry_price", "henry_log_yoy"),
        ("propane_price_bbl", "propane_log_yoy"),
    ):
        prior = [
            price_lookup.get(str(row["prior_year_quarter"]), {}).get(price_column, np.nan)
            for _, row in panel.iterrows()
        ]
        prior = pd.Series(prior, index=panel.index, dtype=float)
        ratio = (panel[price_column] / prior).where(panel[price_column].gt(0) & prior.gt(0))
        panel[output] = 100.0 * np.log(ratio)
    panel["basket_price_log_yoy"] = (
        0.55 * panel["wti_log_yoy"]
        + 0.25 * panel["henry_log_yoy"]
        + 0.20 * panel["propane_log_yoy"]
    )
    panel["implied_volume_basis_log_yoy"] = panel["actual_log_yoy"] - panel["basket_price_log_yoy"]
    panel["lag_implied_volume_basis_log_yoy"] = np.nan
    panel["forecast_cutoff_date"] = panel["quarter"].map(
        lambda value: _cutoff_date(value, cutoff_day)
    )
    panel = panel.sort_values(["ticker", "quarter_ordinal"]).reset_index(drop=True)
    panel["rolling_median_revenue_8q"] = panel.groupby("ticker")["revenue"].transform(
        lambda values: values.shift(1).rolling(8, min_periods=4).median()
    )
    panel["small_denominator_flag"] = (
        panel["rolling_median_revenue_8q"].notna()
        & panel["revenue"].abs().lt(0.10 * panel["rolling_median_revenue_8q"].abs())
    )
    panel["pit_feature_available"] = pd.to_datetime(panel["lag_report_date"]).le(
        panel["forecast_cutoff_date"]
    )
    panel = panel.replace([np.inf, -np.inf], np.nan)
    required = [
        "revenue", "prior_year_revenue", "actual_log_yoy", "wti_log_yoy",
        "henry_log_yoy", "propane_log_yoy", "lag_revenue_log_yoy",
    ]
    panel = panel.loc[
        panel[required].notna().all(axis=1)
        & panel["revenue"].gt(0)
        & panel["pit_feature_available"]
    ].copy()
    return panel.sort_values(["ticker", "quarter_ordinal"]).reset_index(drop=True), audit


def build_silver_alignment_audit(
    arcana_root: Path,
    corrected: pd.DataFrame,
    tickers: Iterable[str],
) -> pd.DataFrame:
    normalized_root = arcana_root / "data-lake" / "silver" / "sec" / "normalized"
    metadata = pd.read_csv(
        arcana_root / "data-lake" / "silver" / "sec" / "us_report_metadata.csv",
        low_memory=False,
    )
    metadata["stock_code"] = metadata["stock_code"].astype(str).str.upper()
    metadata["fiscal_year"] = pd.to_numeric(metadata["fiscal_year"], errors="coerce")
    metadata["fiscal_month"] = pd.to_numeric(metadata["fiscal_month"], errors="coerce")
    metadata["fiscal_quarter"] = ((metadata["fiscal_month"] - 1) // 3 + 1).astype("Int64")
    meta = (
        metadata.loc[metadata["stock_code"].isin(tuple(tickers))]
        .sort_values("report_date")
        .drop_duplicates(["stock_code", "fiscal_year", "fiscal_quarter"], keep="first")
    )
    corrected_lookup = {
        (str(row["ticker"]), str(row["quarter"])): row
        for _, row in corrected.iterrows()
    }
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        source = pd.read_csv(normalized_root / f"us_normalized_{ticker}.csv", low_memory=False)
        source = source.loc[source["canonical_account_id"].eq("REVENUE")].copy()
        source["fiscal_year"] = pd.to_numeric(source["fiscal_year"], errors="coerce")
        source["fiscal_quarter"] = pd.to_numeric(source["fiscal_quarter"], errors="coerce")
        source["silver_source_value"] = pd.to_numeric(source["normalized_amount"], errors="coerce")
        source = source.dropna(subset=["fiscal_year", "fiscal_quarter", "silver_source_value"])
        source = source.sort_values("period").drop_duplicates(
            ["fiscal_year", "fiscal_quarter"], keep="last"
        )
        source = source.merge(
            meta.loc[meta["stock_code"].eq(ticker), [
                "fiscal_year", "fiscal_quarter", "report_date", "rcept_no", "report_name", "source_url",
            ]],
            on=["fiscal_year", "fiscal_quarter"],
            how="left",
        )
        source["quarter"] = [
            f"{int(year)}Q{int(quarter)}"
            for year, quarter in zip(source["fiscal_year"], source["fiscal_quarter"])
        ]
        source["prior_silver_value"] = source.groupby("fiscal_year")["silver_source_value"].shift(1)
        source["prior_silver_quarter"] = source.groupby("fiscal_year")["fiscal_quarter"].shift(1)
        source["silver_derived_revenue"] = np.where(
            source["fiscal_quarter"].eq(1),
            source["silver_source_value"],
            np.where(
                source["prior_silver_quarter"].eq(source["fiscal_quarter"] - 1),
                source["silver_source_value"] - source["prior_silver_value"],
                np.nan,
            ),
        )
        facts = _fact_frame(
            Path(corrected.loc[corrected["ticker"].eq(ticker), "source_path"].iloc[0]),
            REVENUE_FACT_TAGS[ticker],
        )
        for _, row in source.iterrows():
            accession_matches = facts.loc[
                facts["accn"].astype(str).eq(str(row.get("rcept_no")))
                & np.isclose(facts["val"], float(row["silver_source_value"]), rtol=0, atol=0.5)
            ].sort_values("duration_days", ascending=False)
            matched = accession_matches.iloc[0] if len(accession_matches) else None
            quarter = str(row["quarter"])
            prior_quarter = str(pd.Period(quarter, freq="Q") - 4)
            corrected_row = corrected_lookup.get((ticker, quarter))
            corrected_prior_row = corrected_lookup.get((ticker, prior_quarter))
            corrected_revenue = (
                float(corrected_row["revenue"]) if corrected_row is not None else np.nan
            )
            corrected_prior = (
                float(corrected_prior_row["revenue"])
                if corrected_prior_row is not None else np.nan
            )
            old_revenue = float(row["silver_derived_revenue"]) if np.isfinite(row["silver_derived_revenue"]) else np.nan
            rows.append({
                "ticker": ticker,
                "quarter": quarter,
                "revenue": corrected_revenue,
                "duration_days": corrected_row["duration_days"] if corrected_row is not None else np.nan,
                "source_duration_days": corrected_row["source_duration_days"] if corrected_row is not None else np.nan,
                "filing_date": corrected_row["filing_date"] if corrected_row is not None else pd.NaT,
                "form": corrected_row["form"] if corrected_row is not None else None,
                "source_fact": f"us-gaap:{REVENUE_FACT_TAGS[ticker]}",
                "revenue_method": corrected_row["revenue_method"] if corrected_row is not None else None,
                "raw_source_value": corrected_row["raw_source_value"] if corrected_row is not None else np.nan,
                "annual_value": corrected_row["annual_value"] if corrected_row is not None else np.nan,
                "q1_q3_sum": corrected_row["q1_q3_sum"] if corrected_row is not None else np.nan,
                "corrected_accession": corrected_row["accession"] if corrected_row is not None else None,
                "corrected_source_path": corrected_row["source_path"] if corrected_row is not None else None,
                "silver_source_value": float(row["silver_source_value"]),
                "silver_derived_revenue": old_revenue,
                "companyfacts_revenue": corrected_revenue,
                "prior_year_companyfacts_revenue": corrected_prior,
                "old_matches_prior_year_revenue": bool(
                    np.isfinite(old_revenue)
                    and np.isfinite(corrected_prior)
                    and np.isclose(old_revenue, corrected_prior, rtol=1e-9, atol=1.0)
                ),
                "matched_fact_start": matched["start"] if matched is not None else pd.NaT,
                "matched_fact_end": matched["end"] if matched is not None else pd.NaT,
                "matched_fact_duration_days": matched["duration_days"] if matched is not None else np.nan,
                "matched_fact_end_quarter": str(matched["end"].to_period("Q")) if matched is not None else None,
                "source_quarter_offset": (
                    _ordinal(str(matched["end"].to_period("Q"))) - _ordinal(quarter)
                    if matched is not None else np.nan
                ),
                "silver_report_date": row.get("report_date"),
                "silver_form": row.get("report_name"),
                "silver_accession": row.get("rcept_no"),
                "silver_source_url": row.get("source_url"),
                "source_url": corrected_row["source_url"] if corrected_row is not None else None,
                "alignment_status": (
                    "ALIGNED" if matched is not None and str(matched["end"].to_period("Q")) == quarter
                    else "MISALIGNED_COMPARATIVE_FACT" if matched is not None
                    else "NO_EXACT_FACT_MATCH"
                ),
            })
    return pd.DataFrame(rows).sort_values(["ticker", "quarter"]).reset_index(drop=True)
