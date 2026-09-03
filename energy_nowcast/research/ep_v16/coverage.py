from __future__ import annotations

from calendar import isleap
import hashlib
from pathlib import Path
import re
from typing import Callable

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v13.unit_economics import build_annual_production_kpi
from energy_nowcast.research.phase6.financial_targets import EP_TICKERS
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import E_AND_P_GROUPS, group_for_ticker


EVENT_TICKERS = ("EOG", "RRC", "DVN", "SM")
SNAPSHOT_TICKERS = ("MTDR",)
YEARS = tuple(range(2021, 2026))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: object) -> float:
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text.lower() == "nan" or text in {"—", "–", "-", ""}:
        return np.nan
    negative = text.startswith("(") or text.endswith(")")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return np.nan
    result = float(match.group())
    return -abs(result) if negative else result


def _tokens(row: pd.Series) -> list[str]:
    values: list[str] = []
    for raw in row.tolist():
        value = str(raw).strip()
        if not value or value.lower() == "nan":
            continue
        if values and value == values[-1]:
            continue
        values.append(value)
    return values


def _lines(table: pd.DataFrame) -> list[tuple[int, list[str]]]:
    return [(int(index), _tokens(row)) for index, row in table.iterrows()]


def _table_text(table: pd.DataFrame) -> str:
    return " ".join(str(value) for value in table.to_numpy().flatten()).lower()


def _read_tables(path: Path) -> list[pd.DataFrame]:
    try:
        return pd.read_html(path, flavor="lxml")
    except (ValueError, OSError):
        return []


def _release_files(ir_root: Path, ticker: str, reserve_year: int) -> list[Path]:
    directory = ir_root / ticker
    if not directory.exists():
        return []
    prefix = f"{reserve_year + 1}-"
    files = [
        path
        for path in directory.glob(f"{prefix}*.htm")
        if any(f"{prefix}{month:02d}-" in path.name for month in (1, 2, 3))
    ]
    if ticker == "DVN":
        preferred = [path for path in files if "_EX-99.2_" in path.name]
    else:
        preferred = [path for path in files if "_EX-99.1_" in path.name]
    return sorted(preferred or files)


def _find_table(
    ir_root: Path,
    ticker: str,
    reserve_year: int,
    predicate: Callable[[str], bool],
) -> tuple[Path, pd.DataFrame] | None:
    for path in _release_files(ir_root, ticker, reserve_year):
        for table in _read_tables(path):
            if predicate(_table_text(table)):
                return path, table
    return None


def _last_numeric(tokens: list[str]) -> float:
    for token in reversed(tokens[1:]):
        if "%" in token or "/" in token:
            continue
        value = _number(token)
        if np.isfinite(value):
            return value
    return np.nan


def _label_value(
    lines: list[tuple[int, list[str]]], label: str, *, occurrence: int = 0
) -> float:
    matches = [tokens for _, tokens in lines if tokens and label in tokens[0].lower()]
    if len(matches) <= occurrence:
        return np.nan
    return _last_numeric(matches[occurrence])


def _operational_kpi(production_path: Path) -> pd.DataFrame:
    production = pd.read_csv(production_path)
    return build_annual_production_kpi(production).set_index(["ticker", "year"])


def _kpi_value(kpi: pd.DataFrame, ticker: str, year: int) -> float:
    if (ticker, year) not in kpi.index:
        return np.nan
    return float(kpi.loc[(ticker, year), "kpi_production_mboe"])


def _row(
    *,
    ticker: str,
    year: int,
    source: Path,
    route: str,
    semantics: str,
    begin: float,
    end: float,
    production: float,
    operational: float,
    extensions: float = 0.0,
    revisions: float = 0.0,
    purchases: float = 0.0,
    sales: float = 0.0,
    source_table: str,
    production_evidence: str,
) -> dict[str, object]:
    predicted_end = begin + extensions + revisions + purchases - sales - production
    identity_error = end - predicted_end
    ratio = production / operational if operational > 0 else np.nan
    return {
        "ticker": ticker,
        "group": group_for_ticker(ticker),
        "year": year,
        "reserve_route": route,
        "reserve_semantics": semantics,
        "begin_reserves_mboe": begin,
        "end_reserves_mboe": end,
        "production_mboe": production,
        "operational_production_mboe": operational,
        "production_verification_ratio": ratio,
        "extensions_discoveries_mboe": extensions,
        "revisions_mboe": revisions,
        "purchases_mboe": purchases,
        "sales_mboe": sales,
        "total_replacement_additions_mboe": end - begin + production,
        "reserve_identity_error_mboe": identity_error,
        "reserve_identity_error_ratio": abs(identity_error) / end if end > 0 else np.nan,
        "source_file": str(source),
        "source_file_sha256": _sha256(source),
        "source_table": source_table,
        "availability_date": source.name[:10],
        "production_evidence": production_evidence,
        "production_independently_verified": bool(np.isfinite(ratio) and 0.95 <= ratio <= 1.05),
        "research_only": True,
    }


def _parse_eog(ir_root: Path, year: int, kpi: pd.DataFrame) -> dict[str, object] | None:
    found = _find_table(
        ir_root,
        "EOG",
        year,
        lambda text: "oil equivalents (mmboe)" in text
        and "beginning reserves" in text
        and "ending reserves" in text,
    )
    if found is None:
        return None
    source, table = found
    lines = _lines(table)
    start = next(index for index, tokens in lines if tokens and "oil equivalents (mmboe)" in tokens[0].lower())
    section = [(index, tokens) for index, tokens in lines if start < index < start + 10]
    scale = 1_000.0
    purchases = _label_value(section, "purchases in place")
    sales = _label_value(section, "sales in place")
    return _row(
        ticker="EOG",
        year=year,
        source=source,
        route="IR_TOTAL_PROVED_EVENT_ROLLFORWARD",
        semantics="TOTAL_PROVED_MBOE_FULL_EVENT_CHAIN",
        begin=_label_value(section, "beginning reserves") * scale,
        end=_label_value(section, "ending reserves") * scale,
        production=abs(_label_value(section, "production")) * scale,
        operational=_kpi_value(kpi, "EOG", year),
        extensions=_label_value(section, "extensions, discoveries") * scale,
        revisions=_label_value(section, "revisions") * scale,
        purchases=max(purchases, 0.0) * scale if np.isfinite(purchases) else 0.0,
        sales=abs(sales) * scale if np.isfinite(sales) else 0.0,
        source_table=f"{year} Net Proved Reserves Reconciliation Summary / Oil Equivalents",
        production_evidence="SEPARATE_FROZEN_QUARTERLY_OPERATIONAL_KPI",
    )


def _parse_rrc(ir_root: Path, year: int, kpi: pd.DataFrame) -> dict[str, object] | None:
    found = _find_table(
        ir_root,
        "RRC",
        year,
        lambda text: "summary of changes in proved reserves" in text
        and "balance at december" in text,
    )
    if found is None:
        return None
    source, table = found
    lines = _lines(table)
    balances = [
        _last_numeric(tokens)
        for _, tokens in lines
        if tokens and "balance at december" in tokens[0].lower()
    ]
    if len(balances) < 2:
        return None
    scale = 1_000.0 / 6.0
    extensions = _label_value(lines, "extensions, discoveries")
    revisions = sum(
        value
        for value in (
            _label_value(lines, "performance revisions"),
            _label_value(lines, "price revisions"),
        )
        if np.isfinite(value)
    )
    purchases = _label_value(lines, "purchases")
    sales = _label_value(lines, "sales")
    return _row(
        ticker="RRC",
        year=year,
        source=source,
        route="IR_TOTAL_PROVED_EVENT_ROLLFORWARD",
        semantics="TOTAL_PROVED_BCFE_CONVERTED_AT_6MCF_PER_BOE",
        begin=balances[0] * scale,
        end=balances[-1] * scale,
        production=abs(_label_value(lines, "production")) * scale,
        operational=_kpi_value(kpi, "RRC", year),
        extensions=extensions * scale,
        revisions=revisions * scale,
        purchases=max(purchases, 0.0) * scale if np.isfinite(purchases) else 0.0,
        sales=abs(sales) * scale if np.isfinite(sales) else 0.0,
        source_table="Summary of Changes in Proved Reserves",
        production_evidence="SEPARATE_FROZEN_QUARTERLY_OPERATIONAL_KPI",
    )


def _operational_from_dvn(tables: list[pd.DataFrame], year: int) -> float:
    for table in tables:
        text = _table_text(table)
        if "total oil equivalent (mboe/d)" not in text:
            continue
        lines = _lines(table)
        marker = next(
            (index for index, tokens in lines if tokens and "total oil equivalent (mboe/d)" in tokens[0].lower()),
            None,
        )
        if marker is None:
            continue
        for index, tokens in lines:
            if index > marker and tokens and tokens[0].strip().lower() == "total":
                values = [_number(token) for token in tokens[1:] if "%" not in token]
                values = [value for value in values if np.isfinite(value)]
                if values:
                    return values[0] * (366 if isleap(year) else 365)
    return np.nan


def _parse_dvn(ir_root: Path, year: int, kpi: pd.DataFrame) -> dict[str, object] | None:
    found = _find_table(
        ir_root,
        "DVN",
        year,
        lambda text: "oil (mmbbls)" in text
        and "total (mmboe)" in text
        and "extensions and discoveries" in text,
    )
    if found is None:
        return None
    source, table = found
    lines = _lines(table)
    totals = [
        _last_numeric(tokens)
        for _, tokens in lines
        if tokens and tokens[0].strip().lower() == "total proved"
    ]
    if len(totals) < 2:
        return None
    revisions = sum(
        value
        for value in (
            _label_value(lines, "revisions due to prices"),
            _label_value(lines, "revisions other than price"),
        )
        if np.isfinite(value)
    )
    tables = _read_tables(source)
    operational = _operational_from_dvn(tables, year)
    if not np.isfinite(operational):
        operational = _kpi_value(kpi, "DVN", year)
    purchases = _label_value(lines, "purchase of reserves")
    sales = _label_value(lines, "sale of reserves")
    scale = 1_000.0
    return _row(
        ticker="DVN",
        year=year,
        source=source,
        route="IR_TOTAL_PROVED_EVENT_ROLLFORWARD",
        semantics="TOTAL_PROVED_MBOE_FULL_EVENT_CHAIN",
        begin=totals[0] * scale,
        end=totals[-1] * scale,
        production=abs(_label_value(lines, "production")) * scale,
        operational=operational,
        extensions=_label_value(lines, "extensions and discoveries") * scale,
        revisions=revisions * scale,
        purchases=max(purchases, 0.0) * scale if np.isfinite(purchases) else 0.0,
        sales=abs(sales) * scale if np.isfinite(sales) else 0.0,
        source_table="Oil/Gas/NGL Total Proved Reserve Rollforward",
        production_evidence="SEPARATE_FULL_YEAR_OPERATIONAL_PRODUCTION_TABLE",
    )


def _operational_from_sm(tables: list[pd.DataFrame], year: int) -> float:
    for table in tables:
        text = _table_text(table)
        if f"full year {year}" not in text or "total (mboe / mboe/d)" not in text:
            continue
        for _, tokens in _lines(table):
            if not tokens or "total (mboe / mboe/d)" not in tokens[0].lower():
                continue
            last = tokens[-1]
            first = last.split("/")[0]
            value = _number(first)
            if np.isfinite(value):
                return value
    return np.nan


def _parse_sm(ir_root: Path, year: int, kpi: pd.DataFrame) -> dict[str, object] | None:
    found = _find_table(
        ir_root,
        "SM",
        year,
        lambda text: "proved reserves year-end" in text
        and "production" in text,
    )
    if found is None:
        return None
    source, table = found
    lines = _lines(table)
    reserves = [
        _last_numeric(tokens)
        for _, tokens in lines
        if tokens
        and "estimated" in tokens[0].lower()
        and "proved reserves year-end" in tokens[0].lower()
    ]
    if len(reserves) < 2:
        return None
    revisions = sum(
        value
        for _, tokens in lines
        if tokens
        and "revision" in tokens[0].lower()
        and "reserve additions and performance revisions" not in tokens[0].lower()
        and np.isfinite(value := _last_numeric(tokens))
    )
    net_acquisitions = _label_value(lines, "net acquisitions and divestitures")
    if not np.isfinite(net_acquisitions):
        net_acquisitions = 0.0
    additions = next(
        (
            value
            for label in (
                "discovery/extensions",
                "reserve additions and performance revisions",
                "reserve additions",
            )
            if np.isfinite(value := _label_value(lines, label))
        ),
        0.0,
    )
    production = _label_value(lines, "net production")
    if not np.isfinite(production):
        production = _label_value(lines, "production")
    operational = _operational_from_sm(_read_tables(source), year)
    if not np.isfinite(operational):
        operational = _kpi_value(kpi, "SM", year)
    scale = 1_000.0
    return _row(
        ticker="SM",
        year=year,
        source=source,
        route="IR_TOTAL_PROVED_EVENT_ROLLFORWARD",
        semantics="TOTAL_PROVED_MBOE_NET_ACQUISITION_EVENT_CHAIN",
        begin=reserves[0] * scale,
        end=reserves[-1] * scale,
        production=abs(production) * scale,
        operational=operational,
        extensions=additions * scale,
        revisions=revisions * scale,
        purchases=max(net_acquisitions, 0.0) * scale,
        sales=max(-net_acquisitions, 0.0) * scale,
        source_table="Estimated Net Proved Reserves Rollforward",
        production_evidence="SEPARATE_FULL_YEAR_OPERATING_AREA_PRODUCTION_TABLE",
    )


def _parse_mtdr_snapshots(ir_root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for current_year in YEARS:
        found = _find_table(
            ir_root,
            "MTDR",
            current_year,
            lambda text: "estimated proved reserves" in text and "total (mboe)" in text,
        )
        if found is None:
            continue
        source, table = found
        lines = _lines(table)
        total_tokens = next(
            (
                tokens
                for _, tokens in lines
                if tokens and tokens[0].strip().lower().startswith("total (mboe)")
            ),
            None,
        )
        if total_tokens is None:
            continue
        values = [
            _number(token)
            for token in total_tokens[1:]
            if "%" not in token and "/" not in token
        ]
        values = [value for value in values if np.isfinite(value)]
        if len(values) < 2:
            continue
        for year, value in ((current_year, values[0]), (current_year - 1, values[1])):
            rows.append(
                {
                    "ticker": "MTDR",
                    "year": year,
                    "end_reserves_mboe": value,
                    "source_file": str(source),
                    "source_file_sha256": _sha256(source),
                    "availability_date": source.name[:10],
                    "source_table": "Estimated Proved Reserves / Total MBOE",
                }
            )
    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values(["year", "availability_date"])
        .drop_duplicates(["ticker", "year"], keep="first")
        .reset_index(drop=True)
    )


def _build_mtdr_chain(
    ir_root: Path, kpi: pd.DataFrame
) -> list[dict[str, object]]:
    snapshots = _parse_mtdr_snapshots(ir_root)
    rows: list[dict[str, object]] = []
    if snapshots.empty:
        return rows
    snapshots = snapshots.set_index("year")
    for year in sorted(snapshots.index):
        if year - 1 not in snapshots.index:
            continue
        end = float(snapshots.loc[year, "end_reserves_mboe"])
        begin = float(snapshots.loc[year - 1, "end_reserves_mboe"])
        operational = _kpi_value(kpi, "MTDR", int(year))
        if not np.isfinite(operational):
            continue
        source = Path(str(snapshots.loc[year, "source_file"]))
        additions = end - begin + operational
        rows.append(
            _row(
                ticker="MTDR",
                year=int(year),
                source=source,
                route="IR_TOTAL_PROVED_STOCK_FLOW",
                semantics="TOTAL_REPLACEMENT_INCLUDING_ACQUISITIONS_NOT_ORGANIC",
                begin=begin,
                end=end,
                production=operational,
                operational=operational,
                extensions=additions,
                source_table="Consecutive Total Proved Reserve Snapshots",
                production_evidence="SEPARATE_FROZEN_QUARTERLY_OPERATIONAL_KPI",
            )
        )
    return rows


def _parent_rows(parent_panel_path: Path) -> pd.DataFrame:
    parent = pd.read_csv(parent_panel_path)
    rows: list[dict[str, object]] = []
    for item in parent.itertuples(index=False):
        if not np.isfinite(item.begin_reserves_mboe):
            continue
        purchases = float(item.purchases_mboe) if np.isfinite(item.purchases_mboe) else 0.0
        sales = abs(float(item.sales_mboe)) if np.isfinite(item.sales_mboe) else 0.0
        extensions = float(item.extensions_discoveries_mboe)
        revisions = float(item.revisions_mboe)
        improved = (
            float(item.improved_recovery_mboe)
            if np.isfinite(item.improved_recovery_mboe)
            else 0.0
        )
        begin = float(item.begin_reserves_mboe)
        end = float(item.end_reserves_mboe)
        production = float(item.production_mboe)
        identity = end - (
            begin + extensions + revisions + improved + purchases - sales - production
        )
        rows.append(
            {
                "ticker": item.ticker,
                "group": group_for_ticker(str(item.ticker)),
                "year": int(item.year),
                "reserve_route": "FROZEN_V1_5_COMPANYFACTS_ROUTE_AWARE",
                "reserve_semantics": "TOTAL_PROVED_REQUIRED_EVENTS_PARENT_APPROVED",
                "begin_reserves_mboe": begin,
                "end_reserves_mboe": end,
                "production_mboe": production,
                "operational_production_mboe": float(item.kpi_production_mboe),
                "production_verification_ratio": float(item.production_calibration_ratio),
                "extensions_discoveries_mboe": extensions + improved,
                "revisions_mboe": revisions,
                "purchases_mboe": purchases,
                "sales_mboe": sales,
                "total_replacement_additions_mboe": end - begin + production,
                "reserve_identity_error_mboe": identity,
                "reserve_identity_error_ratio": abs(identity) / end if end > 0 else np.nan,
                "source_file": "FROZEN_V1_5_COMPANYFACTS_ROUTE",
                "source_file_sha256": "PARENT_MANIFEST_PROTECTED",
                "source_table": "SEC Companyfacts route-aware reserve facts",
                "availability_date": "PARENT_FROZEN",
                "production_evidence": "SEPARATE_FROZEN_QUARTERLY_OPERATIONAL_KPI",
                "production_independently_verified": bool(
                    0.75 <= float(item.production_calibration_ratio) <= 1.25
                ),
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def _coverage_summary(panel: pd.DataFrame, parent_summary_path: Path) -> pd.DataFrame:
    parent = pd.read_csv(parent_summary_path).set_index("ticker")
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        history = panel.loc[panel["ticker"].eq(ticker)]
        years = int(history["year"].nunique())
        verified = int(history["production_independently_verified"].sum())
        event_route = bool(
            history["reserve_route"].str.contains("EVENT_ROLLFORWARD|V1_5", regex=True).any()
        )
        snapshot_route = bool(history["reserve_route"].eq("IR_TOTAL_PROVED_STOCK_FLOW").any())
        identity_years = int(history["reserve_identity_error_ratio"].le(0.02).sum())
        parent_ready = bool(parent.loc[ticker, "route_aware_reserve_chain_ready"])
        supplemental_ready = bool(
            years >= 3
            and verified >= 3
            and identity_years >= 3
            and (event_route or snapshot_route)
        )
        ready = parent_ready or supplemental_ready
        rows.append(
            {
                "ticker": ticker,
                "group": group_for_ticker(ticker),
                "v15_chain_ready": parent_ready,
                "v16_total_proved_chain_years": years,
                "v16_usable_replacement_years": years,
                "production_verified_years": verified,
                "identity_within_2pct_years": identity_years,
                "event_rollforward_route_present": event_route,
                "snapshot_total_stock_flow_route_present": snapshot_route,
                "route_semantics": ";".join(sorted(set(history["reserve_semantics"]))) if years else "",
                "v16_reserve_chain_ready": ready,
                "coverage_status": (
                    "V16_TOTAL_PROVED_CHAIN_READY"
                    if supplemental_ready
                    else "PRESERVED_FROZEN_V1_5_CHAIN_READY"
                    if parent_ready
                    else "LOCKED_INSUFFICIENT_PROVEN_CHAIN"
                ),
                "organic_replacement_claim_allowed": bool(
                    ready and not snapshot_route and history["reserve_semantics"].str.contains("FULL_EVENT").any()
                ),
                "terminal_anchor_ready": False,
            }
        )
    return pd.DataFrame(rows)


def _group_gate(summary: pd.DataFrame) -> pd.DataFrame:
    ready = summary.loc[summary["v16_reserve_chain_ready"]]
    targets = {"oil_heavy": 3, "gas_heavy": 3, "mixed": 2}
    rows = []
    for group, target in targets.items():
        tickers = sorted(ready.loc[ready["group"].eq(group), "ticker"].tolist())
        rows.append(
            {
                "group": group,
                "ready_tickers": len(tickers),
                "target_tickers": target,
                "target_met": len(tickers) >= target,
                "ticker_list": ";".join(tickers),
            }
        )
    return pd.DataFrame(rows)


def build_v16_reserve_coverage(
    *,
    ir_root: Path,
    production_path: Path,
    parent_panel_path: Path,
    parent_summary_path: Path,
) -> dict[str, pd.DataFrame]:
    kpi = _operational_kpi(production_path)
    supplemental: list[dict[str, object]] = []
    parsers = (_parse_eog, _parse_rrc, _parse_dvn, _parse_sm)
    for parser in parsers:
        for year in YEARS:
            parsed = parser(ir_root, year, kpi)
            if parsed is not None:
                supplemental.append(parsed)
    supplemental.extend(_build_mtdr_chain(ir_root, kpi))
    supplemental_panel = pd.DataFrame(supplemental)
    parent_panel = _parent_rows(parent_panel_path)
    combined = pd.concat([parent_panel, supplemental_panel], ignore_index=True)
    combined = combined.sort_values(["ticker", "year", "reserve_route"]).reset_index(drop=True)
    summary = _coverage_summary(combined, parent_summary_path)
    group_gate = _group_gate(summary)
    ready_count = int(summary["v16_reserve_chain_ready"].sum())
    sector_gate = pd.DataFrame(
        [
            {
                "ep_tickers": len(EP_TICKERS),
                "reserve_chain_ready_tickers": ready_count,
                "sector_target_tickers": 8,
                "sector_target_met": ready_count >= 8,
                "group_targets_met": bool(group_gate["target_met"].all()),
                "coverage_completion_gate": bool(
                    ready_count >= 8 and group_gate["target_met"].all()
                ),
                "oil_heavy_ready": int(
                    group_gate.set_index("group").loc["oil_heavy", "ready_tickers"]
                ),
                "gas_heavy_ready": int(
                    group_gate.set_index("group").loc["gas_heavy", "ready_tickers"]
                ),
                "mixed_ready": int(
                    group_gate.set_index("group").loc["mixed", "ready_tickers"]
                ),
                "production_eligible": False,
                "terminal_anchor_replacement_allowed": False,
            }
        ]
    )
    return {
        "supplemental_ir_reserve_panel": supplemental_panel,
        "v16_combined_reserve_chain_panel": combined,
        "v16_reserve_coverage_summary": summary,
        "v16_reserve_group_gate": group_gate,
        "v16_coverage_completion_gate": sector_gate,
    }
