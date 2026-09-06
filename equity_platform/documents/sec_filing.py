from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .html import adapt_html_document
from .model import CanonicalDocument, DocumentMetadata


_SUPPORTED_FORMS = ("10-K", "10-Q")


@dataclass(frozen=True)
class SecFilingSource:
    """One hash-verified SEC filing plus its Arcana acquisition metadata."""

    path: Path
    metadata_path: Path
    entity: str
    form: str
    filing_date: str
    report_period: str
    source_uri: str
    sha256: str


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_sec_filing_sources(
    *,
    root: Path,
    forms: tuple[str, ...] = _SUPPORTED_FORMS,
    entities: tuple[str, ...] | None = None,
) -> tuple[SecFilingSource, ...]:
    """Discover Arcana SEC HTML while failing closed on lineage mismatches."""

    requested_entities = (
        {entity.strip().upper() for entity in entities} if entities is not None else None
    )
    sources: list[SecFilingSource] = []
    for form in forms:
        if form not in _SUPPORTED_FORMS:
            raise ValueError(f"unsupported SEC filing form: {form}")
        form_root = root / form
        if not form_root.exists():
            continue
        paths = sorted(
            path
            for suffix in ("*.htm", "*.html")
            for path in form_root.glob(f"*/{suffix}")
        )
        for path in paths:
            entity = path.parent.name.upper()
            if requested_entities is not None and entity not in requested_entities:
                continue
            metadata_path = path.with_name(path.name + ".metadata.json")
            if not metadata_path.exists():
                raise ValueError(f"missing SEC filing metadata: {path}")
            row = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_entity = str(row.get("ticker", "")).strip().upper()
            if metadata_entity != entity:
                raise ValueError(
                    f"SEC filing ticker mismatch: directory={entity}, metadata={metadata_entity}"
                )
            metadata_form = str(row.get("form", "")).strip().upper()
            document_type = str(row.get("document_type", "")).strip().upper()
            if metadata_form != form or document_type != form:
                raise ValueError(
                    f"SEC filing form mismatch: directory={form}, "
                    f"metadata={metadata_form}, document_type={document_type}"
                )
            expected_sha256 = str(row.get("sha256", "")).strip().casefold()
            if len(expected_sha256) != 64 or _file_sha256(path) != expected_sha256:
                raise ValueError(f"SEC filing source hash mismatch: {path}")
            filing_date = str(row.get("filing_date", "")).strip()
            report_period = str(row.get("period_of_report", "")).strip()
            source_uri = str(row.get("source_url", "")).strip()
            if not filing_date or not report_period or not source_uri:
                raise ValueError(f"SEC filing PIT metadata is incomplete: {metadata_path}")
            sources.append(SecFilingSource(
                path=path,
                metadata_path=metadata_path,
                entity=entity,
                form=form,
                filing_date=filing_date,
                report_period=report_period,
                source_uri=source_uri,
                sha256=expected_sha256,
            ))
    return tuple(sorted(
        sources,
        key=lambda row: (row.form, row.entity, row.filing_date, row.path.name),
    ))


def sec_filing_canonical_documents(
    sources: tuple[SecFilingSource, ...],
) -> tuple[CanonicalDocument, ...]:
    """Adapt verified filings; filing date is the public PIT availability date."""

    return tuple(
        adapt_html_document(
            path=source.path,
            metadata=DocumentMetadata(
                entity=source.entity,
                source_kind=f"SEC_{source.form.replace('-', '')}",
                document_kind=source.form,
                available_at=source.filing_date,
                report_period=source.report_period,
            ),
            expected_sha256=source.sha256,
            source_uri=source.source_uri,
            include_tables=False,
            include_inline_facts=False,
        )
        for source in sources
    )


__all__ = [
    "SecFilingSource",
    "discover_sec_filing_sources",
    "sec_filing_canonical_documents",
]
