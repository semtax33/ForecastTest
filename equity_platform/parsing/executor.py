from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from equity_platform.documents import CanonicalDocument, DocumentTable
from equity_platform.ir import FactIR, LineageRef

from .rule_ir import (
    CombineMode,
    FailurePolicy,
    ParserRuleIR,
    PeriodMode,
    SelectorKind,
    ValueMode,
)
from equity_platform.numeric import parse_numeric_token


MONTHS = {
    name.casefold(): index
    for index, name in enumerate(
        (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        start=1,
    )
}


@dataclass(frozen=True)
class RuleExecution:
    rule_id: str
    rule_version: int
    status: str
    fact: FactIR | None
    match_trace: dict[str, object]
    capture_trace: dict[str, object]
    error: str | None = None

    def as_row(self) -> dict[str, object]:
        row = {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "status": self.status,
            "error": self.error,
            "match_trace": self.match_trace,
            "capture_trace": self.capture_trace,
        }
        if self.fact is not None:
            row.update(
                {
                    "entity": self.fact.entity,
                    "metric": self.fact.metric,
                    "scope": self.fact.scope,
                    "period": self.fact.period,
                    "unit": self.fact.unit,
                    "value": self.fact.value,
                    "authority": self.fact.authority.name,
                    "source_sha256": self.fact.source.sha256,
                }
            )
        return row


def _period(document: CanonicalDocument, rule: ParserRuleIR) -> str | None:
    if rule.period_mode is PeriodMode.REPORT_PERIOD:
        return document.metadata.report_period
    for pattern in rule.period_patterns:
        match = re.search(pattern, document.text)
        if not match:
            continue
        month_text = match.group("month").casefold()
        month = MONTHS.get(month_text)
        if month is None:
            return None
        return f"{int(match.group('year')):04d}-{month:02d}"
    return None


def _header_matches(row: tuple[str, ...], required: tuple[str, ...]) -> bool:
    cells = {cell.casefold() for cell in row}
    return all(token.casefold() in cells for token in required)


def _month_columns(header: tuple[str, ...], period: str) -> tuple[int, ...]:
    year, month = map(int, period.split("-"))
    month_name = tuple(MONTHS)[month - 1]
    month_abbr = month_name[:3]
    patterns = (
        re.compile(rf"^{month_abbr}\s*-\s*{str(year)[-2:]}$", re.IGNORECASE),
        re.compile(rf"^{month_name}\s*-\s*{str(year)[-2:]}$", re.IGNORECASE),
        re.compile(rf"^{month_name}\s+{year}$", re.IGNORECASE),
    )
    matches = [
        index
        for index, value in enumerate(header)
        if any(pattern.fullmatch(value.strip()) for pattern in patterns)
    ]
    return tuple(matches)


def _table_candidates(
    document: CanonicalDocument, rule: ParserRuleIR, period: str
) -> tuple[list[float], dict[str, object]]:
    values: list[float] = []
    resolved: list[int] = []
    row_traces: list[dict[str, object]] = []
    for table in document.tables:
        headers = [
            (index, row)
            for index, row in enumerate(table.cells)
            if _header_matches(row, rule.table_headers_all)
        ]
        if not headers:
            continue
        for header_position, (header_index, header) in enumerate(headers):
            next_header_index = (
                headers[header_position + 1][0]
                if header_position + 1 < len(headers)
                else len(table.cells)
            )
            label_columns = [
                index
                for index, value in enumerate(header)
                if value.casefold()
                in {item.casefold() for item in rule.table_headers_all}
            ]
            if not label_columns:
                continue
            label_column = label_columns[0]
            if rule.capture_column != "REPORT_MONTH":
                raise ValueError(f"Unsupported capture_column: {rule.capture_column}")
            value_columns = _month_columns(header, period)
            if not value_columns:
                continue
            matching_rows = [
                (index, row)
                for index, row in enumerate(
                    table.cells[header_index + 1 : next_header_index],
                    start=header_index + 1,
                )
                if label_column < len(row)
                and row[label_column].casefold()
                in {label.casefold() for label in rule.row_labels}
            ]
            for row_index, row in matching_rows:
                captured = [
                    (column, parse_numeric_token(row[column]))
                    for column in value_columns
                    if column < len(row)
                ]
                captured = [(column, value) for column, value in captured if value is not None]
                if not captured:
                    continue
                unique_values = {value for _, value in captured}
                if len(unique_values) != 1:
                    continue
                value_column, value = captured[0]
                values.append(value)
                resolved.append(table.resolved_table_index)
                row_traces.append(
                    {
                        "resolved_table_index": table.resolved_table_index,
                        "resolved_header_row": header_index,
                        "resolved_row": row_index,
                        "resolved_column": value_column,
                        "header": header[value_column],
                        "row_label": row[label_column],
                    }
                )
    return values, {
        "candidate_count": len(values),
        "resolved_table_indices": resolved,
        "candidates": row_traces,
    }


def _inline_candidates(
    document: CanonicalDocument, rule: ParserRuleIR, period: str
) -> tuple[list[float], dict[str, object]]:
    names = {name.casefold() for name in rule.fact_names}
    year = int(period[:4])
    candidates = []
    locations = []
    for fact in document.inline_facts:
        if fact.name.casefold() not in names:
            continue
        if rule.dimensions == "NONE" and fact.has_dimensions:
            continue
        if rule.full_year_only:
            if fact.start != f"{year:04d}-01-01" or fact.end != f"{year:04d}-12-31":
                continue
        elif fact.end != period:
            continue
        candidates.append(fact.value)
        locations.append(fact.source_location)
    return candidates, {
        "candidate_count": len(candidates),
        "source_locations": locations,
        "fact_names": list(rule.fact_names),
    }


def _row_value(
    row: tuple[str, ...],
    report_period: str,
    mode: ValueMode,
    value_indices: tuple[int, ...] = (),
) -> tuple[float | None, tuple[float, ...]]:
    values = tuple(
        value
        for token in row
        if (value := parse_numeric_token(token, strict=True)) is not None
    )
    if not values:
        return None, values
    if value_indices:
        if any(index >= len(values) for index in value_indices):
            return None, values
        value = sum(values[index] for index in value_indices)
    else:
        quarter = int(report_period[-1])
        if mode is ValueMode.REPORTED_QUARTER_INDEX:
            index = quarter - 1
        elif mode is ValueMode.CURRENT_YEAR_AFTER_PRIOR_YEAR:
            index = quarter + 4
        else:
            index = 0
        if index >= len(values):
            return None, values
        value = values[index]
    return (value if isfinite(value) and value > 0 else None), values


def _table_row_candidates(
    document: CanonicalDocument, rule: ParserRuleIR, period: str
) -> tuple[list[float], dict[str, object]]:
    unique: dict[tuple[str, float], dict[str, object]] = {}
    for table in document.tables:
        if rule.context_patterns and not all(
            re.search(pattern, table.context, flags=re.IGNORECASE)
            for pattern in rule.context_patterns
        ):
            continue
        for ordinal, row in enumerate(table.cells):
            pattern_index = next(
                (
                    index
                    for index, pattern in enumerate(rule.row_patterns)
                    if any(re.search(pattern, cell, flags=re.IGNORECASE) for cell in row)
                ),
                None,
            )
            if pattern_index is None:
                continue
            value, numeric_values = _row_value(
                row, period, rule.value_mode, rule.value_indices
            )
            if value is None:
                continue
            value *= rule.scale_factor
            row_text = " | ".join(cell for cell in row if cell)
            if rule.scale_when_pattern and re.search(
                rule.scale_when_pattern, row_text, flags=re.IGNORECASE
            ):
                value *= rule.scale_when_factor
            source_row = (
                table.source_row_indices[ordinal]
                if ordinal < len(table.source_row_indices)
                else ordinal
            )
            candidate = {
                "value": value,
                "row_text": row_text,
                "row_pattern_index": pattern_index,
                "resolved_table_index": table.resolved_table_index,
                "source_table_index": (
                    table.source_table_index
                    if table.source_table_index is not None
                    else table.resolved_table_index
                ),
                "source_row_index": source_row,
                "source_uri": table.source_uri or document.source.uri,
                "source_description": table.source_description,
                "table_context": table.context,
                "numeric_token_count": len(numeric_values),
                "numeric_values": list(numeric_values),
            }
            unique[(row_text.casefold(), round(value, 8))] = candidate
    candidates = list(unique.values())
    if rule.combine is CombineMode.ADJACENT_PAIR_SUM_MAX:
        pairs: list[dict[str, object]] = []
        for left in candidates:
            if left["row_pattern_index"] != 0:
                continue
            for right in candidates:
                same_location = (
                    left["source_uri"] == right["source_uri"]
                    and left["source_table_index"] == right["source_table_index"]
                    and abs(
                        int(left["source_row_index"])
                        - int(right["source_row_index"])
                    )
                    <= 3
                )
                if right["row_pattern_index"] != 1 or not same_location:
                    continue
                pairs.append(
                    {
                        "value": float(left["value"]) + float(right["value"]),
                        "members": [left, right],
                    }
                )
        values = [float(pair["value"]) for pair in pairs]
        return values, {
            "candidate_count": len(values),
            "row_candidates": candidates,
            "pair_candidates": pairs,
        }
    return [float(candidate["value"]) for candidate in candidates], {
        "candidate_count": len(candidates),
        "row_candidates": candidates,
    }


def _text_candidates(
    document: CanonicalDocument, rule: ParserRuleIR
) -> tuple[list[float], dict[str, object]]:
    values: list[float] = []
    matches: list[dict[str, object]] = []
    for pattern_index, pattern in enumerate(rule.text_patterns):
        for match in re.finditer(pattern, document.text):
            captured = match.group(str(rule.capture_group))
            value = parse_numeric_token(captured)
            if value is None:
                continue
            values.append(value)
            start, end = match.span()
            matches.append(
                {
                    "pattern_index": pattern_index,
                    "character_start": start,
                    "character_end": end,
                    "captured_text": captured,
                    "source_excerpt": document.text[start:end],
                }
            )
    return values, {
        "candidate_count": len(values),
        "capture_group": rule.capture_group,
        "matches": matches,
    }


def _combine(values: list[float], mode: CombineMode) -> float:
    if mode is CombineMode.UNIQUE:
        if len(values) != 1:
            raise ValueError(f"Expected one candidate, found {len(values)}")
        return values[0]
    if mode is CombineMode.UNIQUE_VALUE:
        unique = sorted(set(values))
        if len(unique) != 1:
            raise ValueError(f"Expected one unique value, found {len(unique)}")
        return unique[0]
    if mode is CombineMode.MAX:
        return max(values)
    if mode is CombineMode.SUM:
        return sum(values)
    if mode is CombineMode.ADJACENT_PAIR_SUM_MAX:
        return max(values)
    raise ValueError(f"Unsupported combine mode: {mode}")


def _assert_candidate_invariants(values: list[float], assertions: tuple[str, ...]) -> None:
    for assertion in assertions:
        if assertion == "MAX_EQUALS_SUM_OF_TWO_OR_SINGLE":
            unique = sorted(set(values))
            if len(unique) == 1:
                continue
            maximum = unique[-1]
            # The disclosures are rounded to 0.1 thousand passengers, so the
            # exact domestic + international identity needs a rounding band.
            tolerance = max(0.2, abs(maximum) * 1e-4)
            if not any(
                abs(left + right - maximum) <= tolerance
                for left_index, left in enumerate(unique[:-1])
                for right in unique[left_index + 1 : -1]
            ):
                raise ValueError(
                    "combined total does not reconcile to two component totals"
                )


def execute_rule(document: CanonicalDocument, rule: ParserRuleIR) -> RuleExecution:
    if document.metadata.source_kind != rule.source or document.metadata.document_kind != rule.document:
        return RuleExecution(rule.rule_id, rule.version, "NOT_APPLICABLE", None, {}, {})
    if rule.entities and document.metadata.entity not in rule.entities:
        return RuleExecution(rule.rule_id, rule.version, "NOT_APPLICABLE", None, {}, {})
    period = _period(document, rule)
    if period is None:
        status = "FAIL_MISSING_PERIOD" if rule.missing is FailurePolicy.FAIL else "SKIP_MISSING_PERIOD"
        return RuleExecution(rule.rule_id, rule.version, status, None, {}, {}, "period not identified")
    if rule.selector is SelectorKind.TABLE:
        values, match_trace = _table_candidates(document, rule, period)
    elif rule.selector is SelectorKind.TABLE_ROW:
        values, match_trace = _table_row_candidates(document, rule, period)
    elif rule.selector is SelectorKind.INLINE_FACT:
        values, match_trace = _inline_candidates(document, rule, period)
    else:
        values, match_trace = _text_candidates(document, rule)
    if not values:
        status = "FAIL_MISSING" if rule.missing is FailurePolicy.FAIL else "SKIP_MISSING"
        return RuleExecution(rule.rule_id, rule.version, status, None, match_trace, {"period": period})
    try:
        _assert_candidate_invariants(values, rule.assertions)
        value = _combine(values, rule.combine)
    except ValueError as exc:
        if rule.ambiguity is FailurePolicy.FAIL:
            return RuleExecution(
                rule.rule_id, rule.version, "FAIL_AMBIGUOUS", None, match_trace,
                {"period": period, "candidate_values": values}, str(exc)
            )
        return RuleExecution(rule.rule_id, rule.version, "SKIP_AMBIGUOUS", None, match_trace, {"period": period})
    if rule.finite and not isfinite(value):
        return RuleExecution(rule.rule_id, rule.version, "FAIL_ASSERTION", None, match_trace, {"period": period}, "not finite")
    if rule.min_value is not None and value < rule.min_value:
        return RuleExecution(rule.rule_id, rule.version, "FAIL_ASSERTION", None, match_trace, {"period": period}, "below minimum")
    if rule.max_value is not None and value > rule.max_value:
        return RuleExecution(rule.rule_id, rule.version, "FAIL_ASSERTION", None, match_trace, {"period": period}, "above maximum")
    capture_trace = {
        "period": period,
        "candidate_values": values,
        "combine": rule.combine.value,
        "selected_value": value,
    }
    lineage = LineageRef(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        match_trace=match_trace,
        capture_trace=capture_trace,
    )
    fact = FactIR(
        entity=document.metadata.entity,
        metric=rule.metric,
        scope=rule.scope,
        period=period,
        unit=rule.unit,
        value=value,
        origin=rule.origin,
        relation=rule.relation,
        evidence=rule.evidence,
        authority=rule.authority,
        source=document.source,
        lineage=lineage,
    )
    return RuleExecution(rule.rule_id, rule.version, "EMITTED", fact, match_trace, capture_trace)


def execute_rules(
    document: CanonicalDocument, rules: tuple[ParserRuleIR, ...]
) -> tuple[RuleExecution, ...]:
    return tuple(execute_rule(document, rule) for rule in rules)
