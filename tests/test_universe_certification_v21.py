from __future__ import annotations

import pandas as pd
import pytest

from equity_platform.certification import certify_universe
from equity_platform.paths import PROJECT_ROOT


def _evidence(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": "TEST",
        "sector": "ENERGY",
        "subindustry": "services",
        "source_coverage_complete": True,
        "financial_history_ready": True,
        "critical_gold_scope_complete": True,
        "critical_numeric_precision": 0.99,
        "critical_recall": 0.95,
        "source_span_coverage": 1.0,
        "lineage_hash_coverage": 1.0,
        "silent_ambiguity_count": 0,
        "issuer_branches_in_core": 0,
        "positional_selectors_in_core": 0,
        "unresolved_critical_accounting_identities": 0,
        "llm_unverified_fact_count": 0,
        "forecast_oos_observations": 4,
        "forecast_point_gate": True,
        "accounting_ready": True,
        "market_ready": True,
        "dcf_inputs_ready": True,
    }
    row.update(overrides)
    return row


def test_certification_is_fail_closed_and_dcf_requires_every_gate() -> None:
    ready = certify_universe(pd.DataFrame([_evidence()])).iloc[0]
    assert ready["universe_class"] == "A_VALUATION_READY"
    assert bool(ready["v21_conditional_dcf_run"])
    assert not bool(ready["fair_value_authority"])
    assert not bool(ready["terminal_input_ready"])

    missing_gold = certify_universe(
        pd.DataFrame(
            [
                _evidence(
                    critical_numeric_precision=float("nan"),
                    critical_recall=float("nan"),
                )
            ]
        )
    ).iloc[0]
    assert missing_gold["universe_class"] == "B_RESEARCH_READY_NEEDS_REVIEW"
    assert not bool(missing_gold["v21_conditional_dcf_run"])
    assert "critical_precision" in missing_gold["parser_failed_gates"]
    assert "critical_recall" in missing_gold["parser_failed_gates"]

    source_missing = certify_universe(
        pd.DataFrame([_evidence(source_coverage_complete=False)])
    ).iloc[0]
    assert source_missing["universe_class"] == "C_PARSER_INCOMPLETE"
    assert source_missing["parser_certification"] == "PARSER_INCOMPLETE"

    weak_forecast = certify_universe(
        pd.DataFrame([_evidence(forecast_point_gate=False)])
    ).iloc[0]
    assert weak_forecast["forecast_certification"] == "VALUATION_RESEARCH_BASELINE_ONLY"
    assert weak_forecast["universe_class"] == "B_RESEARCH_READY_NEEDS_REVIEW"


def test_certification_rejects_duplicate_or_incomplete_universe_rows() -> None:
    with pytest.raises(ValueError, match="unique"):
        certify_universe(pd.DataFrame([_evidence(), _evidence()]))

    incomplete = _evidence()
    incomplete.pop("critical_recall")
    with pytest.raises(ValueError, match="critical_recall"):
        certify_universe(pd.DataFrame([incomplete]))


def test_blind_holdout_adjudication_is_complete_and_fails_precision_gate() -> None:
    audit = pd.read_csv(
        PROJECT_ROOT
        / "configs/certification/platform_v21_blind_holdout_adjudication.csv"
    )
    assert len(audit) == 27
    assert audit["frame_id"].is_unique
    assert int(audit["correct"].sum()) == 17
    critical = audit.loc[audit["critical_numeric"]]
    assert len(critical) == 24
    assert int(critical["correct"].sum()) == 16
    assert float(critical["correct"].mean()) == pytest.approx(2 / 3)
    assert float(critical["correct"].mean()) < 0.99
