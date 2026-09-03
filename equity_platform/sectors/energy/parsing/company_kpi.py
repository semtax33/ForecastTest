from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from equity_platform.documents import (
    DocumentMetadata,
    HtmlFragment,
    adapt_html_fragments,
)
from equity_platform.numeric import parse_numeric_token
from equity_platform.parsing import (
    CombineMode,
    ParserRuleIR,
    ValueMode,
    compile_rule_file,
    execute_rules,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
RULE_PATH = PROJECT_ROOT / "configs/parser_rules/energy/company_kpi.arc"
ENERGY_KPI_RULES = compile_rule_file(RULE_PATH)


@dataclass(frozen=True)
class MetricSpec:
    """Read-only compatibility view; the DSL is the source of truth."""

    metric_id: str
    label_pattern: str
    unit: str
    aggregation: str = "max"
    current_mode: str = "first"
    candidate_selection: str = "all_tables"
    semantic_category: str = "OPERATING_KPI"
    required_context_pattern: str | None = None


def _legacy_mode(mode: ValueMode) -> str:
    return {
        ValueMode.FIRST: "first",
        ValueMode.REPORTED_QUARTER_INDEX: "reported_quarter_index",
        ValueMode.CURRENT_YEAR_AFTER_PRIOR_YEAR: "current_year_after_prior_year",
    }[mode]


def _legacy_aggregation(mode: CombineMode) -> str:
    return {
        CombineMode.MAX: "max",
        CombineMode.SUM: "sum",
        CombineMode.ADJACENT_PAIR_SUM_MAX: "adjacent_pair_sum_max",
        CombineMode.UNIQUE: "first",
        CombineMode.UNIQUE_VALUE: "first",
    }[mode]


def _compatibility_specs() -> dict[str, tuple[MetricSpec, ...]]:
    grouped: dict[str, list[MetricSpec]] = {}
    for rule in ENERGY_KPI_RULES:
        ticker = rule.entities[0]
        grouped.setdefault(ticker, []).append(
            MetricSpec(
                metric_id=rule.metric,
                label_pattern=(
                    rule.row_patterns[0]
                    if len(rule.row_patterns) == 1
                    else "(" + "|".join(rule.row_patterns) + ")"
                ),
                unit=rule.unit,
                aggregation=_legacy_aggregation(rule.combine),
                current_mode=_legacy_mode(rule.value_mode),
                semantic_category=rule.scope,
                required_context_pattern=(
                    rule.context_patterns[0] if rule.context_patterns else None
                ),
            )
        )
    return {ticker: tuple(specs) for ticker, specs in grouped.items()}


KPI_SPECS = _compatibility_specs()


def number(value: str) -> float | None:
    return parse_numeric_token(value.replace(" ", ""), strict=True)


def _document(
    ticker: str,
    filing: dict[str, object],
    documents: Iterable[dict[str, str]],
):
    fragments = tuple(
        HtmlFragment(
            content=document["html"].encode("utf-8"),
            source_uri=document["source_url"],
            source_description=document["description"],
            local_path=document.get("local_path", ""),
            expected_sha256=document.get("sha256"),
        )
        for document in documents
    )
    available_at, _ = filing_availability(filing)
    return adapt_html_fragments(
        fragments=fragments,
        metadata=DocumentMetadata(
            entity=ticker,
            source_kind="SEC_EDGAR",
            document_kind="SEC_8K_EARNINGS_EXHIBIT",
            available_at=available_at.isoformat(),
            report_period=str(filing["report_quarter"]),
        ),
    )


def legacy_table_rows(html: str) -> list[dict[str, object]]:
    """Compatibility projection from canonical DocumentTable to legacy rows."""

    document = adapt_html_fragments(
        fragments=(HtmlFragment(html.encode("utf-8"), "memory://html", "MEMORY"),),
        metadata=DocumentMetadata(
            entity="UNSPECIFIED",
            source_kind="SEC_EDGAR",
            document_kind="SEC_8K_EARNINGS_EXHIBIT",
            available_at="1970-01-01",
            report_period="1970Q1",
        ),
    )
    rows: list[dict[str, object]] = []
    for table in document.tables:
        for ordinal, tokens in enumerate(table.cells):
            values = tuple(
                value
                for token in tokens
                if (value := parse_numeric_token(token, strict=True)) is not None
            )
            rows.append(
                {
                    "table_index": table.source_table_index,
                    "row_index": table.source_row_indices[ordinal],
                    "tokens": list(tokens),
                    "values": values,
                    "row_text": " | ".join(tokens),
                    "table_context": table.context,
                }
            )
    return rows


def current_value(
    row: dict[str, object], report_quarter: str, mode: str
) -> float | None:
    values = tuple(float(value) for value in row["values"])
    if not values:
        return None
    quarter = pd.Period(report_quarter, freq="Q").quarter
    index = {
        "reported_quarter_index": quarter - 1,
        "current_year_after_prior_year": quarter + 4,
    }.get(mode, 0)
    if index >= len(values):
        return None
    value = values[index]
    return value if np.isfinite(value) and value > 0 else None


def filing_availability(
    filing: dict[str, object],
) -> tuple[pd.Timestamp, str]:
    accepted = pd.to_datetime(
        filing.get("acceptanceDateTime"), errors="coerce", utc=True
    )
    if not pd.isna(accepted):
        return accepted.tz_convert("UTC").tz_localize(None), "SEC_ACCEPTANCE_DATETIME"
    filing_date = pd.Timestamp(str(filing["filingDate"])).normalize()
    return filing_date + pd.Timedelta(days=1), "FILING_DATE_PLUS_ONE_FALLBACK"


def _selected_candidates(execution) -> list[dict[str, object]]:
    trace = execution.match_trace
    if execution.fact is None:
        return []
    if "pair_candidates" in trace:
        pairs = trace["pair_candidates"]
        selected = max(pairs, key=lambda item: float(item["value"]))
        return list(selected["members"])
    candidates = list(trace.get("row_candidates", []))
    if execution.fact.lineage.capture_trace["combine"] == CombineMode.SUM.value:
        return candidates
    selected_value = float(execution.fact.value)
    return [
        next(
            candidate
            for candidate in candidates
            if float(candidate["value"]) == selected_value
        )
    ]


def extract_filing_metrics(
    ticker: str,
    filing: dict[str, object],
    documents: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Execute declarative KPI rules and project FactIR into the stable schema."""

    if not documents:
        return []
    document = _document(ticker, filing, documents)
    executions = execute_rules(document, ENERGY_KPI_RULES)
    output: list[dict[str, object]] = []
    filing_date = pd.Timestamp(str(filing["filingDate"])).normalize()
    available_at, availability_source = filing_availability(filing)
    by_id = {rule.rule_id: rule for rule in ENERGY_KPI_RULES}
    for execution in executions:
        if execution.status != "EMITTED" or execution.fact is None:
            continue
        rule: ParserRuleIR = by_id[execution.rule_id]
        selected = _selected_candidates(execution)
        confidence = (
            0.95
            if rule.context_patterns
            else (0.90 if len(selected) == 1 else 0.85)
        )
        output.append(
            {
                "ticker": ticker,
                "report_quarter": str(filing["report_quarter"]),
                "metric_id": execution.fact.metric,
                "metric_value": execution.fact.value,
                "metric_unit": execution.fact.unit,
                "filing_date": filing_date,
                "acceptance_datetime_utc": filing.get("acceptanceDateTime") or pd.NA,
                "ir_publication_datetime_utc": pd.NA,
                "available_at": available_at,
                "availability_source": availability_source,
                "form": "8-K",
                "source_type": "SEC_8K_EARNINGS_EXHIBIT",
                "source_url": ";".join(
                    sorted({str(item["source_uri"]) for item in selected})
                ),
                "source_description": ";".join(
                    sorted({str(item["source_description"]) for item in selected})
                ),
                "source_row_text": " || ".join(
                    str(item["row_text"]) for item in selected
                ),
                "source_table_context": " || ".join(
                    str(item["table_context"]) for item in selected
                ),
                "source_table_indices": ",".join(
                    str(item["source_table_index"]) for item in selected
                ),
                "source_row_indices": ",".join(
                    str(item["source_row_index"]) for item in selected
                ),
                "value_selection_rule": (
                    f"all_tables:{_legacy_aggregation(rule.combine)}:"
                    f"{_legacy_mode(rule.value_mode)}:context="
                    f"{rule.context_patterns[0] if rule.context_patterns else 'none'}"
                ),
                "reported_period_basis": "THREE_MONTHS",
                "semantic_category": execution.fact.scope,
                "parser_rule_confidence": confidence,
                "quality_score": confidence,
                "accession": str(filing["accessionNumber"]),
                "parser_rule_id": execution.rule_id,
                "parser_rule_version": execution.rule_version,
                "parser_rule_sha256": rule.source_sha256,
            }
        )
    return output
