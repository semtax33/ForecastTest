from __future__ import annotations

from pathlib import Path
import re

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd

from ...core.company_kpi import _current_value, _table_rows, select_company_kpis_for_targets
from ...data.cutoff import quarter_cutoff_date
from equity_platform.sectors.energy.forecasting.midstream import SAFE_ACTIVITY_METRICS
from equity_platform.sectors.energy.forecasting.midstream import CONTRACT_PROFILES


MIDSTREAM_EBITDA_RULES: dict[str, tuple[str, str]] = {
    "KMI": (
        r"^adjusted ebitda(?: \(\d+\))?$",
        r"three months ended|preliminary net income.*adjusted ebitda reconciliation",
    ),
    "WMB": (r"^adjusted ebitda$", r"williams summary financial information"),
    "ET": (r"^adjusted ebitda \(consolidated\)$", r"three months ended"),
    "EPD": (
        r"^non-gaap adjusted ebitda(?: \(\d+\))?$",
        r"condensed statements of consolidated operations",
    ),
}


def extract_midstream_adjusted_ebitda(
    source_manifest: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates: list[dict[str, object]] = []
    for source in source_manifest.loc[
        source_manifest["ticker"].isin(MIDSTREAM_EBITDA_RULES)
    ].itertuples(index=False):
        path = Path(str(source.local_path))
        if not path.exists():
            continue
        html = path.read_bytes().decode("utf-8", errors="replace")
        label_pattern, context_pattern = MIDSTREAM_EBITDA_RULES[str(source.ticker)]
        for row in _table_rows(html):
            tokens = [str(token).strip() for token in row["tokens"]]
            label = next(
                (
                    token
                    for token in tokens
                    if re.search(label_pattern, token, flags=re.IGNORECASE)
                ),
                None,
            )
            if label is None or not re.search(
                context_pattern,
                str(row["table_context"]),
                flags=re.IGNORECASE,
            ):
                continue
            value = _current_value(row, str(source.report_quarter), "first")
            if value is None:
                continue
            candidates.append(
                {
                    "ticker": str(source.ticker),
                    "report_quarter": str(source.report_quarter),
                    "adjusted_ebitda_usd_million": float(value),
                    "metric_unit": "usd_million",
                    "reported_period_basis": "THREE_MONTHS",
                    "semantic_category": "COMPANY_ADJUSTED_EBITDA_NON_GAAP",
                    "filing_date": source.filing_date,
                    "available_at": source.available_at,
                    "availability_source": source.availability_source,
                    "source_url": source.source_url,
                    "source_path": str(path),
                    "source_row_text": row["row_text"],
                    "source_table_context": row["table_context"],
                    "source_table_index": row["table_index"],
                    "source_row_index": row["row_index"],
                    "parser_rule": f"label={label_pattern};context={context_pattern};first",
                }
            )
    raw = pd.DataFrame(candidates)
    if raw.empty:
        return raw, raw
    raw["available_at"] = pd.to_datetime(raw["available_at"], errors="coerce")
    raw["filing_date"] = pd.to_datetime(raw["filing_date"], errors="coerce")
    raw["_rounded_value"] = raw["adjusted_ebitda_usd_million"].round(1)
    frequency = (
        raw.groupby(["ticker", "report_quarter", "_rounded_value"], as_index=False)
        .size()
        .rename(columns={"size": "duplicate_support"})
    )
    ranked = raw.merge(
        frequency,
        on=["ticker", "report_quarter", "_rounded_value"],
        how="left",
    ).sort_values(
        [
            "ticker",
            "report_quarter",
            "duplicate_support",
            "available_at",
            "source_table_index",
            "source_row_index",
        ],
        ascending=[True, True, False, True, True, True],
    )
    selected = ranked.groupby(["ticker", "report_quarter"], as_index=False).head(1)
    selected = selected.drop(columns=["_rounded_value"]).sort_values(
        ["ticker", "report_quarter"]
    )
    selected["prior_year_quarter"] = selected["report_quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 4)
    )
    lookup = selected.set_index(["ticker", "report_quarter"])[
        "adjusted_ebitda_usd_million"
    ].to_dict()
    selected["prior_year_adjusted_ebitda_usd_million"] = [
        lookup.get((row.ticker, row.prior_year_quarter), np.nan)
        for row in selected.itertuples()
    ]
    valid = (
        selected["adjusted_ebitda_usd_million"].gt(0)
        & selected["prior_year_adjusted_ebitda_usd_million"].gt(0)
    )
    selected["adjusted_ebitda_log_yoy"] = np.nan
    selected.loc[valid, "adjusted_ebitda_log_yoy"] = 100.0 * np.log(
        selected.loc[valid, "adjusted_ebitda_usd_million"]
        / selected.loc[valid, "prior_year_adjusted_ebitda_usd_million"]
    )
    return raw.drop(columns=["_rounded_value"]), selected.reset_index(drop=True)


def audit_midstream_ebitda_gold(
    selected: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["ticker", "report_quarter"]
    if labels.duplicated(keys).any():
        raise ValueError("Adjusted EBITDA gold labels contain duplicate keys")
    rows = labels.merge(selected, on=keys, how="left", validate="one_to_one")
    tolerance = np.maximum(
        0.1, pd.to_numeric(rows["manual_value"], errors="coerce").abs() * 0.001
    )
    rows["numeric_match"] = (
        rows["adjusted_ebitda_usd_million"].sub(rows["manual_value"]).abs()
        <= tolerance
    )
    rows["unit_match"] = rows["metric_unit"].eq(rows["manual_unit"])
    rows["period_match"] = rows["reported_period_basis"].eq(
        rows["manual_period"]
    )
    rows["semantic_match"] = rows["semantic_category"].eq(
        rows["manual_semantics"]
    )
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
        summary["numeric_accuracy"].ge(0.95)
        & summary["unit_accuracy"].eq(1.0)
        & summary["period_accuracy"].eq(1.0)
        & summary["semantic_accuracy"].ge(0.95)
    )
    return rows, summary


def build_midstream_ebitda_panel(
    selected_ebitda: pd.DataFrame,
    company_kpis: pd.DataFrame,
    structural_panel: pd.DataFrame,
    cutoff_day: int = 61,
) -> pd.DataFrame:
    panel = selected_ebitda.dropna(subset=["adjusted_ebitda_log_yoy"]).copy()
    panel["quarter"] = panel["report_quarter"]
    panel["previous_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 1)
    )
    yoy_lookup = panel.set_index(["ticker", "quarter"])[
        "adjusted_ebitda_log_yoy"
    ].to_dict()
    availability_lookup = selected_ebitda.set_index(["ticker", "report_quarter"])[
        "available_at"
    ].to_dict()
    panel["lag_revenue_log_yoy"] = [
        yoy_lookup.get((row.ticker, row.previous_quarter), np.nan)
        for row in panel.itertuples()
    ]
    panel["lag_report_date"] = [
        availability_lookup.get((row.ticker, row.previous_quarter), pd.NaT)
        for row in panel.itertuples()
    ]
    panel["forecast_cutoff_date"] = panel["quarter"].map(
        lambda value: quarter_cutoff_date(value, cutoff_day)
    )
    panel["pit_lag_ebitda_available"] = pd.to_datetime(
        panel["lag_report_date"], errors="coerce"
    ).le(pd.to_datetime(panel["forecast_cutoff_date"], errors="coerce"))
    panel = panel.loc[
        panel["lag_revenue_log_yoy"].notna()
        & panel["pit_lag_ebitda_available"]
    ].copy()
    targets = panel[["ticker", "quarter"]]
    kpi_features = select_company_kpis_for_targets(
        company_kpis, targets, cutoff_day=cutoff_day, report_lag_quarters=1
    )
    macro_columns = [
        "ticker",
        "quarter",
        "wti_log_yoy",
        "henry_log_yoy",
        "available_at",
    ]
    macro = structural_panel[macro_columns].drop_duplicates(["ticker", "quarter"])
    panel = panel.merge(kpi_features, on=["ticker", "quarter"], how="left").merge(
        macro, on=["ticker", "quarter"], how="left", suffixes=("", "_macro")
    )
    rows: list[dict[str, object]] = []
    for _, row in panel.iterrows():
        ticker = str(row["ticker"])
        values: list[float] = []
        used: list[str] = []
        for column in SAFE_ACTIVITY_METRICS[ticker]:
            value = pd.to_numeric(row.get(column), errors="coerce")
            if np.isfinite(value) and abs(float(value)) <= 80.0:
                values.append(float(value))
                used.append(column.removesuffix("_log_yoy"))
        profile = CONTRACT_PROFILES[ticker]
        volume = float(np.median(values)) if values else 0.0
        commodity = (
            profile["gas_volume_share"]
            * float(pd.to_numeric(row["henry_log_yoy"], errors="coerce"))
            + (1.0 - profile["gas_volume_share"])
            * float(pd.to_numeric(row["wti_log_yoy"], errors="coerce"))
        )
        raw_prediction = (
            profile["fee_share"] * (volume + profile["tariff_escalator"])
            + (1.0 - profile["fee_share"]) * commodity
        )
        output = row.to_dict()
        output.update(
            {
                "subindustry": "midstream",
                "phase": 3,
                "quarter_ordinal": int(pd.Period(row["quarter"], freq="Q").ordinal),
                "revenue": float(row["adjusted_ebitda_usd_million"]) * 1e6,
                "prior_year_revenue": float(
                    row["prior_year_adjusted_ebitda_usd_million"]
                )
                * 1e6,
                "actual_log_yoy": float(row["adjusted_ebitda_log_yoy"]),
                "legacy_prediction": float(row["lag_revenue_log_yoy"]),
                "candidate_prediction": raw_prediction,
                "raw_structural_prediction": raw_prediction,
                "structural_model": "P3.2_MIDSTREAM_ADJUSTED_EBITDA_VOLUME_FEE",
                "structural_feature_status": (
                    "AVAILABLE" if values else "MACRO_ONLY_VOLUME_UNAVAILABLE"
                ),
                "company_volume_log_yoy": volume if values else np.nan,
                "company_volume_metrics_used": ",".join(used),
                "fee_share": profile["fee_share"],
                "tariff_escalator_pct": profile["tariff_escalator"],
                "commodity_effect_log_points": (
                    (1.0 - profile["fee_share"]) * commodity
                ),
                "filing_date": row["filing_date"],
            }
        )
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["ticker", "quarter_ordinal"])


FORWARD_TOPIC = re.compile(
    r"production|throughput|turnaround|maintenance|outage|chemical|refinery",
    flags=re.IGNORECASE,
)
FORWARD_MARKER = re.compile(
    r"next quarter|first quarter|second quarter|third quarter|fourth quarter|"
    r"expect(?:s|ed)?|forecast|guidance|outlook|planned",
    flags=re.IGNORECASE,
)


def scan_integrated_forward_signals(
    source_manifest: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    sources = source_manifest.loc[source_manifest["ticker"].isin(["XOM", "CVX"])]
    for source in sources.itertuples(index=False):
        path = Path(str(source.local_path))
        if not path.exists():
            continue
        soup = BeautifulSoup(
            path.read_bytes().decode("utf-8", errors="replace"), "html.parser"
        )
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        fragments = re.split(r"(?<=[.!?])\s+|\s*\|\s*", text)
        for fragment in fragments:
            normalized = fragment.strip()
            if len(normalized) < 30 or len(normalized) > 700:
                continue
            if "forward-looking statement" in normalized.lower():
                continue
            if not FORWARD_TOPIC.search(normalized) or not FORWARD_MARKER.search(
                normalized
            ):
                continue
            numeric = bool(
                re.search(
                    r"\b\d+(?:\.\d+)?\s*(?:%|percent|bpd|boe|barrels|mboe|kbd|mbd)",
                    normalized,
                    flags=re.IGNORECASE,
                )
            )
            rows.append(
                {
                    "ticker": source.ticker,
                    "report_quarter": source.report_quarter,
                    "candidate_target_quarter": str(
                        pd.Period(str(source.report_quarter), freq="Q") + 1
                    ),
                    "filing_date": source.filing_date,
                    "available_at": source.available_at,
                    "source_url": source.source_url,
                    "source_path": str(path),
                    "forward_text": normalized,
                    "numeric_forward_signal": numeric,
                    "manual_gold_verified": False,
                    "candidate_status": "TEXT_CANDIDATE_REQUIRES_MANUAL_GOLD",
                }
            )
    candidates = pd.DataFrame(rows).drop_duplicates(
        ["ticker", "report_quarter", "forward_text"]
    )
    coverage_rows: list[dict[str, object]] = []
    for ticker in ("XOM", "CVX"):
        company = candidates.loc[candidates["ticker"].eq(ticker)]
        numeric = company.loc[company["numeric_forward_signal"]]
        coverage_rows.append(
            {
                "ticker": ticker,
                "text_candidate_quarters": int(company["report_quarter"].nunique()),
                "numeric_candidate_quarters": int(numeric["report_quarter"].nunique()),
                "manual_gold_verified_quarters": 0,
                "minimum_required_quarters": 8,
                "forward_candidate_unlocked": False,
                "status": "LOCKED_UNTIL_MANUAL_GOLD_AND_8Q_PER_TICKER",
            }
        )
    return candidates, pd.DataFrame(coverage_rows)
