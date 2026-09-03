from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from equity_platform.documents import (
    DocumentMetadata,
    HtmlFragment,
    adapt_html_fragments,
)


def load_ir_tables(
    path: Path,
    *,
    ticker: str,
    report_period: str,
    available_at: str,
    source_uri: str,
) -> list[list[list[str]]]:
    """Load an IR filing through CanonicalDocument, preserving table order."""

    content = path.read_bytes()
    document = adapt_html_fragments(
        fragments=(
            HtmlFragment(
                content=content,
                source_uri=source_uri,
                source_description="COMPANY_IR_OR_SEC_FILING",
                local_path=str(path),
                expected_sha256=sha256(content).hexdigest(),
                numeric_rows_only=False,
                collapse_adjacent_cells=True,
            ),
        ),
        metadata=DocumentMetadata(
            entity=ticker,
            source_kind="COMPANY_IR_SEC",
            document_kind="EARNINGS_RELEASE",
            available_at=available_at,
            report_period=report_period,
        ),
    )
    return [[list(row) for row in table.cells] for table in document.tables]
