"""Canonical Energy filing parsers."""

from .company_kpi import (
    ENERGY_KPI_RULES,
    KPI_SPECS,
    MetricSpec,
    extract_filing_metrics,
    legacy_table_rows,
)
from .ir_tables import load_ir_tables

__all__ = [
    "ENERGY_KPI_RULES",
    "KPI_SPECS",
    "MetricSpec",
    "extract_filing_metrics",
    "legacy_table_rows",
    "load_ir_tables",
]
