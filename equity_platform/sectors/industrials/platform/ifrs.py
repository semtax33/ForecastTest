from __future__ import annotations

from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


IFRS_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue_local": (
        "Revenue",
        "RevenueFromContractsWithCustomers",
        "RevenueFromRenderingOfServices",
    ),
    "operating_profit_local": (
        "OperatingProfitLossOperating",
        "ProfitLossBeforeFinancingAndIncomeTaxes",
        "ProfitLossFromOperatingActivities",
    ),
    "pretax_profit_local": ("ProfitLossBeforeTax",),
    "income_tax_local": ("IncomeTaxExpenseContinuingOperations",),
    "cfo_local": ("CashFlowsFromUsedInOperatingActivities",),
    "capex_local": (
        "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment",
        "AdditionsToNoncurrentAssets",
    ),
    "depreciation_amortization_local": (
        "DepreciationAndAmortisationExpense",
        "AdjustmentsForDepreciationAndAmortisationExpense",
        "DepreciationExpense",
    ),
    "receivables_local": (
        "CurrentTradeReceivables",
        "TradeAndOtherCurrentReceivables",
    ),
    "inventory_local": ("Inventories", "InventoriesTotal"),
    "accounts_payable_local": (
        "TradeAndOtherCurrentPayablesToTradeSuppliers",
        "TradeAndOtherCurrentPayables",
    ),
    "contract_liabilities_local": ("CurrentContractLiabilities",),
    "cash_local": ("CashAndCashEquivalents",),
    "debt_current_local": (
        "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
        "ShorttermBorrowings",
    ),
    "debt_noncurrent_local": ("LongtermBorrowings", "Borrowings"),
    "equity_local": (
        "EquityAttributableToOwnersOfParent",
        "Equity",
    ),
    "shares_outstanding": ("NumberOfSharesOutstanding",),
}

FLOW_METRICS = {
    "revenue_local",
    "operating_profit_local",
    "pretax_profit_local",
    "income_tax_local",
    "cfo_local",
    "capex_local",
    "depreciation_amortization_local",
}

MONTHS = {
    name: index
    for index, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _facts(payload: dict[str, object], concepts: tuple[str, ...], unit: str) -> pd.DataFrame:
    namespace = payload.get("facts", {}).get("ifrs-full", {})
    rows: list[dict[str, object]] = []
    for priority, concept in enumerate(concepts):
        node = namespace.get(concept)
        if not node:
            continue
        units = node.get("units", {})
        selected_unit = unit if unit in units else next(iter(units), None)
        if selected_unit is None:
            continue
        for item in units[selected_unit]:
            if item.get("form") != "20-F":
                continue
            rows.append(
                {
                    **item,
                    "concept": concept,
                    "concept_priority": priority,
                    "unit": selected_unit,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if "start" not in frame:
        frame["start"] = pd.NaT
    frame["start"] = pd.to_datetime(frame["start"], errors="coerce")
    frame["end"] = pd.to_datetime(frame["end"], errors="coerce")
    frame["filed"] = pd.to_datetime(frame["filed"], errors="coerce")
    frame["duration_days"] = (frame["end"] - frame["start"]).dt.days
    return frame


def _select(
    frame: pd.DataFrame, *, accession: str, report_date: str, flow: bool
) -> tuple[float, str, str]:
    if frame.empty:
        return np.nan, "NOT_IDENTIFIED", "NOT_IDENTIFIED"
    candidates = frame.loc[
        frame["accn"].eq(accession)
        & frame["end"].eq(pd.Timestamp(report_date))
    ].copy()
    if flow:
        candidates = candidates.loc[candidates["duration_days"].between(300, 390)]
    else:
        candidates = candidates.loc[candidates["start"].isna()]
    if candidates.empty:
        return np.nan, "NOT_IDENTIFIED", "NOT_IDENTIFIED"
    selected = candidates.sort_values(["concept_priority", "filed"]).iloc[0]
    return float(selected["val"]), str(selected["concept"]), str(selected["unit"])


def _currency(payload: dict[str, object]) -> str:
    revenue = payload["facts"]["ifrs-full"]["Revenue"]["units"]
    candidates = [unit for unit in revenue if unit not in {"USD", "shares", "pure"}]
    return candidates[0] if candidates else next(iter(revenue))


def _annual_ifrs(
    *, project_root: Path, manifest: dict[str, object]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    facts_path = project_root / manifest["companyfacts_path"]
    if _sha(facts_path) != manifest["companyfacts_sha256"]:
        raise ValueError(f"IFRS companyfacts hash mismatch: {facts_path}")
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    currency = _currency(payload)
    facts = {
        metric: _facts(
            payload,
            concepts,
            "shares" if metric == "shares_outstanding" else currency,
        )
        for metric, concepts in IFRS_CONCEPTS.items()
    }
    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    for filing in manifest["filings"]:
        if filing["form"] != "20-F":
            continue
        row: dict[str, object] = {
            "subindustry_code": manifest["subindustry_code"],
            "ticker": manifest["ticker"],
            "fiscal_year": pd.Timestamp(filing["report_date"]).year,
            "report_date": filing["report_date"],
            "filing_date": filing["filing_date"],
            "accession_number": filing["accession_number"],
            "reporting_currency": currency,
            "source_url": filing["source_url"],
            "source_path": filing["local_path"],
            "source_sha256": filing["sha256"],
        }
        for metric, frame in facts.items():
            value, concept, unit = _select(
                frame,
                accession=filing["accession_number"],
                report_date=filing["report_date"],
                flow=metric in FLOW_METRICS,
            )
            row[metric] = value
            selections.append(
                {
                    "ticker": manifest["ticker"],
                    "fiscal_year": row["fiscal_year"],
                    "metric": metric,
                    "value": value,
                    "concept": concept,
                    "unit": unit,
                    "available": pd.notna(value),
                    "accession_number": filing["accession_number"],
                }
            )
        rows.append(row)
    annual = pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)
    if annual.empty:
        return annual, pd.DataFrame(selections)
    annual["operating_margin_pct"] = (
        annual["operating_profit_local"] / annual["revenue_local"] * 100.0
    )
    annual["effective_tax_rate_pct"] = (
        annual["income_tax_local"] / annual["pretax_profit_local"] * 100.0
    ).where(lambda values: values.between(0.0, 50.0), 21.0)
    annual["nopat_local"] = annual["operating_profit_local"] * (
        1.0 - annual["effective_tax_rate_pct"] / 100.0
    )
    annual["total_debt_local"] = annual[
        ["debt_current_local", "debt_noncurrent_local"]
    ].sum(axis=1, min_count=1)
    annual["invested_capital_local"] = (
        annual["total_debt_local"] + annual["equity_local"] - annual["cash_local"]
    )
    annual["average_invested_capital_local"] = (
        annual["invested_capital_local"]
        + annual["invested_capital_local"].shift(1)
    ) / 2.0
    annual["reported_roic_pct"] = (
        annual["nopat_local"] / annual["average_invested_capital_local"] * 100.0
    )
    assets = ["receivables_local", "inventory_local"]
    liabilities = ["accounts_payable_local", "contract_liabilities_local"]
    observed_assets = [item for item in assets if annual[item].notna().any()]
    observed_liabilities = [item for item in liabilities if annual[item].notna().any()]
    scope = observed_assets + observed_liabilities
    annual["operating_nwc_scope"] = "|".join(scope) if scope else "NOT_IDENTIFIED"
    complete = (
        annual[scope].notna().all(axis=1)
        if observed_assets and observed_liabilities
        else pd.Series(False, index=annual.index)
    )
    annual["operating_nwc_minimum_scope_pass"] = complete
    annual["operating_nwc_local"] = (
        annual[observed_assets].sum(axis=1)
        - annual[observed_liabilities].sum(axis=1)
    ).where(complete)
    annual["change_operating_nwc_local"] = annual["operating_nwc_local"].diff()
    annual["core_reinvestment_local"] = (
        annual["capex_local"]
        - annual["depreciation_amortization_local"]
        + annual["change_operating_nwc_local"]
    )
    annual["core_reinvestment_claim_allowed"] = annual[
        [
            "capex_local",
            "depreciation_amortization_local",
            "change_operating_nwc_local",
            "nopat_local",
        ]
    ].notna().all(axis=1)
    annual["core_reinvestment_rate_pct"] = (
        annual["core_reinvestment_local"] / annual["nopat_local"] * 100.0
    ).where(annual["core_reinvestment_claim_allowed"])
    annual["terminal_input_allowed"] = False
    annual["fair_value_authority"] = False
    return annual, pd.DataFrame(selections)


def _clean_cell(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _number(value: object) -> float:
    cleaned = _clean_cell(value).replace(",", "")
    cleaned = re.sub(r"[^0-9.()-]", "", cleaned)
    if not cleaned:
        return np.nan
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    result = float(pd.to_numeric(cleaned, errors="coerce"))
    return -result if negative else result


def build_pac_passenger_traffic(
    *, project_root: Path, manifest: dict[str, object]
) -> dict[str, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    title = re.compile(
        r"Reports\s+(?:I|i)n\s+([A-Za-z]+)\s+(20\d{2})\s+(?:a\s+)?Passenger\s+Traffic",
        re.IGNORECASE,
    )
    for filing in manifest["filings"]:
        if filing["form"] != "6-K":
            continue
        path = project_root / filing["local_path"]
        content = path.read_bytes()
        if _sha(path) != filing["sha256"]:
            raise ValueError(f"PAC 6-K hash mismatch: {path}")
        html = content.decode("utf-8", errors="ignore")
        plain = re.sub(r"<[^>]+>", " ", html)
        plain = re.sub(r"&(?:#\d+|[A-Za-z]+);", " ", plain)
        match = title.search(plain)
        if not match or match.group(1).title() not in MONTHS:
            continue
        month_name, year_text = match.group(1).title(), match.group(2)
        target_period = pd.Period(
            f"{year_text}-{MONTHS[month_name]:02d}", freq="M"
        )
        candidates: list[float] = []
        try:
            tables = pd.read_html(StringIO(html))
        except ValueError:
            tables = []
        for table in tables:
            normalized = table.map(_clean_cell)
            header_candidates = normalized.index[
                normalized.apply(
                    lambda row: row.str.fullmatch("Airport", case=False).any(),
                    axis=1,
                )
            ]
            if len(header_candidates) == 0:
                continue
            header_index = header_candidates[0]
            header = normalized.loc[header_index].tolist()
            body = normalized.loc[header_index + 1 :].copy()
            body.columns = [f"{value}_{index}" for index, value in enumerate(header)]
            airport_column = next(
                (column for column in body if column.lower().startswith("airport_")),
                None,
            )
            if airport_column is None:
                continue
            total = body.loc[body[airport_column].str.fullmatch("Total", case=False)]
            if total.empty:
                continue
            month_pattern = re.compile(
                rf"{month_name[:3]}\s*-?\s*{str(target_period.year)[-2:]}",
                re.IGNORECASE,
            )
            current_columns = [
                column for column in body if month_pattern.search(column)
            ]
            for column in current_columns:
                value = _number(total.iloc[0][column])
                if np.isfinite(value) and value >= 0:
                    candidates.append(value)
        if not candidates:
            source_rows.append(
                {
                    "period": str(target_period),
                    "filing_date": filing["filing_date"],
                    "source_path": filing["local_path"],
                    "source_sha256": filing["sha256"],
                    "selection_status": "TRAFFIC_RELEASE_TABLE_NOT_IDENTIFIED",
                }
            )
            continue
        # Domestic, international and combined tables coexist. The combined total
        # is the maximum and is selected by an outcome-independent accounting rule.
        value = max(candidates)
        rows.append(
            {
                "ticker": "PAC",
                "subindustry_code": "airport_services",
                "period": str(target_period),
                "terminal_passengers_thousands": value,
                "filing_date": filing["filing_date"],
                "available_at": filing["filing_date"],
                "source_url": filing["source_url"],
                "source_path": filing["local_path"],
                "source_sha256": filing["sha256"],
                "quantity_anchor": "TOTAL_TERMINAL_PASSENGERS",
                "historical_pit_input": True,
                "selection_rule": "MAX_TOTAL_ACROSS_DOMESTIC_INTERNATIONAL_COMBINED_TABLES",
            }
        )
        source_rows.append(
            {
                "period": str(target_period),
                "filing_date": filing["filing_date"],
                "source_path": filing["local_path"],
                "source_sha256": filing["sha256"],
                "selection_status": "PARSED",
            }
        )
    monthly = pd.DataFrame(rows)
    if not monthly.empty:
        monthly = monthly.sort_values(["period", "filing_date"]).drop_duplicates(
            "period", keep="first"
        )
        monthly["period_m"] = pd.PeriodIndex(monthly["period"], freq="M")
        monthly["quarter"] = monthly["period_m"].dt.asfreq("Q").astype(str)
        monthly["year"] = monthly["period_m"].dt.year
        monthly["passenger_yoy_pct"] = (
            monthly["terminal_passengers_thousands"]
            / monthly["terminal_passengers_thousands"].shift(12)
            * 100.0
            - 100.0
        )
        quarterly = monthly.groupby("quarter", as_index=False).agg(
            months=("period", "nunique"),
            terminal_passengers_thousands=("terminal_passengers_thousands", "sum"),
            latest_available_at=("available_at", "max"),
        )
        quarterly["complete_quarter"] = quarterly["months"].eq(3)
        quarterly["passenger_yoy_pct"] = (
            quarterly["terminal_passengers_thousands"]
            / quarterly["terminal_passengers_thousands"].shift(4)
            * 100.0
            - 100.0
        )
    else:
        quarterly = pd.DataFrame()
    return {
        "pac_monthly_passenger_traffic": monthly,
        "pac_quarterly_passenger_traffic": quarterly,
        "pac_6k_traffic_selection_audit": pd.DataFrame(source_rows),
    }


def build_ifrs_evidence(
    *, project_root: Path, catalog_manifest_path: Path
) -> dict[str, pd.DataFrame]:
    catalog = json.loads(catalog_manifest_path.read_text(encoding="utf-8"))
    annual_frames: list[pd.DataFrame] = []
    selection_frames: list[pd.DataFrame] = []
    source_rows: list[dict[str, object]] = []
    passenger: dict[str, pd.DataFrame] = {}
    for company in catalog["companies"]:
        manifest_path = project_root / company["manifest_path"]
        if _sha(manifest_path) != company["manifest_sha256"]:
            raise ValueError(f"IFRS manifest hash mismatch: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        annual, selections = _annual_ifrs(project_root=project_root, manifest=manifest)
        annual_frames.append(annual)
        selection_frames.append(selections)
        source_rows.append(
            {
                **company,
                "hashes_verified": True,
                "annual_rows": len(annual),
                "operating_margin_rows": int(annual["operating_margin_pct"].notna().sum()),
                "roic_rows": int(annual["reported_roic_pct"].notna().sum()),
                "core_reinvestment_rows": int(
                    annual["core_reinvestment_claim_allowed"].sum()
                ),
                "quarterly_financial_history_ready": False,
                "terminal_input_allowed": False,
            }
        )
        if company["ticker"] == "PAC":
            passenger = build_pac_passenger_traffic(
                project_root=project_root, manifest=manifest
            )
    return {
        "ifrs_source_inventory": pd.DataFrame(source_rows),
        "ifrs_annual_financial_history": pd.concat(annual_frames, ignore_index=True),
        "ifrs_metric_selection_audit": pd.concat(selection_frames, ignore_index=True),
        **passenger,
    }
