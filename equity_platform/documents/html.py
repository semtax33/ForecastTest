from __future__ import annotations

from hashlib import sha256
from io import StringIO
from pathlib import Path
import re
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from lxml import html as lxml_html
import numpy as np
import pandas as pd

from equity_platform.ir import SourceRef
from equity_platform.numeric import parse_numeric_token

from .model import CanonicalDocument, DocumentMetadata, DocumentTable, InlineFact


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
