from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd

from ...core.company_kpi import _number
from ...data.cutoff import quarter_cutoff_date
from ..v351.revenue import (
    CIKS,
    _fact_frame,
    _original_filing_facts,
    _source_url,
    load_companyfacts_quarterly_revenue,
)


EP_TICKERS = (
    "AR", "CNX", "COP", "DVN", "EOG", "EQT", "FANG",
    "MGY", "MTDR", "NOG", "OVV", "PR", "RRC", "SM",
)
SERVICES_TICKERS = ("SLB", "HAL", "BKR")
REFINING_TICKERS = ("VLO", "MPC", "PSX")
INTEGRATED_TICKERS = ("XOM", "CVX")


OPERATING_INCOME_TAGS = {
    ticker: "OperatingIncomeLoss"
    for ticker in (
        "AR", "DVN", "EOG", "EQT", "FANG", "MGY", "MTDR", "NOG",
        "OVV", "PR", "SM", "VLO", "MPC", "SLB", "HAL", "BKR",
    )
}


# Cash-flow tags are intentionally ticker-specific.  A missing ticker is not
# silently filled with a different accounting concept.
EP_CAPEX_TAGS: dict[str, tuple[str, ...]] = {
    "AR": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "CNX": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "DVN": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "EOG": (
        "PaymentsToAcquireOilAndGasPropertyAndEquipment",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ),
    "EQT": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "FANG": ("PaymentsToAcquireOilAndGasEquipment",),
    "MGY": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "MTDR": ("PaymentsToAcquireOtherPropertyPlantAndEquipment",),
    "NOG": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "OVV": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "PR": (
        "PaymentsToAcquireOilAndGasProperty",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ),
    "RRC": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
    "SM": ("PaymentsToAcquireOilAndGasPropertyAndEquipment",),
}


def _quarter_ordinal(value: str) -> int:
    return int(pd.Period(value, freq="Q").ordinal)


def _quarterly_duration_fact(
    companyfacts_root: Path,
    ticker: str,
    tag: str,
    value_name: str,
) -> pd.DataFrame:
    """Select direct quarterly income-statement facts and derive fourth quarter."""
    path = companyfacts_root / f"CIK{CIKS[ticker]:010d}.json"
    facts = _fact_frame(path, tag)
    if facts.empty:
        return pd.DataFrame()
    direct = _original_filing_facts(facts, "10-Q", 75, 105)
    direct = direct.loc[direct["end"].dt.quarter.isin([1, 2, 3])]
    annual = _original_filing_facts(facts, "10-K", 330, 380)
    annual = annual.loc[annual["end"].dt.quarter.eq(4)]
    rows: dict[str, dict[str, object]] = {}
    for fact in direct.itertuples(index=False):
        quarter = str(fact.quarter)
        rows[quarter] = {
            "ticker": ticker,
            "quarter": quarter,
            value_name: float(fact.val),
            "filing_date": pd.Timestamp(fact.filed),
            "form": str(fact.form),
            "source_fact": f"us-gaap:{tag}",
            "accession": str(fact.accn),
            "source_url": _source_url(CIKS[ticker], str(fact.accn)),
            "source_path": str(path),
            "target_method": "DIRECT_10Q_75_105_DAY_FACT",
        }
    for fact in annual.itertuples(index=False):
        year = int(fact.end.year)
        components = [f"{year}Q{quarter}" for quarter in (1, 2, 3)]
        if not all(quarter in rows for quarter in components):
            continue
        value = float(fact.val) - sum(float(rows[q][value_name]) for q in components)
        quarter = f"{year}Q4"
        rows[quarter] = {
            "ticker": ticker,
            "quarter": quarter,
            value_name: value,
            "filing_date": pd.Timestamp(fact.filed),
            "form": str(fact.form),
            "source_fact": f"us-gaap:{tag}",
            "accession": str(fact.accn),
            "source_url": _source_url(CIKS[ticker], str(fact.accn)),
            "source_path": str(path),
            "target_method": "DERIVED_Q4_FY_MINUS_Q1_Q2_Q3",
        }
    result = pd.DataFrame(rows.values())
    if result.empty:
        return result
    result["quarter_ordinal"] = result["quarter"].map(_quarter_ordinal)
    return result.sort_values("quarter_ordinal").reset_index(drop=True)


def _quarterly_cash_flow_fact(
    companyfacts_root: Path,
    ticker: str,
    tag: str,
) -> pd.DataFrame:
    """Convert Q1/6M/9M/FY cash-flow facts to non-overlapping quarters."""
    path = companyfacts_root / f"CIK{CIKS[ticker]:010d}.json"
    facts = _fact_frame(path, tag)
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
        selected = _original_filing_facts(facts, form, low, high)
        selected = selected.loc[selected["end"].dt.quarter.eq(quarter_number)]
        for _, fact in selected.iterrows():
            cumulative[str(fact["quarter"])] = fact
    rows: list[dict[str, object]] = []
    for year in sorted({pd.Period(q, freq="Q").year for q in cumulative}):
        prior_cumulative = 0.0
        for quarter_number in (1, 2, 3, 4):
            quarter = f"{year}Q{quarter_number}"
            fact = cumulative.get(quarter)
            if fact is None:
                break
            cumulative_value = float(fact["val"])
            quarterly_value = cumulative_value - prior_cumulative
            prior_cumulative = cumulative_value
            rows.append(
                {
                    "ticker": ticker,
                    "quarter": quarter,
                    "cash_capex_usd": quarterly_value,
                    "filing_date": pd.Timestamp(fact["filed"]),
                    "form": str(fact["form"]),
                    "source_fact": f"us-gaap:{tag}",
                    "accession": str(fact["accn"]),
                    "source_url": _source_url(CIKS[ticker], str(fact["accn"])),
                    "source_path": str(path),
                    "target_method": (
                        "DIRECT_Q1_CASH_FLOW"
                        if quarter_number == 1
                        else "YTD_MINUS_PRIOR_YTD_CASH_FLOW"
                    ),
                }
            )
    return pd.DataFrame(rows)


def extract_operating_income(
    companyfacts_root: Path,
    tickers: Iterable[str],
) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        tag = OPERATING_INCOME_TAGS.get(ticker)
        if tag is None:
            continue
        part = _quarterly_duration_fact(
            companyfacts_root, ticker, tag, "operating_income_usd"
        )
        if not part.empty:
            rows.append(part)
    return (
        pd.concat(rows, ignore_index=True, sort=False)
        if rows
        else pd.DataFrame()
    )


def extract_integrated_net_income(companyfacts_root: Path) -> pd.DataFrame:
    parts = [
        _quarterly_duration_fact(
            companyfacts_root, ticker, "ProfitLoss", "net_income_usd"
        )
        for ticker in INTEGRATED_TICKERS
    ]
    parts = [part for part in parts if not part.empty]
    return (
        pd.concat(parts, ignore_index=True, sort=False)
        if parts
        else pd.DataFrame()
    )


def extract_ep_cash_capex(companyfacts_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts: list[pd.DataFrame] = []
    coverage: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        tags = EP_CAPEX_TAGS.get(ticker, ())
        tag_parts = []
        for tag in tags:
            values = _quarterly_cash_flow_fact(companyfacts_root, ticker, tag)
            if not values.empty:
                tag_parts.append(values)
        if not tag_parts:
            coverage.append(
                {
                    "ticker": ticker,
                    "source_tags": ",".join(tags),
                    "quarterly_rows": 0,
                    "status": "LOCKED_NO_STANDARDIZED_CASH_CAPEX_TAG",
                }
            )
            continue
        combined = pd.concat(tag_parts, ignore_index=True)
        provenance = (
            combined.groupby(["ticker", "quarter"], as_index=False)
            .agg(
                cash_capex_usd=("cash_capex_usd", "sum"),
                filing_date=("filing_date", "max"),
                source_fact=("source_fact", lambda x: ",".join(sorted(set(x)))),
                source_url=("source_url", lambda x: ";".join(sorted(set(x)))),
                source_path=("source_path", lambda x: ";".join(sorted(set(x)))),
                target_method=("target_method", lambda x: ",".join(sorted(set(x)))),
            )
        )
        provenance = provenance.loc[provenance["cash_capex_usd"].gt(0)].copy()
        provenance["quarter_ordinal"] = provenance["quarter"].map(_quarter_ordinal)
        provenance["target_semantics"] = "CASH_PAYMENTS_FOR_CAPITAL_ASSETS"
        parts.append(provenance)
        coverage.append(
            {
                "ticker": ticker,
                "source_tags": ",".join(tags),
                "quarterly_rows": len(provenance),
                "status": "STANDARDIZED_GAAP_CASH_FLOW_TAG",
            }
        )
    return (
        pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame(),
        pd.DataFrame(coverage),
    )


def _table_tokens(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, object]] = []
    for table_index, table in enumerate(soup.find_all("table")):
        for row_index, tr in enumerate(table.find_all("tr")):
            cells = tr.find_all(["td", "th"], recursive=False)
            tokens = [
                re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
                for cell in cells
            ]
            tokens = [token for token in tokens if token]
            if tokens:
                rows.append(
                    {
                        "table_index": table_index,
                        "row_index": row_index,
                        "tokens": tokens,
                        "row_text": " | ".join(tokens),
                    }
                )
    return rows


def _first_number(tokens: list[str], start: int = 1) -> float | None:
    for token in tokens[start:]:
        value = _number(token)
        if value is not None and np.isfinite(value):
            return float(value)
    return None


def _xom_segment_rows(html: str) -> list[dict[str, object]]:
    headings = {
        "upstream": "upstream",
        "downstream": "downstream_legacy",
        "energy products": "energy_products",
        "chemical": "chemicals",
        "chemical products": "chemicals",
        "specialty products": "specialty_products",
    }
    output: list[dict[str, object]] = []
    current_segment: str | None = None
    gaap_measure = False
    seen: set[tuple[int, str]] = set()
    for row in _table_tokens(html):
        tokens = [str(token) for token in row["tokens"]]
        first = tokens[0].strip().lower()
        text = str(row["row_text"])
        if first in headings and _first_number(tokens, 0) is None:
            current_segment = headings[first]
        if re.search(r"earnings\s*\(loss\)\s*,?\s*\$m", text, re.I):
            gaap_measure = True
        if re.search(r"earnings.?\(loss\).*u\.s\. gaap", text, re.I):
            gaap_measure = True
        if re.search(r"excluding identified items|adjusted earnings", text, re.I):
            gaap_measure = False
        if current_segment is None or not gaap_measure:
            continue
        labels = {token.strip().lower() for token in tokens}
        if not labels.intersection({"total", "worldwide"}):
            continue
        key = (int(row["table_index"]), current_segment)
        if key in seen:
            continue
        value = _first_number(tokens, 0)
        if value is None:
            continue
        seen.add(key)
        output.append(
            {
                "segment": current_segment,
                "segment_earnings_usd_million": value,
                "source_row_text": text,
                "source_table_index": row["table_index"],
                "source_row_index": row["row_index"],
                "parser_rule": "XOM_GAAP_SEGMENT_HEADING_THEN_FIRST_TOTAL",
            }
        )
    return output


def _cvx_segment_rows(html: str) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    table_rows = _table_tokens(html)
    by_table: dict[int, list[dict[str, object]]] = {}
    for row in table_rows:
        by_table.setdefault(int(row["table_index"]), []).append(row)
    for table_index, rows in by_table.items():
        table_text = " || ".join(str(row["row_text"]) for row in rows[:8])
        if not re.search(r"earnings", table_text, re.I):
            continue
        if re.search(r"reconciliation of non-gaap", table_text, re.I):
            continue
        for row in rows:
            tokens = [str(token) for token in row["tokens"]]
            label = tokens[0].strip().lower()
            match = re.fullmatch(r"(?:total )?(upstream|downstream)", label)
            if not match:
                continue
            value = _first_number(tokens)
            if value is None:
                continue
            output.append(
                {
                    "segment": match.group(1),
                    "segment_earnings_usd_million": value,
                    "source_row_text": row["row_text"],
                    "source_table_index": table_index,
                    "source_row_index": row["row_index"],
                    "parser_rule": "CVX_GAAP_EARNINGS_TABLE_SEGMENT_FIRST_VALUE",
                }
            )
    return output


def extract_integrated_segment_earnings(
    source_manifest: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates: list[dict[str, object]] = []
    sources = source_manifest.loc[source_manifest["ticker"].isin(INTEGRATED_TICKERS)]
    for source in sources.itertuples(index=False):
        path = Path(str(source.local_path))
        if not path.exists():
            continue
        html = path.read_bytes().decode("utf-8", errors="replace")
        parsed = _xom_segment_rows(html) if source.ticker == "XOM" else _cvx_segment_rows(html)
        for row in parsed:
            candidates.append(
                {
                    "ticker": source.ticker,
                    "report_quarter": source.report_quarter,
                    **row,
                    "metric_unit": "usd_million",
                    "reported_period_basis": "THREE_MONTHS",
                    "semantic_category": "GAAP_SEGMENT_EARNINGS",
                    "filing_date": source.filing_date,
                    "available_at": source.available_at,
                    "availability_source": source.availability_source,
                    "source_url": source.source_url,
                    "source_path": str(path),
                }
            )
    raw = pd.DataFrame(candidates)
    if raw.empty:
        return raw, raw
    raw["available_at"] = pd.to_datetime(raw["available_at"], errors="coerce")
    raw["_rounded_value"] = raw["segment_earnings_usd_million"].round(1)
    support = (
        raw.groupby(
            ["ticker", "report_quarter", "segment", "_rounded_value"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "duplicate_support"})
    )
    ranked = raw.merge(
        support,
        on=["ticker", "report_quarter", "segment", "_rounded_value"],
        how="left",
    ).sort_values(
        [
            "ticker", "report_quarter", "segment", "duplicate_support",
            "available_at", "source_table_index", "source_row_index",
        ],
        ascending=[True, True, True, False, True, True, True],
    )
    selected_raw = ranked.groupby(
        ["ticker", "report_quarter", "segment"], as_index=False
    ).head(1)
    selected_rows: list[dict[str, object]] = []
    for (ticker, quarter), group in selected_raw.groupby(
        ["ticker", "report_quarter"], sort=True
    ):
        lookup = group.set_index("segment")["segment_earnings_usd_million"].to_dict()
        if ticker == "XOM":
            mapped = {"upstream": lookup.get("upstream"), "chemicals": lookup.get("chemicals")}
            if "energy_products" in lookup:
                downstream = lookup["energy_products"] + lookup.get("specialty_products", 0.0)
                mapped["downstream"] = downstream
            else:
                mapped["downstream"] = lookup.get("downstream_legacy")
        else:
            mapped = {"upstream": lookup.get("upstream"), "downstream": lookup.get("downstream")}
        for segment, value in mapped.items():
            if value is None or not np.isfinite(value):
                continue
            source_rows = group.loc[
                group["segment"].isin(
                    [segment]
                    if ticker == "CVX" or segment != "downstream"
                    else ["energy_products", "specialty_products", "downstream_legacy"]
                )
            ]
            selected_rows.append(
                {
                    "ticker": ticker,
                    "report_quarter": quarter,
                    "segment": segment,
                    "segment_earnings_usd_million": float(value),
                    "metric_unit": "usd_million",
                    "reported_period_basis": "THREE_MONTHS",
                    "semantic_category": "GAAP_SEGMENT_EARNINGS",
                    "filing_date": source_rows["filing_date"].min(),
                    "available_at": source_rows["available_at"].min(),
                    "source_url": ";".join(sorted(set(source_rows["source_url"].astype(str)))),
                    "source_path": ";".join(sorted(set(source_rows["source_path"].astype(str)))),
                    "source_row_text": "; ".join(source_rows["source_row_text"].astype(str)),
                    "parser_rule": (
                        "XOM_ENERGY_PLUS_SPECIALTY_TO_DOWNSTREAM"
                        if ticker == "XOM" and segment == "downstream" and "energy_products" in lookup
                        else str(source_rows["parser_rule"].iloc[0])
                    ),
                }
            )
    selected = pd.DataFrame(selected_rows)
    return raw.drop(columns=["_rounded_value"]), selected.sort_values(
        ["ticker", "segment", "report_quarter"]
    ).reset_index(drop=True)


def audit_integrated_segment_gold(
    selected: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["ticker", "report_quarter", "segment"]
    if labels.duplicated(keys).any():
        raise ValueError("Integrated segment gold labels contain duplicate keys")
    rows = labels.merge(selected, on=keys, how="left", validate="one_to_one")
    tolerance = np.maximum(0.1, rows["manual_value"].abs() * 0.001)
    rows["numeric_match"] = (
        rows["segment_earnings_usd_million"].sub(rows["manual_value"]).abs()
        <= tolerance
    )
    rows["unit_match"] = rows["metric_unit"].eq(rows["manual_unit"])
    rows["period_match"] = rows["reported_period_basis"].eq(rows["manual_period"])
    rows["semantic_match"] = rows["semantic_category"].eq(rows["manual_semantics"])
    rows["all_match"] = rows[
        ["numeric_match", "unit_match", "period_match", "semantic_match"]
    ].all(axis=1)
    summary = pd.DataFrame(
        [
            {
                "gold_rows": len(rows),
                "numeric_accuracy": rows["numeric_match"].mean(),
                "unit_accuracy": rows["unit_match"].mean(),
                "period_accuracy": rows["period_match"].mean(),
                "semantic_accuracy": rows["semantic_match"].mean(),
                "all_dimension_accuracy": rows["all_match"].mean(),
            }
        ]
    )
    summary["parser_quality_gate"] = (
        summary["gold_rows"].ge(20)
        & summary["numeric_accuracy"].ge(0.95)
        & summary["unit_accuracy"].eq(1.0)
        & summary["period_accuracy"].eq(1.0)
        & summary["semantic_accuracy"].ge(0.95)
    )
    return rows, summary


def _target_change_panel(
    frame: pd.DataFrame,
    *,
    value_column: str,
    transform: str,
    entity_columns: list[str],
    cutoff_day: int = 61,
) -> pd.DataFrame:
    panel = frame.copy()
    panel["quarter"] = panel["quarter"].astype(str)
    panel["entity"] = panel[entity_columns].astype(str).agg("::".join, axis=1)
    panel["quarter_ordinal"] = panel["quarter"].map(_quarter_ordinal)
    lookup = panel.set_index(["entity", "quarter"])[value_column].to_dict()
    available = panel.set_index(["entity", "quarter"])["available_at"].to_dict()
    panel["prior_year_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 4)
    )
    panel["previous_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 1)
    )
    panel["target_value"] = pd.to_numeric(panel[value_column], errors="coerce")
    panel["prior_year_target_value"] = [
        lookup.get((row.entity, row.prior_year_quarter), np.nan)
        for row in panel.itertuples()
    ]
    if transform == "LOG":
        valid = panel["target_value"].gt(0) & panel["prior_year_target_value"].gt(0)
        panel["actual_change"] = np.nan
        panel.loc[valid, "actual_change"] = 100.0 * np.log(
            panel.loc[valid, "target_value"]
            / panel.loc[valid, "prior_year_target_value"]
        )
    elif transform == "DELTA":
        panel["actual_change"] = (
            panel["target_value"] - panel["prior_year_target_value"]
        )
    else:
        raise ValueError(f"Unknown target transform: {transform}")
    change_lookup = panel.set_index(["entity", "quarter"])["actual_change"].to_dict()
    panel["lag_change"] = [
        change_lookup.get((row.entity, row.previous_quarter), np.nan)
        for row in panel.itertuples()
    ]
    panel["lag_report_date"] = [
        available.get((row.entity, row.previous_quarter), pd.NaT)
        for row in panel.itertuples()
    ]
    panel["forecast_cutoff_date"] = panel["quarter"].map(
        lambda value: quarter_cutoff_date(value, cutoff_day)
    )
    panel["pit_lag_target_available"] = pd.to_datetime(
        panel["lag_report_date"], errors="coerce"
    ).le(pd.to_datetime(panel["forecast_cutoff_date"], errors="coerce"))
    return panel.loc[
        panel["actual_change"].notna()
        & panel["lag_change"].notna()
        & panel["pit_lag_target_available"]
    ].copy()


def build_integrated_segment_panel(
    selected: pd.DataFrame,
    revenue: pd.DataFrame,
    driver_panel: pd.DataFrame,
) -> pd.DataFrame:
    earnings = selected.rename(columns={"report_quarter": "quarter"}).copy()
    revenue_view = revenue[["ticker", "quarter", "revenue"]].drop_duplicates(
        ["ticker", "quarter"]
    )
    earnings = earnings.merge(revenue_view, on=["ticker", "quarter"], how="inner")
    earnings["segment_earnings_contribution_margin_pct"] = (
        earnings["segment_earnings_usd_million"] * 1_000_000.0
        / earnings["revenue"]
        * 100.0
    )
    earnings["available_at"] = pd.to_datetime(earnings["available_at"], errors="coerce")
    panel = _target_change_panel(
        earnings,
        value_column="segment_earnings_contribution_margin_pct",
        transform="DELTA",
        entity_columns=["ticker", "segment"],
    )
    features = driver_panel.loc[
        driver_panel["ticker"].isin(INTEGRATED_TICKERS)
    ].drop_duplicates(["ticker", "quarter"])
    columns = [
        "ticker", "quarter", "wti_log_yoy", "henry_log_yoy",
        "product_price_basket_log_yoy", "crack_321_per_bbl_log_yoy",
        "us_crude_production_log_yoy", "us_dry_gas_production_log_yoy",
        "refinery_crude_input_log_yoy", "us_liquid_fuels_consumption_log_yoy",
        "upstream_total_boe_log_yoy", "downstream_throughput_log_yoy",
        "downstream_product_sales_log_yoy", "chemicals_product_sales_log_yoy",
    ]
    columns = [column for column in columns if column in features]
    panel = panel.merge(features[columns], on=["ticker", "quarter"], how="left")
    panel["target_name"] = "SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT"
    panel["target_transform"] = "DELTA"
    panel["change_unit"] = "percentage_points"
    return panel.sort_values(["segment", "entity", "quarter_ordinal"])


def build_operating_margin_panel(
    operating_income: pd.DataFrame,
    companyfacts_root: Path,
    feature_panel: pd.DataFrame,
) -> pd.DataFrame:
    if operating_income.empty:
        return operating_income
    tickers = tuple(sorted(operating_income["ticker"].unique()))
    revenue = load_companyfacts_quarterly_revenue(companyfacts_root, tickers)
    source = operating_income.merge(
        revenue[["ticker", "quarter", "revenue", "filing_date"]].rename(
            columns={"filing_date": "revenue_filing_date"}
        ),
        on=["ticker", "quarter"],
        how="inner",
    )
    source["operating_margin_pct"] = (
        source["operating_income_usd"] / source["revenue"] * 100.0
    )
    source["available_at"] = source[["filing_date", "revenue_filing_date"]].max(axis=1)
    panel = _target_change_panel(
        source,
        value_column="operating_margin_pct",
        transform="DELTA",
        entity_columns=["ticker"],
    )
    features = feature_panel.drop_duplicates(["ticker", "quarter"])
    wanted = [
        "ticker", "quarter", "wti_log_yoy", "henry_log_yoy",
        "propane_log_yoy", "basket_price_log_yoy",
        "product_price_basket_log_yoy", "crack_321_per_bbl_log_yoy",
        "refinery_crude_input_log_yoy", "total_rigs_log_yoy",
        "oil_rigs_log_yoy", "us_liquid_fuels_consumption_log_yoy",
    ]
    wanted = [column for column in wanted if column in features]
    panel = panel.merge(features[wanted], on=["ticker", "quarter"], how="left")
    panel["target_name"] = "CONSOLIDATED_OPERATING_MARGIN_PCT"
    panel["target_transform"] = "DELTA"
    panel["change_unit"] = "percentage_points"
    return panel.sort_values(["entity", "quarter_ordinal"])


def build_capex_panel(
    capex: pd.DataFrame,
    feature_panel: pd.DataFrame,
) -> pd.DataFrame:
    source = capex.copy()
    source["available_at"] = pd.to_datetime(source["filing_date"], errors="coerce")
    panel = _target_change_panel(
        source,
        value_column="cash_capex_usd",
        transform="LOG",
        entity_columns=["ticker"],
    )
    features = feature_panel.drop_duplicates(["ticker", "quarter"])
    wanted = [
        "ticker", "quarter", "wti_log_yoy", "henry_log_yoy",
        "propane_log_yoy", "basket_price_log_yoy",
    ]
    panel = panel.merge(features[wanted], on=["ticker", "quarter"], how="left")
    panel["target_name"] = "CASH_CAPEX"
    panel["target_transform"] = "LOG"
    panel["change_unit"] = "log_points"
    return panel.sort_values(["entity", "quarter_ordinal"])


def target_source_metadata(frame: pd.DataFrame) -> dict[str, object]:
    return {
        "rows": len(frame),
        "tickers": int(frame["ticker"].nunique()) if "ticker" in frame else 0,
        "first_quarter": str(frame["quarter"].min()) if len(frame) else None,
        "last_quarter": str(frame["quarter"].max()) if len(frame) else None,
        "source_facts": (
            sorted(set(frame["source_fact"].astype(str)))
            if "source_fact" in frame
            else []
        ),
    }
