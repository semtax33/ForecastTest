from __future__ import annotations

from dataclasses import dataclass

from equity_platform.ir import SourceRef


@dataclass(frozen=True)
class DocumentMetadata:
    entity: str
    source_kind: str
    document_kind: str
    available_at: str
    report_period: str | None = None


@dataclass(frozen=True)
class DocumentTable:
    """Position-preserving semantic grid produced before rule execution."""

    resolved_table_index: int
    cells: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class InlineFact:
    name: str
    value: float
    unit: str
    start: str | None
    end: str
    has_dimensions: bool
    source_location: str


@dataclass(frozen=True)
class CanonicalDocument:
    metadata: DocumentMetadata
    source: SourceRef
    text: str
    tables: tuple[DocumentTable, ...]
    inline_facts: tuple[InlineFact, ...]
