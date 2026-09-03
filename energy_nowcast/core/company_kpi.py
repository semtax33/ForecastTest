from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Iterable

from equity_platform.sectors.energy.parsing.company_kpi import (
    KPI_SPECS,
    MetricSpec,
    current_value as _current_value,
    extract_filing_metrics as _extract_filing_metrics,
    legacy_table_rows as _table_rows,
    number as _number,
)

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests

from ..data.cutoff import quarter_cutoff_date
from ..research.v351.revenue import CIKS
from .taxonomy import SUBINDUSTRY_TICKERS


SEC_USER_AGENT = "energy-nowcast-research/1.0 codex@openai.com"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


REQUESTED_KPI_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "integrated": {
        "upstream_oil_volume": (),
        "upstream_gas_volume": (),
        "upstream_total_boe": ("upstream_total_boe",),
        "realized_oil_price": (),
        "realized_gas_price": (),
        "refinery_throughput": ("downstream_throughput",),
        "refinery_utilization": (),
        "product_sales_volume": ("downstream_product_sales",),
        "chemical_sales_volume": ("chemicals_product_sales",),
        "upstream_revenue": (),
        "downstream_revenue": (),
        "chemical_revenue": (),
    },
    "refining": {
        "crude_throughput_bpd": ("company_throughput",),
        "total_throughput_bpd": ("company_throughput",),
        "utilization_pct": ("company_utilization",),
        "refining_capacity_bpd": (),
        "gasoline_yield_pct": (),
        "distillate_yield_pct": (),
        "jet_yield_pct": (),
        "product_sales_volume": (),
        "turnaround_flag": (),
        "turnaround_cost_or_guidance": (),
        "region_mix": (),
        "expected_throughput": (),
        "expected_utilization": (),
        "planned_maintenance": (),
    },
    "midstream": {
        "gas_transport_bcf_d": ("gas_transport_volume",),
        "gas_gathering_bcf_d": ("gas_gathering_volume",),
        "gas_processing_bcf_d": ("fee_gas_processing_volume",),
        "crude_transport_mbpd": ("liquids_transport_volume",),
        "ngl_transport_mbpd": ("liquids_transport_volume",),
        "fractionation_mbpd": (),
        "terminal_volume": (),
        "storage_volume_or_capacity": (),
        "fee_based_pct": (),
        "commodity_sensitive_pct": (),
        "take_or_pay_pct": (),
        "segment_revenue": (),
        "segment_ebitda": (),
    },
    "services": {
        "north_america_revenue": ("north_america_activity",),
        "international_revenue": ("international_activity",),
        "segment_revenue": ("completion_production_activity",),
        "orders": ("orders_activity",),
        "backlog": (),
        "book_to_bill": (),
        "international_rig_exposure": (),
        "offshore_exposure": (),
        "pricing_commentary": (),
        "utilization": (),
        "company_guidance": (),
    },
}


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _request(session: requests.Session, url: str) -> requests.Response:
    error: requests.RequestException | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=45)
            response.raise_for_status()
            time.sleep(0.12)
            return response
        except requests.RequestException as exc:
            error = exc
            time.sleep(1.0 * (2**attempt))
    assert error is not None
    raise error


def _filing_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    recent = payload.get("filings", {}).get("recent", {})  # type: ignore[union-attr]
    if not recent:
        return []
    return [dict(zip(recent, values)) for values in zip(*recent.values())]


def _report_quarter(filing_date: str) -> str:
    return str(pd.Timestamp(filing_date).to_period("Q") - 1)


def _filing_availability(filing: dict[str, object]) -> tuple[pd.Timestamp, str]:
    """Return the earliest verified official timestamp at daily PIT precision."""
    accepted = pd.to_datetime(
        filing.get("acceptanceDateTime"), errors="coerce", utc=True
    )
    if not pd.isna(accepted):
        return accepted.tz_convert("UTC").tz_localize(None), "SEC_ACCEPTANCE_DATETIME"
    filing_date = pd.Timestamp(str(filing["filingDate"])).normalize()
    return filing_date + pd.Timedelta(days=1), "FILING_DATE_PLUS_ONE_FALLBACK"


def _earnings_candidates(
    rows: Iterable[dict[str, object]],
    start_year: int,
    end_year: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for row in rows:
        filing_date = pd.to_datetime(row.get("filingDate"), errors="coerce")
        if pd.isna(filing_date) or str(row.get("form")) != "8-K":
            continue
        if "2.02" not in str(row.get("items") or ""):
            continue
        report_quarter = _report_quarter(str(filing_date.date()))
        report_period = pd.Period(report_quarter, freq="Q")
        days_after_end = (filing_date.normalize() - report_period.end_time.normalize()).days
        if not 1 <= days_after_end <= 65:
            continue
        if not start_year - 1 <= report_period.year <= end_year:
            continue
        output = dict(row)
        output["report_quarter"] = report_quarter
        candidates.append(output)
    return candidates


def _exhibit_documents(index_html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(index_html, "html.parser")
    rows: list[dict[str, str]] = []
    for tr in soup.select("table.tableFile tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.select("td")]
        link = tr.select_one("a")
        if len(cells) < 4 or link is None or not cells[3].upper().startswith("EX-99"):
            continue
        name = str(link.get("href") or "").split("/")[-1]
        if not name.lower().endswith((".htm", ".html")):
            continue
        rows.append(
            {
                "description": cells[1],
                "document": name,
                "document_type": cells[3],
            }
        )
    return rows


def _add_yoy(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        metrics["metric_log_yoy"] = np.nan
        return metrics
    result = metrics.copy()
    result["prior_year_quarter"] = result["report_quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 4)
    )
    lookup = {
        (str(row.ticker), str(row.metric_id), str(row.report_quarter)): float(
            row.metric_value
        )
        for row in result.itertuples()
        if float(row.metric_value) > 0
    }
    result["prior_year_metric_value"] = [
        lookup.get((row.ticker, row.metric_id, row.prior_year_quarter), np.nan)
        for row in result.itertuples()
    ]
    valid = result["metric_value"].gt(0) & result["prior_year_metric_value"].gt(0)
    result["metric_log_yoy"] = np.nan
    result.loc[valid, "metric_log_yoy"] = 100.0 * np.log(
        result.loc[valid, "metric_value"]
        / result.loc[valid, "prior_year_metric_value"]
    )
    return result


def refresh_company_kpi_snapshot(
    output: Path,
    tickers: tuple[str, ...],
    start_year: int = 2019,
    end_year: int | None = None,
) -> dict[str, object]:
    end_year = end_year or datetime.now().year
    output.mkdir(parents=True, exist_ok=True)
    raw_root = output / "raw"
    session = requests.Session()
    session.headers.update({"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    metric_rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    filing_audit: list[dict[str, object]] = []
    for ticker in tickers:
        cik = str(CIKS[ticker]).zfill(10)
        submissions_url = f"{SEC_SUBMISSIONS}/CIK{cik}.json"
        payload = _request(session, submissions_url).json()
        candidates = _earnings_candidates(
            _filing_rows(payload), start_year=start_year, end_year=end_year
        )
        by_quarter: dict[str, list[tuple[dict[str, object], list[dict[str, object]]]]] = {}
        for filing in candidates:
            available_at, availability_source = _filing_availability(filing)
            accession = str(filing["accessionNumber"])
            accession_compact = accession.replace("-", "")
            archive_base = f"{SEC_ARCHIVES}/{int(cik)}/{accession_compact}"
            index_url = f"{archive_base}/{accession}-index.html"
            ticker_dir = raw_root / ticker
            ticker_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"{filing['filingDate']}_{accession}_"
            cached_documents = sorted(ticker_dir.glob(f"{prefix}*"))
            if cached_documents:
                exhibits = [
                    {
                        "description": "CACHED_SEC_EX99",
                        "document": path.name.removeprefix(prefix),
                        "document_type": "EX-99",
                    }
                    for path in cached_documents
                ]
            else:
                index_response = _request(session, index_url)
                exhibits = _exhibit_documents(index_response.text)
            documents: list[dict[str, object]] = []
            for exhibit in exhibits:
                source_url = f"{archive_base}/{exhibit['document']}"
                local_name = (
                    f"{filing['filingDate']}_{accession}_{exhibit['document']}"
                    .replace("/", "_")
                )
                local_path = ticker_dir / local_name
                if local_path.exists() and local_path.stat().st_size > 0:
                    content = local_path.read_bytes()
                else:
                    content = _request(session, source_url).content
                    local_path.write_bytes(content)
                html = content.decode("utf-8", errors="replace")
                documents.append(
                    {
                        **exhibit,
                        "html": html,
                        "source_url": source_url,
                        "local_path": str(local_path),
                    }
                )
                source_rows.append(
                    {
                        "ticker": ticker,
                        "report_quarter": filing["report_quarter"],
                        "filing_date": filing["filingDate"],
                        "acceptance_datetime_utc": (
                            filing.get("acceptanceDateTime") or pd.NA
                        ),
                        "ir_publication_datetime_utc": pd.NA,
                        "available_at": available_at,
                        "availability_source": availability_source,
                        "accession": accession,
                        "document_type": exhibit["document_type"],
                        "description": exhibit["description"],
                        "source_url": source_url,
                        "local_path": str(local_path),
                        "sha256": _sha256_bytes(content),
                    }
                )
            extracted = _extract_filing_metrics(ticker, filing, documents)
            by_quarter.setdefault(str(filing["report_quarter"]), []).append(
                (filing, extracted)
            )
        for report_quarter, alternatives in by_quarter.items():
            # Prefer the filing with the widest standardized KPI coverage, then
            # the earliest such earnings release for conservative availability.
            filing, extracted = sorted(
                alternatives,
                key=lambda item: (-len(item[1]), str(item[0]["filingDate"])),
            )[0]
            metric_rows.extend(extracted)
            filing_audit.append(
                {
                    "ticker": ticker,
                    "report_quarter": report_quarter,
                    "filing_date": filing["filingDate"],
                    "acceptance_datetime_utc": (
                        filing.get("acceptanceDateTime") or pd.NA
                    ),
                    "available_at": _filing_availability(filing)[0],
                    "availability_source": _filing_availability(filing)[1],
                    "accession": filing["accessionNumber"],
                    "standardized_metric_count": len(extracted),
                    "status": "SELECTED" if extracted else "NO_STANDARDIZED_KPI_MATCH",
                    "alternative_filings": len(alternatives),
                }
            )
    metrics = _add_yoy(pd.DataFrame(metric_rows))
    sources = pd.DataFrame(source_rows).drop_duplicates("source_url")
    audit = pd.DataFrame(filing_audit)
    metrics.to_csv(output / "company_kpi_quarterly.csv", index=False)
    sources.to_csv(output / "source_manifest.csv", index=False)
    audit.to_csv(output / "filing_coverage.csv", index=False)
    coverage = (
        metrics.groupby(["ticker", "metric_id"], as_index=False)
        .agg(
            first_report_quarter=("report_quarter", "min"),
            last_report_quarter=("report_quarter", "max"),
            observations=("metric_value", "count"),
            yoy_observations=("metric_log_yoy", "count"),
            mean_quality_score=("quality_score", "mean"),
        )
        if not metrics.empty
        else pd.DataFrame()
    )
    coverage.to_csv(output / "metric_coverage.csv", index=False)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "SEC_EDGAR_OFFICIAL_8K_EARNINGS_EXHIBITS",
        "paid_data_used": False,
        "availability_policy": (
            "MIN_VERIFIED_OFFICIAL_TIMESTAMP_DAILY_PIT;"
            "SEC_ACCEPTANCE_DATETIME_WITH_FILING_PLUS_ONE_FALLBACK;"
            "IR_TIMESTAMP_NULL_UNLESS_VERIFIED"
        ),
        "parser_rule_version": "KPI_PARSER_CONTEXT_V2",
        "start_year": start_year,
        "end_year": end_year,
        "tickers": list(tickers),
        "metric_rows": len(metrics),
        "source_documents": len(sources),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return metadata


def load_company_kpis(snapshot: Path) -> pd.DataFrame:
    path = snapshot / "company_kpi_quarterly.csv"
    if not path.exists():
        raise FileNotFoundError(f"Company KPI snapshot is missing: {path}")
    frame = pd.read_csv(path)
    frame["filing_date"] = pd.to_datetime(frame["filing_date"], errors="coerce")
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce")
    return frame


def requested_kpi_coverage(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for subindustry, tickers in SUBINDUSTRY_TICKERS.items():
        for ticker in tickers:
            company = metrics.loc[metrics["ticker"].eq(ticker)]
            available = set(company["metric_id"].astype(str))
            for requested, mapped in REQUESTED_KPI_MAP[subindustry].items():
                matched = tuple(metric for metric in mapped if metric in available)
                selected = company.loc[company["metric_id"].isin(matched)]
                rows.append(
                    {
                        "subindustry": subindustry,
                        "ticker": ticker,
                        "requested_metric": requested,
                        "mapped_metric_ids": ",".join(matched),
                        "status": (
                            "PARSED_SEC_8K_EARNINGS_EXHIBIT"
                            if matched
                            else "NOT_YET_STANDARDIZED"
                        ),
                        "observations": int(len(selected)),
                        "yoy_observations": int(selected["metric_log_yoy"].count()),
                        "mean_quality_score": (
                            float(selected["quality_score"].mean())
                            if len(selected)
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(rows)


def select_company_kpis_for_targets(
    metrics: pd.DataFrame,
    targets: pd.DataFrame,
    cutoff_day: int = 61,
    report_lag_quarters: int = 1,
) -> pd.DataFrame:
    if report_lag_quarters < 1:
        raise ValueError("report_lag_quarters must be at least one")
    keys = targets[["ticker", "quarter"]].drop_duplicates().copy()
    keys["forecast_cutoff_date"] = keys["quarter"].map(
        lambda value: quarter_cutoff_date(value, cutoff_day)
    )
    rows: list[dict[str, object]] = []
    for target in keys.itertuples(index=False):
        required_report_quarter = str(
            pd.Period(target.quarter, freq="Q") - report_lag_quarters
        )
        eligible = metrics.loc[
            metrics["ticker"].eq(target.ticker)
            & metrics["metric_log_yoy"].notna()
            & metrics["available_at"].dt.normalize().le(
                pd.Timestamp(target.forecast_cutoff_date).normalize()
            )
            & metrics["report_quarter"].eq(required_report_quarter)
        ].copy()
        latest = (
            eligible.sort_values(["available_at", "report_quarter"])
            .groupby("metric_id", as_index=False)
            .tail(1)
        )
        output: dict[str, object] = {
            "ticker": target.ticker,
            "quarter": target.quarter,
            "forecast_cutoff_date": target.forecast_cutoff_date,
            "company_kpi_metric_count": len(latest),
            "company_kpi_status": "AVAILABLE" if len(latest) else "UNAVAILABLE",
            "company_kpi_available_at": latest["available_at"].max() if len(latest) else pd.NaT,
            "company_kpi_report_quarter": (
                max(latest["report_quarter"], key=lambda value: pd.Period(value, freq="Q"))
                if len(latest)
                else pd.NA
            ),
            "company_kpi_report_lag_quarters": report_lag_quarters,
            "company_kpi_quality_score": (
                float(latest["quality_score"].mean()) if len(latest) else np.nan
            ),
            "company_kpi_rule_confidence": (
                float(latest["parser_rule_confidence"].mean())
                if len(latest) and "parser_rule_confidence" in latest
                else np.nan
            ),
            "company_kpi_age_days": (
                int(
                    (
                        pd.Timestamp(target.forecast_cutoff_date).normalize()
                        - latest["available_at"].max().normalize()
                    ).days
                )
                if len(latest)
                else np.nan
            ),
            "kpi_used": bool(len(latest)),
            "fallback_used": not bool(len(latest)),
            "company_kpi_source_urls": (
                ";".join(sorted(set(latest["source_url"].astype(str))))
                if len(latest)
                else pd.NA
            ),
        }
        for row in latest.itertuples():
            output[f"{row.metric_id}_log_yoy"] = float(row.metric_log_yoy)
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["quarter", "ticker"]).reset_index(drop=True)
