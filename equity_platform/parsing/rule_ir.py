from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from equity_platform.ir import AuthorityLevel, EvidenceStatus, FactOrigin, RelationType


class SelectorKind(StrEnum):
    TABLE = "TABLE"
    TABLE_ROW = "TABLE_ROW"
    INLINE_FACT = "INLINE_FACT"
    TEXT = "TEXT"


class PeriodMode(StrEnum):
    DOCUMENT_TEXT_MONTH = "DOCUMENT_TEXT_MONTH"
    REPORT_PERIOD = "REPORT_PERIOD"


class CombineMode(StrEnum):
    UNIQUE = "UNIQUE"
    UNIQUE_VALUE = "UNIQUE_VALUE"
    MAX = "MAX"
    SUM = "SUM"
    ADJACENT_PAIR_SUM_MAX = "ADJACENT_PAIR_SUM_MAX"


class ValueMode(StrEnum):
    FIRST = "FIRST"
    REPORTED_QUARTER_INDEX = "REPORTED_QUARTER_INDEX"
    CURRENT_YEAR_AFTER_PRIOR_YEAR = "CURRENT_YEAR_AFTER_PRIOR_YEAR"


class FailurePolicy(StrEnum):
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class ParserRuleIR:
    rule_id: str
    version: int
    source: str
    document: str
    selector: SelectorKind
    period_mode: PeriodMode
    period_patterns: tuple[str, ...]
    table_headers_all: tuple[str, ...]
    row_labels: tuple[str, ...]
    row_patterns: tuple[str, ...]
    context_patterns: tuple[str, ...]
    capture_column: str | None
    fact_names: tuple[str, ...]
    text_patterns: tuple[str, ...]
    capture_group: str | None
    full_year_only: bool
    dimensions: str
    combine: CombineMode
    metric: str
    scope: str
    unit: str
    origin: FactOrigin
    relation: RelationType
    evidence: EvidenceStatus
    authority: AuthorityLevel
    min_value: float | None
    max_value: float | None
    finite: bool
    assertions: tuple[str, ...]
    ambiguity: FailurePolicy
    missing: FailurePolicy
    source_sha256: str
    entities: tuple[str, ...] = ()
    value_mode: ValueMode = ValueMode.FIRST
    value_indices: tuple[int, ...] = ()
    scale_factor: float = 1.0
    scale_when_pattern: str | None = None
    scale_when_factor: float = 1.0

    def validate(self) -> None:
        if not self.rule_id or self.version < 1:
            raise ValueError("Rules require an id and positive version")
        if self.selector is SelectorKind.TABLE:
            if not self.table_headers_all or not self.row_labels or not self.capture_column:
                raise ValueError("Table rules require headers, row labels, and capture_column")
            if self.fact_names or self.text_patterns or self.capture_group:
                raise ValueError("Table rules cannot declare fact or text selectors")
            if self.row_patterns or self.context_patterns:
                raise ValueError("Table rules cannot declare row-pattern selectors")
        if self.selector is SelectorKind.TABLE_ROW:
            if not self.row_patterns:
                raise ValueError("Table-row rules require row_patterns")
            if self.table_headers_all or self.row_labels or self.capture_column:
                raise ValueError("Table-row rules cannot declare grid-table selectors")
            if self.fact_names or self.text_patterns or self.capture_group:
                raise ValueError("Table-row rules cannot declare fact or text selectors")
        if self.selector is SelectorKind.INLINE_FACT:
            if not self.fact_names:
                raise ValueError("Inline-fact rules require fact_names")
            if (
                self.table_headers_all
                or self.row_labels
                or self.capture_column
                or self.text_patterns
                or self.capture_group
                or self.row_patterns
                or self.context_patterns
            ):
                raise ValueError("Inline-fact rules cannot declare table or text selectors")
        if self.selector is SelectorKind.TEXT:
            if not self.text_patterns or not self.capture_group:
                raise ValueError("Text rules require patterns and a capture_group")
            if self.table_headers_all or self.row_labels or self.capture_column or self.fact_names:
                raise ValueError("Text rules cannot declare table or inline-fact selectors")
            if self.row_patterns or self.context_patterns:
                raise ValueError("Text rules cannot declare row-pattern selectors")
        if self.period_mode is PeriodMode.DOCUMENT_TEXT_MONTH and not self.period_patterns:
            raise ValueError("Text-month rules require period_patterns")
        if self.dimensions not in {"ANY", "NONE"}:
            raise ValueError("dimensions must be ANY or NONE")
        if self.value_indices and self.selector is not SelectorKind.TABLE_ROW:
            raise ValueError("value_indices are supported only by table-row rules")
        if any(index < 0 for index in self.value_indices):
            raise ValueError("value_indices must be non-negative")
        if self.scale_factor <= 0 or self.scale_when_factor <= 0:
            raise ValueError("scale factors must be positive")
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError("min_value cannot exceed max_value")
        allowed_assertions = {"MAX_EQUALS_SUM_OF_TWO_OR_SINGLE"}
        unknown = set(self.assertions) - allowed_assertions
        if unknown:
            raise ValueError(f"Unknown parser assertions: {sorted(unknown)}")
