from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Iterable

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


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    label_pattern: str
    unit: str
    aggregation: str = "max"
    current_mode: str = "first"
    candidate_selection: str = "all_tables"
    semantic_category: str = "OPERATING_KPI"
    required_context_pattern: str | None = None


KPI_SPECS: dict[str, tuple[MetricSpec, ...]] = {
    "XOM": (
        MetricSpec(
            "upstream_total_boe", r"oil-equivalent production", "koebd",
            semantic_category="TOTAL_OIL_EQUIVALENT_PRODUCTION_VOLUME",
        ),
        MetricSpec(
            "downstream_product_sales", r"energy products sales", "kbd",
            semantic_category="ENERGY_PRODUCTS_SALES_VOLUME",
        ),
        MetricSpec(
            "chemicals_product_sales", r"chemical products sales", "kt",
            semantic_category="CHEMICAL_PRODUCTS_SALES_VOLUME",
        ),
    ),
    "CVX": (
        MetricSpec(
            "upstream_total_boe", r"^net oil-equivalent production$", "mboed",
            semantic_category="TOTAL_OIL_EQUIVALENT_PRODUCTION_VOLUME",
        ),
        MetricSpec(
            "downstream_throughput", r"^refinery crude unit inputs$", "mbd", "sum",
            semantic_category="REFINERY_CRUDE_INPUT_VOLUME",
        ),
        MetricSpec(
            "downstream_product_sales", r"^refined product sales$", "mbd", "sum",
            semantic_category="REFINED_PRODUCTS_SALES_VOLUME",
        ),
    ),
    "VLO": (
        MetricSpec(
            "company_throughput", r"^total throughput volumes$", "mbpd",
            semantic_category="TOTAL_REFINERY_THROUGHPUT_VOLUME",
        ),
    ),
    "MPC": (
        MetricSpec(
            "company_throughput",
            r"^(crude oil refined|other charge and blendstocks)$",
            "mbpd",
            "adjacent_pair_sum_max",
            semantic_category="TOTAL_REFINERY_THROUGHPUT_VOLUME",
        ),
        MetricSpec(
            "company_utilization", r"^crude oil capacity utilization", "pct",
            semantic_category="CRUDE_CAPACITY_UTILIZATION",
        ),
    ),
    "PSX": (
        MetricSpec(
            "company_throughput",
            r"^crude oil charge input",
            "mbd",
            "max",
            "reported_quarter_index",
            semantic_category="CRUDE_CHARGE_INPUT_VOLUME",
        ),
        MetricSpec(
            "company_utilization",
            r"^crude oil capacity utilization",
            "pct",
            "max",
            "reported_quarter_index",
            semantic_category="CRUDE_CAPACITY_UTILIZATION",
        ),
    ),
    "KMI": (
        MetricSpec(
            "gas_transport_volume", r"^transport volumes", "bbtu_d",
            semantic_category="NATURAL_GAS_TRANSPORT_VOLUME",
        ),
        MetricSpec(
            "gas_gathering_volume", r"^gathering volumes", "bbtu_d",
            semantic_category="NATURAL_GAS_GATHERING_VOLUME",
        ),
    ),
    "WMB": (
        MetricSpec(
            "gas_transport_volume",
            r"^avg\. daily transportation volumes",
            "mmdth",
            "sum",
            "current_year_after_prior_year",
            semantic_category="NATURAL_GAS_TRANSPORT_VOLUME",
        ),
        MetricSpec(
            "gas_gathering_volume",
            r"^gathering volumes \(bcf/d\)",
            "bcf_d",
            "sum",
            "current_year_after_prior_year",
            semantic_category="NATURAL_GAS_GATHERING_VOLUME",
        ),
    ),
    "ET": (
        MetricSpec(
            "gas_transport_volume", r"^natural gas transported", "bbtu_d", "sum",
            semantic_category="NATURAL_GAS_TRANSPORT_VOLUME",
        ),
        MetricSpec(
            "gas_gathering_volume", r"^gathered volumes", "bbtu_d", "sum",
            semantic_category="NATURAL_GAS_GATHERING_VOLUME",
        ),
        MetricSpec(
            "liquids_transport_volume",
            r"^(ngl|crude(?: oil)?) transportation volumes",
            "mbbls_d",
            "sum",
            semantic_category="COMBINED_NGL_AND_CRUDE_TRANSPORT_VOLUME",
        ),
    ),
    "EPD": (
        MetricSpec(
            "equivalent_pipeline_volume",
            r"^equivalent pipeline transportation volumes",
            "mbpd",
            semantic_category="EQUIVALENT_PIPELINE_TRANSPORT_VOLUME",
        ),
        MetricSpec(
            "fee_gas_processing_volume",
            r"^fee-based natural gas processing volumes",
            "bcf_d",
            semantic_category="FEE_BASED_GAS_PROCESSING_VOLUME",
        ),
    ),
    "SLB": (
        MetricSpec(
            "international_activity",
            r"^international(?: revenue)?$",
            "usd_million",
            candidate_selection="all_tables",
            semantic_category="GEOGRAPHIC_REVENUE",
            required_context_pattern=r"three months ended",
        ),
        MetricSpec(
            "north_america_activity",
            r"^north america(?: revenue)?\*?$",
            "usd_million",
            candidate_selection="all_tables",
            semantic_category="GEOGRAPHIC_REVENUE",
            required_context_pattern=r"three months ended",
        ),
    ),
    "HAL": (
        MetricSpec(
            "completion_production_activity",
            r"^completion and production$",
            "usd_million",
            candidate_selection="all_tables",
            semantic_category="SEGMENT_REVENUE",
            required_context_pattern=r"three months ended",
        ),
        MetricSpec(
            "north_america_activity",
            r"^north america$",
            "usd_million",
            candidate_selection="all_tables",
            semantic_category="GEOGRAPHIC_REVENUE",
            required_context_pattern=r"three months ended",
        ),
    ),
    "BKR": (
        MetricSpec(
            "orders_activity",
            r"^(total )?orders$",
            "usd_million",
            candidate_selection="all_tables",
            semantic_category="COMPANY_ORDERS",
            required_context_pattern=r"three months ended",
        ),
        MetricSpec(
            "international_activity",
            r"^international$",
            "usd_million",
            candidate_selection="all_tables",
            semantic_category="GEOGRAPHIC_REVENUE",
            required_context_pattern=r"three months ended",
        ),
    ),
}

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


_NUMERIC = re.compile(r"^[-+]?\$?\d[\d,]*(?:\.\d+)?%?$")


def _number(value: str) -> float | None:
    normalized = value.replace("\xa0", " ").strip().replace(" ", "")
    negative = normalized.startswith("(") and (
        normalized.endswith(")") or normalized.endswith(")%")
    )
    normalized = normalized.replace("(", "").replace(")", "")
    if not _NUMERIC.match(normalized):
        return None
    normalized = normalized.replace("$", "").replace(",", "")
    normalized = normalized.rstrip("%")
    try:
        number = float(normalized)
    except ValueError:
        return None
    return -number if negative else number


def _table_rows(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    output: list[dict[str, object]] = []
    seen: set[tuple[str, tuple[float, ...]]] = set()
    for table_index, table in enumerate(soup.find_all("table")):
        context_rows: list[str] = []
        for context_tr in table.find_all("tr", recursive=False)[:4]:
            context = re.sub(
                r"\s+", " ", context_tr.get_text(" | ", strip=True)
            ).strip()
            if context:
                context_rows.append(context)
        table_context = " || ".join(context_rows)[:2_000]
        for row_index, tr in enumerate(table.find_all("tr")):
            cells = tr.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            tokens = [
                re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
                for cell in cells
            ]
            tokens = [token for token in tokens if token]
            values = tuple(
                number for token in tokens if (number := _number(token)) is not None
            )
            text = " | ".join(tokens)
            key = (text.lower(), values)
            if not values or key in seen:
                continue
            seen.add(key)
            output.append(
                {
                    "table_index": table_index,
                    "row_index": row_index,
                    "tokens": tokens,
                    "values": values,
                    "row_text": text,
                    "table_context": table_context,
                }
            )
    return output


def _label_matches(row: dict[str, object], pattern: str) -> bool:
    tokens = row["tokens"]
    return any(re.search(pattern, str(token), flags=re.IGNORECASE) for token in tokens)


def _current_value(
    row: dict[str, object],
    report_quarter: str,
    mode: str,
) -> float | None:
    values = tuple(float(value) for value in row["values"])
    quarter = pd.Period(report_quarter, freq="Q").quarter
    if not values:
        return None
    if mode == "reported_quarter_index":
        index = quarter - 1
    elif mode == "current_year_after_prior_year":
        index = quarter + 4
    else:
        index = 0
    if index >= len(values):
        return None
    value = values[index]
    return value if np.isfinite(value) and value > 0 else None


def _normalize_metric_value(spec: MetricSpec, row_text: str, value: float) -> float:
    """Normalize company presentation changes into the declared metric unit."""
    if spec.unit == "bcf_d" and re.search(r"mmcf/d", row_text, flags=re.IGNORECASE):
        return value / 1_000.0
    return value


def _extract_filing_metrics(
    ticker: str,
    filing: dict[str, object],
    documents: list[dict[str, str]],
) -> list[dict[str, object]]:
    report_quarter = str(filing["report_quarter"])
    candidates: dict[str, list[dict[str, object]]] = {
        spec.metric_id: [] for spec in KPI_SPECS[ticker]
    }
    for document in documents:
        rows = _table_rows(document["html"])
        for spec in KPI_SPECS[ticker]:
            for row in rows:
                if not _label_matches(row, spec.label_pattern):
                    continue
                if spec.required_context_pattern and not re.search(
                    spec.required_context_pattern,
                    str(row["table_context"]),
                    flags=re.IGNORECASE,
                ):
                    continue
                value = _current_value(row, report_quarter, spec.current_mode)
                if value is None:
                    continue
                value = _normalize_metric_value(spec, str(row["row_text"]), value)
                candidates[spec.metric_id].append(
                    {
                        "value": value,
                        "row_text": row["row_text"],
                        "table_index": row["table_index"],
                        "row_index": row["row_index"],
                        "table_context": row["table_context"],
                        "numeric_token_count": len(row["values"]),
                        "source_url": document["source_url"],
                        "source_description": document["description"],
                    }
                )
    output: list[dict[str, object]] = []
    for spec in KPI_SPECS[ticker]:
        values = candidates[spec.metric_id]
        if not values:
            continue
        # Nested SEC tables can repeat an identical logical row.  De-duplicate
        # those repetitions before company-level aggregation.
        unique: dict[tuple[str, float], dict[str, object]] = {}
        for item in values:
            key = (str(item["row_text"]).lower(), round(float(item["value"]), 8))
            unique[key] = item
        values = list(unique.values())
        if spec.candidate_selection == "max_numeric_tokens":
            maximum_tokens = max(int(item["numeric_token_count"]) for item in values)
            values = [
                item
                for item in values
                if int(item["numeric_token_count"]) == maximum_tokens
            ]
        elif spec.candidate_selection == "company_total_quarter":
            maximum_tokens = max(int(item["numeric_token_count"]) for item in values)
            minimum_tokens = max(3, maximum_tokens - 1)
            values = [
                item
                for item in values
                if int(item["numeric_token_count"]) >= minimum_tokens
            ]
        if spec.aggregation == "adjacent_pair_sum_max":
            pairs: list[tuple[float, list[dict[str, object]]]] = []
            for left in values:
                left_text = str(left["row_text"]).lower()
                if not left_text.startswith("crude oil refined"):
                    continue
                for right in values:
                    right_text = str(right["row_text"]).lower()
                    same_location = (
                        left["source_url"] == right["source_url"]
                        and left["table_index"] == right["table_index"]
                        and abs(int(left["row_index"]) - int(right["row_index"])) <= 3
                    )
                    if not same_location or not right_text.startswith(
                        "other charge and blendstocks"
                    ):
                        continue
                    pairs.append(
                        (
                            float(left["value"]) + float(right["value"]),
                            [left, right],
                        )
                    )
            if not pairs:
                continue
            metric_value, selected = max(pairs, key=lambda item: item[0])
        elif spec.aggregation == "sum":
            metric_value = float(sum(float(item["value"]) for item in values))
            selected = values
        elif spec.aggregation == "first":
            metric_value = float(values[0]["value"])
            selected = [values[0]]
        else:
            chosen = max(values, key=lambda item: float(item["value"]))
            metric_value = float(chosen["value"])
            selected = [chosen]
        filing_date = pd.Timestamp(str(filing["filingDate"])).normalize()
        available_at, availability_source = _filing_availability(filing)
        output.append(
            {
                "ticker": ticker,
                "report_quarter": report_quarter,
                "metric_id": spec.metric_id,
                "metric_value": metric_value,
                "metric_unit": spec.unit,
                "filing_date": filing_date,
                "acceptance_datetime_utc": (
                    filing.get("acceptanceDateTime") or pd.NA
                ),
                "ir_publication_datetime_utc": pd.NA,
                "available_at": available_at,
                "availability_source": availability_source,
                "form": "8-K",
                "source_type": "SEC_8K_EARNINGS_EXHIBIT",
                "source_url": ";".join(sorted({str(item["source_url"]) for item in selected})),
                "source_description": ";".join(
                    sorted({str(item["source_description"]) for item in selected})
                ),
                "source_row_text": " || ".join(str(item["row_text"]) for item in selected),
                "source_table_context": " || ".join(
                    str(item["table_context"]) for item in selected
                ),
                "source_table_indices": ",".join(
                    str(item["table_index"]) for item in selected
                ),
                "source_row_indices": ",".join(
                    str(item["row_index"]) for item in selected
                ),
                "value_selection_rule": (
                    f"{spec.candidate_selection}:{spec.aggregation}:"
                    f"{spec.current_mode}:context="
                    f"{spec.required_context_pattern or 'none'}"
                ),
                "reported_period_basis": "THREE_MONTHS",
                "semantic_category": spec.semantic_category,
                "parser_rule_confidence": (
                    0.95
                    if (
                        spec.candidate_selection != "all_tables"
                        or spec.required_context_pattern
                    )
                    else (0.90 if len(selected) == 1 else 0.85)
                ),
                # Retained for downstream compatibility.  This is a rule
                # confidence, not a claim of externally verified accuracy.
                "quality_score": (
                    0.95
                    if (
                        spec.candidate_selection != "all_tables"
                        or spec.required_context_pattern
                    )
                    else (0.90 if len(selected) == 1 else 0.85)
                ),
                "accession": str(filing["accessionNumber"]),
            }
        )
    return output


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
