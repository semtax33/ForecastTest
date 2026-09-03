from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.aerospace_defense.lmt.xbrl import (
    _parse_filing,
    build_lmt_reinvestment_roic_evidence,
)
from equity_platform.sectors.industrials.v17.reinvestment import _contexts, _local_name, _numeric
from lxml import etree


SEGMENT_MEMBERS = {
    "aeronautics_systems": "AeronauticsSystemsMember",
    "defense_systems": "DefenseSystemsMember",
    "mission_systems": "MissionSystemsMember",
    "space_systems": "SpaceSystemsMember",
}
SEGMENT_METRICS = {
    "Revenues": ("sales_usd", "revenue_usd"),
    "OperatingIncomeLoss": ("operating_profit_usd", "operating_income_usd"),
}
CONCEPT_FAMILIES = {
    "statement_revenue_operating_income_tax": ("Revenues", "OperatingIncomeLoss", "IncomeTaxExpense"),
    "statement_cash_flow_capex_depreciation": ("NetCashProvided", "PaymentsToAcquire", "Depreciation"),
    "statement_working_capital": ("ReceivablesNetCurrent", "Inventory", "AccountsPayableCurrent"),
    "note_segments": ("OperatingSegmentsMember", "SegmentReporting"),
    "note_revenue_and_contracts": ("ContractWithCustomer", "RevenueFromContractWithCustomerTextBlock"),
    "note_contract_assets_liabilities": ("ContractWithCustomerAsset", "ContractWithCustomerLiability"),
    "note_remaining_performance_obligation": ("RevenueRemainingPerformanceObligation",),
    "note_program_accounting": ("Program", "ContractsAccountedForUnderPercentageOfCompletionMember"),
    "note_pension": ("Pension",),
    "note_goodwill_intangibles": ("Goodwill", "IntangibleAssets"),
    "note_debt": ("DebtDisclosureTextBlock", "LongTermDebt"),
    "note_income_taxes": ("IncomeTaxDisclosureTextBlock", "EffectiveIncomeTaxRate"),
    "capital_structure": ("LongTermDebt", "StockholdersEquity", "CashAndCash"),
}
_CONCEPT = re.compile(r'\bname=["\']([^"\']+)["\']', re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _period(report_date: str) -> str:
    quarter = {3: 1, 6: 2, 9: 3, 12: 4}[pd.Timestamp(report_date).month]
    return f"{report_date[:4]}Q{quarter}"


def _source_inventory(project_root: Path, manifest_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows: list[dict[str, object]] = []
    family_rows: list[dict[str, object]] = []
    for item in manifest["files"]:
        path = project_root / item["local_path"]
        raw = path.read_text(encoding="utf-8", errors="ignore")
        concepts = sorted(set(_CONCEPT.findall(raw)))
        source_rows.append(
            {
                **item,
                "resolved_path": str(path),
                "file_exists": path.exists(),
                "hash_match": _sha256(path) == item["sha256"],
                "inline_xbrl_concept_count": len(concepts),
            }
        )
        for family, needles in CONCEPT_FAMILIES.items():
            matched = sorted(
                concept
                for concept in concepts
                if any(needle.lower() in concept.lower() for needle in needles)
            )
            family_rows.append(
                {
                    "form": item["form"],
                    "filing_date": item["filing_date"],
                    "report_date": item["report_date"],
                    "accession_number": item["accession_number"],
                    "family": family,
                    "present": bool(matched),
                    "matched_concept_count": len(matched),
                    "matched_concepts": "|".join(matched),
                    "source_url": item["source_url"],
                    "source_sha256": item["sha256"],
                }
            )
    inventory = pd.DataFrame(source_rows).sort_values(["filing_date", "form"]).reset_index(drop=True)
    coverage = pd.DataFrame(family_rows)
    coverage["coverage_denominator_policy"] = "ALL_PERIODIC_FILINGS"
    coverage.loc[coverage["family"].isin(["note_pension", "note_goodwill_intangibles"]), "coverage_denominator_policy"] = "ANNUAL_10K_ONLY"
    coverage["applicable"] = ~(
        coverage["coverage_denominator_policy"].eq("ANNUAL_10K_ONLY")
        & ~coverage["form"].eq("10-K")
    )
    coverage["present_when_applicable"] = coverage["present"] & coverage["applicable"]
    summary = coverage.groupby(["family", "coverage_denominator_policy"], as_index=False).agg(
        filings=("present", "size"),
        filings_with_family=("present", "sum"),
        applicable_filings=("applicable", "sum"),
        applicable_filings_with_family=("present_when_applicable", "sum"),
    )
    summary["coverage_pct"] = summary["applicable_filings_with_family"] / summary["applicable_filings"] * 100.0
    return inventory, coverage, summary


def _segment_reconciliation(
    raw_facts: pd.DataFrame,
    inventory: pd.DataFrame,
    ir_history: pd.DataFrame,
    scope_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for _, source in inventory.sort_values("report_date").iterrows():
        report_date = str(source["report_date"])
        filing = raw_facts.loc[raw_facts["accession_number"].eq(source["accession_number"])].copy()
        for segment, member in SEGMENT_MEMBERS.items():
            for concept, (ir_column, metric) in SEGMENT_METRICS.items():
                candidates = filing.loc[
                    filing["concept_local"].eq(concept)
                    & filing["end_date"].eq(report_date)
                    & filing["dimension_count"].eq(2)
                    & filing["dimensions"].fillna("").str.contains(member, regex=False)
                    & filing["dimensions"].fillna("").str.contains("OperatingSegmentsMember", regex=False)
                ].copy()
                candidates["duration_days"] = (
                    pd.to_datetime(candidates["end_date"])
                    - pd.to_datetime(candidates["start_date"])
                ).dt.days
                candidates = candidates.loc[
                    candidates["duration_days"].between(330, 370)
                    if source["form"] == "10-K"
                    else candidates["duration_days"].between(70, 110)
                ].drop_duplicates("value_usd")
                sec_value = float(candidates.iloc[0]["value_usd"]) if len(candidates) == 1 else np.nan
                if source["form"] == "10-K":
                    comparable = ir_history.loc[
                        ir_history["period"].str.startswith(report_date[:4])
                        & ir_history["segment"].eq(segment),
                        ir_column,
                    ]
                    ir_value = float(comparable.sum()) if len(comparable) == 4 else np.nan
                    comparison_basis = "SEC_ANNUAL_VS_SUM_OF_FOUR_IR_QUARTERS"
                    scope_comparable = not bool(
                        scope_audit.loc[
                            scope_audit["period"].str.startswith(report_date[:4])
                            & scope_audit["segment"].eq(segment),
                            "material_scope_change",
                        ].any()
                    )
                else:
                    comparable = ir_history.loc[
                        ir_history["period"].eq(_period(report_date))
                        & ir_history["segment"].eq(segment),
                        ir_column,
                    ]
                    ir_value = float(comparable.iloc[0]) if len(comparable) == 1 else np.nan
                    comparison_basis = "SEC_CURRENT_QUARTER_VS_IR_CURRENT_QUARTER"
                    scope_comparable = True
                difference = sec_value - ir_value
                identity_pass = bool(np.isfinite(difference) and abs(difference) <= 1.0)
                rows.append(
                    {
                        "period": _period(report_date),
                        "form": source["form"],
                        "segment": segment,
                        "metric": metric,
                        "candidate_facts": len(candidates),
                        "sec_xbrl_value_usd": sec_value,
                        "ir_value_usd": ir_value,
                        "difference_usd": difference,
                        "absolute_difference_usd": abs(difference),
                        "scope_comparable": scope_comparable,
                        "identity_pass": identity_pass,
                        "reconciliation_gate_pass": bool(identity_pass or not scope_comparable),
                        "comparison_basis": comparison_basis,
                        "sec_filing_date": source["filing_date"],
                        "sec_source_url": source["source_url"],
                        "sec_source_sha256": source["sha256"],
                    }
                )
    cross = pd.DataFrame(rows)
    applicable = cross.loc[cross["scope_comparable"]]
    summary = pd.DataFrame(
        [
            {
                "expected_segment_metric_cells": len(inventory) * len(SEGMENT_MEMBERS) * len(SEGMENT_METRICS),
                "selected_segment_metric_cells": int(cross["sec_xbrl_value_usd"].notna().sum()),
                "scope_comparable_cells": len(applicable),
                "scope_recast_excluded_cells": int((~cross["scope_comparable"]).sum()),
                "sec_ir_segment_identity_pass_cells": int(applicable["identity_pass"].sum()),
                "sec_ir_segment_identity_coverage_pct": float(applicable["identity_pass"].mean() * 100.0),
                "maximum_applicable_segment_absolute_difference_usd": float(applicable["absolute_difference_usd"].max()),
                "segment_reconciliation_gate_pass": bool(len(cross) == 184 and cross["reconciliation_gate_pass"].all()),
            }
        ]
    )
    return cross, summary


def _program_adjustments(raw_facts: pd.DataFrame) -> pd.DataFrame:
    frame = raw_facts.loc[
        raw_facts["concept_local"].eq("OperatingIncomeLoss")
        & raw_facts["dimension_count"].ge(3)
        & raw_facts["dimensions"].fillna("").str.contains("ContractsAccountedForUnderPercentageOfCompletionMember", regex=False)
    ].copy()
    frame["duration_days"] = (
        pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])
    ).dt.days
    frame = frame.loc[frame["duration_days"].between(70, 110) & frame["value_usd"].abs().ge(50e6)].copy()
    frame["segment"] = pd.NA
    for segment, member in SEGMENT_MEMBERS.items():
        frame.loc[frame["dimensions"].str.contains(member, regex=False), "segment"] = segment
    frame = frame.loc[frame["segment"].notna()].copy()
    frame["period"] = pd.PeriodIndex(pd.to_datetime(frame["end_date"]), freq="Q").astype(str)
    frame["program_member"] = frame["dimensions"].str.split("|").map(
        lambda values: "|".join(
            sorted(
                value
                for value in values
                if value not in SEGMENT_MEMBERS.values()
                and "PercentageOfCompletion" not in value
                and value != "us-gaap:ContractsAccountedForUnderPercentageOfCompletionMember"
            )
        )
    )
    frame = frame.sort_values(["period", "segment", "program_member", "filing_date", "value_usd"])
    frame = frame.drop_duplicates(["period", "segment", "program_member"], keep="first")
    frame["program_adjustment_usd"] = frame["value_usd"]
    frame["margin_claim_treatment"] = "EXCLUDE_EXPLICIT_PROGRAM_ADJUSTMENT_PERIOD"
    frame["terminal_input_allowed"] = False
    return frame[
        [
            "period", "segment", "program_member", "program_adjustment_usd", "dimensions", "filing_date",
            "accession_number", "source_url", "source_sha256", "margin_claim_treatment",
            "terminal_input_allowed",
        ]
    ].sort_values(["period", "segment", "program_member"]).reset_index(drop=True)


ANNUAL_FACTS = {
    "revenue_usd": ("Revenues",),
    "operating_income_usd": ("OperatingIncomeLoss",),
    "pretax_income_usd": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "income_tax_usd": ("IncomeTaxExpenseBenefit",),
    "cfo_usd": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex_usd": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "depreciation_amortization_usd": ("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"),
    "research_development_usd": ("ResearchAndDevelopmentExpense",),
    "receivables_usd": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
    "inventory_usd": ("InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings", "InventoryNet"),
    "accounts_payable_usd": ("AccountsPayableCurrent",),
    "contract_assets_usd": ("ContractWithCustomerAssetNetCurrent", "ContractWithCustomerAssetNet"),
    "contract_liabilities_usd": ("ContractWithCustomerLiabilityCurrent",),
    "cash_usd": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt_current_usd": ("LongTermDebtCurrent", "DebtCurrent"),
    "debt_noncurrent_usd": ("LongTermDebtNoncurrent",),
    "equity_usd": ("StockholdersEquity",),
    "goodwill_usd": ("Goodwill",),
    "intangibles_ex_goodwill_usd": ("IntangibleAssetsNetExcludingGoodwill",),
    "pension_liability_usd": ("PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent", "DefinedBenefitPensionPlanLiabilitiesNoncurrent"),
}
ANNUAL_FLOWS = {
    "revenue_usd", "operating_income_usd", "pretax_income_usd", "income_tax_usd", "cfo_usd",
    "capex_usd", "depreciation_amortization_usd", "research_development_usd",
}


def _noc_annual_economics(
    inventory: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    wanted = {concept for concepts in ANNUAL_FACTS.values() for concept in concepts}
    for _, source in inventory.loc[inventory["form"].eq("10-K")].sort_values("report_date").iterrows():
        tree = etree.parse(str(source["resolved_path"]), etree.XMLParser(recover=True, huge_tree=True))
        contexts = _contexts(tree)
        facts: list[dict[str, object]] = []
        for node in tree.xpath("//*[local-name()='nonFraction']"):
            concept = _local_name(node.get("name", ""))
            context = contexts.get(node.get("contextRef", ""), {})
            value = _numeric(node)
            if concept in wanted and context and value is not None:
                facts.append({"concept": concept, "value_usd": value, "context_ref": node.get("contextRef"), **context})
        fact_frame = pd.DataFrame(facts)
        report_date = str(source["report_date"])
        row: dict[str, object] = {
            "fiscal_year": int(report_date[:4]), "period": _period(report_date),
            "filing_date": source["filing_date"], "report_date": report_date,
            "source_url": source["source_url"], "source_sha256": source["sha256"],
        }
        for metric, concepts in ANNUAL_FACTS.items():
            candidates = fact_frame.loc[
                fact_frame["concept"].isin(concepts)
                & fact_frame["end_date"].eq(report_date)
                & fact_frame["dimension_count"].eq(0)
            ].copy()
            if metric in ANNUAL_FLOWS:
                candidates["duration_days"] = (
                    pd.to_datetime(candidates["end_date"]) - pd.to_datetime(candidates["start_date"])
                ).dt.days
                candidates = candidates.loc[candidates["duration_days"].between(330, 370)]
            else:
                candidates = candidates.loc[candidates["instant"]]
            candidates["priority"] = candidates["concept"].map({name: index for index, name in enumerate(concepts)})
            candidates = candidates.sort_values(["priority", "context_ref"]).drop_duplicates("value_usd")
            value = float(candidates.iloc[0]["value_usd"]) if len(candidates) else np.nan
            if metric == "debt_current_usd" and not np.isfinite(value):
                value = 0.0
                rule = "DERIVED_ZERO_WHEN_CURRENT_DEBT_NOT_REPORTED"
            else:
                rule = "CONSOLIDATED_NO_DIMENSION_ANNUAL_CONTEXT" if np.isfinite(value) else "MISSING_FAIL_CLOSED"
            row[metric] = value
            selections.append(
                {
                    "fiscal_year": row["fiscal_year"], "metric": metric, "value_usd": value,
                    "available": bool(np.isfinite(value)), "selection_rule": rule,
                    "selected_concept": candidates.iloc[0]["concept"] if len(candidates) else None,
                    "source_url": source["source_url"], "source_sha256": source["sha256"],
                }
            )
        rows.append(row)
    annual = pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)
    tax_rate = annual["income_tax_usd"] / annual["pretax_income_usd"]
    annual["effective_tax_rate_pct"] = tax_rate.where(tax_rate.between(0.0, 0.50), 0.21) * 100.0
    annual["nopat_usd"] = annual["operating_income_usd"] * (1.0 - annual["effective_tax_rate_pct"] / 100.0)
    annual["operating_nwc_usd"] = annual["receivables_usd"] + annual["inventory_usd"] + annual["contract_assets_usd"] - annual["accounts_payable_usd"] - annual["contract_liabilities_usd"]
    annual["change_operating_nwc_usd"] = annual["operating_nwc_usd"].diff()
    annual["net_capex_usd"] = annual["capex_usd"] - annual["depreciation_amortization_usd"]
    annual["core_reinvestment_usd"] = annual["net_capex_usd"] + annual["change_operating_nwc_usd"]
    annual["innovation_adjusted_reinvestment_usd"] = annual["core_reinvestment_usd"] + annual["research_development_usd"]
    annual["total_debt_usd"] = annual["debt_current_usd"] + annual["debt_noncurrent_usd"]
    annual["invested_capital_usd"] = annual["total_debt_usd"] + annual["equity_usd"] - annual["cash_usd"]
    annual["average_invested_capital_usd"] = (annual["invested_capital_usd"] + annual["invested_capital_usd"].shift(1)) / 2.0
    annual["reported_roic_pct"] = annual["nopat_usd"] / annual["average_invested_capital_usd"] * 100.0
    annual["core_reinvestment_rate_pct"] = annual["core_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    annual["innovation_adjusted_reinvestment_rate_pct"] = annual["innovation_adjusted_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    annual["fcff_cash_proxy_usd"] = annual["cfo_usd"] - annual["capex_usd"]
    annual["terminal_input_allowed"] = False
    selection = pd.DataFrame(selections)
    coverage = selection.groupby("metric", as_index=False).agg(years=("available", "size"), years_available=("available", "sum"))
    coverage["coverage_pct"] = coverage["years_available"] / coverage["years"] * 100.0
    critical = set(ANNUAL_FACTS) - {"goodwill_usd", "intangibles_ex_goodwill_usd", "pension_liability_usd"}
    critical_min = float(coverage.loc[coverage["metric"].isin(critical), "coverage_pct"].min())
    summary = pd.DataFrame([{
        "annual_10k_filings": len(annual), "metrics_audited": len(ANNUAL_FACTS),
        "critical_annual_metric_minimum_coverage_pct": critical_min,
        "reported_roic_years": int(annual["reported_roic_pct"].notna().sum()),
        "latest_reported_roic_pct": float(annual.iloc[-1]["reported_roic_pct"]),
        "latest_core_reinvestment_rate_pct": float(annual.iloc[-1]["core_reinvestment_rate_pct"]),
        "latest_innovation_adjusted_reinvestment_rate_pct": float(annual.iloc[-1]["innovation_adjusted_reinvestment_rate_pct"]),
        "research_evidence_ready": bool(len(annual) == 6 and critical_min >= 80.0 and annual["reported_roic_pct"].notna().sum() >= 5),
        "segment_roic_claim_allowed": False, "terminal_input_allowed": False,
    }])
    return annual, selection, coverage, summary


def build_noc_sec_evidence(
    *,
    project_root: Path,
    sec_manifest_path: Path,
    ir_inventory: pd.DataFrame,
    ir_history: pd.DataFrame,
    ir_backlog: pd.DataFrame,
    scope_audit: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    inventory, concept_coverage, family_summary = _source_inventory(project_root, sec_manifest_path)
    parsed = build_lmt_reinvestment_roic_evidence(sec_inventory=inventory)
    raw = parsed["lmt_periodic_relevant_xbrl_facts"]
    cross, cross_summary = _segment_reconciliation(raw, inventory, ir_history, scope_audit)
    programs = _program_adjustments(raw)
    annual, annual_selections, annual_coverage, annual_summary = _noc_annual_economics(inventory)
    periodic_selections = parsed["lmt_periodic_note_fact_selections"]
    rpo = periodic_selections.loc[
        periodic_selections["metric"].eq("remaining_performance_obligation_usd")
        & periodic_selections["available"].astype(bool),
        ["period", "value_usd", "source_url", "source_sha256"],
    ].rename(columns={"value_usd": "sec_rpo_usd", "source_url": "sec_source_url"})
    backlog_sum = ir_backlog.groupby("period", as_index=False).agg(
        ir_segment_backlog_sum_usd=("backlog_usd", "sum"), ir_segment_rows=("segment", "size")
    )
    backlog_cross = backlog_sum.merge(rpo, on="period", how="inner", validate="one_to_one")
    backlog_cross["difference_usd"] = backlog_cross["ir_segment_backlog_sum_usd"] - backlog_cross["sec_rpo_usd"]
    backlog_cross["difference_pct"] = backlog_cross["difference_usd"] / backlog_cross["sec_rpo_usd"] * 100.0
    # NOC's consolidated RPO fact is reported to the nearest $0.1 billion,
    # while its four IR segment rows are reported to the nearest $1 million.
    backlog_cross["rounding_identity_pass"] = backlog_cross["difference_pct"].abs().le(0.07)
    cross_summary["rpo_backlog_periods"] = len(backlog_cross)
    cross_summary["rpo_backlog_identity_pass_periods"] = int(backlog_cross["rounding_identity_pass"].sum())
    cross_summary["rpo_backlog_maximum_absolute_difference_pct"] = float(backlog_cross["difference_pct"].abs().max())
    cross_summary["segment_and_backlog_reconciliation_gate_pass"] = bool(
        cross_summary.iloc[0]["segment_reconciliation_gate_pass"]
        and len(backlog_cross) == 23
        and backlog_cross["rounding_identity_pass"].all()
    )
    selected_ir = ir_inventory.loc[ir_inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")]
    source_summary = pd.DataFrame(
        [
            {
                "sec_filings": len(inventory),
                "sec_10k_filings": int(inventory["form"].eq("10-K").sum()),
                "sec_10q_filings": int(inventory["form"].eq("10-Q").sum()),
                "sec_hash_matches": int(inventory["hash_match"].sum()),
                "ir_earnings_releases": len(selected_ir),
                "ir_hash_matches": int(selected_ir["hash_match"].sum()),
                "concept_families_audited": len(family_summary),
                "concept_family_minimum_coverage_pct": float(family_summary["coverage_pct"].min()),
                "coverage_denominators_are_applicability_aware": True,
                "source_gate_pass": bool(
                    len(inventory) == 23
                    and inventory["hash_match"].all()
                    and len(selected_ir) == 26
                    and selected_ir["hash_match"].all()
                    and family_summary["coverage_pct"].min() >= 80.0
                ),
                "html_only": True,
                "pdf_parsing_used": False,
            }
        ]
    )
    renamed = {
        key.replace("lmt_", "noc_"): value
        for key, value in parsed.items()
        if key not in {"lmt_periodic_relevant_xbrl_facts"}
    }
    return {
        **renamed,
        "noc_sec_periodic_source_inventory": inventory,
        "noc_sec_concept_coverage": concept_coverage,
        "noc_sec_concept_family_summary": family_summary,
        "noc_source_audit_summary": source_summary,
        "noc_periodic_relevant_xbrl_facts": raw,
        "noc_sec_ir_segment_reconciliation": cross,
        "noc_sec_ir_segment_reconciliation_summary": cross_summary,
        "noc_sec_rpo_ir_backlog_reconciliation": backlog_cross,
        "noc_program_adjustment_registry": programs,
        "noc_annual_reinvestment_roic_bridge": annual,
        "noc_annual_economics_fact_selections": annual_selections,
        "noc_annual_economics_fact_coverage": annual_coverage,
        "noc_reinvestment_roic_summary": annual_summary,
    }
