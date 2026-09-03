"""V3.5 multi-company E&P KPI research package."""

from .adapters import StandardizedKPIBundle, build_standardized_kpis
from .strategy import KPIHierarchicalStrategy, V35StrategyConfig
from .taxonomy import E_AND_P_GROUPS, all_tickers, group_for_ticker
from .validation import validate_v35, v35_promotion_gate

__all__ = [
    "E_AND_P_GROUPS",
    "KPIHierarchicalStrategy",
    "StandardizedKPIBundle",
    "V35StrategyConfig",
    "all_tickers",
    "build_standardized_kpis",
    "group_for_ticker",
    "validate_v35",
    "v35_promotion_gate",
]
