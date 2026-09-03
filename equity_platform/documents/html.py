from __future__ import annotations

from hashlib import sha256
from io import StringIO
from pathlib import Path
import re
import warnings
from dataclasses import dataclass

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from lxml import html as lxml_html
import numpy as np
import pandas as pd

from equity_platform.ir import SourceRef
from equity_platform.numeric import parse_numeric_token

from .model import CanonicalDocument, DocumentMetadata, DocumentTable, InlineFact


@dataclass(frozen=True)
class HtmlFragment:
    """One immutable source fragment in a composite filing document."""

    content: bytes
    source_uri: str
    source_description: str
    local_path: str = ""
    expected_sha256: str | None = None
    numeric_rows_only: bool = True
    collapse_adjacent_cells: bool = False


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _inline_facts(soup: BeautifulSoup) -> tuple[InlineFact, ...]:
    contexts: dict[str, tuple[str | None, str, bool]] = {}
    for context in soup.find_all(lambda tag: tag.name and tag.name.endswith("context")):
        context_id = context.get("id")
        if not context_id:
            continue
        start_tag = context.find(lambda tag: tag.name and tag.name.endswith("startdate"))
        end_tag = context.find(lambda tag: tag.name and tag.name.endswith("enddate"))
        instant_tag = context.find(lambda tag: tag.name and tag.name.endswith("instant"))
        start = _clean(start_tag.get_text()) if start_tag else None
        end = _clean(end_tag.get_text()) if end_tag else _clean(instant_tag.get_text()) if instant_tag else ""
        if not end:
            continue
        has_dimensions = bool(
            context.find(
                lambda tag: tag.name
                and (
                    tag.name.endswith("explicitmember")
                    or tag.name.endswith("typedmember")
                )
            )
        )
        contexts[str(context_id)] = (start, end, has_dimensions)

    facts: list[InlineFact] = []
    fact_tags = soup.find_all(
        lambda tag: tag.name
        and (tag.name.endswith("nonfraction") or tag.name.endswith("nonnumeric"))
        and tag.get("name")
        and tag.get("contextref")
    )
    for ordinal, tag in enumerate(fact_tags):
        context = contexts.get(str(tag.get("contextref")))
        if context is None or str(tag.get("nil", "false")).lower() == "true":
            continue
        start, end, has_dimensions = context
        scale_text = str(tag.get("scale", "0"))
        try:
            scale = int(scale_text)
        except ValueError:
            scale = 0
        value = parse_numeric_token(
            tag.get_text(" ", strip=True), scale=scale, sign=tag.get("sign")
        )
        if value is None:
            continue
        facts.append(
            InlineFact(
                name=str(tag.get("name")),
                value=value,
                unit=str(tag.get("unitref", "NOT_IDENTIFIED")),
                start=start,
                end=end,
                has_dimensions=has_dimensions,
                source_location=f"inline_fact:{ordinal}",
            )
        )
    return tuple(facts)


def adapt_html_document(
    *,
    path: Path,
    metadata: DocumentMetadata,
    expected_sha256: str,
    source_uri: str,
    include_tables: bool,
    include_inline_facts: bool,
) -> CanonicalDocument:
    """Convert raw HTML into the only document model visible to parser rules."""

    actual_sha = _sha(path)
    if actual_sha != expected_sha256:
        raise ValueError(f"Source hash mismatch: {path}")
    content = path.read_bytes()
    html = content.decode("utf-8", errors="ignore")
    text = " ".join(lxml_html.fromstring(content).text_content().split())
    tables: list[DocumentTable] = []
    if include_tables:
        try:
            parsed_tables = pd.read_html(StringIO(html))
        except ValueError:
            parsed_tables = []
        for index, table in enumerate(parsed_tables):
            data_cells = tuple(
                tuple(_clean(value) for value in row)
                for row in table.to_numpy(dtype=object)
            )
            default_columns = isinstance(table.columns, pd.RangeIndex)
            if isinstance(table.columns, pd.MultiIndex):
                header_cells = tuple(
                    " ".join(
                        part
                        for part in (_clean(value) for value in column)
                        if part and not part.lower().startswith("unnamed:")
                    )
                    for column in table.columns
                )
            else:
                header_cells = tuple(_clean(value) for value in table.columns)
            cells = (
                (header_cells,) + data_cells
                if not default_columns and any(header_cells)
                else data_cells
            )
            tables.append(DocumentTable(resolved_table_index=index, cells=cells))
    if include_inline_facts:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")
        inline = _inline_facts(soup)
    else:
        inline = ()
    source = SourceRef(
        source_type=metadata.source_kind,
        uri=source_uri,
        local_path=path.as_posix(),
        sha256=actual_sha,
        available_at=metadata.available_at,
    )
    return CanonicalDocument(
        metadata=metadata,
        source=source,
        text=text,
        tables=tuple(tables),
        inline_facts=inline,
    )


def adapt_html_fragments(
    *, fragments: tuple[HtmlFragment, ...], metadata: DocumentMetadata
) -> CanonicalDocument:
    """Adapt multiple SEC/IR HTML exhibits into a provenance-preserving row IR.

    This adapter intentionally mirrors browser-visible table rows.  It is used
    for operating KPIs whose issuer presentations do not expose stable XBRL
    concepts.  Rules see only :class:`CanonicalDocument`, never BeautifulSoup.
    """

    if not fragments:
        raise ValueError("At least one HTML fragment is required")
    tables: list[DocumentTable] = []
    text_parts: list[str] = []
    fragment_hashes: list[str] = []
    resolved_index = 0
    for fragment in fragments:
        actual_sha = sha256(fragment.content).hexdigest()
        if fragment.expected_sha256 and actual_sha != fragment.expected_sha256:
            raise ValueError(f"Source hash mismatch: {fragment.local_path}")
        fragment_hashes.append(actual_sha)
        html = fragment.content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        text_parts.append(" ".join(soup.get_text(" ", strip=True).split()))
        seen: set[tuple[str, tuple[float, ...]]] = set()
        for source_table_index, table in enumerate(soup.find_all("table")):
            context_rows = []
            for context_tr in table.find_all("tr", recursive=False)[:4]:
                context = re.sub(
                    r"\s+", " ", context_tr.get_text(" | ", strip=True)
                ).strip()
                if context:
                    context_rows.append(context)
            context = " || ".join(context_rows)[:2_000]
            rows: list[tuple[str, ...]] = []
            row_indices: list[int] = []
            for source_row_index, tr in enumerate(table.find_all("tr")):
                cells = tr.find_all(["td", "th"], recursive=False)
                if not cells:
                    continue
                tokens = tuple(
                    token
                    for cell in cells
                    if (
                        token := re.sub(
                            r"\s+", " ", cell.get_text(" ", strip=True)
                        ).strip()
                    )
                )
                if fragment.collapse_adjacent_cells:
                    tokens = tuple(
                        token
                        for index, token in enumerate(tokens)
                        if index == 0 or token != tokens[index - 1]
                    )
                numeric = tuple(
                    value
                    for token in tokens
                    if (value := parse_numeric_token(token, strict=True)) is not None
                )
                row_text = " | ".join(tokens)
                key = (row_text.casefold(), numeric)
                if (fragment.numeric_rows_only and not numeric) or key in seen:
                    continue
                seen.add(key)
                rows.append(tokens)
                row_indices.append(source_row_index)
            if not rows:
                continue
            tables.append(
                DocumentTable(
                    resolved_table_index=resolved_index,
                    cells=tuple(rows),
                    context=context,
                    source_uri=fragment.source_uri,
                    source_description=fragment.source_description,
                    source_table_index=source_table_index,
                    source_row_indices=tuple(row_indices),
                )
            )
            resolved_index += 1
    aggregate_sha = sha256("".join(fragment_hashes).encode("ascii")).hexdigest()
    source = SourceRef(
        source_type=metadata.source_kind,
        uri=";".join(fragment.source_uri for fragment in fragments),
        local_path=";".join(fragment.local_path for fragment in fragments),
        sha256=aggregate_sha,
        available_at=metadata.available_at,
    )
    return CanonicalDocument(
        metadata=metadata,
        source=source,
        text=" ".join(text_parts),
        tables=tuple(tables),
        inline_facts=(),
    )
