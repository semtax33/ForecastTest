from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pandas as pd


CONCEPT_FAMILIES = {
    "statement_revenue_operating_income_tax": ("Revenues", "OperatingIncomeLoss", "IncomeTaxExpense"),
    "statement_cash_flow_capex_depreciation": ("NetCashProvided", "PaymentsToAcquireProductiveAssets", "Depreciation"),
    "statement_working_capital": ("ReceivablesNetCurrent", "Inventory", "AccountsPayableCurrent"),
    "note_segments": ("OperatingSegmentsMember", "SegmentReporting"),
    "note_revenue_and_contracts": ("ContractWithCustomer", "RevenueFromContractWithCustomerTextBlock"),
    "note_contract_assets_liabilities": ("ContractWithCustomerAsset", "ContractWithCustomerLiability"),
    "note_remaining_performance_obligation": ("RevenueRemainingPerformanceObligation",),
    "note_program_gains_losses": ("ProgramGainsLosses", "ClassifiedProgramsGainsLosses"),
    "note_rd": ("ResearchAndDevelopmentExpense",),
    "note_pension_cas": ("Pension", "FasCas", "FASAndCAS"),
    "note_goodwill_intangibles": ("Goodwill", "IntangibleAssets"),
    "note_inventory": ("InventoryDisclosureTextBlock", "ScheduleOfInventory"),
    "note_property_plant_equipment": ("PropertyPlantAndEquipmentTextBlock", "PropertyPlantAndEquipmentDisclosureTextBlock"),
    "note_debt_and_fair_value": ("DebtDisclosureTextBlock", "LongTermDebtFairValue"),
    "note_income_taxes": ("IncomeTaxDisclosureTextBlock", "EffectiveIncomeTaxRate"),
    "note_commitments_contingencies": ("CommitmentsAndContingencies", "LossContingency", "Guarantee"),
    "note_leases": ("OperatingLease", "FinanceLease"),
    "note_stock_compensation": ("ShareBasedCompensation", "StockBasedCompensation"),
    "note_acquisitions_divestitures": ("BusinessCombination", "PaymentsToAcquireBusinesses", "SaleOfBusiness"),
    "capital_structure": ("LongTermDebt", "StockholdersEquity", "CashAndCash"),
}
_CONCEPT = re.compile(r'\bname=["\']([^"\']+)["\']', re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_lmt_source_audit(*, project_root: Path, sec_manifest_path: Path, ir_inventory: pd.DataFrame) -> dict[str, pd.DataFrame]:
    manifest = json.loads(sec_manifest_path.read_text(encoding="utf-8"))
    sec_rows: list[dict[str, object]] = []
    family_rows: list[dict[str, object]] = []
    for item in manifest["files"]:
        path = project_root / item["local_path"]
        raw = path.read_text(encoding="utf-8", errors="ignore")
        concepts = sorted(set(_CONCEPT.findall(raw)))
        sec_rows.append({
            **item,
            "resolved_path": str(path),
            "file_exists": path.exists(),
            "hash_match": _sha256(path) == item["sha256"],
            "inline_xbrl_concept_count": len(concepts),
        })
        for family, needles in CONCEPT_FAMILIES.items():
            matched = sorted(concept for concept in concepts if any(needle.lower() in concept.lower() for needle in needles))
            family_rows.append({
                "form": item["form"],
                "filing_date": item["filing_date"],
                "report_date": item["report_date"],
                "accession_number": item["accession_number"],
                "family": family,
                "evidence_layer": "NOTE" if family.startswith("note_") else "FINANCIAL_STATEMENT",
                "present": bool(matched),
                "matched_concept_count": len(matched),
                "matched_text_block_count": sum("textblock" in concept.lower() for concept in matched),
                "matched_concepts": "|".join(matched),
                "source_url": item["source_url"],
                "source_sha256": item["sha256"],
            })
    sec = pd.DataFrame(sec_rows).sort_values(["filing_date", "form"]).reset_index(drop=True)
    concepts = pd.DataFrame(family_rows)
    concepts["coverage_denominator_policy"] = "ALL_PERIODIC_FILINGS"
    concepts.loc[
        concepts["family"].isin(["note_rd", "note_leases", "note_property_plant_equipment"]),
        "coverage_denominator_policy",
    ] = "ANNUAL_10K_ONLY"
    concepts.loc[
        concepts["family"].isin(["note_program_gains_losses", "note_acquisitions_divestitures"]),
        "coverage_denominator_policy",
    ] = "EVENT_CONDITIONAL_NOT_SCORED"
    concepts["applicable"] = True
    concepts.loc[
        concepts["coverage_denominator_policy"].eq("ANNUAL_10K_ONLY") & ~concepts["form"].eq("10-K"),
        "applicable",
    ] = False
    concepts.loc[
        concepts["coverage_denominator_policy"].eq("EVENT_CONDITIONAL_NOT_SCORED"),
        "applicable",
    ] = False
    concepts["present_when_applicable"] = concepts["present"] & concepts["applicable"]
    family_summary = concepts.groupby(
        ["evidence_layer", "form", "family", "coverage_denominator_policy"], as_index=False
    ).agg(
        filings=("present", "size"),
        filings_with_family=("present", "sum"),
        applicable_filings=("applicable", "sum"),
        applicable_filings_with_family=("present_when_applicable", "sum"),
        filings_with_text_block=("matched_text_block_count", lambda values: int((values > 0).sum())),
    )
    family_summary["raw_presence_pct"] = family_summary["filings_with_family"] / family_summary["filings"] * 100.0
    family_summary["coverage_pct"] = (
        family_summary["applicable_filings_with_family"] / family_summary["applicable_filings"] * 100.0
    ).where(family_summary["applicable_filings"].gt(0))
    family_summary["coverage_status"] = family_summary["coverage_denominator_policy"].where(
        family_summary["coverage_pct"].isna(),
        "APPLICABILITY_ADJUSTED_COVERAGE",
    )
    ir = ir_inventory.loc[ir_inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")].copy()
    summary = pd.DataFrame([{
        "sec_filings": len(sec),
        "sec_10k_filings": int(sec["form"].eq("10-K").sum()),
        "sec_10q_filings": int(sec["form"].eq("10-Q").sum()),
        "sec_hash_matches": int(sec["hash_match"].sum()),
        "ir_earnings_releases": len(ir),
        "ir_hash_matches": int(ir["hash_match"].sum()),
        "financial_statement_family_minimum_coverage_pct": float(family_summary.loc[family_summary["evidence_layer"].eq("FINANCIAL_STATEMENT"), "coverage_pct"].min()),
        "note_family_minimum_coverage_pct": float(family_summary.loc[family_summary["evidence_layer"].eq("NOTE"), "coverage_pct"].min()),
        "note_families_audited": int(concepts.loc[concepts["evidence_layer"].eq("NOTE"), "family"].nunique()),
        "event_conditional_note_families": int(
            concepts.loc[
                concepts["coverage_denominator_policy"].eq("EVENT_CONDITIONAL_NOT_SCORED"),
                "family",
            ].nunique()
        ),
        "coverage_denominators_are_applicability_aware": True,
        "all_sec_hashes_match": bool(sec["hash_match"].all()),
        "all_ir_hashes_match": bool(ir["hash_match"].all()),
        "periodic_filing_inventory_complete": bool(len(sec) == 23 and sec["form"].eq("10-K").sum() == 6 and sec["form"].eq("10-Q").sum() == 17),
        "source_gate_pass": bool(
            len(sec) == 23
            and sec["hash_match"].all()
            and len(ir) == 27
            and ir["hash_match"].all()
            and family_summary.loc[family_summary["coverage_pct"].notna(), "coverage_pct"].min() >= 80.0
        ),
        "html_only": True,
        "pdf_parsing_used": False,
    }])
    return {
        "lmt_sec_periodic_source_inventory": sec,
        "lmt_sec_concept_coverage": concepts,
        "lmt_sec_concept_family_summary": family_summary,
        "lmt_source_audit_summary": summary,
    }
