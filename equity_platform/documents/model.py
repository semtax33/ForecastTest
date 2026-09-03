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
    context: str = ""
    source_uri: str = ""
    source_description: str = ""
    source_table_index: int | None = None
    source_row_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class InlineFact:
    name: str
    value: float
    unit: str
    start: str | None
    end: str
    has_dimensions: bool
    source_location: str
    literal: str = ""


@dataclass(frozen=True)
class DocumentSentence:
    """A sentence plus the local document context needed by text IE."""

    sentence_index: int
    text: str
    char_start: int
    char_end: int
    heading: str | None = None
    section: str | None = None
    inline_fact_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.sentence_index < 0 or self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("Document sentences require ordered non-negative spans")
        if not self.text.strip():
            raise ValueError("Document sentences cannot be blank")


@dataclass(frozen=True)
class CanonicalDocument:
    metadata: DocumentMetadata
    source: SourceRef
    text: str
    tables: tuple[DocumentTable, ...]
    inline_facts: tuple[InlineFact, ...]
    sentences: tuple[DocumentSentence, ...] = ()
