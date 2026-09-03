from __future__ import annotations

from enum import IntEnum, StrEnum


class DriverRole(StrEnum):
    """The shared economic vocabulary; not a universal forecasting formula."""

    PRICE = "P"
    QUANTITY = "Q"
    COST = "C"
    INVESTMENT = "I"


class DataAuthority(StrEnum):
    HISTORICAL_PIT_MODEL_INPUT = "HISTORICAL_PIT_MODEL_INPUT"
    CURRENT_REVISED_CONTEXT_ONLY = "CURRENT_REVISED_CONTEXT_ONLY"
    COMPANY_DISCLOSED_PIT_INPUT = "COMPANY_DISCLOSED_PIT_INPUT"
    NOT_IDENTIFIED = "NOT_IDENTIFIED"


class ForecastAuthority(StrEnum):
    STRONG = "STRONG"
    MIXED = "MIXED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    NOT_TESTED = "NOT_TESTED"


class AuthorityLevel(IntEnum):
    """Monotone authority used by policy gates throughout the platform."""

    UNIDENTIFIED = 0
    CONTEXT_ONLY = 10
    RESEARCH_DIAGNOSTIC = 20
    RESEARCH_EVIDENCE = 30
    OOS_VALIDATED = 40
    VALUATION_INPUT = 50
    TERMINAL_INPUT = 60
    PRODUCTION_INPUT = 70


class AuthorityViolation(ValueError):
    pass


def require_authority(
    actual: AuthorityLevel,
    required: AuthorityLevel,
    *,
    purpose: str,
) -> None:
    if actual < required:
        raise AuthorityViolation(
            f"{purpose} requires {required.name}, received {actual.name}"
        )
