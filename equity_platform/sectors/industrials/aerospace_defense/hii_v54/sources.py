from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    return " ".join(soup.stripped_strings)


def evidence_window(text: str, needle: str, radius: int = 260) -> str:
    index = text.lower().find(needle.lower())
    if index < 0:
        raise ValueError(f"Evidence phrase missing: {needle}")
    return text[max(0, index - radius) : index + len(needle) + radius]


def source_fields(path: Path, *, source_url: str | None = None) -> dict[str, object]:
    return {
        "source_path": str(path),
        "source_url": source_url or "",
        "source_sha256": sha256_file(path),
    }


def compact_row_values(row: pd.Series) -> list[str]:
    values: list[str] = []
    for value in row.tolist():
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and (not values or values[-1] != text):
            values.append(text)
    return values


def _table_text(table: pd.DataFrame) -> str:
    return " ".join(table.astype(str).fillna("").values.flatten())


def _find_guidance_table(path: Path) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(pd.read_html(path)):
        text = _table_text(table)
        if (
            "Outlook" in text
            and "Shipbuilding Operating Margin" in text
            and "Mission Technologies Segment Operating Margin" in text
        ):
            return index, table
    raise ValueError(f"Guidance table missing from {path}")


def _row_current_value(table: pd.DataFrame, label_prefix: str) -> str:
    labels = table.iloc[:, 0].fillna("").astype(str).str.strip()
    matches = table.loc[labels.str.startswith(label_prefix)]
    if matches.empty:
        raise ValueError(f"Expected a guidance row starting with {label_prefix!r}")
    # Some releases show both a hypothetical tax-law FCF and the current-law FCF.
    # The final row is the operative current outlook in those tables.
    values = compact_row_values(matches.iloc[-1])
    if len(values) < 2:
        raise ValueError(f"No value found for guidance row {label_prefix!r}")
    return values[-1]


def _parse_range(text: str, *, scale: float = 1.0) -> tuple[float, float]:
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))]
    if not numbers:
        return float("nan"), float("nan")
    if len(numbers) == 1:
        numbers.append(numbers[0])
    negative = "(" in text and ")" in text
    low, high = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
    if negative:
        low, high = -high, -low
    return low * scale, high * scale


def _money_range(text: str) -> tuple[float, float]:
    upper = text.upper()
    scale = 1_000_000_000.0 if "B" in upper else 1_000_000.0
    return _parse_range(text, scale=scale)


def _percentage_range(text: str) -> tuple[float, float]:
    return _parse_range(text)


def parse_guidance_vintages(
    *, root: Path, inventory_path: Path, start_period: str
) -> pd.DataFrame:
    inventory = pd.read_csv(root / inventory_path)
    inventory = inventory.loc[
        inventory["model_use"].ne("NOT_SELECTED")
        & inventory["period"].astype(str).ge(start_period)
    ].sort_values("period")
    rows: list[dict[str, object]] = []
    for record in inventory.itertuples():
        path = Path(str(record.source_path))
        if not path.is_file() or sha256_file(path) != str(record.actual_sha256):
            raise ValueError(f"IR source hash mismatch: {path}")
        table_index, table = _find_guidance_table(path)
        header = _table_text(table)
        year_match = re.search(r"FY(\d{2})\s+Outlook", header, re.IGNORECASE)
        forecast_year = (
            2000 + int(year_match.group(1))
            if year_match
            else int(str(record.period)[:4])
        )
        ship_revenue = _money_range(_row_current_value(table, "Shipbuilding Revenue"))
        ship_margin = _percentage_range(
            _row_current_value(table, "Shipbuilding Operating Margin")
        )
        mission_revenue = _money_range(
            _row_current_value(table, "Mission Technologies Revenue")
        )
        mission_margin = _percentage_range(
            _row_current_value(table, "Mission Technologies Segment Operating Margin")
        )
        mission_ebitda = _percentage_range(
            _row_current_value(table, "Mission Technologies EBITDA Margin")
        )
        fas_cas = _money_range(_row_current_value(table, "Operating FAS/CAS Adjustment"))
        state_labels = table.iloc[:, 0].fillna("").astype(str).str.strip()
        state_match = table.loc[state_labels.str.startswith("Non-current State Income Tax")]
        state = (
            _money_range(compact_row_values(state_match.iloc[0])[-1])
            if len(state_match) == 1
            else (float("nan"), float("nan"))
        )
        fcf = _money_range(_row_current_value(table, "Free Cash Flow"))
        rows.append(
            {
                "forecast_origin_period": record.period,
                "filing_date": record.filing_date,
                "forecast_year": forecast_year,
                "shipbuilding_revenue_low_usd": ship_revenue[0],
                "shipbuilding_revenue_high_usd": ship_revenue[1],
                "shipbuilding_revenue_midpoint_usd": np.mean(ship_revenue),
                "shipbuilding_margin_low_pct": ship_margin[0],
                "shipbuilding_margin_high_pct": ship_margin[1],
                "shipbuilding_margin_midpoint_pct": np.mean(ship_margin),
                "mission_revenue_low_usd": mission_revenue[0],
                "mission_revenue_high_usd": mission_revenue[1],
                "mission_revenue_midpoint_usd": np.mean(mission_revenue),
                "mission_margin_low_pct": mission_margin[0],
                "mission_margin_high_pct": mission_margin[1],
                "mission_margin_midpoint_pct": np.mean(mission_margin),
                "mission_ebitda_margin_low_pct": mission_ebitda[0],
                "mission_ebitda_margin_high_pct": mission_ebitda[1],
                "mission_ebitda_margin_midpoint_pct": np.mean(mission_ebitda),
                "operating_fas_cas_low_usd": fas_cas[0],
                "operating_fas_cas_high_usd": fas_cas[1],
                "operating_fas_cas_midpoint_usd": np.mean(fas_cas),
                "noncurrent_state_tax_low_usd": state[0],
                "noncurrent_state_tax_high_usd": state[1],
                "noncurrent_state_tax_midpoint_usd": np.mean(state),
                "free_cash_flow_low_usd": fcf[0],
                "free_cash_flow_high_usd": fcf[1],
                "free_cash_flow_midpoint_usd": np.mean(fcf),
                "table_index": table_index,
                **source_fields(path, source_url=str(record.source_url)),
                "pit_at_forecast_origin": True,
            }
        )
    result = pd.DataFrame(rows)
    if result["forecast_origin_period"].duplicated().any():
        raise ValueError("Guidance origins must be unique")
    return result


def parse_workforce_history(ten_k_paths: Iterable[Path]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted(ten_k_paths):
        year_match = re.search(r"hii-(\d{4})\d{4}", path.name)
        if not year_match:
            raise ValueError(f"Cannot infer year from {path.name}")
        year = int(year_match.group(1))
        text = document_text(path)

        def number(pattern: str) -> float:
            match = re.search(pattern, text, re.IGNORECASE)
            return float(match.group(1).replace(",", "")) if match else float("nan")

        employees = number(r"We have (?:approximately|over) ([\d,]+)\s+employees")
        engineers = number(r"approximately ([\d,]+) engineers and designers")
        advanced = number(r"approximately ([\d,]+) employees with advanced degrees")
        long_tenure = number(r"approximately ([\d,]+) employees with more than 40 years")
        collective = number(
            r"Of the Company's (?:approximately|over) [\d,]+ employees, (?:approximately )?([\d.]+)\s*% are covered"
        )
        rows.append(
            {
                "year": year,
                "approximate_employees": employees,
                "engineers_and_designers": engineers,
                "employees_with_advanced_degrees": advanced,
                "employees_over_40_years_service": long_tenure,
                "collective_bargaining_coverage_pct": collective,
                "labor_hours_disclosed": False,
                "headcount_is_approximate": True,
                "authority": "WORKFORCE_CAPACITY_CONTEXT_NOT_LABOR_HOUR_PRODUCTIVITY",
                **source_fields(path),
            }
        )
    return pd.DataFrame(rows)


def parse_bls_labor_snapshot(
    path: Path, *, max_reference_period: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    titles = payload["series_titles"]
    rows: list[dict[str, object]] = []
    for series in payload["response"]["Results"]["series"]:
        series_id = series["seriesID"]
        for item in series["data"]:
            period = str(item["period"])
            if not re.fullmatch(r"M\d{2}", period) or period == "M13":
                continue
            month = int(period[1:])
            reference_period = f"{item['year']}M{month:02d}"
            if reference_period > max_reference_period:
                continue
            rows.append(
                {
                    "series_id": series_id,
                    "series_title": titles[series_id],
                    "reference_period": reference_period,
                    "reference_date": f"{item['year']}-{month:02d}-01",
                    "value": float(item["value"]),
                    "footnotes": "|".join(
                        str(note.get("text", "")) for note in item.get("footnotes", [])
                    ),
                    "pit_model_input_allowed": False,
                    "authority": payload["authority"],
                    "source_url": payload["source_url"],
                    "source_path": str(path),
                    "source_sha256": sha256_file(path),
                    "retrieved_at_utc": payload["retrieved_at_utc"],
                }
            )
    history = pd.DataFrame(rows).sort_values(["series_id", "reference_period"])
    summary_rows: list[dict[str, object]] = []
    for series_id, group in history.groupby("series_id"):
        group = group.set_index("reference_period")
        current = float(group.loc["2026M06", "value"])
        prior = float(group.loc["2025M06", "value"])
        summary_rows.append(
            {
                "series_id": series_id,
                "series_title": group.iloc[0]["series_title"],
                "reference_period": "2026M06",
                "current_value": current,
                "prior_year_value": prior,
                "year_over_year_pct": (current / prior - 1.0) * 100.0,
                "pit_model_input_allowed": False,
                "authority": payload["authority"],
            }
        )
    summary = pd.DataFrame(summary_rows)
    lookup = summary.set_index("series_id")["year_over_year_pct"]
    labor_input = (
        (1.0 + float(lookup["CES3133661101"]) / 100.0)
        * (1.0 + float(lookup["CES3133600002"]) / 100.0)
        * (1.0 + float(lookup["CES3133600003"]) / 100.0)
        - 1.0
    ) * 100.0
    summary["composite_labor_input_cost_proxy_yoy_pct"] = labor_input
    summary["scope_limitation"] = (
        "Employment is ship-building specific; hours and earnings are broader transportation-equipment proxies."
    )
    return history.reset_index(drop=True), summary


def build_cost_recovery_evidence(latest_ten_k: Path) -> pd.DataFrame:
    text = document_text(latest_ten_k)
    definitions = [
        (
            "FIRM_FIXED_PRICE",
            "not generally subject to adjustment regardless of costs incurred",
            "Predetermined price leaves cost overruns with the contractor.",
        ),
        (
            "FIXED_PRICE_INCENTIVE",
            "subject to a cost-share limit that affects profitability",
            "Allowable costs are reimbursed only until the cost-share limit; thereafter economics become firm-fixed-price-like.",
        ),
        (
            "COST_TYPE",
            "reimbursement of the contractor's allowable costs plus a fee",
            "Allowable costs are reimbursed plus profit fee, reducing direct overrun exposure.",
        ),
        (
            "TIME_AND_MATERIALS",
            "fixed hourly billing rate for each direct labor hour expended",
            "Direct labor is billed at fixed hourly rates and allowable materials are reimbursed.",
        ),
        (
            "ESCALATION_PROVISION",
            "difference in basis between our actual material costs and industry indices",
            "Index-linked escalation can mitigate inflation but leaves basis risk versus actual material cost.",
        ),
    ]
    rows = []
    for mechanism, needle, interpretation in definitions:
        rows.append(
            {
                "mechanism": mechanism,
                "interpretation": interpretation,
                "evidence_excerpt": evidence_window(text, needle),
                "contract_level_clause_coverage_disclosed": False,
                "price_reset_amount_disclosed": False,
                "terminal_margin_point_input_allowed": False,
                "authority": "MECHANISM_DEFINITION_AND_RISK_EVIDENCE_ONLY",
                **source_fields(latest_ten_k),
            }
        )
    return pd.DataFrame(rows)


def build_program_event_timeline(latest_ten_k: Path) -> pd.DataFrame:
    text = document_text(latest_ten_k)
    events = [
        (
            "LHA_10_HELMAND_PROVINCE",
            2023,
            2024,
            "long-lead-time material contract for Helmand Province",
            "Long-lead material award followed by detail-design and construction modification.",
        ),
        (
            "LPD_32_PHILADELPHIA",
            2022,
            2023,
            "long-lead-time material contract for Philadelphia",
            "Long-lead material award followed by detail-design and construction modification.",
        ),
        (
            "COLUMBIA_NEXT_FIVE_BOATS",
            np.nan,
            2023,
            "award modification for long-lead-time material and advance construction for the next five boats",
            "Award modification disclosed, but no separately identified initial award or price-reset amount.",
        ),
        (
            "LPD_33_TO_35_MULTI_SHIP",
            np.nan,
            2024,
            "multi-ship procurement contract for the construction of Travis Manion",
            "Multi-ship procurement award disclosed without a separately identified price-reset event.",
        ),
    ]
    rows: list[dict[str, object]] = []
    for program, initial_year, modification_year, needle, interpretation in events:
        lag = (
            modification_year - int(initial_year)
            if np.isfinite(initial_year)
            else np.nan
        )
        rows.append(
            {
                "program": program,
                "initial_or_long_lead_award_year": initial_year,
                "detail_or_modification_year": modification_year,
                "observed_event_lag_years": lag,
                "interpretation": interpretation,
                "evidence_excerpt": evidence_window(text, needle),
                "event_is_verified_price_reset": False,
                "award_to_price_reset_lag_identifiable": False,
                "terminal_margin_point_input_allowed": False,
                **source_fields(latest_ten_k),
            }
        )
    return pd.DataFrame(rows)
