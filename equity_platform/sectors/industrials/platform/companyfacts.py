from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


CONCEPTS: dict[str, tuple[str, ...]] = {
    "shares_outstanding": ("EntityCommonStockSharesOutstanding",),
    "diluted_weighted_average_shares": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
    "revenue_usd": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "Revenues",
    ),
    "operating_income_usd": ("OperatingIncomeLoss",),
    "pretax_income_usd": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "income_tax_usd": ("IncomeTaxExpenseBenefit",),
    "cfo_usd": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex_usd": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForProceedsFromPropertyPlantAndEquipment",
    ),
    "depreciation_amortization_usd": (
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        "DepreciationAndAmortization",
    ),
    "research_development_usd": ("ResearchAndDevelopmentExpense",),
    "receivables_usd": (
        "AccountsReceivableNetCurrent",
        "AccountsNotesAndLoansReceivableNetCurrent",
        "AccountsReceivableNet",
        "AccountsReceivableGrossCurrent",
    ),
    "inventory_usd": ("InventoryNet",),
    "accounts_payable_usd": (
        "AccountsPayableCurrent",
        "AccountsPayableTradeCurrentAndNoncurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent",
    ),
    "contract_assets_usd": ("ContractWithCustomerAssetCurrent", "UnbilledReceivablesCurrent"),
    "contract_liabilities_usd": (
        "ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueCurrent",
    ),
    "remaining_performance_obligation_usd": ("RevenueRemainingPerformanceObligation",),
    "cash_usd": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "debt_current_usd": (
        "DebtCurrent",
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "OtherLongTermDebtCurrent",
        "FinanceLeaseLiabilityCurrent",
    ),
    "debt_noncurrent_usd": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "FinanceLeaseLiabilityNoncurrent",
    ),
    "equity_usd": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "goodwill_usd": ("Goodwill",),
    "intangibles_ex_goodwill_usd": (
        "FiniteLivedIntangibleAssetsNet",
        "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
    ),
    "stock_compensation_usd": ("ShareBasedCompensation",),
}

INCOME_FLOWS = {"revenue_usd", "operating_income_usd", "pretax_income_usd", "income_tax_usd"}
CUMULATIVE_FLOWS = {
    "cfo_usd",
    "capex_usd",
    "depreciation_amortization_usd",
    "research_development_usd",
    "stock_compensation_usd",
    "diluted_weighted_average_shares",
}
FLOW_METRICS = INCOME_FLOWS | CUMULATIVE_FLOWS
NOTE_METRICS = {
    "research_development_usd",
    "contract_assets_usd",
    "contract_liabilities_usd",
    "remaining_performance_obligation_usd",
    "stock_compensation_usd",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _facts(
    payload: dict[str, object], aliases: Iterable[str], *, namespace: str = "us-gaap"
) -> pd.DataFrame:
    us_gaap = payload.get("facts", {}).get(namespace, {})
    rows: list[dict[str, object]] = []
    for priority, concept in enumerate(aliases):
        node = us_gaap.get(concept)
        if not node:
            continue
        units = node.get("units", {})
        unit = "USD" if "USD" in units else next(iter(units), None)
        if unit is None:
            continue
        for item in units[unit]:
            if item.get("form") not in {"10-K", "10-Q"}:
                continue
            rows.append(
                {
                    **item,
                    "concept": concept,
                    "concept_priority": priority,
                    "unit": unit,
                }
            )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        if "start" not in frame:
            frame["start"] = pd.NaT
        frame["start"] = pd.to_datetime(
            frame["start"], errors="coerce", format="mixed"
        ).astype("datetime64[ns]")
        frame["end"] = pd.to_datetime(
            frame["end"], errors="coerce", format="mixed"
        ).astype("datetime64[ns]")
        frame["filed"] = pd.to_datetime(
            frame["filed"], errors="coerce", format="mixed"
        ).astype("datetime64[ns]")
        frame["duration_days"] = (frame["end"] - frame["start"]).dt.days
    return frame


def _select(
    frame: pd.DataFrame,
    *,
    accession: str,
    report_date: str,
    form: str,
    fiscal_period: str,
    metric: str,
) -> tuple[float, str | None, float, str]:
    if frame.empty:
        return np.nan, None, np.nan, "NOT_IDENTIFIED"
    if metric == "shares_outstanding":
        candidates = frame.loc[
            frame["accn"].eq(accession)
            & frame["form"].eq(form)
            & frame["start"].isna()
        ].copy()
        if not candidates.empty:
            selected = candidates.sort_values(
                ["concept_priority", "end"], ascending=[True, False]
            ).iloc[0]
            return (
                float(selected["val"]),
                str(selected["concept"]),
                np.nan,
                "COVER_PAGE_INSTANT",
            )
    candidates = frame.loc[
        frame["accn"].eq(accession)
        & frame["form"].eq(form)
        & frame["end"].eq(pd.Timestamp(report_date))
    ].copy()
    if candidates.empty:
        return np.nan, None, np.nan, "NOT_IDENTIFIED"
    if metric not in FLOW_METRICS:
        candidates = candidates.loc[candidates["start"].isna()]
        if candidates.empty:
            return np.nan, None, np.nan, "NOT_IDENTIFIED"
        selected = candidates.sort_values(["concept_priority", "filed"]).iloc[0]
        return float(selected["val"]), str(selected["concept"]), np.nan, "INSTANT"
    candidates = candidates.loc[candidates["duration_days"].between(55, 390)]
    if candidates.empty:
        return np.nan, None, np.nan, "NOT_IDENTIFIED"
    if form == "10-K" or fiscal_period == "FY":
        candidates = candidates.loc[candidates["duration_days"].between(300, 390)]
        ascending = [True, False]
    elif metric in INCOME_FLOWS:
        quarter = candidates.loc[candidates["duration_days"].between(55, 115)]
        if not quarter.empty:
            candidates = quarter
        ascending = [True, True]
    else:
        ascending = [True, False]
    if candidates.empty:
        return np.nan, None, np.nan, "NOT_IDENTIFIED"
    selected = candidates.sort_values(
        ["concept_priority", "duration_days"], ascending=ascending
    ).iloc[0]
    selection = "DISCRETE_FLOW" if selected["duration_days"] <= 115 else "CUMULATIVE_FLOW"
    return (
        float(selected["val"]),
        str(selected["concept"]),
        float(selected["duration_days"]),
        selection,
    )


def _quarterly(periodic: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (ticker, fiscal_year), group in periodic.groupby(["ticker", "fiscal_year"]):
        quarters = group.loc[group["fiscal_period"].isin(["Q1", "Q2", "Q3"])]
        annual = group.loc[group["fiscal_period"].eq("FY")]
        for row in quarters.itertuples(index=False):
            result = {
                "subindustry_code": row.subindustry_code,
                "ticker": ticker,
                "fiscal_year": fiscal_year,
                "fiscal_period": row.fiscal_period,
                "period": row.period,
                "report_date": row.report_date,
                "filing_date": row.filing_date,
                "form": row.form,
                "accession_number": row.accession_number,
                "source_url": row.source_url,
                "source_sha256": row.source_sha256,
            }
            quarter_number = int(row.fiscal_period[-1])
            for metric in FLOW_METRICS:
                value = getattr(row, metric)
                selection = getattr(row, f"{metric}_selection")
                if selection == "DISCRETE_FLOW" or quarter_number == 1:
                    discrete = value
                else:
                    prior = quarters.loc[
                        quarters["fiscal_period"].eq(f"Q{quarter_number - 1}"), metric
                    ]
                    discrete = value - prior.iloc[0] if pd.notna(value) and not prior.empty and pd.notna(prior.iloc[0]) else np.nan
                result[metric] = discrete
            for metric in set(CONCEPTS) - FLOW_METRICS:
                result[metric] = getattr(row, metric)
            rows.append(result)
        if not annual.empty:
            row = annual.sort_values("filing_date").iloc[0]
            result = {
                "subindustry_code": row["subindustry_code"],
                "ticker": ticker,
                "fiscal_year": fiscal_year,
                "fiscal_period": "Q4",
                "period": row["period"],
                "report_date": row["report_date"],
                "filing_date": row["filing_date"],
                "form": row["form"],
                "accession_number": row["accession_number"],
                "source_url": row["source_url"],
                "source_sha256": row["source_sha256"],
            }
            for metric in FLOW_METRICS:
                prior_sum = sum(
                    item[metric]
                    for item in rows
                    if item["ticker"] == ticker
                    and item["fiscal_year"] == fiscal_year
                    and item["fiscal_period"] in {"Q1", "Q2", "Q3"}
                    and pd.notna(item[metric])
                )
                prior_count = sum(
                    1
                    for item in rows
                    if item["ticker"] == ticker
                    and item["fiscal_year"] == fiscal_year
                    and item["fiscal_period"] in {"Q1", "Q2", "Q3"}
                    and pd.notna(item[metric])
                )
                result[metric] = row[metric] - prior_sum if pd.notna(row[metric]) and prior_count == 3 else np.nan
            for metric in set(CONCEPTS) - FLOW_METRICS:
                result[metric] = row[metric]
            rows.append(result)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["operating_margin_pct"] = frame["operating_income_usd"] / frame["revenue_usd"] * 100.0
    frame["pretax_margin_pct"] = frame["pretax_income_usd"] / frame["revenue_usd"] * 100.0
    frame["model_profit_margin_pct"] = np.nan
    frame["model_profit_target_definition"] = "NOT_IDENTIFIED"
    frame["model_profit_target_authority"] = "NOT_IDENTIFIED"
    for ticker, index in frame.groupby("ticker").groups.items():
        operating_coverage = frame.loc[index, "operating_margin_pct"].notna().mean()
        pretax_coverage = frame.loc[index, "pretax_margin_pct"].notna().mean()
        if operating_coverage >= 0.80:
            frame.loc[index, "model_profit_margin_pct"] = frame.loc[
                index, "operating_margin_pct"
            ]
            frame.loc[index, "model_profit_target_definition"] = "OPERATING_MARGIN"
            frame.loc[index, "model_profit_target_authority"] = "REPORTED_STANDARD_TAG"
        elif pretax_coverage >= 0.80:
            frame.loc[index, "model_profit_margin_pct"] = frame.loc[
                index, "pretax_margin_pct"
            ]
            frame.loc[index, "model_profit_target_definition"] = "PROFIT_PROXY_PRETAX"
            frame.loc[index, "model_profit_target_authority"] = (
                "PROXY_NOT_OPERATING_MARGIN"
            )
    frame["effective_tax_rate_pct"] = (frame["income_tax_usd"] / frame["pretax_income_usd"] * 100.0).where(lambda values: values.between(0.0, 50.0))
    frame["nopat_usd"] = frame["operating_income_usd"] * (1.0 - frame["effective_tax_rate_pct"].fillna(21.0) / 100.0)
    frame["fcff_cash_proxy_usd"] = frame["cfo_usd"] - frame["capex_usd"]
    frame["historical_pit_input"] = True
    frame["terminal_input_allowed"] = False
    return frame.sort_values(["ticker", "report_date"]).reset_index(drop=True)


def _annual_reinvestment(periodic: pd.DataFrame) -> pd.DataFrame:
    annual = periodic.loc[periodic["fiscal_period"].eq("FY")].copy()
    annual = annual.sort_values(["ticker", "fiscal_year"])
    annual["effective_tax_rate_pct"] = (
        annual["income_tax_usd"] / annual["pretax_income_usd"] * 100.0
    ).where(lambda values: values.between(0.0, 50.0), 21.0)
    annual["nopat_usd"] = annual["operating_income_usd"] * (
        1.0 - annual["effective_tax_rate_pct"] / 100.0
    )
    annual["operating_margin_pct"] = (
        annual["operating_income_usd"] / annual["revenue_usd"] * 100.0
    )
    annual["pretax_margin_pct"] = (
        annual["pretax_income_usd"] / annual["revenue_usd"] * 100.0
    )
    annual["total_debt_usd"] = annual["debt_current_usd"].fillna(0.0) + annual[
        "debt_noncurrent_usd"
    ].fillna(0.0)
    annual["invested_capital_usd"] = (
        annual["total_debt_usd"] + annual["equity_usd"] - annual["cash_usd"]
    )
    annual["average_invested_capital_usd"] = annual.groupby("ticker")[
        "invested_capital_usd"
    ].transform(lambda values: (values + values.shift(1)) / 2.0)
    annual["reported_roic_pct"] = (
        annual["nopat_usd"] / annual["average_invested_capital_usd"] * 100.0
    )
    asset_components = ["receivables_usd", "inventory_usd", "contract_assets_usd"]
    liability_components = ["accounts_payable_usd", "contract_liabilities_usd"]
    annual["operating_nwc_usd"] = np.nan
    annual["operating_nwc_component_count"] = 0
    annual["operating_nwc_scope"] = "NOT_IDENTIFIED"
    annual["operating_nwc_minimum_scope_pass"] = False
    for ticker, index in annual.groupby("ticker").groups.items():
        observed_assets = [
            metric for metric in asset_components if annual.loc[index, metric].notna().any()
        ]
        observed_liabilities = [
            metric
            for metric in liability_components
            if annual.loc[index, metric].notna().any()
        ]
        scope = observed_assets + observed_liabilities
        minimum_scope = bool(observed_assets and observed_liabilities)
        annual.loc[index, "operating_nwc_component_count"] = len(scope)
        annual.loc[index, "operating_nwc_scope"] = (
            "|".join(scope) if scope else "NOT_IDENTIFIED"
        )
        if not minimum_scope:
            continue
        # A component never reported by this company is treated as outside the
        # observable scope, not as a measured zero. An observed component must
        # still be present in each period; partial-period gaps fail closed.
        complete = annual.loc[index, scope].notna().all(axis=1)
        assets = annual.loc[index, observed_assets].sum(axis=1)
        liabilities = annual.loc[index, observed_liabilities].sum(axis=1)
        annual.loc[index, "operating_nwc_usd"] = (assets - liabilities).where(
            complete
        )
        annual.loc[index, "operating_nwc_minimum_scope_pass"] = complete
    annual["operating_nwc_complete"] = annual["operating_nwc_minimum_scope_pass"]
    annual["change_operating_nwc_usd"] = annual.groupby("ticker")[
        "operating_nwc_usd"
    ].diff()
    annual["core_reinvestment_usd"] = (
        annual["capex_usd"]
        - annual["depreciation_amortization_usd"]
        + annual["change_operating_nwc_usd"]
    )
    annual["core_reinvestment_claim_allowed"] = annual[
        [
            "capex_usd",
            "depreciation_amortization_usd",
            "change_operating_nwc_usd",
            "nopat_usd",
        ]
    ].notna().all(axis=1)
    annual["core_reinvestment_usd"] = annual["core_reinvestment_usd"].where(
        annual["core_reinvestment_claim_allowed"]
    )
    annual["core_reinvestment_rate_pct"] = (
        annual["core_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    )
    annual["innovation_adjusted_reinvestment_usd"] = (
        annual["core_reinvestment_usd"] + annual["research_development_usd"]
    )
    annual["innovation_adjusted_reinvestment_rate_pct"] = (
        annual["innovation_adjusted_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    )
    annual["innovation_adjusted_reinvestment_claim_allowed"] = annual[
        ["core_reinvestment_usd", "research_development_usd"]
    ].notna().all(axis=1)
    annual["terminal_input_allowed"] = False
    return annual.reset_index(drop=True)


def build_subindustry_companyfacts_evidence(
    *, project_root: Path, catalog_manifest_path: Path, cutoff: pd.Timestamp
) -> dict[str, pd.DataFrame]:
    catalog = json.loads(catalog_manifest_path.read_text(encoding="utf-8"))
    periodic_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    for company in catalog["companies"]:
        if company["status"] != "READY":
            continue
        manifest_path = project_root / company["manifest_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        companyfacts_path = project_root / manifest["companyfacts_path"]
        submissions_path = project_root / manifest["submissions_path"]
        if _sha256(companyfacts_path) != manifest["companyfacts_sha256"]:
            raise ValueError(f"Companyfacts hash mismatch: {companyfacts_path}")
        if _sha256(submissions_path) != manifest["submissions_sha256"]:
            raise ValueError(f"Submissions hash mismatch: {submissions_path}")
        payload = json.loads(companyfacts_path.read_text(encoding="utf-8"))
        metric_facts = {
            metric: _facts(
                payload,
                aliases,
                namespace="dei" if metric == "shares_outstanding" else "us-gaap",
            )
            for metric, aliases in CONCEPTS.items()
        }
        all_metric_facts = pd.concat(
            [frame for frame in metric_facts.values() if not frame.empty],
            ignore_index=True,
        )
        for filing in manifest["filings"]:
            if pd.Timestamp(filing["filing_date"]) > cutoff:
                continue
            metadata = all_metric_facts.loc[
                all_metric_facts["accn"].eq(filing["accession_number"])
                & all_metric_facts["end"].eq(pd.Timestamp(filing["report_date"]))
            ]
            if metadata.empty:
                continue
            fiscal_year = int(metadata["fy"].dropna().mode().iloc[0])
            fiscal_period = str(metadata["fp"].dropna().mode().iloc[0])
            row: dict[str, object] = {
                "subindustry_code": filing["subindustry_code"],
                "ticker": filing["ticker"],
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "period": str(pd.Period(filing["report_date"], freq="Q")),
                "report_date": filing["report_date"],
                "filing_date": filing["filing_date"],
                "form": filing["form"],
                "accession_number": filing["accession_number"],
                "source_url": filing["source_url"],
                "source_sha256": filing["sha256"],
            }
            for metric, frame in metric_facts.items():
                value, concept, duration, selection = _select(
                    frame,
                    accession=filing["accession_number"],
                    report_date=filing["report_date"],
                    form=filing["form"],
                    fiscal_period=fiscal_period,
                    metric=metric,
                )
                row[metric] = value
                row[f"{metric}_selection"] = selection
                selection_rows.append(
                    {
                        "subindustry_code": filing["subindustry_code"],
                        "ticker": filing["ticker"],
                        "period": row["period"],
                        "fiscal_year": fiscal_year,
                        "fiscal_period": fiscal_period,
                        "metric": metric,
                        "concept": concept,
                        "value": value,
                        "duration_days": duration,
                        "selection": selection,
                        "evidence_layer": "NOTE" if metric in NOTE_METRICS else "FINANCIAL_STATEMENT",
                        "available": bool(pd.notna(value)),
                        "filing_date": filing["filing_date"],
                        "accession_number": filing["accession_number"],
                    }
                )
            periodic_rows.append(row)
        source_rows.append(
            {
                "subindustry_code": manifest["subindustry_code"],
                "ticker": manifest["ticker"],
                "cik": manifest["cik"],
                "filings": len(manifest["filings"]),
                "form_10k_count": sum(row["form"] == "10-K" for row in manifest["filings"]),
                "form_10q_count": sum(row["form"] == "10-Q" for row in manifest["filings"]),
                "manifest_path": str(manifest_path),
                "manifest_sha256": _sha256(manifest_path),
                "companyfacts_sha256": manifest["companyfacts_sha256"],
                "submissions_sha256": manifest["submissions_sha256"],
                "hashes_verified": True,
            }
        )
    periodic = pd.DataFrame(periodic_rows).sort_values(["ticker", "report_date"])
    selections = pd.DataFrame(selection_rows)
    coverage = selections.groupby(
        ["subindustry_code", "ticker", "evidence_layer", "metric"], as_index=False
    ).agg(filings=("available", "size"), available_filings=("available", "sum"))
    coverage["coverage_pct"] = coverage["available_filings"] / coverage["filings"] * 100.0
    quarterly = _quarterly(periodic)
    annual = _annual_reinvestment(periodic)
    summaries: list[dict[str, object]] = []
    for (subindustry, ticker), group in quarterly.groupby(["subindustry_code", "ticker"]):
        annual_group = annual.loc[annual["ticker"].eq(ticker)]
        note = coverage.loc[
            coverage["ticker"].eq(ticker) & coverage["evidence_layer"].eq("NOTE")
        ]
        summaries.append(
            {
                "subindustry_code": subindustry,
                "ticker": ticker,
                "quarterly_rows": len(group),
                "quarterly_revenue_rows": int(group["revenue_usd"].notna().sum()),
                "quarterly_margin_rows": int(group["operating_margin_pct"].notna().sum()),
                "quarterly_model_profit_rows": int(
                    group["model_profit_margin_pct"].notna().sum()
                ),
                "model_profit_target_definition": str(
                    group["model_profit_target_definition"].mode().iloc[0]
                ),
                "model_profit_target_authority": str(
                    group["model_profit_target_authority"].mode().iloc[0]
                ),
                "annual_rows": len(annual_group),
                "reported_roic_rows": int(annual_group["reported_roic_pct"].notna().sum()),
                "core_reinvestment_rows": int(annual_group["core_reinvestment_rate_pct"].notna().sum()),
                "innovation_reinvestment_rows": int(annual_group["innovation_adjusted_reinvestment_claim_allowed"].sum()),
                "note_metric_mean_coverage_pct": float(note["coverage_pct"].mean()),
                "company_forecast_history_ready": bool(
                    group["revenue_usd"].notna().sum() >= 16
                    and group["model_profit_margin_pct"].notna().sum() >= 16
                ),
                "roic_reinvestment_research_ready": bool(
                    annual_group["reported_roic_pct"].notna().sum() >= 3
                ),
                "terminal_input_allowed": False,
            }
        )
    return {
        "subindustry_sec_source_inventory": pd.DataFrame(source_rows),
        "subindustry_companyfacts_metric_selections": selections,
        "subindustry_companyfacts_metric_coverage": coverage,
        "subindustry_periodic_financial_history": periodic.reset_index(drop=True),
        "subindustry_quarterly_financial_history": quarterly,
        "subindustry_annual_roic_reinvestment_history": annual,
        "subindustry_companyfacts_summary": pd.DataFrame(summaries),
    }
