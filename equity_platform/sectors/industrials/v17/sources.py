from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pandas as pd


CONCEPT_FAMILIES = {
    "segment": ("Segment", "ProductOrServiceAxis"),
    "inventory": ("Inventory",),
    "ppe_capex_depreciation": ("PropertyPlant", "CapitalExpenditure", "PaymentsToAcquireProperty", "Depreciation"),
    "goodwill_intangibles": ("Goodwill", "IntangibleAssets"),
    "research_development": ("ResearchAndDevelopment",),
    "restructuring": ("Restructur",),
    "pension_opeb": ("Pension", "Postretirement"),
    "warranty": ("Warranty",),
    "income_tax": ("IncomeTax",),
    "acquisitions": ("PaymentsToAcquireBusinesses", "BusinessAcquisition"),
    "debt_equity_cash": ("LongTermDebt", "StockholdersEquity", "CashAndCash"),
}
_CONCEPT = re.compile(r'\bname=["\']([^"\']+)["\']', re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_audit(
    *,
    project_root: Path,
    sec_manifest_path: Path,
    ir_history: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    manifest = json.loads(sec_manifest_path.read_text(encoding="utf-8"))
    sec_rows: list[dict[str, object]] = []
    concept_rows: list[dict[str, object]] = []
    for item in manifest["files"]:
        path = project_root / item["local_path"]
        raw = path.read_text(encoding="utf-8", errors="ignore")
        concepts = sorted(set(_CONCEPT.findall(raw)))
        hash_match = _sha256(path) == item["sha256"]
        sec_rows.append(
            {
                **item,
                "resolved_path": str(path),
                "file_exists": path.exists(),
                "hash_match": hash_match,
                "inline_xbrl_concept_count": len(concepts),
            }
        )
        for family, needles in CONCEPT_FAMILIES.items():
            matched = sorted({concept for concept in concepts if any(needle.lower() in concept.lower() for needle in needles)})
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
    coverage = pd.DataFrame(concept_rows)

    ir = ir_history[
        ["period", "filing_date", "source_url", "source_path", "source_sha256"]
    ].drop_duplicates().copy()
    ir["file_exists"] = ir["source_path"].map(lambda value: Path(value).exists())
    ir["actual_sha256"] = ir["source_path"].map(lambda value: _sha256(Path(value)))
    ir["hash_match"] = ir["source_sha256"].eq(ir["actual_sha256"])
    ir["source_role"] = "CAT_EARNINGS_RELEASE_SEGMENT_ACTUAL_AND_DRIVER_EVIDENCE"
    ir["pdf_parsing_used"] = False

    family_summary = (
        coverage.groupby(["form", "family"], as_index=False)
        .agg(filings=("present", "size"), filings_with_family=("present", "sum"))
    )
    family_summary["coverage_pct"] = family_summary["filings_with_family"] / family_summary["filings"] * 100.0
    summary = pd.DataFrame(
        [
            {
                "sec_filings": len(sec),
                "sec_10k_filings": int(sec["form"].eq("10-K").sum()),
                "sec_10q_filings": int(sec["form"].eq("10-Q").sum()),
                "sec_hash_matches": int(sec["hash_match"].sum()),
                "ir_earnings_releases": len(ir),
                "ir_quarters": ir["period"].nunique(),
                "ir_hash_matches": int(ir["hash_match"].sum()),
                "all_sec_hashes_match": bool(sec["hash_match"].all()),
                "all_ir_hashes_match": bool(ir["hash_match"].all()),
                "expected_periodic_filing_count": 23,
                "periodic_filing_inventory_complete": bool(
                    len(sec) == 23
                    and sec["form"].eq("10-K").sum() == 6
                    and sec["form"].eq("10-Q").sum() == 17
                ),
                "html_only": True,
                "pdf_parsing_used": False,
                "source_gate_pass": bool(
                    len(sec) == 23
                    and sec["hash_match"].all()
                    and len(ir) == 23
                    and ir["hash_match"].all()
                ),
            }
        ]
    )
    return {
        "sec_periodic_source_inventory": sec,
        "sec_footnote_concept_coverage": coverage,
        "sec_footnote_family_summary": family_summary,
        "ir_driver_source_inventory": ir.reset_index(drop=True),
        "v1_7_source_audit_summary": summary,
    }
