from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.ir import FactIR
from equity_platform.text_ie import (
    KPIFrame,
    KPIRelationIR,
    TextExtractionResult,
    derive_difference,
    extract_text_kpis,
)


@dataclass(frozen=True)
class CatBacklogSemanticResult:
    """Validated CAT backlog facts produced by the semantic text-IE layer."""

    current: FactIR
    prior: FactIR
    not_expected_next_year: FactIR
    expected_within_next_year: FactIR
    frames: tuple[KPIFrame, ...]
    relations: tuple[KPIRelationIR, ...]
    review_count: int


def _unique_fact(result: TextExtractionResult, metric: str) -> FactIR:
    matches = tuple(fact for fact in result.facts if fact.metric == metric)
    if len(matches) != 1:
        raise ValueError(f"Expected one {metric} fact, received {len(matches)}")
    fact = matches[0]
    if not isinstance(fact, FactIR):
        raise TypeError(f"Text IE emitted a non-FactIR object for {metric}")
    return fact


def parse_cat_backlog_semantic_ir(source: pd.Series) -> CatBacklogSemanticResult:
    """Parse CAT narrative backlog without issuer-specific Python extraction.

    The issuer-specific function only selects and validates the required
    concepts. Sentence interpretation itself is driven by the shared
    ``text_rule`` DSL and canonical KPIFrame runtime.
    """

    fiscal_year = int(source["fiscal_year"])
    path = Path(str(source["resolved_path"]))
    document = adapt_html_document(
        path=path,
        metadata=DocumentMetadata(
            entity="CAT",
            source_kind="SEC_10K",
            document_kind="ANNUAL_REPORT",
            available_at=pd.Timestamp(source["filing_date"]).date().isoformat(),
            report_period=str(fiscal_year),
        ),
        expected_sha256=str(source["source_sha256"]),
        source_uri=str(source["source_url"]),
        include_tables=False,
        include_inline_facts=True,
    )
    result = extract_text_kpis(document)
    current = _unique_fact(result, "FIRM_ORDER_BACKLOG")
    prior = _unique_fact(result, "PRIOR_YEAR_FIRM_ORDER_BACKLOG")
    not_expected = _unique_fact(result, "BACKLOG_NOT_EXPECTED")
    if current.period != str(fiscal_year):
        raise ValueError("Current backlog period does not match the filing fiscal year")
    if prior.period != str(fiscal_year - 1):
        raise ValueError("Prior backlog period is not the immediately preceding year")
    if not_expected.period != str(fiscal_year + 1):
        raise ValueError("Not-expected backlog does not resolve to the next fill year")
    expected = derive_difference(
        current,
        not_expected,
        metric="BACKLOG_EXPECTED_WITHIN_NEXT_YEAR",
        period=str(fiscal_year + 1),
    )
    return CatBacklogSemanticResult(
        current=current,
        prior=prior,
        not_expected_next_year=not_expected,
        expected_within_next_year=expected,
        frames=result.frames,
        relations=result.relations,
        review_count=len(result.reviews),
    )
