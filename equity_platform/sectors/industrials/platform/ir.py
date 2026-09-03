from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import pandas as pd

from .registry import INDUSTRIALS_SUBINDUSTRIES


ROLE_TERMS: dict[str, tuple[bytes, ...]] = {
    "P": (b"price", b"pricing", b"yield", b"rate", b"arpu", b"surcharge"),
    "Q": (
        b"volume", b"backlog", b"order", b"deliver", b"throughput",
        b"passenger", b"container", b"subscriber", b"customer", b"shipment",
        b"carload", b"utilization", b"load factor", b"available seat miles",
    ),
    "C": (
        b"cost", b"fuel", b"labor", b"labour", b"wage", b"material",
        b"inflation", b"margin", b"casm", b"maintenance", b"freight expense",
    ),
    "I": (
        b"capex", b"capital expenditure", b"research and development", b"r&d",
        b"inventory", b"fleet", b"capacity", b"investment", b"working capital",
        b"acquisition",
    ),
}


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def build_arcana_ir_evidence(
    *,
    ir_root: Path,
    start_date: pd.Timestamp = pd.Timestamp("2021-01-01"),
    cutoff: pd.Timestamp,
    verified_cache_path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Audit Arcana's SEC Exhibit 99 IR corpus and identify P/Q/C/I evidence.

    This is a discovery/coverage layer. Keyword hits never become numerical model
    inputs without a company-specific table parser and unit audit.
    """
    document_rows: list[dict[str, object]] = []
    inventory_rows: list[dict[str, object]] = []
    cache: dict[str, dict[str, object]] = {}
    if verified_cache_path is not None and verified_cache_path.exists():
        cached = pd.read_csv(verified_cache_path)
        cache = {
            str(row["source_path"]): row.to_dict()
            for _, row in cached.iterrows()
            if bool(row.get("metadata_sha256_matches", False))
        }
    for profile in INDUSTRIALS_SUBINDUSTRIES:
        ticker = profile.representative_ticker
        company_dir = ir_root / ticker
        metadata_files = (
            sorted(company_dir.glob("*.metadata.json")) if company_dir.exists() else []
        )
        ticker_rows: list[dict[str, object]] = []
        for metadata_path in metadata_files:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            filing_date = pd.Timestamp(metadata["filing_date"])
            if filing_date < start_date or filing_date > cutoff:
                continue
            html_path = Path(str(metadata_path)[: -len(".metadata.json")])
            if not html_path.exists():
                continue
            cached_row = cache.get(str(html_path))
            cache_reusable = bool(
                cached_row
                and cached_row.get("source_sha256") == metadata.get("sha256")
                and html_path.stat().st_size == int(metadata.get("byte_size", -1))
            )
            if cache_reusable:
                actual_hash = str(cached_row["source_sha256"])
                hits = {
                    "P": int(cached_row["price_keyword_hits"]),
                    "Q": int(cached_row["quantity_keyword_hits"]),
                    "C": int(cached_row["cost_keyword_hits"]),
                    "I": int(cached_row["investment_keyword_hits"]),
                }
                verification_mode = "REUSED_VERIFIED_SHA_WITH_SIZE_GATE"
            else:
                content = html_path.read_bytes()
                actual_hash = _sha256_bytes(content)
                lowered = content.lower()
                hits = {
                    role: sum(lowered.count(term) for term in terms)
                    for role, terms in ROLE_TERMS.items()
                }
                verification_mode = "SHA256_RECOMPUTED"
            row = {
                "subindustry_code": profile.code,
                "ticker": ticker,
                "filing_date": filing_date.date().isoformat(),
                "accession_number": metadata.get("accession_number"),
                "form": metadata.get("form"),
                "document_type": metadata.get("document_type"),
                "source_url": metadata.get("source_url"),
                "source_path": str(html_path),
                "source_sha256": actual_hash,
                "metadata_sha256_matches": actual_hash == metadata.get("sha256"),
                "source_byte_size": html_path.stat().st_size,
                "hash_verification_mode": verification_mode,
                "price_keyword_hits": hits["P"],
                "quantity_keyword_hits": hits["Q"],
                "cost_keyword_hits": hits["C"],
                "investment_keyword_hits": hits["I"],
                "numerical_model_input_allowed": False,
                "use": "KPI_DISCOVERY_AND_EVIDENCE_ROUTING_ONLY",
                "pdf_parsing_used": False,
            }
            ticker_rows.append(row)
            document_rows.append(row)
        frame = pd.DataFrame(ticker_rows)
        inventory_rows.append(
            {
                "subindustry_code": profile.code,
                "ticker": ticker,
                "ir_directory_exists": company_dir.exists(),
                "ir_documents_in_window": len(frame),
                "first_ir_filing_date": (
                    frame["filing_date"].min() if not frame.empty else pd.NA
                ),
                "latest_ir_filing_date": (
                    frame["filing_date"].max() if not frame.empty else pd.NA
                ),
                "documents_with_price_evidence": int(
                    frame["price_keyword_hits"].gt(0).sum()
                )
                if not frame.empty
                else 0,
                "documents_with_quantity_evidence": int(
                    frame["quantity_keyword_hits"].gt(0).sum()
                )
                if not frame.empty
                else 0,
                "documents_with_cost_evidence": int(
                    frame["cost_keyword_hits"].gt(0).sum()
                )
                if not frame.empty
                else 0,
                "documents_with_investment_evidence": int(
                    frame["investment_keyword_hits"].gt(0).sum()
                )
                if not frame.empty
                else 0,
                "hash_mismatches": int((~frame["metadata_sha256_matches"]).sum())
                if not frame.empty
                else 0,
                "hashes_reused_from_verified_cache": int(
                    frame["hash_verification_mode"]
                    .eq("REUSED_VERIFIED_SHA_WITH_SIZE_GATE")
                    .sum()
                )
                if not frame.empty
                else 0,
                "company_specific_numeric_parser_required": True,
                "numerical_model_input_allowed": False,
                "status": "IR_HTML_EVIDENCE_READY"
                if len(frame)
                else "NO_DOMESTIC_IR_HTML_IN_ARCANA",
            }
        )
    return {
        "subindustry_ir_document_evidence": pd.DataFrame(document_rows),
        "subindustry_ir_coverage_inventory": pd.DataFrame(inventory_rows),
    }
