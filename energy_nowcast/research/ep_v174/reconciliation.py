from __future__ import annotations

from calendar import isleap
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TRIANGULATION_TOLERANCE_PCT = 10.0
WPX_CIK = "0001518832"
WPX_ACCESSION = "0001518832-20-000019"
WPX_PERIOD_START = "2020-01-01"
WPX_PERIOD_END = "2020-09-30"


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fact(
    facts: dict[str, Any],
    tag: str,
    *,
    accession: str = WPX_ACCESSION,
    start: str = WPX_PERIOD_START,
    end: str = WPX_PERIOD_END,
) -> tuple[float, str]:
    records = (
        facts.get("facts", {})
        .get("us-gaap", {})
        .get(tag, {})
        .get("units", {})
        .get("USD", [])
    )
    matches = [
        record
        for record in records
        if record.get("accn") == accession
        and record.get("start") == start
        and record.get("end") == end
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one WPX fact for {tag} {start}:{end}; found {len(matches)}"
        )
    return float(matches[0]["val"]), _record_hash({**matches[0], "tag": tag})


def _symmetric_gap_pct(left: float, right: float) -> float:
    midpoint_abs = (abs(left) + abs(right)) / 2.0
    return abs(left - right) / midpoint_abs * 100.0 if midpoint_abs else np.nan


def build_dvn_nopat_discrepancy_reconciliation(
    *, companyfacts_root: Path, parent_triangulation: pd.DataFrame
) -> pd.DataFrame:
    facts_path = companyfacts_root / f"CIK{WPX_CIK}.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    tags = {
        "parent_net_income": "NetIncomeLoss",
        "consolidated_net_income": "ProfitLoss",
        "noncontrolling_interest": "NetIncomeLossAttributableToNoncontrollingInterest",
        "discontinued_operations_net_of_tax": "IncomeLossFromDiscontinuedOperationsNetOfTax",
        "operating_income": "OperatingIncomeLoss",
        "interest_expense": "InterestExpense",
        "income_tax": "IncomeTaxExpenseBenefit",
        "pretax_continuing_income": "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "other_nonoperating_income": "OtherNonoperatingIncomeExpense",
        "impairment_oil_gas": "ImpairmentOfOilAndGasProperties",
    }
    values: dict[str, float] = {}
    hashes: list[str] = []
    for name, tag in tags.items():
        values[name], record_hash = _fact(facts, tag)
        hashes.append(record_hash)

    parent = parent_triangulation.loc[
        parent_triangulation["ticker"].eq("DVN")
        & parent_triangulation["fiscal_year"].eq(2021)
    ].iloc[0]
    period_days = (
        pd.Timestamp(WPX_PERIOD_END) - pd.Timestamp(WPX_PERIOD_START)
    ).days + 1
    year_days = 366 if isleap(pd.Timestamp(WPX_PERIOD_END).year) else 365
    annualization = year_days / period_days
    pretax = values["pretax_continuing_income"]
    income_tax = values["income_tax"]
    tax_rate = float(np.clip(abs(income_tax / pretax), 0.0, 0.35))

    parent_to_consolidated_adjustment = (
        values["consolidated_net_income"] - values["parent_net_income"]
    )
    continuing_consolidated_net_income = (
        values["consolidated_net_income"]
        - values["discontinued_operations_net_of_tax"]
    )
    scope_adjustment_ytd = (
        continuing_consolidated_net_income - values["parent_net_income"]
    )
    scope_adjustment_annualized = scope_adjustment_ytd * annualization
    adjusted_route_a = (
        continuing_consolidated_net_income
        + values["interest_expense"] * (1.0 - tax_rate)
    ) * annualization
    route_b = values["operating_income"] * (1.0 - tax_rate) * annualization
    adjusted_gap = _symmetric_gap_pct(adjusted_route_a, route_b)
    nonoperating_residual_pretax = (
        values["pretax_continuing_income"]
        - values["operating_income"]
        + values["interest_expense"]
    )
    nonoperating_residual_after_tax_annualized = (
        nonoperating_residual_pretax * (1.0 - tax_rate) * annualization
    )
    route_identity_error = (
        adjusted_route_a - route_b - nonoperating_residual_after_tax_annualized
    )
    parent_scope_identity_error = (
        values["consolidated_net_income"]
        - values["parent_net_income"]
        - values["noncontrolling_interest"]
    )
    continuing_income_identity_error = (
        continuing_consolidated_net_income
        - (values["pretax_continuing_income"] - values["income_tax"])
    )
    headline_route_a = float(
        parent["route_a_net_income_plus_after_tax_interest_usd"]
    )
    headline_route_b = float(parent["route_b_operating_income_after_tax_usd"])
    headline_difference = headline_route_a - headline_route_b
    explained_difference = (
        -scope_adjustment_annualized
        + nonoperating_residual_after_tax_annualized
    )
    unexplained_difference = headline_difference - explained_difference

    return pd.DataFrame(
        [
            {
                "ticker": "DVN",
                "fiscal_year": 2021,
                "target": "WPX Energy",
                "target_period_start": WPX_PERIOD_START,
                "target_period_end": WPX_PERIOD_END,
                "period_days": period_days,
                "annualization_factor": annualization,
                "tax_rate": tax_rate,
                "parent_attributable_net_income_ytd_usd": values[
                    "parent_net_income"
                ],
                "consolidated_net_income_ytd_usd": values[
                    "consolidated_net_income"
                ],
                "noncontrolling_interest_ytd_usd": values[
                    "noncontrolling_interest"
                ],
                "discontinued_operations_net_of_tax_ytd_usd": values[
                    "discontinued_operations_net_of_tax"
                ],
                "continuing_consolidated_net_income_ytd_usd": continuing_consolidated_net_income,
                "operating_income_ytd_usd": values["operating_income"],
                "interest_expense_ytd_usd": values["interest_expense"],
                "pretax_continuing_income_ytd_usd": values[
                    "pretax_continuing_income"
                ],
                "income_tax_benefit_ytd_usd": values["income_tax"],
                "other_nonoperating_income_ytd_usd": values[
                    "other_nonoperating_income"
                ],
                "impairment_oil_gas_ytd_usd": values["impairment_oil_gas"],
                "headline_route_a_usd": headline_route_a,
                "headline_route_b_usd": headline_route_b,
                "headline_route_gap_pct": float(
                    parent["route_a_b_symmetric_gap_pct"]
                ),
                "noncontrolling_scope_adjustment_annualized_usd": parent_to_consolidated_adjustment
                * annualization,
                "discontinued_operations_scope_adjustment_annualized_usd": -values[
                    "discontinued_operations_net_of_tax"
                ]
                * annualization,
                "total_ownership_and_operation_scope_adjustment_annualized_usd": scope_adjustment_annualized,
                "scope_adjusted_route_a_usd": adjusted_route_a,
                "scope_adjusted_route_b_usd": route_b,
                "scope_adjusted_route_gap_pct": adjusted_gap,
                "nonoperating_residual_pretax_ytd_usd": nonoperating_residual_pretax,
                "nonoperating_residual_after_tax_annualized_usd": nonoperating_residual_after_tax_annualized,
                "impairment_annualized_usd": values["impairment_oil_gas"]
                * annualization,
                "impairment_gap_adjustment_usd": 0.0,
                "derivative_gap_adjustment_usd": 0.0,
                "unusual_tax_gap_adjustment_usd": 0.0,
                "financing_scope_gap_after_interest_addback_usd": 0.0,
                "period_mismatch_days": 0,
                "headline_difference_usd": headline_difference,
                "explained_difference_usd": explained_difference,
                "unexplained_difference_usd": unexplained_difference,
                "parent_scope_identity_error_usd": parent_scope_identity_error,
                "continuing_income_identity_error_usd": continuing_income_identity_error,
                "route_reconciliation_identity_error_usd": route_identity_error,
                "predeclared_tolerance_pct": TRIANGULATION_TOLERANCE_PCT,
                "scope_adjusted_two_route_triangulated": bool(
                    adjusted_gap <= TRIANGULATION_TOLERANCE_PCT
                ),
                "primary_discrepancy_cause": "PARENT_ATTRIBUTABLE_NET_INCOME_INCLUDES_DISCONTINUED_OPERATIONS_WHILE_ROUTE_B_IS_CONTINUING_CONSOLIDATED_OPERATIONS",
                "impairment_treatment": "COMMON_TO_BOTH_CONTINUING_OPERATIONS_ROUTES_NOT_A_GAP_DRIVER",
                "derivative_treatment": "NO_SEPARATE_GAP_ADJUSTMENT_BOTH_ROUTES_RETAIN_REPORTED_CONTINUING_OPERATIONS",
                "tax_treatment": "SAME_PREDECLARED_TARGET_EFFECTIVE_TAX_RATE_APPLIED_TO_BOTH_ROUTES",
                "period_treatment": "EXACT_SAME_2020_YTD_PERIOD",
                "source_companyfacts_path": str(facts_path),
                "source_evidence_bundle_sha256": hashlib.sha256(
                    "|".join(sorted(hashes)).encode("ascii")
                ).hexdigest(),
                "source_cell_checks": len(hashes),
                "source_cell_checks_passed": len(hashes),
                "research_only": True,
                "terminal_input_allowed": False,
            }
        ]
    )


def build_scope_adjusted_triangulation(
    *, parent_triangulation: pd.DataFrame, reconciliation: pd.DataFrame
) -> pd.DataFrame:
    result = parent_triangulation.copy()
    result["v1_7_3_two_route_nopat_triangulated"] = result[
        "two_route_nopat_triangulated"
    ]
    result["validation_route_a_usd"] = result[
        "route_a_net_income_plus_after_tax_interest_usd"
    ]
    result["validation_route_b_usd"] = result[
        "route_b_operating_income_after_tax_usd"
    ]
    result["validation_route_gap_pct"] = result["route_a_b_symmetric_gap_pct"]
    result["validation_scope_adjustment_applied"] = False
    result["validation_scope_adjustment_semantics"] = (
        "V1_7_3_SAME_PERIOD_ROUTES_UNCHANGED"
    )
    result["v1_7_4_scope_adjusted_two_route_triangulated"] = result[
        "two_route_nopat_triangulated"
    ]
    result["validated_cohort_candidate"] = result["ticker"].isin(["FANG", "DVN"])

    rec = reconciliation.iloc[0]
    mask = result["ticker"].eq("DVN") & result["fiscal_year"].eq(2021)
    result.loc[mask, "validation_route_a_usd"] = rec[
        "scope_adjusted_route_a_usd"
    ]
    result.loc[mask, "validation_route_b_usd"] = rec[
        "scope_adjusted_route_b_usd"
    ]
    result.loc[mask, "validation_route_gap_pct"] = rec[
        "scope_adjusted_route_gap_pct"
    ]
    result.loc[mask, "validation_scope_adjustment_applied"] = True
    result.loc[mask, "validation_scope_adjustment_semantics"] = (
        "PARENT_TO_CONSOLIDATED_AND_DISCONTINUED_OPERATIONS_SCOPE_RECONCILED"
    )
    result.loc[mask, "v1_7_4_scope_adjusted_two_route_triangulated"] = rec[
        "scope_adjusted_two_route_triangulated"
    ]
    result["terminal_input_allowed"] = False
    result["research_only"] = True
    return result
