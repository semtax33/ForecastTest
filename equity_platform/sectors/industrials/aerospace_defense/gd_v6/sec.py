from __future__ import annotations

from pathlib import Path

from lxml import etree
import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.aerospace_defense.lmt.xbrl import (
    _annual_bridge,
    _quarterly_bridge,
)
from equity_platform.sectors.industrials.aerospace_defense.noc.sec import (
    _source_inventory,
)
from equity_platform.sectors.industrials.v17.reinvestment import (
    _contexts,
    _local_name,
    _numeric,
)


FACTS = {
    "shares_outstanding": ("EntityCommonStockSharesOutstanding",),
    "revenue_usd": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ),
    "operating_income_usd": ("OperatingIncomeLoss",),
    "pretax_income_usd": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "income_tax_usd": ("IncomeTaxExpenseBenefit",),
    "cfo_usd": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex_usd": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "depreciation_amortization_usd": (
        "DepreciationAndAmortization",
        "Depreciation",
    ),
    "research_development_usd": ("ResearchAndDevelopmentExpense",),
    "business_acquisitions_usd": (
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesGross",
    ),
    "receivables_usd": ("AccountsReceivableNetCurrent",),
    "inventory_usd": ("InventoryNet",),
    "accounts_payable_usd": ("AccountsPayableCurrent",),
    "contract_assets_usd": ("UnbilledReceivablesCurrent",),
    "contract_liabilities_usd": ("ContractWithCustomerLiabilityCurrent",),
    "remaining_performance_obligation_usd": (
        "RevenueRemainingPerformanceObligation",
    ),
    "program_gains_losses_usd": ("ProgramGainsLosses",),
    "cash_usd": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "debt_current_usd": ("DebtCurrent", "LongTermDebtCurrent"),
    "debt_noncurrent_usd": ("LongTermDebtNoncurrent",),
    "equity_usd": ("StockholdersEquity",),
    "goodwill_usd": ("Goodwill",),
    "intangibles_ex_goodwill_usd": ("FiniteLivedIntangibleAssetsNet",),
    "pension_liability_usd": (
        "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent",
        "DefinedBenefitPensionPlanLiabilitiesNoncurrent",
    ),
    "fas_cas_pension_adjustment_usd": (
        "FasCasPensionAdjustment",
        "FASAndCASPensionAdjustment",
    ),
}
FLOW_METRICS = {
    "revenue_usd",
    "operating_income_usd",
    "pretax_income_usd",
    "income_tax_usd",
    "cfo_usd",
    "capex_usd",
    "depreciation_amortization_usd",
    "research_development_usd",
    "business_acquisitions_usd",
    "program_gains_losses_usd",
    "fas_cas_pension_adjustment_usd",
}


def _parse_filing(path: Path, source: pd.Series) -> pd.DataFrame:
    tree = etree.parse(str(path), etree.XMLParser(recover=True, huge_tree=True))
    contexts = _contexts(tree)
    wanted = {concept for aliases in FACTS.values() for concept in aliases}
    rows: list[dict[str, object]] = []
    for node in tree.xpath("//*[local-name()='nonFraction']"):
        concept = _local_name(node.get("name", ""))
        if concept not in wanted:
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
                "concept": node.get("name", ""),
                "concept_local": concept,
                "value_usd": value,
                "context_ref": node.get("contextRef"),
                **context,
                "source_url": source["source_url"],
                "source_sha256": source["sha256"],
            }
        )
    return pd.DataFrame(rows)


def _select_metric(
    facts: pd.DataFrame, metric: str, report_date: str, form: str
) -> tuple[float, str | None, str | None]:
    aliases = FACTS[metric]
    matching = facts.loc[
        facts["concept_local"].isin(aliases) & facts["end_date"].eq(report_date)
    ].copy()
    frame = matching.loc[matching["dimension_count"].eq(0)].copy()
    if metric in FLOW_METRICS:
        frame["duration_days"] = (
            pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])
        ).dt.days
        frame = frame.loc[
            frame["duration_days"].between(330, 370)
            if form == "10-K"
            else frame["duration_days"].between(70, 290)
        ]
    else:
        frame = frame.loc[frame["instant"]]
    if frame.empty and metric == "debt_current_usd":
        noncurrent = facts.loc[
            facts["concept_local"].eq("LongTermDebtNoncurrent")
            & facts["end_date"].eq(report_date)
            & facts["dimension_count"].eq(0)
            & facts["instant"]
        ]
        if not noncurrent.empty:
            return (
                0.0,
                "DERIVED:CURRENT_DEBT_ZERO_WHEN_NOT_REPORTED",
                str(noncurrent.sort_values("context_ref").iloc[0]["context_ref"]),
            )
    if frame.empty:
        return np.nan, None, None
    frame["concept_priority"] = frame["concept_local"].map(
        {name: index for index, name in enumerate(aliases)}
    )
    sort = ["concept_priority"] + (
        ["duration_days"] if metric in FLOW_METRICS else []
    ) + ["context_ref"]
    ascending = [True] + ([False] if metric in FLOW_METRICS else []) + [True]
    selected = frame.sort_values(sort, ascending=ascending).iloc[0]
    return (
        float(selected["value_usd"]),
        str(selected["concept"]),
        str(selected["context_ref"]),
    )


def _gd_fiscal_quarter(report_date: str) -> int:
    month = pd.Timestamp(report_date).month
    if month in {3, 4}:
        return 1
    if month in {6, 7}:
        return 2
    if month in {9, 10}:
        return 3
    if month == 12:
        return 4
    raise ValueError(f"Unsupported GD fiscal report date: {report_date}")


def _select_periodic(
    inventory: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = pd.concat(
        [
            _parse_filing(Path(str(source["resolved_path"])), source)
            for _, source in inventory.iterrows()
        ],
        ignore_index=True,
    )
    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    for _, source in inventory.sort_values("report_date").iterrows():
        report_date = str(source["report_date"])
        quarter = _gd_fiscal_quarter(report_date)
        filing = raw.loc[raw["accession_number"].eq(source["accession_number"])]
        row: dict[str, object] = {
            "form": source["form"],
            "fiscal_year": int(report_date[:4]),
            "fiscal_quarter": quarter,
            "period": f"{report_date[:4]}Q{quarter}",
            "filing_date": source["filing_date"],
            "report_date": report_date,
            "source_url": source["source_url"],
            "source_sha256": source["sha256"],
        }
        for metric in FACTS:
            value, concept, context_ref = _select_metric(
                filing, metric, report_date, str(source["form"])
            )
            row[metric] = value
            selections.append(
                {
                    "form": source["form"],
                    "period": row["period"],
                    "filing_date": source["filing_date"],
                    "accession_number": source["accession_number"],
                    "metric": metric,
                    "value_usd": value,
                    "available": bool(np.isfinite(value)),
                    "selected_concept": concept,
                    "selected_context_ref": context_ref,
                    "source_url": source["source_url"],
                    "source_sha256": source["sha256"],
                    "evidence_layer": (
                        "NOTE"
                        if metric
                        in {
                            "contract_assets_usd",
                            "contract_liabilities_usd",
                            "remaining_performance_obligation_usd",
                            "program_gains_losses_usd",
                            "research_development_usd",
                            "business_acquisitions_usd",
                            "pension_liability_usd",
                            "fas_cas_pension_adjustment_usd",
                        }
                        else "FINANCIAL_STATEMENT"
                    ),
                    "selection_rule": "GD_CONSOLIDATED_REPORT_DATE_CONTEXT",
                }
            )
        rows.append(row)
    periodic = pd.DataFrame(rows).sort_values(
        ["fiscal_year", "fiscal_quarter"]
    ).reset_index(drop=True)
    return raw, periodic, pd.DataFrame(selections)


def _coverage(selections: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = selections.copy()
    result["applicable"] = True
    result.loc[
        result["metric"].eq("research_development_usd")
        & ~result["form"].eq("10-K"),
        "applicable",
    ] = False
    result.loc[
        result["metric"].isin(
            {"business_acquisitions_usd", "program_gains_losses_usd"}
        ),
        "applicable",
    ] = False
    result.loc[
        result["metric"].eq("fas_cas_pension_adjustment_usd"), "applicable"
    ] = False
    result["available_when_applicable"] = result["available"] & result["applicable"]
    coverage = result.groupby(["evidence_layer", "metric"], as_index=False).agg(
        periodic_filings=("available", "size"),
        filings_available=("available", "sum"),
        applicable_filings=("applicable", "sum"),
        applicable_filings_available=("available_when_applicable", "sum"),
    )
    coverage["coverage_pct"] = (
        coverage["applicable_filings_available"]
        / coverage["applicable_filings"]
        * 100.0
    ).where(coverage["applicable_filings"].gt(0))
    annual = (
        result.loc[result["form"].eq("10-K")]
        .groupby(["evidence_layer", "metric"], as_index=False)
        .agg(
            annual_filings=("available", "size"),
            years_available=("available", "sum"),
        )
    )
    annual["coverage_pct"] = (
        annual["years_available"] / annual["annual_filings"] * 100.0
    )
    return coverage, annual


def _reconcile_to_ir(
    quarterly: pd.DataFrame, company_history: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sec = quarterly[
        [
            "period",
            "form",
            "filing_date",
            "source_url",
            "source_sha256",
            "discrete_revenue_usd",
            "discrete_operating_income_usd",
        ]
    ]
    ir = company_history[
        ["period", "revenue_usd", "operating_income_usd", "source_sha256"]
    ].rename(columns={"source_sha256": "ir_source_sha256"})
    result = sec.merge(ir, on="period", how="inner", validate="one_to_one")
    rows: list[dict[str, object]] = []
    for record in result.itertuples():
        for metric in ("revenue", "operating_income"):
            sec_value = float(getattr(record, f"discrete_{metric}_usd"))
            ir_value = float(getattr(record, f"{metric}_usd"))
            difference = sec_value - ir_value
            rows.append(
                {
                    "period": record.period,
                    "form": record.form,
                    "metric": metric,
                    "sec_value_usd": sec_value,
                    "ir_value_usd": ir_value,
                    "difference_usd": difference,
                    "identity_pass": bool(abs(difference) <= 1.0),
                    "filing_date": record.filing_date,
                    "sec_source_url": record.source_url,
                    "sec_source_sha256": record.source_sha256,
                    "ir_source_sha256": record.ir_source_sha256,
                }
            )
    detail = pd.DataFrame(rows)
    revenue = detail.loc[detail["metric"].eq("revenue")]
    operating = detail.loc[detail["metric"].eq("operating_income")]
    summary = pd.DataFrame(
        [
            {
                "comparable_periods": result["period"].nunique(),
                "comparable_metric_cells": len(detail),
                "identity_pass_cells": int(detail["identity_pass"].sum()),
                "identity_pass_pct": float(detail["identity_pass"].mean() * 100.0),
                "maximum_absolute_difference_usd": float(
                    detail["difference_usd"].abs().max()
                ),
                "revenue_identity_pass_cells": int(revenue["identity_pass"].sum()),
                "revenue_identity_expected_cells": len(revenue),
                "revenue_reconciliation_gate_pass": bool(revenue["identity_pass"].all()),
                "operating_income_identity_pass_cells": int(
                    operating["identity_pass"].sum()
                ),
                "operating_income_identity_expected_cells": len(operating),
                "operating_income_maximum_absolute_difference_usd": float(
                    operating["difference_usd"].abs().max()
                ),
                "operating_income_reconciliation_complete": bool(
                    operating["identity_pass"].all()
                ),
                "unidentified_operating_income_bridge_rows": int(
                    (~operating["identity_pass"]).sum()
                ),
                "reconciliation_gate_pass": bool(detail["identity_pass"].all()),
            }
        ]
    )
    return detail, summary


def build_gd_sec_evidence(
    *, project_root: Path, manifest_path: Path, company_history: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    inventory, concept_coverage, family_summary = _source_inventory(
        project_root, manifest_path
    )
    raw, periodic, selections = _select_periodic(inventory)
    annual = _annual_bridge(periodic)
    quarterly = _quarterly_bridge(periodic)
    metric_coverage, annual_coverage = _coverage(selections)
    reconciliation, reconciliation_summary = _reconcile_to_ir(
        quarterly, company_history
    )
    reconciliation_row = reconciliation_summary.iloc[0]
    critical = {
        "operating_income_usd",
        "income_tax_usd",
        "capex_usd",
        "depreciation_amortization_usd",
        "inventory_usd",
        "receivables_usd",
        "accounts_payable_usd",
        "contract_assets_usd",
        "cash_usd",
        "equity_usd",
    }
    critical_annual = annual_coverage.loc[
        annual_coverage["metric"].isin(critical), "coverage_pct"
    ]
    annual["historical_diagnostic_only"] = True
    annual["terminal_input_allowed"] = False
    summary = pd.DataFrame(
        [
            {
                "sec_filings": len(inventory),
                "sec_10k_filings": int(inventory["form"].eq("10-K").sum()),
                "sec_10q_filings": int(inventory["form"].eq("10-Q").sum()),
                "sec_hash_matches": int(inventory["hash_match"].sum()),
                "raw_relevant_xbrl_facts": len(raw),
                "financial_statement_metric_mean_coverage_pct": float(
                    metric_coverage.loc[
                        metric_coverage["evidence_layer"].eq("FINANCIAL_STATEMENT"),
                        "coverage_pct",
                    ].mean()
                ),
                "note_metric_mean_coverage_pct": float(
                    metric_coverage.loc[
                        metric_coverage["evidence_layer"].eq("NOTE"),
                        "coverage_pct",
                    ].mean()
                ),
                "critical_annual_metric_minimum_coverage_pct": float(
                    critical_annual.min()
                ),
                "reported_roic_years": int(annual["reported_roic_pct"].notna().sum()),
                "quarterly_statement_chain_complete_rows": int(
                    quarterly["quarterly_statement_chain_complete"].sum()
                ),
                "sec_ir_revenue_reconciliation_pass": bool(
                    reconciliation_row["revenue_reconciliation_gate_pass"]
                ),
                "sec_ir_operating_income_reconciliation_complete": bool(
                    reconciliation_row["operating_income_reconciliation_complete"]
                ),
                "sec_ir_unidentified_operating_income_bridge_rows": int(
                    reconciliation_row["unidentified_operating_income_bridge_rows"]
                ),
                "sec_ir_reconciliation_pass": bool(
                    reconciliation_row["reconciliation_gate_pass"]
                ),
                "source_gate_pass": bool(
                    len(inventory) == 27
                    and inventory["hash_match"].all()
                    and critical_annual.min() >= 80.0
                    and annual["reported_roic_pct"].notna().sum() >= 5
                    and reconciliation_row["revenue_reconciliation_gate_pass"]
                ),
                "r_and_d_authority": "R_AND_D_NOT_IDENTIFIED_NOT_ZERO_AUTHORITY",
                "terminal_input_allowed": False,
                "pdf_parsing_used": False,
            }
        ]
    )
    roic_summary = pd.DataFrame(
        [
            {
                "annual_observations": len(annual),
                "reported_roic_years": int(annual["reported_roic_pct"].notna().sum()),
                "reported_roic_median_pct": float(annual["reported_roic_pct"].median()),
                "latest_reported_roic_pct": float(annual.iloc[-1]["reported_roic_pct"]),
                "latest_through_cycle_roic_median_pct": float(
                    annual.iloc[-1]["through_cycle_reported_roic_median_pct"]
                ),
                "latest_core_reinvestment_rate_pct": float(
                    annual.iloc[-1]["core_reinvestment_rate_pct"]
                ),
                "latest_innovation_adjusted_reinvestment_rate_pct": float(
                    annual.iloc[-1]["innovation_adjusted_reinvestment_rate_pct"]
                ),
                "research_evidence_ready": bool(summary.iloc[0]["source_gate_pass"]),
                "historical_diagnostic_only": True,
                "terminal_input_allowed": False,
            }
        ]
    )
    return {
        "gd_sec_source_inventory": inventory,
        "gd_sec_concept_coverage": concept_coverage,
        "gd_sec_concept_family_summary": family_summary,
        "gd_periodic_relevant_xbrl_facts": raw,
        "gd_periodic_fact_selections": selections,
        "gd_periodic_metric_coverage": metric_coverage,
        "gd_annual_metric_coverage": annual_coverage,
        "gd_periodic_financial_history": periodic,
        "gd_quarterly_reinvestment_note_bridge": quarterly,
        "gd_annual_reinvestment_roic_bridge": annual,
        "gd_sec_ir_reconciliation": reconciliation,
        "gd_sec_ir_reconciliation_summary": reconciliation_summary,
        "gd_reinvestment_roic_summary": roic_summary,
        "gd_sec_source_summary": summary,
    }
