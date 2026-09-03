"""Shared Industrials forecasting platform.

Subindustry packages provide economic adapters.  This package owns invariant
contracts, source authority, validation and valuation primitives.
"""

from .domain import (
    DataAuthority,
    DriverRole,
    ForecastAuthority,
    SourceDefinition,
    SubindustryProfile,
    classify_forecast_authority,
)
from .forecast import (
    build_company_forecast_origins,
    build_company_forecast_panel,
    build_company_pit_industry_features,
    run_fixed_oos_company_forecasts,
)
from .registry import INDUSTRIALS_SUBINDUSTRIES, get_subindustry_profile
from .validation import build_aggregate_error_decomposition
from .bls import build_industrials_bls_sensor_map
from .companyfacts import build_subindustry_companyfacts_evidence
from .ir import build_arcana_ir_evidence
from .valuation import (
    DcfAssumptions,
    build_conditional_valuation_research,
    build_market_wacc_evidence,
    enterprise_value,
    solve_parameter,
)
from .pqci_context import build_arcana_pqci_context
from .ifrs import build_ifrs_evidence, build_pac_passenger_traffic

__all__ = [
    "DataAuthority",
    "DriverRole",
    "ForecastAuthority",
    "SourceDefinition",
    "SubindustryProfile",
    "classify_forecast_authority",
    "build_company_forecast_origins",
    "build_company_forecast_panel",
    "build_company_pit_industry_features",
    "run_fixed_oos_company_forecasts",
    "INDUSTRIALS_SUBINDUSTRIES",
    "get_subindustry_profile",
    "build_aggregate_error_decomposition",
    "build_industrials_bls_sensor_map",
    "build_subindustry_companyfacts_evidence",
    "build_arcana_ir_evidence",
    "DcfAssumptions",
    "build_conditional_valuation_research",
    "build_market_wacc_evidence",
    "enterprise_value",
    "solve_parameter",
    "build_arcana_pqci_context",
    "build_ifrs_evidence",
    "build_pac_passenger_traffic",
]
