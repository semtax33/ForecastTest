"""Sector-neutral forecasting validation primitives."""

from .baselines import attach_naive_baseline
from .cross_section_metrics import *  # noqa: F401,F403
from .intervals import *  # noqa: F401,F403
from .leave_one_company_out import *  # noqa: F401,F403
from .metrics import *  # noqa: F401,F403
from .promotion_gate import *  # noqa: F401,F403

__all__ = ["attach_naive_baseline"]
