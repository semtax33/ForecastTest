"""E&P V1.3 normalized unit-economics and independent-risk research."""

from .unit_economics import build_unit_economics_research
from .wacc_research import build_wacc_research
from .benchmark import freeze_v13, verify_v13

__all__ = [
    "build_unit_economics_research",
    "build_wacc_research",
    "freeze_v13",
    "verify_v13",
]
