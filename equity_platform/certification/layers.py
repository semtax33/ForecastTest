from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LayerThresholds:
    critical_precision: float = 0.99
    critical_recall: float = 0.95
    narrative_precision: float = 0.90
    narrative_recall: float = 0.80
    source_span_coverage: float = 1.0
    lineage_hash_coverage: float = 1.0
    minimum_oos_observations: int = 4


LAYER_REQUIRED_COLUMNS = {
    "ticker",
    "sector",
    "source_coverage_complete",
    "lineage_hash_coverage",
    "critical_gold_scope_complete",
    "critical_numeric_precision",
    "critical_recall",
    "narrative_precision",
    "narrative_recall",
    "source_span_coverage",
    "silent_ambiguity_count",
    "issuer_branches_in_core",
    "positional_selectors_in_core",
    "llm_unverified_fact_count",
    "accounting_ready",
    "industry_data_ready",
    "forecast_oos_observations",
    "forecast_point_gate",
    "market_ready",
    "dcf_inputs_ready",
    "terminal_input_ready",
}


def _at_least(value: object, threshold: float) -> bool:
    return bool(pd.notna(value) and float(value) >= threshold)


def certify_layers(
    evidence: pd.DataFrame,
    thresholds: LayerThresholds = LayerThresholds(),
) -> pd.DataFrame:
    """Build the fail-closed L0→L3 certification funnel.

    Narrative evidence has its own research-only gate.  It never weakens the
    critical fact thresholds and cannot grant valuation authority.
    """

    missing = LAYER_REQUIRED_COLUMNS - set(evidence)
    if missing:
        raise ValueError(f"Layer evidence is missing: {sorted(missing)}")
    if evidence["ticker"].duplicated().any():
        raise ValueError("Layer certification requires unique tickers")

    rows: list[dict[str, object]] = []
    for source in evidence.to_dict(orient="records"):
        l0_checks = {
            "source_coverage": bool(source["source_coverage_complete"]),
            "lineage_hash": _at_least(
                source["lineage_hash_coverage"], thresholds.lineage_hash_coverage
            ),
        }
        l0 = all(l0_checks.values())
        l1_checks = {
            "l0_source": l0,
            "critical_gold_scope": bool(source["critical_gold_scope_complete"]),
            "critical_precision": _at_least(
                source["critical_numeric_precision"], thresholds.critical_precision
            ),
            "critical_recall": _at_least(
                source["critical_recall"], thresholds.critical_recall
            ),
            "source_span": _at_least(
                source["source_span_coverage"], thresholds.source_span_coverage
            ),
            "silent_ambiguity": int(source["silent_ambiguity_count"]) == 0,
            "issuer_branch": int(source["issuer_branches_in_core"]) == 0,
            "positional_selector": int(source["positional_selectors_in_core"]) == 0,
            "llm_verified": int(source["llm_unverified_fact_count"]) == 0,
        }
        l1 = all(l1_checks.values())
        narrative_ready = (
            l0
            and _at_least(
                source["narrative_precision"], thresholds.narrative_precision
            )
            and _at_least(source["narrative_recall"], thresholds.narrative_recall)
        )
        observations = (
            int(source["forecast_oos_observations"])
            if pd.notna(source["forecast_oos_observations"])
            else 0
        )
        l2_checks = {
            "l1_parser": l1,
            "accounting": bool(source["accounting_ready"]),
            "industry_data": bool(source["industry_data_ready"]),
            "forecast_observations": observations >= thresholds.minimum_oos_observations,
            "forecast_point_gate": bool(source["forecast_point_gate"]),
        }
        l2 = all(l2_checks.values())
        l3_checks = {
            "l2_economics": l2,
            "market": bool(source["market_ready"]),
            "dcf_inputs": bool(source["dcf_inputs_ready"]),
            "terminal_authority": bool(source["terminal_input_ready"]),
        }
        l3 = all(l3_checks.values())
        highest = (
            "L3_VALUATION_READY"
            if l3
            else "L2_ECONOMICS_READY"
            if l2
            else "L1_PARSER_READY"
            if l1
            else "L0_SOURCE_READY"
            if l0
            else "UNREADY"
        )
        rows.append(
            {
                **source,
                "l0_source_ready": l0,
                "l0_failed_gates": "|".join(k for k, v in l0_checks.items() if not v),
                "l1_parser_ready": l1,
                "l1_failed_gates": "|".join(k for k, v in l1_checks.items() if not v),
                "narrative_evidence_ready": narrative_ready,
                "l2_economics_ready": l2,
                "l2_failed_gates": "|".join(k for k, v in l2_checks.items() if not v),
                "l3_valuation_ready": l3,
                "l3_failed_gates": "|".join(k for k, v in l3_checks.items() if not v),
                "highest_certification_level": highest,
                "strict_dcf_allowed": l3,
                "fair_value_authority": False,
                "production_promoted": False,
            }
        )
    return pd.DataFrame(rows).sort_values(["sector", "ticker"]).reset_index(drop=True)
