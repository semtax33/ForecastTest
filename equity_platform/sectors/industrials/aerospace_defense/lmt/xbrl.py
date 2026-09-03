from __future__ import annotations

from pathlib import Path

from lxml import etree
import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v17.reinvestment import _contexts, _local_name, _numeric


FACTS = {
    "revenue_usd": ("Revenues",),
    "operating_income_usd": ("OperatingIncomeLoss",),
    "pretax_income_usd": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "income_tax_usd": ("IncomeTaxExpenseBenefit",),
    "cfo_usd": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex_usd": ("PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "depreciation_amortization_usd": (
        "DepreciationAndAmortizationIncludingDiscontinuedOperations",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ),
    "research_development_usd": ("ResearchAndDevelopmentExpense",),
    "business_acquisitions_usd": ("PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"),
    "receivables_usd": ("ReceivablesNetCurrent",),
    "inventory_usd": ("InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings", "InventoryNet"),
    "accounts_payable_usd": ("AccountsPayableCurrent",),
    "contract_assets_usd": ("ContractWithCustomerAssetNetCurrent", "ContractWithCustomerAssetNet"),
    "contract_liabilities_usd": ("ContractWithCustomerLiabilityCurrent",),
    "remaining_performance_obligation_usd": ("RevenueRemainingPerformanceObligation",),
    "program_gains_losses_usd": ("ProgramGainsLosses", "ProgramAdditionalGainsLosses", "ClassifiedProgramsGainsLosses"),
    "cash_usd": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt_current_usd": ("LongTermDebtCurrent", "DebtCurrent"),
    "debt_noncurrent_usd": ("LongTermDebtNoncurrent",),
    "equity_usd": ("StockholdersEquity",),
    "goodwill_usd": ("Goodwill",),
    "intangibles_ex_goodwill_usd": ("IntangibleAssetsNetExcludingGoodwill",),
    "pension_liability_usd": ("DefinedBenefitPensionPlanLiabilitiesNoncurrent", "DefinedBenefitPensionPlanCurrentAndNoncurrentLiabilities"),
    "fas_cas_pension_adjustment_usd": ("FasCasPensionAdjustment", "FASAndCASPensionAdjustment"),
}
FLOW_METRICS = {
    "revenue_usd", "operating_income_usd", "pretax_income_usd", "income_tax_usd", "cfo_usd",
    "capex_usd", "depreciation_amortization_usd", "research_development_usd",
    "business_acquisitions_usd", "program_gains_losses_usd", "fas_cas_pension_adjustment_usd",
}


def _parse_filing(path: Path, source: pd.Series) -> pd.DataFrame:
    tree = etree.parse(str(path), etree.XMLParser(recover=True, huge_tree=True))
    contexts = _contexts(tree)
    wanted = {concept for candidates in FACTS.values() for concept in candidates}
    rows: list[dict[str, object]] = []
    for node in tree.xpath("//*[local-name()='nonFraction']"):
        concept = node.get("name", "")
        if _local_name(concept) not in wanted:
            continue
        value = _numeric(node)
        context = contexts.get(node.get("contextRef", ""), {})
        if value is None or not context:
            continue
        rows.append({
            "form": source["form"], "filing_date": source["filing_date"], "report_date": source["report_date"],
            "accession_number": source["accession_number"], "concept": concept, "concept_local": _local_name(concept),
            "value_usd": value, "context_ref": node.get("contextRef"), **context,
            "source_url": source["source_url"], "source_sha256": source["sha256"],
        })
    return pd.DataFrame(rows)


def _select_metric(facts: pd.DataFrame, metric: str, report_date: str, form: str) -> tuple[float, str | None, str | None]:
    candidates = FACTS[metric]
    matching = facts.loc[facts["concept_local"].isin(candidates) & facts["end_date"].eq(report_date)].copy()
    frame = matching.loc[matching["dimension_count"].eq(0)].copy()
    if metric in FLOW_METRICS:
        frame["duration_days"] = (pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])).dt.days
        frame = frame.loc[frame["duration_days"].between(330, 370) if form == "10-K" else frame["duration_days"].between(70, 290)]
    else:
        frame = frame.loc[frame["instant"]]
    if frame.empty and metric == "fas_cas_pension_adjustment_usd":
        dimensional = matching.loc[
            matching["dimension_count"].eq(1)
            & matching["dimensions"].fillna("").str.contains("MaterialReconcilingItemsMember", regex=False)
        ].copy()
        dimensional["duration_days"] = (
            pd.to_datetime(dimensional["end_date"]) - pd.to_datetime(dimensional["start_date"])
        ).dt.days
        frame = dimensional.loc[
            dimensional["duration_days"].between(330, 370)
            if form == "10-K"
            else dimensional["duration_days"].between(70, 290)
        ]
    if frame.empty and metric == "program_gains_losses_usd":
        dimensional = matching.loc[
            matching["dimension_count"].eq(2)
            & matching["dimensions"].fillna("").str.contains("Member", regex=False)
        ].copy()
        dimensional["duration_days"] = (
            pd.to_datetime(dimensional["end_date"]) - pd.to_datetime(dimensional["start_date"])
        ).dt.days
        dimensional = dimensional.loc[
            dimensional["duration_days"].between(330, 370)
            if form == "10-K"
            else dimensional["duration_days"].between(70, 290)
        ]
        if not dimensional.empty:
            max_duration = dimensional["duration_days"].max()
            dimensional = dimensional.loc[dimensional["duration_days"].eq(max_duration)].drop_duplicates("context_ref")
            return (
                float(dimensional["value_usd"].sum()),
                "SUM_SEGMENT_PROGRAM_CONTEXTS",
                "|".join(sorted(dimensional["context_ref"].astype(str).unique())),
            )
    if frame.empty and metric == "debt_current_usd":
        # A zero balance is commonly presented as an omitted line or dash and
        # therefore has no ix:nonFraction fact.  Derive zero only when the same
        # report-date balance sheet contains consolidated non-current debt.
        # The selection table keeps this separate from raw XBRL presence.
        noncurrent = facts.loc[
            facts["concept_local"].eq("LongTermDebtNoncurrent")
            & facts["end_date"].eq(report_date)
            & facts["dimension_count"].eq(0)
            & facts["instant"]
        ]
        if not noncurrent.empty:
            context_ref = str(noncurrent.sort_values("context_ref").iloc[0]["context_ref"])
            return 0.0, "DERIVED:CURRENT_DEBT_ZERO_WHEN_NOT_REPORTED", context_ref
    if frame.empty:
        return np.nan, None, None
    frame["concept_priority"] = frame["concept_local"].map({name: index for index, name in enumerate(candidates)})
    sort = ["concept_priority"] + (["duration_days"] if metric in FLOW_METRICS else []) + ["context_ref"]
    ascending = [True] + ([False] if metric in FLOW_METRICS else []) + [True]
    selected = frame.sort_values(sort, ascending=ascending).iloc[0]
    return float(selected["value_usd"]), str(selected["concept"]), str(selected["context_ref"])


def _quarter(report_date: str) -> int:
    return {3: 1, 6: 2, 9: 3, 12: 4}[pd.Timestamp(report_date).month]


def _select_periodic(sec_inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = pd.concat([_parse_filing(Path(str(source["resolved_path"])), source) for _, source in sec_inventory.iterrows()], ignore_index=True)
    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    for _, source in sec_inventory.sort_values("report_date").iterrows():
        report_date = str(source["report_date"])
        filing = raw.loc[raw["accession_number"].eq(source["accession_number"])]
        row: dict[str, object] = {
            "form": source["form"], "fiscal_year": int(report_date[:4]), "fiscal_quarter": _quarter(report_date),
            "period": f"{report_date[:4]}Q{_quarter(report_date)}", "filing_date": source["filing_date"],
            "report_date": report_date, "source_url": source["source_url"], "source_sha256": source["sha256"],
        }
        for metric in FACTS:
            value, concept, context_ref = _select_metric(filing, metric, report_date, str(source["form"]))
            row[metric] = value
            selections.append({
                "form": source["form"], "period": row["period"], "filing_date": source["filing_date"],
                "accession_number": source["accession_number"], "metric": metric,
                "value_usd": value, "available": bool(np.isfinite(value)), "selected_concept": concept,
                "selected_context_ref": context_ref, "source_url": source["source_url"], "source_sha256": source["sha256"],
                "evidence_layer": "NOTE" if metric in {"contract_assets_usd", "contract_liabilities_usd", "remaining_performance_obligation_usd", "program_gains_losses_usd", "research_development_usd", "business_acquisitions_usd", "pension_liability_usd", "fas_cas_pension_adjustment_usd"} else "FINANCIAL_STATEMENT",
                "selection_rule": (
                    "ZERO_WHEN_CURRENT_DEBT_NOT_REPORTED_AND_NONCURRENT_DEBT_IS_REPORTED"
                    if concept == "DERIVED:CURRENT_DEBT_ZERO_WHEN_NOT_REPORTED"
                    else "SUM_SEGMENT_PROGRAM_CONTEXTS"
                    if concept == "SUM_SEGMENT_PROGRAM_CONTEXTS"
                    else "CONSOLIDATED_NO_DIMENSION_REPORT_DATE_CONTEXT"
                ),
                "derived_value": bool(concept and str(concept).startswith("DERIVED:")),
            })
        rows.append(row)
    return raw, pd.DataFrame(rows).sort_values(["fiscal_year", "fiscal_quarter"]).reset_index(drop=True), pd.DataFrame(selections)


def _annual_bridge(periodic: pd.DataFrame) -> pd.DataFrame:
    annual = periodic.loc[periodic["form"].eq("10-K")].copy().reset_index(drop=True)
    for column in ["business_acquisitions_usd", "research_development_usd", "program_gains_losses_usd", "fas_cas_pension_adjustment_usd"]:
        annual[column] = annual[column].fillna(0.0)
    tax_rate = annual["income_tax_usd"] / annual["pretax_income_usd"]
    annual["effective_tax_rate_pct"] = tax_rate.where(tax_rate.between(0.0, 0.50), 0.21) * 100.0
    annual["nopat_usd"] = annual["operating_income_usd"] * (1.0 - annual["effective_tax_rate_pct"] / 100.0)
    annual["operating_nwc_usd"] = annual["receivables_usd"] + annual["inventory_usd"] + annual["contract_assets_usd"] - annual["accounts_payable_usd"] - annual["contract_liabilities_usd"]
    annual["change_operating_nwc_usd"] = annual["operating_nwc_usd"].diff()
    annual["net_capex_usd"] = annual["capex_usd"] - annual["depreciation_amortization_usd"]
    annual["core_reinvestment_usd"] = annual["net_capex_usd"] + annual["change_operating_nwc_usd"]
    annual["innovation_adjusted_reinvestment_usd"] = annual["core_reinvestment_usd"] + annual["research_development_usd"]
    annual["total_including_mna_reinvestment_usd"] = annual["innovation_adjusted_reinvestment_usd"] + annual["business_acquisitions_usd"]
    annual["total_debt_usd"] = annual["debt_current_usd"].fillna(0.0) + annual["debt_noncurrent_usd"].fillna(0.0)
    annual["invested_capital_usd"] = annual["total_debt_usd"] + annual["equity_usd"] - annual["cash_usd"]
    annual["average_invested_capital_usd"] = (annual["invested_capital_usd"] + annual["invested_capital_usd"].shift(1)) / 2.0
    annual["reported_roic_pct"] = annual["nopat_usd"] / annual["average_invested_capital_usd"] * 100.0
    annual["pension_adjusted_invested_capital_usd"] = annual["invested_capital_usd"] + annual["pension_liability_usd"].fillna(0.0)
    annual["average_pension_adjusted_invested_capital_usd"] = (annual["pension_adjusted_invested_capital_usd"] + annual["pension_adjusted_invested_capital_usd"].shift(1)) / 2.0
    annual["pension_adjusted_roic_pct"] = annual["nopat_usd"] / annual["average_pension_adjusted_invested_capital_usd"] * 100.0
    annual["tangible_invested_capital_usd"] = annual["invested_capital_usd"] - annual["goodwill_usd"].fillna(0.0) - annual["intangibles_ex_goodwill_usd"].fillna(0.0)
    annual["average_tangible_invested_capital_usd"] = (annual["tangible_invested_capital_usd"] + annual["tangible_invested_capital_usd"].shift(1)) / 2.0
    annual["tangible_roic_sensitivity_pct"] = annual["nopat_usd"] / annual["average_tangible_invested_capital_usd"] * 100.0
    for prefix in ["core", "innovation_adjusted", "total_including_mna"]:
        annual[f"{prefix}_reinvestment_rate_pct"] = annual[f"{prefix}_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    annual["incremental_nopat_usd"] = annual["nopat_usd"].diff()
    annual["incremental_roic_on_prior_innovation_reinvestment_pct"] = annual["incremental_nopat_usd"] / annual["innovation_adjusted_reinvestment_usd"].shift(1) * 100.0
    annual["through_cycle_reported_roic_median_pct"] = annual["reported_roic_pct"].rolling(3, min_periods=3).median()
    annual["fcff_cash_proxy_usd"] = annual["cfo_usd"] - annual["capex_usd"]
    annual["fcff_accounting_bridge_usd"] = annual["nopat_usd"] + annual["depreciation_amortization_usd"] - annual["capex_usd"] - annual["change_operating_nwc_usd"]
    annual["fcff_bridge_difference_usd"] = annual["fcff_cash_proxy_usd"] - annual["fcff_accounting_bridge_usd"]
    annual["terminal_input_allowed"] = False
    return annual


def _quarterly_bridge(periodic: pd.DataFrame) -> pd.DataFrame:
    frame = periodic.copy()
    frame["operating_nwc_usd"] = frame["receivables_usd"] + frame["inventory_usd"] + frame["contract_assets_usd"] - frame["accounts_payable_usd"] - frame["contract_liabilities_usd"]
    frame["change_operating_nwc_usd"] = frame["operating_nwc_usd"].diff()
    result = frame[["period", "fiscal_year", "fiscal_quarter", "form", "filing_date", "report_date", "source_url", "source_sha256", "operating_nwc_usd", "change_operating_nwc_usd"]].copy()
    for metric in sorted(FLOW_METRICS):
        values: list[float] = []
        for _, row in frame.iterrows():
            current = row[metric]
            quarter = int(row["fiscal_quarter"])
            if quarter == 1:
                values.append(current)
            else:
                prior = frame.loc[frame["fiscal_year"].eq(row["fiscal_year"]) & frame["fiscal_quarter"].eq(quarter - 1), metric]
                values.append(current - prior.iloc[0] if pd.notna(current) and not prior.empty and pd.notna(prior.iloc[0]) else np.nan)
        result[f"discrete_{metric}"] = values
    result["discrete_effective_tax_rate_pct"] = (result["discrete_income_tax_usd"] / result["discrete_pretax_income_usd"]).where(lambda values: values.between(0.0, 0.50), 0.21) * 100.0
    result["discrete_nopat_usd"] = result["discrete_operating_income_usd"] * (1.0 - result["discrete_effective_tax_rate_pct"] / 100.0)
    result["discrete_fcff_cash_proxy_usd"] = result["discrete_cfo_usd"] - result["discrete_capex_usd"]
    result["quarterly_statement_chain_complete"] = result[["discrete_revenue_usd", "discrete_operating_income_usd", "discrete_income_tax_usd", "discrete_cfo_usd", "discrete_capex_usd", "change_operating_nwc_usd"]].notna().all(axis=1)
    result["quarterly_note_contract_chain_complete"] = frame[["contract_assets_usd", "contract_liabilities_usd", "remaining_performance_obligation_usd"]].notna().all(axis=1).to_numpy()
    result["historical_pit_input"] = True
    result["terminal_input_allowed"] = False
    return result


def build_lmt_reinvestment_roic_evidence(*, sec_inventory: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raw, periodic, selections = _select_periodic(sec_inventory)
    annual = _annual_bridge(periodic)
    quarterly = _quarterly_bridge(periodic)
    raw_presence = raw.groupby("accession_number")["concept_local"].agg(set).to_dict()
    metric_policy = {
        "research_development_usd": "ANNUAL_10K_ONLY",
        "business_acquisitions_usd": "EVENT_CONDITIONAL_NOT_SCORED",
        "program_gains_losses_usd": "EVENT_CONDITIONAL_NOT_SCORED",
        "fas_cas_pension_adjustment_usd": "DISCLOSURE_REGIME_ONLY",
    }
    selections = selections.copy()
    selections["coverage_denominator_policy"] = selections["metric"].map(metric_policy).fillna("ALL_PERIODIC_FILINGS")
    selections["source_concept_present"] = [
        bool(set(FACTS[metric]) & raw_presence.get(accession, set()))
        for metric, accession in selections[["metric", "accession_number"]].itertuples(index=False, name=None)
    ]
    selections["applicable"] = True
    selections.loc[
        selections["coverage_denominator_policy"].eq("ANNUAL_10K_ONLY") & ~selections["form"].eq("10-K"),
        "applicable",
    ] = False
    selections.loc[
        selections["coverage_denominator_policy"].eq("EVENT_CONDITIONAL_NOT_SCORED"),
        "applicable",
    ] = False
    selections.loc[
        selections["coverage_denominator_policy"].eq("DISCLOSURE_REGIME_ONLY"),
        "applicable",
    ] = selections["source_concept_present"]
    selections["available_when_applicable"] = selections["available"] & selections["applicable"]
    coverage = selections.groupby(
        ["evidence_layer", "metric", "coverage_denominator_policy"], as_index=False
    ).agg(
        periodic_filings=("available", "size"),
        filings_available=("available", "sum"),
        applicable_filings=("applicable", "sum"),
        applicable_filings_available=("available_when_applicable", "sum"),
        source_concept_filings=("source_concept_present", "sum"),
    )
    coverage["raw_presence_pct"] = coverage["source_concept_filings"] / coverage["periodic_filings"] * 100.0
    coverage["selection_availability_pct"] = coverage["filings_available"] / coverage["periodic_filings"] * 100.0
    coverage["coverage_pct"] = (
        coverage["applicable_filings_available"] / coverage["applicable_filings"] * 100.0
    ).where(coverage["applicable_filings"].gt(0))
    annual_coverage = selections.loc[selections["form"].eq("10-K")].groupby(["evidence_layer", "metric"], as_index=False).agg(annual_filings=("available", "size"), years_available=("available", "sum"))
    annual_coverage["coverage_pct"] = annual_coverage["years_available"] / annual_coverage["annual_filings"] * 100.0
    critical = {"operating_income_usd", "income_tax_usd", "capex_usd", "depreciation_amortization_usd", "inventory_usd", "receivables_usd", "accounts_payable_usd", "contract_assets_usd", "contract_liabilities_usd", "cash_usd", "equity_usd"}
    critical_coverage = annual_coverage.loc[annual_coverage["metric"].isin(critical), "coverage_pct"]
    summary = pd.DataFrame([{
        "periodic_filings_parsed": len(periodic), "annual_10k_filings": int(periodic["form"].eq("10-K").sum()),
        "quarterly_10q_filings": int(periodic["form"].eq("10-Q").sum()), "raw_relevant_xbrl_facts": len(raw),
        "financial_statement_metric_mean_coverage_pct": float(coverage.loc[coverage["evidence_layer"].eq("FINANCIAL_STATEMENT"), "coverage_pct"].mean()),
        "note_metric_mean_coverage_pct": float(coverage.loc[coverage["evidence_layer"].eq("NOTE"), "coverage_pct"].mean()),
        "coverage_denominators_are_applicability_aware": True,
        "critical_annual_metric_minimum_coverage_pct": float(critical_coverage.min()),
        "quarterly_statement_chain_complete_rows": int(quarterly["quarterly_statement_chain_complete"].sum()),
        "quarterly_note_contract_chain_complete_rows": int(quarterly["quarterly_note_contract_chain_complete"].sum()),
        "reported_roic_years": int(annual["reported_roic_pct"].notna().sum()),
        "latest_reported_roic_pct": float(annual.iloc[-1]["reported_roic_pct"]),
        "latest_pension_adjusted_roic_pct": float(annual.iloc[-1]["pension_adjusted_roic_pct"]),
        "latest_through_cycle_roic_median_pct": float(annual.iloc[-1]["through_cycle_reported_roic_median_pct"]),
        "latest_innovation_adjusted_reinvestment_rate_pct": float(annual.iloc[-1]["innovation_adjusted_reinvestment_rate_pct"]),
        "research_evidence_ready": bool(len(periodic) == 23 and len(annual) == 6 and critical_coverage.min() >= 80.0 and annual["reported_roic_pct"].notna().sum() >= 5),
        "segment_roic_claim_allowed": False, "terminal_input_allowed": False,
    }])
    return {
        "lmt_periodic_relevant_xbrl_facts": raw,
        "lmt_periodic_note_fact_selections": selections,
        "lmt_periodic_note_fact_coverage": coverage,
        "lmt_annual_note_fact_coverage": annual_coverage,
        "lmt_annual_reinvestment_roic_bridge": annual,
        "lmt_quarterly_reinvestment_note_bridge": quarterly,
        "lmt_reinvestment_roic_summary": summary,
    }
