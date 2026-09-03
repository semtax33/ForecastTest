"""Industrials V2 cross-company portability research.

This package is intentionally separate from the frozen CAT V1.7 package.
"""

from .forecast import build_cmi_portability_forecast
from .ir import build_cmi_ir_evidence
from .reinvestment import build_cmi_reinvestment_roic_evidence
from .research import build_v2_gates
from .sources import build_cmi_source_audit
from .uncertainty import build_uncertainty_calibration

__all__ = [
    "build_cmi_ir_evidence",
    "build_cmi_portability_forecast",
    "build_cmi_reinvestment_roic_evidence",
    "build_cmi_source_audit",
    "build_uncertainty_calibration",
    "build_v2_gates",
]
