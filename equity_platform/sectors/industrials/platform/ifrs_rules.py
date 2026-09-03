from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.parsing import compile_rule_file, execute_rules
from equity_platform.parsing.rule_ir import PeriodMode, SelectorKind


FORM_DOCUMENT = {
    "20-F": ("SEC_20F", "ANNUAL_REPORT"),
    "6-K": ("SEC_6K", "OPERATING_RELEASE"),
}


def _profile_path(project_root: Path, ticker: str) -> Path:
    return project_root / "configs/parser_rules/industrials" / f"{ticker.lower()}.arc"


def build_ifrs_rule_evidence(
    *, project_root: Path, manifest: dict[str, object]
) -> dict[str, pd.DataFrame]:
    """Run an optional issuer vocabulary profile through the shared DSL runtime."""

    profile_path = _profile_path(project_root, str(manifest["ticker"]))
    if not profile_path.exists():
        return {
            "parser_rule_inventory": pd.DataFrame(),
            "parser_rule_execution_audit": pd.DataFrame(),
            "parser_fact_ir": pd.DataFrame(),
        }
    rules = compile_rule_file(profile_path)
    inventory = pd.DataFrame(
        [
            {
                "ticker": manifest["ticker"],
                "rule_id": rule.rule_id,
                "rule_version": rule.version,
                "selector": rule.selector.value,
                "metric": rule.metric,
                "rule_source_path": profile_path.relative_to(project_root).as_posix(),
                "rule_source_sha256": rule.source_sha256,
            }
            for rule in rules
        ]
    )
    execution_rows: list[dict[str, object]] = []
    fact_rows: list[dict[str, object]] = []
    for filing in manifest["filings"]:
        form = str(filing["form"])
        if form not in FORM_DOCUMENT:
            continue
        source_kind, document_kind = FORM_DOCUMENT[form]
        applicable = tuple(
            rule
            for rule in rules
            if rule.source == source_kind and rule.document == document_kind
        )
        if not applicable:
            continue
        path = project_root / str(filing["local_path"])
        metadata = DocumentMetadata(
            entity=str(manifest["ticker"]),
            source_kind=source_kind,
            document_kind=document_kind,
            available_at=str(filing["filing_date"]),
            report_period=str(filing["report_date"] or "") or None,
        )
        include_inline = any(rule.selector is SelectorKind.INLINE_FACT for rule in applicable)
        include_tables = any(
            rule.selector is SelectorKind.TABLE
            and rule.period_mode is not PeriodMode.DOCUMENT_TEXT_MONTH
            for rule in applicable
        )
        document = adapt_html_document(
            path=path,
            metadata=metadata,
            expected_sha256=str(filing["sha256"]),
            source_uri=str(filing["source_url"]),
            include_tables=include_tables,
            include_inline_facts=include_inline,
        )
        text_month_rules = tuple(
            rule
            for rule in applicable
            if rule.selector is SelectorKind.TABLE
            and rule.period_mode is PeriodMode.DOCUMENT_TEXT_MONTH
        )
        if text_month_rules and any(
            re.search(pattern, document.text)
            for rule in text_month_rules
            for pattern in rule.period_patterns
        ):
            document = adapt_html_document(
                path=path,
                metadata=metadata,
                expected_sha256=str(filing["sha256"]),
                source_uri=str(filing["source_url"]),
                include_tables=True,
                include_inline_facts=include_inline,
            )
        for execution in execute_rules(document, applicable):
            row = execution.as_row()
            row.update(
                {
                    "ticker": manifest["ticker"],
                    "form": form,
                    "filing_date": filing["filing_date"],
                    "accession_number": filing["accession_number"],
                    "source_path": filing["local_path"],
                }
            )
            execution_rows.append(row)
            if execution.fact is None:
                continue
            fact = execution.fact
            fact_rows.append(
                {
                    "entity": fact.entity,
                    "metric": fact.metric,
                    "scope": fact.scope,
                    "period": fact.period,
                    "unit": fact.unit,
                    "value": fact.value,
                    "origin": fact.origin.value,
                    "relation": fact.relation.value,
                    "evidence": fact.evidence.value,
                    "authority": fact.authority.name,
                    "available_at": fact.source.available_at,
                    "source_url": fact.source.uri,
                    "source_path": filing["local_path"],
                    "source_sha256": fact.source.sha256,
                    "rule_id": fact.lineage.rule_id,
                    "rule_version": fact.lineage.rule_version,
                    "rule_source_sha256": next(
                        rule.source_sha256
                        for rule in applicable
                        if rule.rule_id == fact.lineage.rule_id
                    ),
                    "match_trace": fact.lineage.match_trace,
                    "capture_trace": fact.lineage.capture_trace,
                }
            )
    return {
        "parser_rule_inventory": inventory,
        "parser_rule_execution_audit": pd.DataFrame(execution_rows),
        "parser_fact_ir": pd.DataFrame(fact_rows),
    }
