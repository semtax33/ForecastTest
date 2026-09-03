from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Callable, Mapping


class FormulaId(StrEnum):
    REVENUE_PRICE_QUANTITY = "REVENUE_PRICE_QUANTITY"
    EBIT_REVENUE_MARGIN = "EBIT_REVENUE_MARGIN"
    NOPAT_IDENTITY = "NOPAT_IDENTITY"
    ROIC_IDENTITY = "ROIC_IDENTITY"
    GROWTH_REINVESTMENT_IDENTITY = "GROWTH_REINVESTMENT_IDENTITY"
    FCFF_IDENTITY = "FCFF_IDENTITY"
    EV_TO_COMMON_EQUITY = "EV_TO_COMMON_EQUITY"


def _revenue(values: Mapping[str, float]) -> float:
    return values["price"] * values["quantity"]


def _ebit(values: Mapping[str, float]) -> float:
    if "operating_margin_pct" in values:
        return values["revenue"] * values["operating_margin_pct"] / 100.0
    return values["revenue"] * values["operating_margin"]


def _nopat(values: Mapping[str, float]) -> float:
    if "tax_rate_pct" in values:
        return values["ebit"] * (1.0 - values["tax_rate_pct"] / 100.0)
    return values["ebit"] * (1.0 - values["tax_rate"])


def _roic(values: Mapping[str, float]) -> float:
    return values["nopat"] / values["average_invested_capital"]


def _reinvestment_rate(values: Mapping[str, float]) -> float:
    return values["growth"] / values["roic"]


def _fcff(values: Mapping[str, float]) -> float:
    return values["nopat"] - values["reinvestment"]


def _equity(values: Mapping[str, float]) -> float:
    return (
        values["enterprise_value"]
        - values["debt"]
        + values["cash"]
        - values.get("noncontrolling_interest", 0.0)
        - values.get("preferred_stock", 0.0)
    )


FORMULA_REGISTRY: dict[FormulaId, Callable[[Mapping[str, float]], float]] = {
    FormulaId.REVENUE_PRICE_QUANTITY: _revenue,
    FormulaId.EBIT_REVENUE_MARGIN: _ebit,
    FormulaId.NOPAT_IDENTITY: _nopat,
    FormulaId.ROIC_IDENTITY: _roic,
    FormulaId.GROWTH_REINVESTMENT_IDENTITY: _reinvestment_rate,
    FormulaId.FCFF_IDENTITY: _fcff,
    FormulaId.EV_TO_COMMON_EQUITY: _equity,
}


def evaluate_formula(formula_id: FormulaId, values: Mapping[str, float]) -> float:
    try:
        result = float(FORMULA_REGISTRY[formula_id](values))
    except (KeyError, ZeroDivisionError) as exc:
        raise ValueError(f"Invalid inputs for {formula_id.value}: {exc}") from exc
    if not isfinite(result):
        raise ValueError(f"{formula_id.value} produced a non-finite value")
    return result
