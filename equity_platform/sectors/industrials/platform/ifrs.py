from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .ifrs_rules import build_ifrs_rule_evidence


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
    # AdditionsToNoncurrentAssets is deliberately excluded: for concession
    # operators it can be a balance-like disclosure, not period cash CapEx.
    "capex_local": (
        "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment",
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
    "equity_local": ("EquityAttributableToOwnersOfParent", "Equity"),
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
        frame["accn"].eq(accession) & frame["end"].eq(pd.Timestamp(report_date))
    ].copy()
    candidates = (
        candidates.loc[candidates["duration_days"].between(300, 390)]
        if flow
        else candidates.loc[candidates["start"].isna()]
    )
    if candidates.empty:
        return np.nan, "NOT_IDENTIFIED", "NOT_IDENTIFIED"
    selected = candidates.sort_values(["concept_priority", "filed"]).iloc[0]
    return float(selected["val"]), str(selected["concept"]), str(selected["unit"])


def _currency(payload: dict[str, object]) -> str:
    namespace = payload["facts"]["ifrs-full"]
    revenue_node = next(
        (namespace[concept] for concept in IFRS_CONCEPTS["revenue_local"] if concept in namespace),
        None,
    )
    if revenue_node is None:
        raise ValueError("IFRS revenue concept not identified")
    units = revenue_node["units"]
    candidates = [unit for unit in units if unit not in {"USD", "shares", "pure"}]
    return candidates[0] if candidates else next(iter(units))


def _annual_ifrs(
    *, project_root: Path, manifest: dict[str, object]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    facts_path = project_root / str(manifest["companyfacts_path"])
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
                accession=str(filing["accession_number"]),
                report_date=str(filing["report_date"]),
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
                    "parser": "SEC_COMPANYFACTS_IFRS",
                }
            )
        rows.append(row)
    annual = pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)
    return annual, pd.DataFrame(selections)


def _derive_annual_economics(annual: pd.DataFrame) -> pd.DataFrame:
    annual = annual.copy()
    if annual.empty:
        return annual
    if "zero_margin_construction_revenue_local" not in annual:
        annual["zero_margin_construction_revenue_local"] = np.nan
    annual["economic_revenue_local"] = (
        annual["revenue_local"] - annual["zero_margin_construction_revenue_local"]
    ).where(
        annual["zero_margin_construction_revenue_local"].notna(),
        annual["revenue_local"],
    )
    annual["gaap_operating_margin_pct"] = (
        annual["operating_profit_local"] / annual["revenue_local"] * 100.0
    )
    annual["economic_operating_margin_pct"] = (
        annual["operating_profit_local"] / annual["economic_revenue_local"] * 100.0
    )
    annual["operating_margin_pct"] = annual["economic_operating_margin_pct"]
    annual["model_revenue_definition"] = np.where(
        annual["zero_margin_construction_revenue_local"].notna(),
        "GAAP_REVENUE_MINUS_IFRIC12_ZERO_MARGIN_CONSTRUCTION",
        "GAAP_REVENUE",
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
        annual["invested_capital_local"] + annual["invested_capital_local"].shift(1)
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
    # Missing R&D is unknown, never zero. A separate innovation route must earn authority.
    annual["research_development_local"] = np.nan
    annual["innovation_reinvestment_claim_allowed"] = False
    annual["terminal_input_allowed"] = False
    annual["fair_value_authority"] = False
    return annual


def _apply_parser_facts(
    annual: pd.DataFrame, parser_facts: pd.DataFrame
) -> pd.DataFrame:
    annual = annual.copy()
    annual["zero_margin_construction_revenue_local"] = np.nan
    annual["ifric12_rule_id"] = pd.NA
    if annual.empty or parser_facts.empty:
        return _derive_annual_economics(annual)
    capex = parser_facts.loc[parser_facts["metric"].eq("CONCESSION_CAPEX")].copy()
    if not capex.empty:
        capex["fiscal_year"] = pd.to_datetime(capex["period"]).dt.year
        capex = capex.sort_values("available_at").drop_duplicates(
            ["entity", "fiscal_year"], keep="first"
        )
        lookup = capex.set_index(["entity", "fiscal_year"])
        for index, row in annual.iterrows():
            key = (row["ticker"], int(row["fiscal_year"]))
            if key not in lookup.index:
                continue
            fact = lookup.loc[key]
            value = float(fact["value"])
            annual.at[index, "capex_local"] = value
            # IFRIC 12 improvement revenue equals its cost and contributes no
            # operating profit; remove it for the passenger-economics bridge.
            annual.at[index, "zero_margin_construction_revenue_local"] = value
            annual.at[index, "ifric12_rule_id"] = fact["rule_id"]
    return _derive_annual_economics(annual)


def _yoy_by_period(frame: pd.DataFrame, *, periods: int) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    lookup = frame.set_index("period")["terminal_passengers_thousands"]
    frequency = "M" if periods == 12 else "Q"
    current = pd.PeriodIndex(frame["period"], freq=frequency)
    previous_keys = (current - periods).astype(str)
    previous = pd.Series(previous_keys, index=frame.index).map(lookup).astype(float)
    return frame["terminal_passengers_thousands"] / previous * 100.0 - 100.0


def _traffic_frames(rule_evidence: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    facts = rule_evidence["parser_fact_ir"]
    if facts.empty or "metric" not in facts:
        traffic = pd.DataFrame()
    else:
        traffic = facts.loc[facts["metric"].eq("TERMINAL_PASSENGERS")].copy()
    if traffic.empty:
        monthly = pd.DataFrame()
        quarterly = pd.DataFrame()
    else:
        monthly = traffic.rename(
            columns={"entity": "ticker", "value": "terminal_passengers_thousands"}
        ).sort_values(["period", "available_at"])
        monthly = monthly.drop_duplicates("period", keep="first")
        monthly["subindustry_code"] = "airport_services"
        monthly["filing_date"] = monthly["available_at"]
        monthly["quantity_anchor"] = "TOTAL_TERMINAL_PASSENGERS"
        monthly["historical_pit_input"] = True
        monthly["selection_rule"] = monthly["rule_id"]
        monthly["period_m"] = pd.PeriodIndex(monthly["period"], freq="M")
        monthly["quarter"] = monthly["period_m"].dt.asfreq("Q").astype(str)
        monthly["year"] = monthly["period_m"].dt.year
        monthly["passenger_yoy_pct"] = _yoy_by_period(monthly, periods=12)
        quarterly = monthly.groupby("quarter", as_index=False).agg(
            months=("period", "nunique"),
            terminal_passengers_thousands=("terminal_passengers_thousands", "sum"),
            latest_available_at=("available_at", "max"),
        )
        quarterly["complete_quarter"] = quarterly["months"].eq(3)
        quarterly["period"] = quarterly["quarter"]
        quarterly["passenger_yoy_pct"] = _yoy_by_period(quarterly, periods=4).where(
            quarterly["complete_quarter"]
        )
        quarterly = quarterly.drop(columns="period")
    audit = rule_evidence["parser_rule_execution_audit"]
    if not audit.empty:
        audit = audit.loc[
            audit["rule_id"].eq("airport.monthly_terminal_passengers")
        ].copy()
        audit["selection_status"] = audit["status"]
    return {
        "pac_monthly_passenger_traffic": monthly,
        "pac_quarterly_passenger_traffic": quarterly,
        "pac_6k_traffic_selection_audit": audit,
    }


def build_pac_passenger_traffic(
    *, project_root: Path, manifest: dict[str, object]
) -> dict[str, pd.DataFrame]:
    return _traffic_frames(
        build_ifrs_rule_evidence(project_root=project_root, manifest=manifest)
    )


def build_ifrs_evidence(
    *, project_root: Path, catalog_manifest_path: Path
) -> dict[str, pd.DataFrame]:
    catalog = json.loads(catalog_manifest_path.read_text(encoding="utf-8"))
    annual_frames: list[pd.DataFrame] = []
    selection_frames: list[pd.DataFrame] = []
    rule_artifacts: list[dict[str, pd.DataFrame]] = []
    source_rows: list[dict[str, object]] = []
    for company in catalog["companies"]:
        manifest_path = project_root / company["manifest_path"]
        if _sha(manifest_path) != company["manifest_sha256"]:
            raise ValueError(f"IFRS manifest hash mismatch: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        annual, selections = _annual_ifrs(project_root=project_root, manifest=manifest)
        rules = build_ifrs_rule_evidence(project_root=project_root, manifest=manifest)
        annual = _apply_parser_facts(annual, rules["parser_fact_ir"])
        annual_frames.append(annual)
        selection_frames.append(selections)
        rule_artifacts.append(rules)
        quantity_rows = (
            int(rules["parser_fact_ir"]["metric"].eq("TERMINAL_PASSENGERS").sum())
            if not rules["parser_fact_ir"].empty
            else 0
        )
        source_rows.append(
            {
                **company,
                "hashes_verified": True,
                "annual_rows": len(annual),
                "operating_margin_rows": int(annual["operating_margin_pct"].notna().sum()),
                "roic_rows": int(annual["reported_roic_pct"].notna().sum()),
                "core_reinvestment_rows": int(annual["core_reinvestment_claim_allowed"].sum()),
                "quantity_anchor_rows": quantity_rows,
                "parser_rule_count": len(rules["parser_rule_inventory"]),
                "quarterly_financial_history_ready": False,
                "terminal_input_allowed": False,
            }
        )

    def concat(key: str) -> pd.DataFrame:
        frames = [artifact[key] for artifact in rule_artifacts if not artifact[key].empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    combined_rules = {
        "parser_rule_inventory": concat("parser_rule_inventory"),
        "parser_rule_execution_audit": concat("parser_rule_execution_audit"),
        "parser_fact_ir": concat("parser_fact_ir"),
    }
    return {
        "ifrs_source_inventory": pd.DataFrame(source_rows),
        "ifrs_annual_financial_history": pd.concat(annual_frames, ignore_index=True),
        "ifrs_metric_selection_audit": pd.concat(selection_frames, ignore_index=True),
        **combined_rules,
        **_traffic_frames(combined_rules),
    }
