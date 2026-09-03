from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from equity_platform.ir import AuthorityLevel, EvidenceStatus, FactOrigin, RelationType


class SelectorKind(StrEnum):
    TABLE = "TABLE"
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

    def validate(self) -> None:
        if not self.rule_id or self.version < 1:
            raise ValueError("Rules require an id and positive version")
        if self.selector is SelectorKind.TABLE:
            if not self.table_headers_all or not self.row_labels or not self.capture_column:
                raise ValueError("Table rules require headers, row labels, and capture_column")
            if self.fact_names or self.text_patterns or self.capture_group:
                raise ValueError("Table rules cannot declare fact or text selectors")
        if self.selector is SelectorKind.INLINE_FACT:
            if not self.fact_names:
                raise ValueError("Inline-fact rules require fact_names")
            if (
                self.table_headers_all
                or self.row_labels
                or self.capture_column
                or self.text_patterns
                or self.capture_group
            ):
                raise ValueError("Inline-fact rules cannot declare table or text selectors")
        if self.selector is SelectorKind.TEXT:
            if not self.text_patterns or not self.capture_group:
                raise ValueError("Text rules require patterns and a capture_group")
            if self.table_headers_all or self.row_labels or self.capture_column or self.fact_names:
                raise ValueError("Text rules cannot declare table or inline-fact selectors")
        if self.period_mode is PeriodMode.DOCUMENT_TEXT_MONTH and not self.period_patterns:
            raise ValueError("Text-month rules require period_patterns")
        if self.dimensions not in {"ANY", "NONE"}:
            raise ValueError("dimensions must be ANY or NONE")
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError("min_value cannot exceed max_value")
        allowed_assertions = {"MAX_EQUALS_SUM_OF_TWO_OR_SINGLE"}
        unknown = set(self.assertions) - allowed_assertions
        if unknown:
            raise ValueError(f"Unknown parser assertions: {sorted(unknown)}")
