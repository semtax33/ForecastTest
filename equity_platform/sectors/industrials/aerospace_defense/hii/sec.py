from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from lxml import etree

from equity_platform.sectors.industrials.aerospace_defense.lmt.xbrl import (
    _annual_bridge,
    build_lmt_reinvestment_roic_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.noc.sec import _source_inventory
from equity_platform.sectors.industrials.v17.reinvestment import _contexts, _local_name, _numeric


SEGMENT_MEMBERS = {
    "ingalls_shipbuilding": ("IngallsMember",),
    "newport_news_shipbuilding": ("NewportNewsShipbuildingMember",),
    "mission_technologies": ("MissionTechnologiesMember", "TechnicalSolutionsMember"),
}
HII_ALIASES = {
    "receivables_usd": ("AccountsReceivableNetCurrent", "AccountsReceivableNet"),
    "intangibles_ex_goodwill_usd": ("FiniteLivedIntangibleAssetsNet",),
    "debt_current_usd": ("LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermDebtCurrent"),
    "debt_noncurrent_usd": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "contract_liabilities_usd": (
        "ContractWithCustomerLiabilityCurrent", "BillingsInExcessOfCostCurrent"
    ),
    "fas_cas_pension_adjustment_usd": ("FasCasAdjustment",),
    "program_gains_losses_usd": ("ChangeInAccountingEstimateEffectOfChangeOnOperatingResults",),
}
HII_ALIAS_FLOW = {"fas_cas_pension_adjustment_usd", "program_gains_losses_usd"}


def _period(report_date: str) -> str:
    quarter = {3: 1, 6: 2, 9: 3, 12: 4}[pd.Timestamp(report_date).month]
    return f"{report_date[:4]}Q{quarter}"


def _segment_sec_ir_reconciliation(
    raw: pd.DataFrame,
    inventory: pd.DataFrame,
    ir_history: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, source in inventory.iterrows():
        period = _period(str(source["report_date"]))
        quarter = int(period[-1])
        filing = raw.loc[
            raw["accession_number"].eq(source["accession_number"])
            & raw["concept_local"].isin(["Revenues", "OperatingIncomeLoss"])
            & raw["end_date"].eq(source["report_date"])
        ].copy()
        filing["duration_days"] = (
            pd.to_datetime(filing["end_date"]) - pd.to_datetime(filing["start_date"])
        ).dt.days
        target_days = 365 if quarter == 4 else 90
        for segment, members in SEGMENT_MEMBERS.items():
            for concept, ir_metric in {"Revenues": "sales_usd", "OperatingIncomeLoss": "operating_profit_usd"}.items():
                member_pattern = "|".join(members)
                candidates = filing.loc[
                    filing["concept_local"].eq(concept)
                    & filing["dimensions"].fillna("").str.contains(member_pattern, regex=True)
                    & (
                        filing["dimension_count"].eq(1)
                        | (
                            filing["dimension_count"].eq(2)
                            & filing["dimensions"].fillna("").str.contains("OperatingSegmentsMember", regex=False)
                        )
                    )
                ].copy()
                candidates["duration_distance"] = (candidates["duration_days"] - target_days).abs()
                candidates = candidates.sort_values(["duration_distance", "context_ref"])
                if candidates.empty:
                    sec_value = np.nan
                    context_ref = None
                else:
                    sec_value = float(candidates.iloc[0]["value_usd"])
                    context_ref = candidates.iloc[0]["context_ref"]
                if quarter == 4:
                    ir_values = ir_history.loc[
                        ir_history["segment"].eq(segment)
                        & ir_history["period"].str.startswith(period[:4]), ir_metric
                    ]
                    ir_value = float(ir_values.sum()) if len(ir_values) == 4 else np.nan
                    comparison_basis = "SEC_ANNUAL_VS_SUM_AS_REPORTED_IR_QUARTERS"
                else:
                    ir_values = ir_history.loc[
                        ir_history["segment"].eq(segment) & ir_history["period"].eq(period), ir_metric
                    ]
                    ir_value = float(ir_values.iloc[0]) if len(ir_values) == 1 else np.nan
                    comparison_basis = "SEC_DISCRETE_QUARTER_VS_AS_REPORTED_IR_QUARTER"
                difference = sec_value - ir_value if np.isfinite(sec_value) and np.isfinite(ir_value) else np.nan
                rows.append({
                    "period": period, "form": source["form"], "segment": segment, "metric": ir_metric,
                    "sec_value_usd": sec_value, "ir_value_usd": ir_value, "difference_usd": difference,
                    "identity_pass": bool(np.isfinite(difference) and abs(difference) <= 1.0),
                    "comparison_basis": comparison_basis, "context_ref": context_ref,
                    "filing_date": source["filing_date"], "source_url": source["source_url"],
                    "source_sha256": source["sha256"],
                })
    return pd.DataFrame(rows)


def _hii_alias_selections(inventory: pd.DataFrame) -> pd.DataFrame:
    wanted = {name for aliases in HII_ALIASES.values() for name in aliases}
    rows: list[dict[str, object]] = []
    for _, source in inventory.iterrows():
        tree = etree.parse(str(source["resolved_path"]), etree.XMLParser(recover=True, huge_tree=True))
        contexts = _contexts(tree)
        facts: list[dict[str, object]] = []
        for node in tree.xpath("//*[local-name()='nonFraction']"):
            concept = _local_name(node.get("name", ""))
            if concept not in wanted:
                continue
            context = contexts.get(node.get("contextRef", ""), {})
            value = _numeric(node)
            if context and value is not None:
                facts.append({"concept": concept, "value_usd": value, "context_ref": node.get("contextRef"), **context})
        frame = pd.DataFrame(facts)
        for metric, aliases in HII_ALIASES.items():
            candidates = frame.loc[
                frame["concept"].isin(aliases)
                & frame["end_date"].eq(source["report_date"])
                & frame["dimension_count"].eq(0)
            ].copy() if len(frame) else pd.DataFrame()
            if len(candidates) and metric in HII_ALIAS_FLOW:
                candidates["duration_days"] = (
                    pd.to_datetime(candidates["end_date"]) - pd.to_datetime(candidates["start_date"])
                ).dt.days
                lower, upper = ((330, 370) if source["form"] == "10-K" else (70, 290))
                candidates = candidates.loc[candidates["duration_days"].between(lower, upper)]
            elif len(candidates):
                candidates = candidates.loc[candidates["instant"]]
            if len(candidates):
                candidates["priority"] = candidates["concept"].map({name: index for index, name in enumerate(aliases)})
                if metric in HII_ALIAS_FLOW:
                    candidates = candidates.sort_values(["priority", "duration_days", "context_ref"], ascending=[True, False, True])
                else:
                    candidates = candidates.sort_values(["priority", "context_ref"])
                selected = candidates.iloc[0]
                value, concept, context_ref = float(selected["value_usd"]), selected["concept"], selected["context_ref"]
            else:
                value, concept, context_ref = np.nan, None, None
            rows.append({
                "form": source["form"], "period": _period(str(source["report_date"])),
                "filing_date": source["filing_date"], "report_date": source["report_date"],
                "accession_number": source["accession_number"], "metric": metric,
                "value_usd": value, "available": bool(np.isfinite(value)),
                "selected_concept": concept, "selected_context_ref": context_ref,
                "selection_rule": "HII_CONSOLIDATED_ALIAS_REPORT_DATE_CONTEXT",
                "source_url": source["source_url"], "source_sha256": source["sha256"],
                "evidence_layer": "NOTE" if metric in HII_ALIAS_FLOW | {"contract_liabilities_usd"} else "FINANCIAL_STATEMENT",
            })
    return pd.DataFrame(rows)


def _complete_annual_bridge(
    annual: pd.DataFrame, aliases: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = annual.copy()
    annual_aliases = aliases.loc[aliases["form"].eq("10-K")]
    fill_rows: list[dict[str, object]] = []
    for index, row in result.iterrows():
        period = row["period"]
        for metric in HII_ALIASES:
            candidate = annual_aliases.loc[
                annual_aliases["period"].eq(period) & annual_aliases["metric"].eq(metric)
            ]
            old_value = result.at[index, metric]
            alias_value = candidate.iloc[0]["value_usd"] if len(candidate) else np.nan
            applied = bool(
                np.isfinite(alias_value)
                and (pd.isna(old_value) or metric in HII_ALIAS_FLOW)
            )
            if applied:
                result.at[index, metric] = alias_value
            fill_rows.append({
                "period": period, "metric": metric, "original_value_usd": old_value,
                "alias_value_usd": alias_value, "alias_applied": applied,
                "final_value_usd": result.at[index, metric],
                "selected_concept": candidate.iloc[0]["selected_concept"] if len(candidate) else None,
            })
    completed = _annual_bridge(result)
    completed["historical_diagnostic_only"] = True
    completed["terminal_input_allowed"] = False
    return completed, pd.DataFrame(fill_rows)


def build_hii_sec_evidence(
    *, project_root: Path, manifest_path: Path, ir_history: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    inventory, concept_coverage, family_summary = _source_inventory(project_root, manifest_path)
    lmt = build_lmt_reinvestment_roic_evidence(sec_inventory=inventory)
    artifacts = {key.replace("lmt_", "hii_"): value for key, value in lmt.items()}
    raw = artifacts["hii_periodic_relevant_xbrl_facts"]
    alias_selections = _hii_alias_selections(inventory)
    annual, alias_audit = _complete_annual_bridge(
        artifacts["hii_annual_reinvestment_roic_bridge"], alias_selections
    )
    artifacts["hii_annual_reinvestment_roic_bridge"] = annual
    artifacts["hii_alias_fact_selections"] = alias_selections
    artifacts["hii_annual_alias_completion_audit"] = alias_audit
    reconciliation = _segment_sec_ir_reconciliation(raw, inventory, ir_history)
    comparable = reconciliation.loc[reconciliation["sec_value_usd"].notna() & reconciliation["ir_value_usd"].notna()]
    roic_summary = artifacts["hii_reinvestment_roic_summary"].copy()
    critical_metrics = [
        "operating_income_usd", "income_tax_usd", "capex_usd",
        "depreciation_amortization_usd", "inventory_usd", "receivables_usd",
        "accounts_payable_usd", "contract_assets_usd", "cash_usd", "equity_usd",
    ]
    critical = float(annual[critical_metrics].notna().mean().mul(100.0).min())
    roic_summary["critical_annual_metric_minimum_coverage_pct"] = critical
    roic_summary["alias_completed_annual_cells"] = int(alias_audit["alias_applied"].sum())
    roic_summary["latest_reported_roic_pct"] = float(annual.iloc[-1]["reported_roic_pct"])
    roic_summary["latest_pension_adjusted_roic_pct"] = float(annual.iloc[-1]["pension_adjusted_roic_pct"])
    roic_summary["latest_through_cycle_roic_median_pct"] = float(annual.iloc[-1]["through_cycle_reported_roic_median_pct"])
    roic_summary["latest_core_reinvestment_rate_pct"] = float(annual.iloc[-1]["core_reinvestment_rate_pct"])
    roic_summary["latest_innovation_adjusted_reinvestment_rate_pct"] = float(annual.iloc[-1]["innovation_adjusted_reinvestment_rate_pct"])
    roic_summary["research_evidence_ready"] = bool(
        len(inventory) >= 24 and len(annual) >= 6 and critical >= 80.0
        and annual["reported_roic_pct"].notna().sum() >= 5
    )
    roic_summary["historical_diagnostic_only"] = True
    roic_summary["margin_authority"] = False
    roic_summary["terminal_input_allowed"] = False
    artifacts["hii_reinvestment_roic_summary"] = roic_summary
    source_summary = pd.DataFrame([{
        "sec_filings": len(inventory), "sec_10k_filings": int(inventory["form"].eq("10-K").sum()),
        "sec_10q_filings": int(inventory["form"].eq("10-Q").sum()),
        "sec_hash_matches": int(inventory["hash_match"].sum()),
        "concept_families_audited": len(family_summary),
        "concept_family_minimum_coverage_pct": float(family_summary["coverage_pct"].min()),
        "segment_metric_comparable_cells": len(comparable),
        "segment_metric_identity_pass_cells": int(comparable["identity_pass"].sum()),
        "segment_metric_identity_pass_pct": float(comparable["identity_pass"].mean() * 100.0) if len(comparable) else 0.0,
        "source_gate_pass": bool(len(inventory) == 27 and inventory["hash_match"].all() and len(comparable) >= 120 and comparable["identity_pass"].all()),
        "pdf_parsing_used": False,
    }])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_summary = pd.DataFrame([{
        "dataset": manifest["dataset"], "start_date": manifest["start_date"],
        "cutoff_date": manifest["cutoff_date"], "filing_count": manifest["filing_count"],
        "ten_k_count": manifest["form_counts"]["10-K"], "ten_q_count": manifest["form_counts"]["10-Q"],
        "periodic_history_years": pd.Timestamp(manifest["cutoff_date"]).year - pd.Timestamp(manifest["start_date"]).year + 1,
        "six_year_criterion_pass": bool(manifest["form_counts"]["10-K"] >= 6),
    }])
    return {
        "hii_sec_source_inventory": inventory,
        "hii_sec_concept_coverage": concept_coverage,
        "hii_sec_concept_family_summary": family_summary,
        "hii_sec_ir_segment_reconciliation": reconciliation,
        "hii_sec_source_summary": source_summary,
        "hii_sec_manifest_summary": manifest_summary,
        **artifacts,
    }
