from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CertificationThresholds:
    critical_numeric_precision: float = 0.99
    critical_recall: float = 0.95
    source_span_coverage: float = 1.0
    lineage_hash_coverage: float = 1.0
    minimum_oos_observations: int = 4


REQUIRED_COLUMNS = {
    "ticker",
    "sector",
    "subindustry",
    "source_coverage_complete",
    "financial_history_ready",
    "critical_gold_scope_complete",
    "critical_numeric_precision",
    "critical_recall",
    "source_span_coverage",
    "lineage_hash_coverage",
    "silent_ambiguity_count",
    "issuer_branches_in_core",
    "positional_selectors_in_core",
    "unresolved_critical_accounting_identities",
    "llm_unverified_fact_count",
    "forecast_oos_observations",
    "forecast_point_gate",
    "accounting_ready",
    "market_ready",
    "dcf_inputs_ready",
}


def _at_least(value: object, threshold: float) -> bool:
    return bool(pd.notna(value) and float(value) >= threshold)


def certify_universe(
    evidence: pd.DataFrame,
    thresholds: CertificationThresholds = CertificationThresholds(),
) -> pd.DataFrame:
    """Apply predeclared parser -> forecast -> valuation gates per ticker.

    Missing accuracy evidence fails closed.  A prior research DCF may still be
    exposed as a diagnostic, but it never makes a ticker V2.1 eligible.
    """

    missing = REQUIRED_COLUMNS - set(evidence)
    if missing:
        raise ValueError(f"Certification evidence is missing: {sorted(missing)}")
    if evidence["ticker"].duplicated().any():
        duplicates = sorted(evidence.loc[evidence["ticker"].duplicated(), "ticker"])
        raise ValueError(f"Universe tickers must be unique: {duplicates}")

    rows: list[dict[str, object]] = []
    for source in evidence.to_dict(orient="records"):
        source_ready = bool(source["source_coverage_complete"])
        financial_ready = bool(source["financial_history_ready"])
        precision_pass = _at_least(
            source["critical_numeric_precision"],
            thresholds.critical_numeric_precision,
        )
        recall_pass = _at_least(
            source["critical_recall"], thresholds.critical_recall
        )
        parser_checks = {
            "source_coverage": source_ready,
            "financial_history": financial_ready,
            "critical_gold_scope": bool(source["critical_gold_scope_complete"]),
            "critical_precision": precision_pass,
            "critical_recall": recall_pass,
            "source_span": _at_least(
                source["source_span_coverage"],
                thresholds.source_span_coverage,
            ),
            "lineage_hash": _at_least(
                source["lineage_hash_coverage"],
                thresholds.lineage_hash_coverage,
            ),
            "silent_ambiguity": int(source["silent_ambiguity_count"]) == 0,
            "issuer_branch": int(source["issuer_branches_in_core"]) == 0,
            "positional_selector": int(source["positional_selectors_in_core"]) == 0,
            "accounting_identity": int(
                source["unresolved_critical_accounting_identities"]
            )
            == 0,
            "llm_verified": int(source["llm_unverified_fact_count"]) == 0,
        }
        parser_pass = all(parser_checks.values())
        if not source_ready or not financial_ready:
            parser_status = "PARSER_INCOMPLETE"
        elif parser_pass:
            parser_status = "PARSER_CERTIFIED"
        else:
            parser_status = "RESEARCH_READY_NEEDS_REVIEW"

        observation_value = source["forecast_oos_observations"]
        observations = int(observation_value) if pd.notna(observation_value) else 0
        if observations < thresholds.minimum_oos_observations:
            forecast_status = "NOT_TESTED"
            forecast_pass = False
        elif bool(source["forecast_point_gate"]):
            forecast_status = "OOS_POINT_GATE_PASS"
            forecast_pass = True
        else:
            forecast_status = "VALUATION_RESEARCH_BASELINE_ONLY"
            forecast_pass = False

        valuation_checks = {
            "parser": parser_pass,
            "forecast": forecast_pass,
            "accounting": bool(source["accounting_ready"]),
            "market": bool(source["market_ready"]),
            "dcf_inputs": bool(source["dcf_inputs_ready"]),
        }
        valuation_pass = all(valuation_checks.values())
        if valuation_pass:
            valuation_status = "VALUATION_READY"
            universe_class = "A_VALUATION_READY"
        elif parser_status == "PARSER_INCOMPLETE":
            valuation_status = "NOT_ELIGIBLE"
            universe_class = "C_PARSER_INCOMPLETE"
        else:
            valuation_status = "VALUATION_RESEARCH_BASELINE_ONLY"
            universe_class = "B_RESEARCH_READY_NEEDS_REVIEW"

        failed_parser = [name for name, passed in parser_checks.items() if not passed]
        failed_valuation = [
            name for name, passed in valuation_checks.items() if not passed
        ]
        rows.append(
            {
                **source,
                "critical_precision_gate": precision_pass,
                "critical_recall_gate": recall_pass,
                "parser_certification": parser_status,
                "parser_failed_gates": "|".join(failed_parser),
                "forecast_certification": forecast_status,
                "valuation_eligibility": valuation_status,
                "valuation_failed_gates": "|".join(failed_valuation),
                "universe_class": universe_class,
                "v21_conditional_dcf_run": valuation_pass,
                "fair_value_authority": False,
                "terminal_input_ready": False,
                "production_promoted": False,
            }
        )
    result = pd.DataFrame(rows).sort_values(["sector", "subindustry", "ticker"])
    numeric = result.select_dtypes(include=[np.number])
    if numeric.replace([np.inf, -np.inf], np.nan).isna().all(axis=None):
        raise ValueError("Certification produced no finite numeric evidence")
    return result.reset_index(drop=True)
