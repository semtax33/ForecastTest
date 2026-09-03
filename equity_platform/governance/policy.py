from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from equity_platform.ir import AuthorityLevel


class PolicyPurpose(StrEnum):
    RESEARCH = "RESEARCH"
    FORECAST = "FORECAST"
    VALUATION = "VALUATION"
    TERMINAL = "TERMINAL"
    PRODUCTION = "PRODUCTION"


PURPOSE_AUTHORITY = {
    PolicyPurpose.RESEARCH: AuthorityLevel.RESEARCH_DIAGNOSTIC,
    PolicyPurpose.FORECAST: AuthorityLevel.OOS_VALIDATED,
    PolicyPurpose.VALUATION: AuthorityLevel.VALUATION_INPUT,
    PolicyPurpose.TERMINAL: AuthorityLevel.TERMINAL_INPUT,
    PolicyPurpose.PRODUCTION: AuthorityLevel.PRODUCTION_INPUT,
}


@dataclass(frozen=True)
class PolicyDecision:
    purpose: PolicyPurpose
    actual: AuthorityLevel
    required: AuthorityLevel
    allowed: bool
    reason: str


def evaluate_authority(
    *, actual: AuthorityLevel, purpose: PolicyPurpose
) -> PolicyDecision:
    required = PURPOSE_AUTHORITY[purpose]
    allowed = actual >= required
    return PolicyDecision(
        purpose=purpose,
        actual=actual,
        required=required,
        allowed=allowed,
        reason="AUTHORITY_SUFFICIENT"
        if allowed
        else f"AUTHORITY_REQUIRED_{required.name}_ACTUAL_{actual.name}",
    )
