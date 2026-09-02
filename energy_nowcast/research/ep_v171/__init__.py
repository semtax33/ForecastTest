"""E&P V1.7.1 M&A numerator and purchase-accounting proof research."""

from .cohort import build_v171_company_year_bridge, build_v171_deal_cohorts
from .evidence import build_acquisition_proof, build_divestiture_proof
from .gate import build_v171_gate

__all__ = [
    "build_acquisition_proof",
    "build_divestiture_proof",
    "build_v171_company_year_bridge",
    "build_v171_deal_cohorts",
    "build_v171_gate",
]
