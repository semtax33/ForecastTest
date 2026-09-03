"""E&P V1.7.4 cohort closure and organic ROIC validation research."""

from energy_nowcast.research.ep_v174.closure import (
    build_closed_three_year_cohorts,
    build_fang_divestiture_nopat_range,
    build_fang_transaction_perimeter_evidence,
    build_organic_roic_validation_ranges,
)
from energy_nowcast.research.ep_v174.gate import build_v174_gate
from energy_nowcast.research.ep_v174.reconciliation import (
    build_dvn_nopat_discrepancy_reconciliation,
    build_scope_adjusted_triangulation,
)

__all__ = [
    "build_closed_three_year_cohorts",
    "build_dvn_nopat_discrepancy_reconciliation",
    "build_fang_divestiture_nopat_range",
    "build_fang_transaction_perimeter_evidence",
    "build_organic_roic_validation_ranges",
    "build_scope_adjusted_triangulation",
    "build_v174_gate",
]
