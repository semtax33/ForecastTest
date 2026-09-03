from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pandas as pd


CONCEPT_FAMILIES = {
    "revenue": ("RevenueFromContract", "SalesRevenue", "Revenues"),
    "operating_income_tax": ("OperatingIncomeLoss", "IncomeTaxExpense"),
    "working_capital": ("Inventory", "AccountsReceivable", "AccountsPayable"),
    "ppe_capex_depreciation": (
        "PropertyPlant",
        "PaymentsToAcquireProperty",
        "CapitalExpenditure",
        "Depreciation",
    ),
    "goodwill_intangibles": ("Goodwill", "IntangibleAssets"),
    "research_development": ("ResearchAndDevelopment",),
    "acquisitions": ("PaymentsToAcquireBusinesses", "BusinessAcquisition"),
    "debt_equity_cash": ("LongTermDebt", "StockholdersEquity", "CashAndCash"),
    "pension_opeb": ("Pension", "Postretirement"),
    "warranty": ("Warranty",),
}
_CONCEPT = re.compile(r'\bname=["\']([^"\']+)["\']', re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_cmi_source_audit(
    *,
    project_root: Path,
    sec_manifest_path: Path,
    ir_inventory: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    manifest = json.loads(sec_manifest_path.read_text(encoding="utf-8"))
    sec_rows: list[dict[str, object]] = []
    concept_rows: list[dict[str, object]] = []
    for item in manifest["files"]:
        path = project_root / item["local_path"]
        raw = path.read_text(encoding="utf-8", errors="ignore")
        concepts = sorted(set(_CONCEPT.findall(raw)))
        row = {
            **item,
            "resolved_path": str(path),
            "file_exists": path.exists(),
            "hash_match": _sha256(path) == item["sha256"],
            "inline_xbrl_concept_count": len(concepts),
        }
        sec_rows.append(row)
        for family, needles in CONCEPT_FAMILIES.items():
            matched = sorted(
                concept for concept in concepts
                if any(needle.lower() in concept.lower() for needle in needles)
            )
            concept_rows.append(
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
    sec = pd.DataFrame(sec_rows).sort_values(["filing_date", "form"]).reset_index(drop=True)
    concepts = pd.DataFrame(concept_rows)
    family_summary = (
        concepts.groupby(["form", "family"], as_index=False)
        .agg(filings=("present", "size"), filings_with_family=("present", "sum"))
    )
    family_summary["coverage_pct"] = (
        family_summary["filings_with_family"] / family_summary["filings"] * 100.0
    )
    ir = ir_inventory.loc[
        ir_inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")
    ].copy()
    summary = pd.DataFrame(
        [
            {
                "sec_filings": len(sec),
                "sec_10k_filings": int(sec["form"].eq("10-K").sum()),
                "sec_10q_filings": int(sec["form"].eq("10-Q").sum()),
                "sec_hash_matches": int(sec["hash_match"].sum()),
                "ir_earnings_releases": len(ir),
                "ir_hash_matches": int(ir["hash_match"].sum()),
                "all_sec_hashes_match": bool(sec["hash_match"].all()),
                "all_ir_hashes_match": bool(ir["hash_match"].all()),
                "periodic_filing_inventory_complete": bool(
                    len(sec) == 23
                    and sec["form"].eq("10-K").sum() == 6
                    and sec["form"].eq("10-Q").sum() == 17
                ),
                "source_gate_pass": bool(
                    len(sec) == 23
                    and sec["hash_match"].all()
                    and len(ir) == 27
                    and ir["hash_match"].all()
                ),
                "html_only": True,
                "pdf_parsing_used": False,
            }
        ]
    )
    return {
        "cmi_sec_periodic_source_inventory": sec,
        "cmi_sec_concept_coverage": concepts,
        "cmi_sec_concept_family_summary": family_summary,
        "cmi_source_audit_summary": summary,
    }
