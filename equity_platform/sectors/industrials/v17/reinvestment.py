from __future__ import annotations

from pathlib import Path
import re

from lxml import etree
import numpy as np
import pandas as pd


FACTS = {
    "revenue_usd": ("RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"),
    "operating_income_usd": ("OperatingIncomeLoss",),
    "pretax_income_usd": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
    "income_tax_usd": ("IncomeTaxExpenseBenefit",),
    "cfo_usd": ("NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    "capex_usd": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "equipment_on_lease_capex_usd": ("PaymentsToAcquireEquipmentOnLease",),
    "business_acquisitions_usd": ("PaymentsToAcquireBusinessesNetOfCashAcquired",),
    "depreciation_amortization_usd": ("DepreciationDepletionAndAmortization",),
    "research_development_usd": ("ResearchAndDevelopmentExpense",),
    "restructuring_cost_usd": ("RestructuringCosts", "RestructuringCharges"),
    "inventory_usd": ("InventoryNet",),
    "inventory_raw_material_usd": ("InventoryRawMaterialsNetOfReserves",),
    "inventory_work_in_process_usd": ("InventoryWorkInProcessNetOfReserves",),
    "inventory_finished_goods_usd": ("InventoryFinishedGoodsNetOfReserves",),
    "inventory_supplies_usd": ("InventorySuppliesNetOfReserves",),
    "trade_receivables_usd": ("AccountsReceivableNetCurrent", "ContractWithCustomerReceivableAfterAllowanceForCreditLossCurrent"),
    "accounts_payable_usd": ("AccountsPayableCurrent",),
    "ppe_net_usd": ("PropertyPlantAndEquipmentNet",),
    "goodwill_usd": ("Goodwill",),
    "intangibles_ex_goodwill_usd": ("IntangibleAssetsNetExcludingGoodwill",),
    "cash_usd": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt_current_usd": ("LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermDebtCurrent"),
    "debt_noncurrent_usd": ("LongTermDebtNoncurrent",),
    "equity_usd": ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"),
    "pension_opeb_liability_usd": ("PensionAndOtherPostretirementAndPostemploymentBenefitPlansLiabilitiesNoncurrent", "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent"),
    "warranty_accrual_usd": ("ProductWarrantyAccrual",),
}
FLOW_METRICS = {
    "revenue_usd", "operating_income_usd", "pretax_income_usd", "income_tax_usd", "cfo_usd",
    "capex_usd", "equipment_on_lease_capex_usd", "business_acquisitions_usd",
    "depreciation_amortization_usd", "research_development_usd", "restructuring_cost_usd",
}


def _local_name(concept: str) -> str:
    return concept.split(":", 1)[-1]


def _numeric(node: etree._Element) -> float | None:
    text = "".join(node.itertext()).strip().replace(",", "").replace("$", "")
    text = re.sub(r"\s+", "", text)
    if not text or text in {"—", "-"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = float(text)
    except ValueError:
        return None
    value *= 10 ** int(node.get("scale", "0"))
    if node.get("sign") == "-" or negative:
        value *= -1.0
    return value


def _contexts(tree: etree._ElementTree) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for context in tree.xpath("//*[local-name()='context']"):
        context_id = context.get("id")
        if not context_id:
            continue
        values = {etree.QName(child).localname: (child.text or "") for child in context.iter() if etree.QName(child).localname in {"startDate", "endDate", "instant"}}
        dimensions = ["".join(member.itertext()).strip() for member in context.xpath(".//*[local-name()='explicitMember' or local-name()='typedMember']")]
        result[context_id] = {
            "start_date": values.get("startDate"),
            "end_date": values.get("endDate") or values.get("instant"),
            "instant": bool(values.get("instant")),
            "dimensions": "|".join(dimensions),
            "dimension_count": len(dimensions),
        }
    return result


def _parse_filing(path: Path, source: pd.Series) -> pd.DataFrame:
    parser = etree.XMLParser(recover=True, huge_tree=True)
    tree = etree.parse(str(path), parser)
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
        rows.append(
            {
                "form": source["form"],
                "filing_date": source["filing_date"],
                "report_date": source["report_date"],
                "accession_number": source["accession_number"],
                "concept": concept,
                "concept_local": _local_name(concept),
                "value_usd": value,
                "context_ref": node.get("contextRef"),
                **context,
                "source_url": source["source_url"],
                "source_sha256": source["sha256"],
            }
        )
    return pd.DataFrame(rows)


def _select_metric(facts: pd.DataFrame, metric: str, report_date: str, form: str) -> tuple[float, str, str] | tuple[float, None, None]:
    candidates = FACTS[metric]
    matching = facts.loc[
        facts["concept_local"].isin(candidates)
        & facts["end_date"].eq(report_date)
    ].copy()
    frame = matching.loc[matching["dimension_count"].eq(0)].copy()
    if metric in FLOW_METRICS:
        frame["duration_days"] = (pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])).dt.days
        frame = frame.loc[frame["duration_days"].between(330, 370) if form == "10-K" else frame["duration_days"].between(70, 290)]
    else:
        frame = frame.loc[frame["instant"]]
    if frame.empty and metric == "debt_current_usd":
        dimensional = matching.loc[matching["instant"] & matching["dimension_count"].eq(1)].drop_duplicates("context_ref")
        if len(dimensional) == 2:
            return float(dimensional["value_usd"].sum()), str(dimensional.iloc[0]["concept"]), "SUM_MPE_AND_FINANCIAL_PRODUCTS_CONTEXTS"
    if frame.empty:
        return np.nan, None, None
    frame["concept_priority"] = frame["concept_local"].map({name: index for index, name in enumerate(candidates)})
    sort_columns = ["concept_priority"] + (["duration_days"] if metric in FLOW_METRICS else []) + ["context_ref"]
    ascending = [True] + ([False] if metric in FLOW_METRICS else []) + [True]
    selected = frame.sort_values(sort_columns, ascending=ascending).iloc[0]
    return float(selected["value_usd"]), str(selected["concept"]), str(selected["context_ref"])


def build_reinvestment_roic_evidence(
    *,
    sec_inventory: pd.DataFrame,
    mpe_roic_history: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    annual_sources = sec_inventory.loc[sec_inventory["form"].eq("10-K")].copy()
    raw_frames = [_parse_filing(Path(source["resolved_path"]), source) for _, source in sec_inventory.iterrows()]
    raw = pd.concat(raw_frames, ignore_index=True)
    selections: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    for _, source in annual_sources.sort_values("report_date").iterrows():
        filing_facts = raw.loc[raw["accession_number"].eq(source["accession_number"])]
        row: dict[str, object] = {
            "fiscal_year": int(str(source["report_date"])[:4]),
            "filing_date": source["filing_date"],
            "report_date": source["report_date"],
            "source_url": source["source_url"],
            "source_sha256": source["sha256"],
        }
        for metric in FACTS:
            value, concept, context_ref = _select_metric(filing_facts, metric, str(source["report_date"]), "10-K")
            row[metric] = value
            selections.append(
                {
                    "fiscal_year": row["fiscal_year"],
                    "metric": metric,
                    "value_usd": value,
                    "selected_concept": concept,
                    "selected_context_ref": context_ref,
                    "available": bool(np.isfinite(value)),
                    "selection_rule": "CONSOLIDATED_NO_DIMENSION_CURRENT_ANNUAL_OR_INSTANT_CONTEXT",
                    "source_url": source["source_url"],
                    "source_sha256": source["sha256"],
                }
            )
        annual_rows.append(row)
    annual = pd.DataFrame(annual_rows).sort_values("fiscal_year").reset_index(drop=True)
    for column in ["debt_current_usd", "debt_noncurrent_usd", "business_acquisitions_usd", "research_development_usd", "restructuring_cost_usd"]:
        annual[column] = annual[column].fillna(0.0)
    tax_rate = annual["income_tax_usd"] / annual["pretax_income_usd"]
    annual["effective_tax_rate_pct"] = tax_rate.where(tax_rate.between(0.0, 0.50), 0.21) * 100.0
    annual["nopat_usd"] = annual["operating_income_usd"] * (1.0 - annual["effective_tax_rate_pct"] / 100.0)
    annual["total_debt_usd"] = annual["debt_current_usd"] + annual["debt_noncurrent_usd"]
    annual["debt_selection_method"] = "CURRENT_SEGMENT_SUM_PLUS_CONSOLIDATED_NONCURRENT"
    annual["reported_invested_capital_usd"] = annual["equity_usd"] + annual["total_debt_usd"] - annual["cash_usd"]
    annual["average_reported_invested_capital_usd"] = (annual["reported_invested_capital_usd"] + annual["reported_invested_capital_usd"].shift(1)) / 2.0
    annual["reported_roic_pct"] = annual["nopat_usd"] / annual["average_reported_invested_capital_usd"] * 100.0
    annual["tangible_invested_capital_sensitivity_usd"] = annual["reported_invested_capital_usd"] - annual["goodwill_usd"].fillna(0.0) - annual["intangibles_ex_goodwill_usd"].fillna(0.0)
    annual["average_tangible_invested_capital_sensitivity_usd"] = (annual["tangible_invested_capital_sensitivity_usd"] + annual["tangible_invested_capital_sensitivity_usd"].shift(1)) / 2.0
    annual["tangible_roic_sensitivity_pct"] = annual["nopat_usd"] / annual["average_tangible_invested_capital_sensitivity_usd"] * 100.0
    annual["operating_nwc_usd"] = annual["inventory_usd"] + annual["trade_receivables_usd"] - annual["accounts_payable_usd"]
    annual["change_operating_nwc_usd"] = annual["operating_nwc_usd"].diff()
    annual["gross_productive_asset_capex_usd"] = annual["capex_usd"] + annual["equipment_on_lease_capex_usd"]
    annual["organic_net_capex_reinvestment_usd"] = annual["gross_productive_asset_capex_usd"] - annual["depreciation_amortization_usd"]
    annual["core_reinvestment_proxy_usd"] = annual["organic_net_capex_reinvestment_usd"] + annual["change_operating_nwc_usd"]
    annual["innovation_adjusted_reinvestment_proxy_usd"] = annual["core_reinvestment_proxy_usd"] + annual["research_development_usd"]
    annual["total_including_mna_reinvestment_proxy_usd"] = annual["innovation_adjusted_reinvestment_proxy_usd"] + annual["business_acquisitions_usd"]
    for prefix in ["core", "innovation_adjusted", "total_including_mna"]:
        annual[f"{prefix}_reinvestment_rate_pct"] = annual[f"{prefix}_reinvestment_proxy_usd"] / annual["nopat_usd"] * 100.0
    annual["inventory_components_sum_usd"] = annual[["inventory_raw_material_usd", "inventory_work_in_process_usd", "inventory_finished_goods_usd", "inventory_supplies_usd"]].sum(axis=1, min_count=4)
    annual["inventory_note_identity_error_usd"] = annual["inventory_usd"] - annual["inventory_components_sum_usd"]
    annual["inventory_note_identity_pass"] = annual["inventory_note_identity_error_usd"].abs().le(1.0)
    annual["financial_products_contamination"] = True
    annual["terminal_input_allowed"] = False

    periodic_rows: list[dict[str, object]] = []
    periodic_selections: list[dict[str, object]] = []
    for _, source in sec_inventory.sort_values("report_date").iterrows():
        filing_facts = raw.loc[raw["accession_number"].eq(source["accession_number"])]
        report_date = str(source["report_date"])
        report_month = int(report_date[5:7])
        row: dict[str, object] = {
            "fiscal_year": int(report_date[:4]),
            "fiscal_quarter": {3: 1, 6: 2, 9: 3, 12: 4}.get(report_month),
            "form": source["form"],
            "filing_date": source["filing_date"],
            "report_date": report_date,
            "source_url": source["source_url"],
            "source_sha256": source["sha256"],
        }
        for metric in FACTS:
            value, concept, context_ref = _select_metric(filing_facts, metric, report_date, str(source["form"]))
            row[metric] = value
            periodic_selections.append(
                {
                    "form": source["form"],
                    "fiscal_year": row["fiscal_year"],
                    "fiscal_quarter": row["fiscal_quarter"],
                    "metric": metric,
                    "value_usd": value,
                    "available": bool(np.isfinite(value)),
                    "selected_concept": concept,
                    "selected_context_ref": context_ref,
                    "source_url": source["source_url"],
                    "source_sha256": source["sha256"],
                }
            )
        periodic_rows.append(row)
    periodic = pd.DataFrame(periodic_rows).sort_values(["fiscal_year", "fiscal_quarter"]).reset_index(drop=True)
    periodic["operating_nwc_usd"] = periodic["inventory_usd"] + periodic["trade_receivables_usd"] - periodic["accounts_payable_usd"]
    periodic["change_operating_nwc_usd"] = periodic["operating_nwc_usd"].diff()
    discrete = periodic[["fiscal_year", "fiscal_quarter", "form", "filing_date", "report_date", "source_url", "source_sha256", "operating_nwc_usd", "change_operating_nwc_usd"]].copy()
    for metric in sorted(FLOW_METRICS):
        values: list[float] = []
        complete: list[bool] = []
        for _, row in periodic.iterrows():
            quarter = int(row["fiscal_quarter"])
            current = row[metric]
            if quarter == 1:
                values.append(current)
                complete.append(bool(pd.notna(current)))
                continue
            prior = periodic.loc[
                periodic["fiscal_year"].eq(row["fiscal_year"])
                & periodic["fiscal_quarter"].eq(quarter - 1),
                metric,
            ]
            values.append(current - prior.iloc[0] if pd.notna(current) and not prior.empty and pd.notna(prior.iloc[0]) else np.nan)
            complete.append(bool(pd.notna(values[-1])))
        discrete[f"discrete_{metric}"] = values
        discrete[f"discrete_{metric}_complete"] = complete
    discrete["discrete_gross_productive_asset_capex_usd"] = discrete["discrete_capex_usd"] + discrete["discrete_equipment_on_lease_capex_usd"]
    discrete["discrete_net_capex_usd"] = discrete["discrete_gross_productive_asset_capex_usd"] - discrete["discrete_depreciation_amortization_usd"]
    discrete["discrete_core_reinvestment_proxy_usd"] = discrete["discrete_net_capex_usd"] + discrete["change_operating_nwc_usd"]
    discrete["discrete_innovation_adjusted_reinvestment_proxy_usd"] = discrete["discrete_core_reinvestment_proxy_usd"] + discrete["discrete_research_development_usd"]
    discrete["discrete_total_including_mna_reinvestment_proxy_usd"] = discrete["discrete_innovation_adjusted_reinvestment_proxy_usd"] + discrete["discrete_business_acquisitions_usd"]
    discrete["quarterly_note_chain_complete"] = discrete[[f"discrete_{metric}_complete" for metric in FLOW_METRICS]].all(axis=1) & discrete["change_operating_nwc_usd"].notna()
    discrete["terminal_input_allowed"] = False

    mpe = mpe_roic_history[["fiscal_year", "mpe_nopat_usd", "mpe_invested_capital_usd", "mpe_roic_pct", "incremental_roic_pct"]].copy()
    cross = annual.merge(mpe, on="fiscal_year", how="left")
    cross["consolidated_minus_mpe_nopat_usd"] = cross["nopat_usd"] - cross["mpe_nopat_usd"]
    cross["consolidated_minus_mpe_roic_pct_points"] = cross["reported_roic_pct"] - cross["mpe_roic_pct"]
    cross["comparison_purpose"] = "FINANCIAL_PRODUCTS_AND_PERIMETER_SENSITIVITY_NOT_TERMINAL_CALIBRATION"

    selected = pd.DataFrame(selections)
    coverage = selected.groupby("metric", as_index=False).agg(years=("fiscal_year", "size"), years_available=("available", "sum"))
    coverage["coverage_pct"] = coverage["years_available"] / coverage["years"] * 100.0
    critical = ["operating_income_usd", "income_tax_usd", "capex_usd", "equipment_on_lease_capex_usd", "depreciation_amortization_usd", "inventory_usd", "trade_receivables_usd", "accounts_payable_usd", "goodwill_usd", "cash_usd", "debt_current_usd", "debt_noncurrent_usd", "equity_usd"]
    critical_coverage = coverage.loc[coverage["metric"].isin(critical), "coverage_pct"]
    summary = pd.DataFrame(
        [
            {
                "annual_10k_filings": len(annual_sources),
                "annual_periods": len(annual),
                "raw_relevant_xbrl_facts": len(raw),
                "periodic_filings_parsed": len(periodic),
                "quarterly_discrete_complete_rows": int(discrete["quarterly_note_chain_complete"].sum()),
                "selected_metrics": len(FACTS),
                "critical_metric_minimum_coverage_pct": float(critical_coverage.min()),
                "inventory_identity_pass_years": int(annual["inventory_note_identity_pass"].sum()),
                "latest_reported_roic_pct": float(annual.iloc[-1]["reported_roic_pct"]),
                "latest_tangible_roic_sensitivity_pct": float(annual.iloc[-1]["tangible_roic_sensitivity_pct"]),
                "latest_core_reinvestment_rate_pct": float(annual.iloc[-1]["core_reinvestment_rate_pct"]),
                "latest_innovation_adjusted_reinvestment_rate_pct": float(annual.iloc[-1]["innovation_adjusted_reinvestment_rate_pct"]),
                "latest_total_including_mna_reinvestment_rate_pct": float(annual.iloc[-1]["total_including_mna_reinvestment_rate_pct"]),
                "mpe_and_consolidated_perimeters_kept_separate": True,
                "research_evidence_ready": bool(len(annual) == 6 and critical_coverage.min() >= 80.0),
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {
        "periodic_relevant_xbrl_facts": raw,
        "annual_note_fact_selections": selected,
        "annual_note_fact_coverage": coverage,
        "annual_reinvestment_roic_bridge": annual,
        "periodic_note_fact_selections": pd.DataFrame(periodic_selections),
        "periodic_note_fact_bridge": periodic,
        "quarterly_reinvestment_note_bridge": discrete,
        "mpe_consolidated_roic_perimeter_crosscheck": cross,
        "reinvestment_roic_evidence_summary": summary,
    }
