from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from lxml import html as lxml_html

from .taxonomy import all_tickers, group_for_ticker


ACTUAL_COLUMNS = [
    "ticker", "quarter", "oil_mbpd", "ngl_mbpd", "gas_mmcfd", "total_mboed",
    "raw_total_value", "raw_total_unit", "normalized_total_unit", "conversion_rule",
    "filing_date", "source_url", "source_path", "quality_score", "mna_flag", "adapter",
]
GUIDANCE_COLUMNS = [
    "ticker", "target_quarter", "oil_mbpd_low", "oil_mbpd_high", "oil_mbpd_mid",
    "ngl_mbpd_low", "ngl_mbpd_high", "ngl_mbpd_mid", "gas_mmcfd_low",
    "gas_mmcfd_high", "gas_mmcfd_mid", "total_mboed_low", "total_mboed_high",
    "total_mboed_mid", "raw_total_mid", "raw_total_unit", "normalized_total_unit",
    "conversion_rule", "period_semantics", "filing_date", "source_url", "source_path",
    "quality_score", "adapter",
]
PRICE_COLUMNS = [
    "ticker", "quarter", "realized_oil_price", "realized_ngl_price",
    "realized_gas_price", "hedge_included", "filing_date", "source_url",
    "source_path", "quality_score", "adapter",
]


@dataclass(frozen=True)
class CompanyAdapterSpec:
    ticker: str
    parser_family: str
    actual_source_policy: str
    guidance_source_policy: str
    realized_price_source_policy: str
    local_operational_source_available: bool = True


COMPANY_ADAPTERS = {
    "EOG": CompanyAdapterSpec("EOG", "EOG_COMPONENT_V327", "VALIDATED_CSV", "VALIDATED_CSV", "IR_TABLE"),
    "FANG": CompanyAdapterSpec("FANG", "FANG_SELECTED_V321", "VALIDATED_CSV", "VALIDATED_CSV", "IR_TABLE"),
    "PR": CompanyAdapterSpec("PR", "PR_IR_TABLE_V1", "IR_TABLE", "IR_TABLE", "IR_TABLE"),
    "MTDR": CompanyAdapterSpec("MTDR", "MTDR_IR_TABLE_V1", "IR_TABLE", "IR_TABLE", "IR_TABLE"),
    "MGY": CompanyAdapterSpec("MGY", "MGY_IR_TABLE_V1", "IR_TABLE", "IR_TABLE", "IR_TABLE"),
    "NOG": CompanyAdapterSpec("NOG", "NOG_IR_TABLE_V1", "IR_TABLE", "IR_TABLE", "IR_TABLE"),
    "EQT": CompanyAdapterSpec("EQT", "EQT_IR_TABLE_V1", "IR_TABLE", "IR_TABLE", "IR_TABLE"),
    "AR": CompanyAdapterSpec("AR", "AR_NET_PRODUCTION_V1", "IR_TABLE_SPECIAL", "IR_TABLE", "IR_TABLE"),
    "RRC": CompanyAdapterSpec("RRC", "RRC_MCFE_V1", "IR_TABLE_SPECIAL", "IR_TABLE", "IR_TABLE"),
    "CNX": CompanyAdapterSpec("CNX", "CNX_MCFE_V1", "IR_TABLE_SPECIAL", "IR_TABLE", "IR_TABLE"),
    "COP": CompanyAdapterSpec("COP", "COP_SELECTED_V321", "VALIDATED_CSV", "VALIDATED_CSV", "IR_TABLE"),
    "DVN": CompanyAdapterSpec("DVN", "DVN_SELECTED_V321", "VALIDATED_CSV", "VALIDATED_CSV", "IR_TABLE"),
    "OVV": CompanyAdapterSpec(
        "OVV", "OVV_MISSING_LOCAL_SOURCE", "MISSING", "MISSING", "MISSING", False
    ),
    "SM": CompanyAdapterSpec("SM", "SM_MBOE_PER_DAY_V1", "IR_TABLE_SPECIAL", "IR_TABLE", "IR_TABLE"),
}


def adapter_registry_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ticker": spec.ticker,
            "group": group_for_ticker(spec.ticker),
            "parser_family": spec.parser_family,
            "actual_source_policy": spec.actual_source_policy,
            "guidance_source_policy": spec.guidance_source_policy,
            "realized_price_source_policy": spec.realized_price_source_policy,
            "local_operational_source_available": spec.local_operational_source_available,
        }
        for spec in COMPANY_ADAPTERS.values()
    ])


def _clean_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    return text.replace("–", "-").replace("—", "-").replace("−", "-")


def _collapse(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = _clean_text(value)
        if not clean or clean.lower() == "nan":
            continue
        if not result or result[-1] != clean:
            result.append(clean)
    return result


def _table_rows(path: Path) -> list[list[list[str]]]:
    raw = path.read_bytes()
    try:
        document = lxml_html.fromstring(raw)
    except (ValueError, TypeError):
        return []
    tables: list[list[list[str]]] = []
    for table in document.xpath(".//table"):
        rows: list[list[str]] = []
        for row in table.xpath(".//tr"):
            values = _collapse(
                " ".join(cell.text_content().split())
                for cell in row.xpath("./th|./td")
            )
            if values:
                rows.append(values)
        if rows:
            tables.append(rows)
    return tables


NUMBER = re.compile(r"(?<![A-Za-z])\(?\s*\$?\s*(-?\d[\d,]*(?:\.\d+)?)\s*\)?")


def _numbers(values: Iterable[str]) -> list[float]:
    result: list[float] = []
    for value in values:
        for match in NUMBER.finditer(value):
            raw = match.group(0)
            number = float(match.group(1).replace(",", ""))
            if "(" in raw and ")" in raw and not match.group(1).startswith("-"):
                number = -number
            result.append(number)
    return result


def _midpoint(values: Iterable[str]) -> float:
    numbers = _numbers(values)
    if not numbers:
        return float("nan")
    if len(numbers) >= 2:
        return float((numbers[0] + numbers[1]) / 2.0)
    return float(numbers[0])


def _range(values: Iterable[str]) -> tuple[float, float, float]:
    numbers = _numbers(values)
    if not numbers:
        return np.nan, np.nan, np.nan
    if len(numbers) == 1:
        return numbers[0], numbers[0], numbers[0]
    low, high = sorted(numbers[:2])
    return low, high, (low + high) / 2.0


def _guidance_scale_sanity(value: float, metric: str) -> float:
    """Normalize common BOE/day and Bbl/day guidance into thousands/day.

    IR tables frequently omit the unit from the row itself and put it in a
    spanning header. Values above these physical upper bounds are the raw
    BOE/day, Bbl/day, or Mcf/day representation of the same KPI.
    """
    if not np.isfinite(value):
        return value
    if metric in {"total", "oil", "ngl"} and abs(value) > 5000.0:
        return value / 1000.0
    if metric == "gas" and abs(value) > 30000.0:
        return value / 1000.0
    return value


def _unit_and_conversion(label: str, metric: str, value: float) -> tuple[str, str]:
    compact = label.lower().replace(" ", "")
    if metric == "total":
        if "bcfe" in compact:
            return "BCFE", "BCFE_TO_MBOE_PER_DAY_X1000_DIV_DAYS_DIV_6"
        if "mmcfe/d" in compact or "averagedailyproduction(mmcfe" in compact:
            return "MMCFE/D", "MMCFE_PER_DAY_TO_MBOE_PER_DAY_DIV_6"
        if "mmcfe" in compact:
            return "MMCFE", "MMCFE_TO_MBOE_PER_DAY_DIV_DAYS_DIV_6"
        if "mcfeperday" in compact:
            return "MCFE/D", "MCFE_PER_DAY_TO_MBOE_PER_DAY_DIV_6000"
        if "mcfe" in compact:
            return "MCFE", "MCFE_TO_MBOE_PER_DAY_DIV_DAYS_DIV_6000"
        if "boe/d" in compact and "mboe/d" not in compact:
            return "BOE/D", "BOE_PER_DAY_TO_MBOE_PER_DAY_DIV_1000"
        if "mboe/d" in compact or "mboed" in compact or "mboeperday" in compact:
            return "MBOE/D", "IDENTITY"
        if "mboe" in compact:
            return "MBOE", "MBOE_TO_MBOE_PER_DAY_DIV_DAYS"
        if abs(value) > 5000.0:
            return "BOE/D_INFERRED", "BOE_PER_DAY_TO_MBOE_PER_DAY_DIV_1000_SANITY"
    return "UNRESOLVED", "IDENTITY_UNRESOLVED_UNIT"


def _guidance_period_semantics(table_text: str) -> str:
    text = table_text.lower()
    has_quarter = bool(re.search(
        r"\bq[1-4]\b|\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\b|\bquarterly\b",
        text,
    ))
    has_annual = any(marker in text for marker in (
        "full year", "full-year", "fiscal year", "year ended", "annual guidance",
    ))
    if has_quarter and has_annual:
        return "MIXED_PERIOD_TABLE"
    if has_quarter:
        return "QUARTERLY_EXPLICIT"
    if has_annual:
        return "ANNUAL"
    return "UNRESOLVED"


def _days_in_quarter(quarter: str) -> int:
    period = pd.Period(quarter, freq="Q")
    return int((period.end_time.normalize() - period.start_time.normalize()).days + 1)


def _daily_value(value: float, label: str, metric: str, quarter: str) -> float:
    lower = label.lower().replace(" ", "")
    days = _days_in_quarter(quarter)
    if metric == "total":
        if "perday" in lower and "mcfe" in lower:
            return value / (6.0 if "mmcfe" in lower else 6000.0)
        if "mmcfe/d" in lower or "averagedailyproduction(mmcfe" in lower:
            return value / 6.0
        if "mmcfe" in lower:
            return value / days / 6.0
        if "mcfeperday" in lower:
            return value / 6000.0
        if "mcfe" in lower:
            return value / days / 6000.0
        if "bcfe" in lower:
            return value * 1000.0 / days / 6.0
        if "mboe/d" in lower or "mboed" in lower or "mboeperday" in lower:
            return value
        if "boe/d" in lower:
            return value / 1000.0
        if "mboe" in lower:
            return value / days
    if metric in {"oil", "ngl"}:
        if "perday" in lower and "bbl" in lower:
            return value if "mbbl" in lower else value / 1000.0
        if any(unit in lower for unit in ("mbbl/d", "mbbld", "mbo/d", "mbblperday", "mbbls/d")):
            return value
        if "bbl/d" in lower or "bo/d" in lower:
            return value / 1000.0
        if "mbbl" in lower:
            return value / days
    if metric == "gas":
        if "perday" in lower and "mcf" in lower:
            return value if "mmcf" in lower else value / 1000.0
        if "mmcf/d" in lower or "mmcfd" in lower:
            return value
        if "bcf" in lower:
            return value * 1000.0 / days
        if "mmcf" in lower:
            return value / days
    return value


def _metadata(path: Path) -> dict[str, object]:
    metadata_path = Path(str(path) + ".metadata.json")
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    return {}


def _release_date(path: Path, metadata: dict[str, object]) -> pd.Timestamp:
    value = metadata.get("filing_date") or path.name[:10]
    return pd.Timestamp(value)


def _source_url(path: Path, metadata: dict[str, object]) -> str:
    return str(metadata.get("source_url") or path)


def _actual_quarter(release_date: pd.Timestamp) -> str:
    return str(release_date.to_period("Q") - 1)


def _direct_metric(label: str) -> str | None:
    compact = label.lower().replace(" ", "")
    if any(pattern in compact for pattern in (
        "dailycombinedvolumes", "totalproduction", "totaloilequivalent",
        "dailycombinedproduction", "combinedvolumes", "totalsalesvolume",
        "productionvolume(bcfe", "productionvolumes(mboe", "averagedailyproduction",
        "total(mboe", "equivalent(mboeperday", "gasequivalent(mcfe",
    )):
        return "total"
    if any(pattern in compact for pattern in (
        "dailyoilvolumes", "oilproduction", "oil(mbbl", "oil(bbl/d",
        "oil(mbblperday", "oil(mbbls/d",
        "crudeoilproduction", "condensateproduction",
    )):
        return "oil"
    if any(pattern in compact for pattern in (
        "naturalgasliquids(mbbl", "nglproduction", "ngl(mbbl",
        "naturalgasliquidsproduction",
    )):
        return "ngl"
    if any(pattern in compact for pattern in (
        "naturalgas(mmcf", "naturalgasproduction", "gasproduction(mmcf",
        "dailygasvolumes",
    )):
        return "gas"
    return None


def _price_metric(label: str) -> str | None:
    lower = label.lower()
    if any(excluded in lower for excluded in ("benchmark", "west texas", "henry hub", "mont belvieu")):
        return None
    if "price" not in lower:
        return None
    if "ngl" in lower or "natural gas liquid" in lower:
        return "ngl"
    if "natural gas" in lower or "per mcf" in lower or "per mcfe" in lower:
        return "gas"
    if "oil" in lower or "crude" in lower or "per bbl" in lower:
        return "oil"
    return None


def _extract_actual_from_file(
    ticker: str,
    path: Path,
    tables: list[list[list[str]]] | None = None,
    metadata: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    metadata = metadata or _metadata(path)
    filing_date = _release_date(path, metadata)
    quarter = _actual_quarter(filing_date)
    production: dict[str, float] = {key: np.nan for key in ("oil", "ngl", "gas", "total")}
    raw_total_value = np.nan
    raw_total_unit = "UNRESOLVED"
    conversion_rule = "NO_TOTAL_ROW"
    prices: dict[str, float] = {key: np.nan for key in ("oil", "ngl", "gas")}
    for rows in tables if tables is not None else _table_rows(path):
        table_text = " ".join(" ".join(row) for row in rows).lower()
        actual_table = any(marker in table_text for marker in (
            "three months ended", "selected operating data", "volumes and prices",
            "production data", "production volumes", "net production", "average daily production",
            "average sales prices",
        ))
        if not actual_table:
            continue
        section: str | None = None
        daily_section = False
        for row in rows:
            label = row[0]
            lower = label.lower()
            if "average per day" in lower or "average daily" in lower:
                daily_section = True
            elif "during the period" in lower or lower.endswith("volumes:"):
                daily_section = False
            if ticker == "AR" and lower == "average net production" and len(_numbers(row[1:])) >= 5:
                values = _numbers(row[1:])
                production["gas"] = values[0]
                production["oil"] = values[1] / 1000.0
                production["ngl"] = (values[2] + values[3]) / 1000.0
                production["total"] = values[4] / 6.0
                raw_total_value = values[4]
                raw_total_unit = "MMCFE/D"
                conversion_rule = "MMCFE_PER_DAY_TO_MBOE_PER_DAY_DIV_6"
                continue
            if "crude oil" in lower and "volume" in lower:
                section = "oil"
            elif ("natural gas liquids" in lower or "ngl" in lower) and "volume" in lower:
                section = "ngl"
            elif "natural gas" in lower and "volume" in lower:
                section = "gas"
            elif ("oil equivalent" in lower or "total production" in lower) and "volume" in lower:
                section = "total"
            metric = _direct_metric(label)
            values = _numbers(row[1:])
            if metric and values and not np.isfinite(production[metric]):
                unit_label = label + (" per day" if daily_section else "")
                production[metric] = _daily_value(values[0], unit_label, metric, quarter)
                if metric == "total":
                    raw_total_value = values[0]
                    raw_total_unit, conversion_rule = _unit_and_conversion(
                        unit_label, metric, values[0]
                    )
            elif section and lower in {"total", "composite"} and values and not np.isfinite(production[section]):
                production[section] = _daily_value(values[0], label, section, quarter)
                if section == "total":
                    raw_total_value = values[0]
                    raw_total_unit, conversion_rule = _unit_and_conversion(
                        label, section, values[0]
                    )
            price_metric = _price_metric(label)
            if price_metric and values and not np.isfinite(prices[price_metric]):
                prices[price_metric] = values[0]
    if not np.isfinite(production["total"]):
        components = production["oil"] + production["ngl"] + production["gas"] / 6.0
        if sum(np.isfinite(production[key]) for key in ("oil", "ngl", "gas")) >= 2 and np.isfinite(components):
            production["total"] = components
            raw_total_unit = "DERIVED_COMPONENTS"
            conversion_rule = "OIL_PLUS_NGL_PLUS_GAS_DIV_6"
    source_url = _source_url(path, metadata)
    completeness = sum(np.isfinite(production[key]) for key in production)
    actual = None
    if np.isfinite(production["total"]) and 1.0 <= production["total"] <= 5000.0:
        actual = {
            "ticker": ticker,
            "quarter": quarter,
            "oil_mbpd": production["oil"],
            "ngl_mbpd": production["ngl"],
            "gas_mmcfd": production["gas"],
            "total_mboed": production["total"],
            "raw_total_value": raw_total_value,
            "raw_total_unit": raw_total_unit,
            "normalized_total_unit": "MBOE/D",
            "conversion_rule": conversion_rule,
            "filing_date": filing_date,
            "source_url": source_url,
            "source_path": str(path),
            "quality_score": min(0.55 + 0.10 * completeness, 0.95),
            "mna_flag": False,
            "adapter": f"{ticker}_IR_TABLE_V1",
        }
    price_row = None
    if any(np.isfinite(value) for value in prices.values()):
        price_row = {
            "ticker": ticker,
            "quarter": quarter,
            "realized_oil_price": prices["oil"],
            "realized_ngl_price": prices["ngl"],
            "realized_gas_price": prices["gas"],
            "hedge_included": False,
            "filing_date": filing_date,
            "source_url": source_url,
            "source_path": str(path),
            "quality_score": min(0.50 + 0.12 * sum(np.isfinite(v) for v in prices.values()), 0.90),
            "adapter": f"{ticker}_IR_TABLE_V1",
        }
    return actual, price_row


def _extract_guidance_from_file(
    ticker: str,
    path: Path,
    tables: list[list[list[str]]] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object] | None:
    metadata = metadata or _metadata(path)
    filing_date = _release_date(path, metadata)
    target = str(filing_date.to_period("Q"))
    candidates: list[tuple[int, str, dict[str, tuple[float, float, float]], dict[str, str]]] = []
    semantic_priority = {
        "QUARTERLY_EXPLICIT": 3,
        "MIXED_PERIOD_TABLE": 2,
        "ANNUAL": 1,
        "UNRESOLVED": 0,
    }
    for rows in tables if tables is not None else _table_rows(path):
        table_text = " ".join(" ".join(row) for row in rows).lower()
        if "guidance" not in table_text:
            continue
        semantics = _guidance_period_semantics(table_text)
        metrics: dict[str, tuple[float, float, float]] = {
            key: (np.nan, np.nan, np.nan) for key in ("oil", "ngl", "gas", "total")
        }
        labels: dict[str, str] = {}
        for row in rows:
            label = row[0]
            lower = label.lower()
            metric = _direct_metric(label)
            if metric is None or not _numbers(row[1:]):
                continue
            values = _range(row[1:])
            if "oil production" in lower and "total" in lower:
                all_values = _numbers(row[1:])
                if len(all_values) >= 4:
                    metrics["oil"] = tuple([*sorted(all_values[:2]), sum(all_values[:2]) / 2.0])
                    metrics["total"] = tuple([*sorted(all_values[2:4]), sum(all_values[2:4]) / 2.0])
                    labels["oil"] = label
                    labels["total"] = label
                    continue
            if not np.isfinite(metrics[metric][2]):
                metrics[metric] = values
                labels[metric] = label
        if any(np.isfinite(values[2]) for values in metrics.values()):
            candidates.append((semantic_priority[semantics], semantics, metrics, labels))
    if not candidates:
        return None
    _, period_semantics, metrics, labels = max(candidates, key=lambda item: item[0])
    quality = 0.85 if period_semantics == "QUARTERLY_EXPLICIT" else 0.60
    result: dict[str, object] = {
        "ticker": ticker,
        "target_quarter": target,
        "period_semantics": period_semantics,
        "filing_date": filing_date,
        "source_url": _source_url(path, metadata),
        "source_path": str(path),
        "quality_score": quality,
        "adapter": f"{ticker}_IR_GUIDANCE_V1",
    }
    for metric, (low, high, mid) in metrics.items():
        raw_label = labels.get(metric, "")
        normalized = tuple(
            _guidance_scale_sanity(
                _daily_value(
                    value,
                    raw_label,
                    metric,
                    target,
                ),
                metric,
            )
            if np.isfinite(value) else np.nan
            for value in (low, high, mid)
        )
        result[f"{metric}_mboed_low" if metric == "total" else f"{metric}_mbpd_low" if metric in {"oil", "ngl"} else "gas_mmcfd_low"] = normalized[0]
        result[f"{metric}_mboed_high" if metric == "total" else f"{metric}_mbpd_high" if metric in {"oil", "ngl"} else "gas_mmcfd_high"] = normalized[1]
        result[f"{metric}_mboed_mid" if metric == "total" else f"{metric}_mbpd_mid" if metric in {"oil", "ngl"} else "gas_mmcfd_mid"] = normalized[2]
    raw_total_mid = metrics["total"][2]
    raw_unit, conversion_rule = _unit_and_conversion(
        labels.get("total", ""), "total", raw_total_mid
    ) if np.isfinite(raw_total_mid) else ("UNRESOLVED", "NO_TOTAL_GUIDANCE")
    result.update({
        "raw_total_mid": raw_total_mid,
        "raw_total_unit": raw_unit,
        "normalized_total_unit": "MBOE/D",
        "conversion_rule": conversion_rule,
    })
    return result


def _legacy_actuals(data_lake: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    eog = pd.read_csv(data_lake / "energy_v3_2_7_actual_EOG.csv")
    rows.append(pd.DataFrame({
        "ticker": "EOG", "quarter": eog["quarter"].astype(str),
        "oil_mbpd": eog["oil_production"], "ngl_mbpd": eog["ngl_production"],
        "gas_mmcfd": eog["gas_production"], "total_mboed": eog["total_production"],
        "raw_total_value": eog["total_production"], "raw_total_unit": "MBOE/D",
        "normalized_total_unit": "MBOE/D", "conversion_rule": "IDENTITY_VALIDATED",
        "filing_date": pd.to_datetime(eog["release_date"]), "source_url": eog["source_url"],
        "source_path": str(data_lake / "energy_v3_2_7_actual_EOG.csv"),
        "quality_score": eog["data_quality_score"], "mna_flag": False,
        "adapter": "EOG_VALIDATED_COMPONENT_V327",
    }))
    for ticker in ("COP", "FANG", "DVN"):
        path = data_lake / f"energy_v3_2_1_actual_selected_{ticker}.csv"
        source = pd.read_csv(path)
        rows.append(pd.DataFrame({
            "ticker": ticker, "quarter": source["quarter"].astype(str),
            "oil_mbpd": source["oil_production"], "ngl_mbpd": np.nan,
            "gas_mmcfd": np.nan, "total_mboed": source["total_production"],
            "raw_total_value": source["total_production"], "raw_total_unit": "MBOE/D",
            "normalized_total_unit": "MBOE/D", "conversion_rule": "IDENTITY_VALIDATED",
            "filing_date": pd.to_datetime(source["filing_date"]), "source_url": source["source"],
            "source_path": str(path), "quality_score": np.where(source["total_production"].notna(), 0.90, 0.65),
            "mna_flag": False, "adapter": f"{ticker}_VALIDATED_V321",
        }))
    return pd.concat(rows, ignore_index=True)[ACTUAL_COLUMNS]


def _legacy_guidance(data_lake: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    eog = pd.read_csv(data_lake / "energy_v3_2_7_guidance_EOG.csv")
    rows.append(pd.DataFrame({
        "ticker": "EOG", "target_quarter": eog["target_quarter"].astype(str),
        "oil_mbpd_low": eog["guidance_oil_production"], "oil_mbpd_high": eog["guidance_oil_production"], "oil_mbpd_mid": eog["guidance_oil_production"],
        "ngl_mbpd_low": eog["guidance_ngl_production"], "ngl_mbpd_high": eog["guidance_ngl_production"], "ngl_mbpd_mid": eog["guidance_ngl_production"],
        "gas_mmcfd_low": eog["guidance_gas_production"], "gas_mmcfd_high": eog["guidance_gas_production"], "gas_mmcfd_mid": eog["guidance_gas_production"],
        "total_mboed_low": eog["guidance_total_production"], "total_mboed_high": eog["guidance_total_production"], "total_mboed_mid": eog["guidance_total_production"],
        "raw_total_mid": eog["guidance_total_production"], "raw_total_unit": "MBOE/D",
        "normalized_total_unit": "MBOE/D", "conversion_rule": "IDENTITY_VALIDATED",
        "period_semantics": "QUARTERLY_VALIDATED",
        "filing_date": pd.to_datetime(eog["release_date"]), "source_url": eog["source_url"],
        "source_path": str(data_lake / "energy_v3_2_7_guidance_EOG.csv"),
        "quality_score": eog["guidance_data_quality_score"], "adapter": "EOG_VALIDATED_GUIDANCE_V327",
    }))
    for ticker in ("COP", "FANG", "DVN"):
        path = data_lake / f"energy_v3_2_1_guidance_selected_{ticker}.csv"
        source = pd.read_csv(path)
        total = source["guidance_total_production"]
        oil = source["guidance_oil_production"]
        rows.append(pd.DataFrame({
            "ticker": ticker, "target_quarter": source["target_quarter"].astype(str),
            "oil_mbpd_low": oil, "oil_mbpd_high": oil, "oil_mbpd_mid": oil,
            "ngl_mbpd_low": np.nan, "ngl_mbpd_high": np.nan, "ngl_mbpd_mid": np.nan,
            "gas_mmcfd_low": np.nan, "gas_mmcfd_high": np.nan, "gas_mmcfd_mid": np.nan,
            "total_mboed_low": total, "total_mboed_high": total, "total_mboed_mid": total,
            "raw_total_mid": total, "raw_total_unit": "MBOE/D",
            "normalized_total_unit": "MBOE/D", "conversion_rule": "IDENTITY_VALIDATED",
            "period_semantics": "QUARTERLY_VALIDATED",
            "filing_date": pd.to_datetime(source["filing_date"]), "source_url": source["source"],
            "source_path": str(path), "quality_score": 0.90, "adapter": f"{ticker}_VALIDATED_GUIDANCE_V321",
        }))
    return pd.concat(rows, ignore_index=True)[GUIDANCE_COLUMNS]


@dataclass(frozen=True)
class StandardizedKPIBundle:
    production_actuals: pd.DataFrame
    production_guidance: pd.DataFrame
    realized_prices: pd.DataFrame
    coverage: pd.DataFrame


def _remove_isolated_parser_outliers(frame: pd.DataFrame) -> pd.DataFrame:
    kept: list[pd.DataFrame] = []
    for _, company in frame.groupby("ticker", sort=False):
        company = company.sort_values("quarter").copy()
        values = company["total_mboed"].astype(float)
        previous = values.shift(1)
        following = values.shift(-1)
        isolated_low = values.lt(0.35 * pd.concat([previous, following], axis=1).min(axis=1))
        isolated_high = values.gt(3.0 * pd.concat([previous, following], axis=1).max(axis=1))
        kept.append(company.loc[~(isolated_low | isolated_high)])
    return pd.concat(kept, ignore_index=True)


def build_standardized_kpis(data_lake: Path, ir_root: Path) -> StandardizedKPIBundle:
    actual_rows: list[dict[str, object]] = []
    guidance_rows: list[dict[str, object]] = []
    price_rows: list[dict[str, object]] = []
    generic_tickers = tuple(
        ticker for ticker, spec in COMPANY_ADAPTERS.items()
        if spec.actual_source_policy.startswith("IR_TABLE")
    )
    ir_tickers = tuple(
        ticker for ticker, spec in COMPANY_ADAPTERS.items()
        if spec.local_operational_source_available
    )
    for ticker in ir_tickers:
        for path in sorted((ir_root / ticker).glob("*.htm")):
            raw_lower = path.read_bytes().lower()
            if b"production" not in raw_lower:
                continue
            tables = _table_rows(path)
            metadata = _metadata(path)
            actual, price = _extract_actual_from_file(ticker, path, tables, metadata)
            if actual and ticker in generic_tickers:
                actual_rows.append(actual)
            if price:
                price_rows.append(price)
            guidance = _extract_guidance_from_file(ticker, path, tables, metadata)
            if guidance:
                guidance_rows.append(guidance)

    actuals = pd.concat([
        _legacy_actuals(data_lake), pd.DataFrame(actual_rows, columns=ACTUAL_COLUMNS)
    ], ignore_index=True)
    guidance = pd.concat([
        _legacy_guidance(data_lake), pd.DataFrame(guidance_rows, columns=GUIDANCE_COLUMNS)
    ], ignore_index=True)
    prices = pd.DataFrame(price_rows, columns=PRICE_COLUMNS)

    actuals = (
        actuals.sort_values(["ticker", "quarter", "quality_score", "filing_date"])
        .drop_duplicates(["ticker", "quarter"], keep="last")
        .reset_index(drop=True)
    )
    actuals = actuals.loc[pd.to_numeric(actuals["total_mboed"], errors="coerce").gt(0)].copy()
    actuals = actuals.loc[
        actuals["oil_mbpd"].isna() | actuals["total_mboed"].ge(actuals["oil_mbpd"])
    ].copy()
    actuals = _remove_isolated_parser_outliers(actuals)
    prior_total = {
        (str(row["ticker"]), str(pd.Period(row["quarter"], freq="Q") + 4)): float(row["total_mboed"])
        for _, row in actuals.iterrows()
    }
    actuals["production_yoy"] = [
        100.0 * np.log(float(row["total_mboed"]) / prior_total.get((str(row["ticker"]), str(row["quarter"])), np.nan))
        for _, row in actuals.iterrows()
    ]
    actuals["mna_flag"] = actuals["production_yoy"].abs().gt(50.0)
    actuals = actuals.drop(columns="production_yoy")
    guidance = (
        guidance.sort_values(["ticker", "target_quarter", "quality_score", "filing_date"])
        .drop_duplicates(["ticker", "target_quarter"], keep="last")
        .reset_index(drop=True)
    )
    prices = (
        prices.sort_values(["ticker", "quarter", "quality_score", "filing_date"])
        .drop_duplicates(["ticker", "quarter"], keep="last")
        .reset_index(drop=True)
    )
    # Fail closed on differentials, percentages, and hedging rows that a loose
    # IR label can otherwise mistake for absolute realized prices.
    plausible_price_ranges = {
        "realized_oil_price": (10.0, 200.0),
        "realized_ngl_price": (1.0, 100.0),
        "realized_gas_price": (0.10, 30.0),
    }
    for column, (low, high) in plausible_price_ranges.items():
        numeric = pd.to_numeric(prices[column], errors="coerce")
        prices[column] = numeric.where(numeric.between(low, high))
    prices = prices.dropna(subset=list(plausible_price_ranges), how="all").reset_index(drop=True)
    coverage_rows = []
    for ticker in all_tickers():
        company_actuals = actuals.loc[actuals["ticker"].eq(ticker)]
        company_guidance = guidance.loc[guidance["ticker"].eq(ticker)]
        company_prices = prices.loc[prices["ticker"].eq(ticker)]
        coverage_rows.append({
            "ticker": ticker,
            "group": group_for_ticker(ticker),
            "actual_quarters": len(company_actuals),
            "guidance_quarters": len(company_guidance),
            "realized_price_quarters": len(company_prices),
            "first_actual_quarter": company_actuals["quarter"].min() if len(company_actuals) else None,
            "last_actual_quarter": company_actuals["quarter"].max() if len(company_actuals) else None,
            "status": "READY" if len(company_actuals) >= 12 else "INSUFFICIENT_KPI_HISTORY",
        })
    return StandardizedKPIBundle(actuals, guidance, prices, pd.DataFrame(coverage_rows))
