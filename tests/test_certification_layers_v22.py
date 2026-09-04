from __future__ import annotations

import pandas as pd

from equity_platform.certification import certify_layers


def _row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": "TEST",
        "sector": "ENERGY",
        "source_coverage_complete": True,
        "lineage_hash_coverage": 1.0,
        "critical_gold_scope_complete": True,
        "critical_numeric_precision": 0.99,
        "critical_recall": 0.95,
        "narrative_precision": 0.90,
        "narrative_recall": 0.80,
        "source_span_coverage": 1.0,
        "silent_ambiguity_count": 0,
        "issuer_branches_in_core": 0,
        "positional_selectors_in_core": 0,
        "llm_unverified_fact_count": 0,
        "accounting_ready": True,
        "industry_data_ready": True,
        "forecast_oos_observations": 4,
        "forecast_point_gate": True,
        "market_ready": True,
        "dcf_inputs_ready": True,
        "terminal_input_ready": True,
    }
    row.update(updates)
    return row


def test_layer_funnel_is_monotone_and_terminal_is_a_hard_l3_gate() -> None:
    ready = certify_layers(pd.DataFrame([_row()])).iloc[0]
    assert ready["highest_certification_level"] == "L3_VALUATION_READY"
    assert bool(ready["strict_dcf_allowed"])

    terminal_locked = certify_layers(
        pd.DataFrame([_row(terminal_input_ready=False)])
    ).iloc[0]
    assert bool(terminal_locked["l2_economics_ready"])
    assert not bool(terminal_locked["l3_valuation_ready"])
    assert "terminal_authority" in terminal_locked["l3_failed_gates"]

    parser_failed = certify_layers(
        pd.DataFrame([_row(critical_numeric_precision=0.989)])
    ).iloc[0]
    assert bool(parser_failed["l0_source_ready"])
    assert not bool(parser_failed["l1_parser_ready"])
    assert not bool(parser_failed["l2_economics_ready"])
    assert not bool(parser_failed["l3_valuation_ready"])


def test_narrative_gate_is_separate_from_critical_parser_authority() -> None:
    result = certify_layers(
        pd.DataFrame([_row(narrative_precision=0.50)])
    ).iloc[0]
    assert bool(result["l1_parser_ready"])
    assert not bool(result["narrative_evidence_ready"])
    assert bool(result["l3_valuation_ready"])
    assert not bool(result["fair_value_authority"])

    low_recall = certify_layers(
        pd.DataFrame([_row(narrative_precision=1.0, narrative_recall=0.79)])
    ).iloc[0]
    assert not bool(low_recall["narrative_evidence_ready"])
    assert bool(low_recall["l1_parser_ready"])
