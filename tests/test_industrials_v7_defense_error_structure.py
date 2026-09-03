from __future__ import annotations

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.platform.validation import (
    build_aggregate_error_decomposition,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v7_defense_cross_company_error_audit"


def test_error_decomposition_exact_identity() -> None:
    walk = pd.DataFrame(
        {
            "period": ["2025Q1", "2025Q1"],
            "segment": ["A", "B"],
            "actual_sales_usd": [100.0, 100.0],
            "predicted_sales_usd": [110.0, 95.0],
            "naive_prior_year_sales_usd": [80.0, 90.0],
        }
    )
    result = build_aggregate_error_decomposition(walk, company="TEST")
    row = result["period_error_decomposition"].iloc[0]
    assert row["sum_segment_absolute_error_usd"] == 15.0
    assert row["aggregate_model_absolute_error_usd"] == 5.0
    assert row["cancellation_benefit_usd"] == 10.0
    assert row["decomposition_identity_error_usd"] == 0.0


def test_four_company_audit_preserves_hypothesis_only_authority() -> None:
    gate = pd.read_csv(OUTPUT / "industrials_v7_defense_gate.csv").iloc[0]
    summary = pd.read_csv(OUTPUT / "defense_error_decomposition_summary.csv")
    assert gate["companies"] == 4
    assert gate["company_periods"] == 24
    assert bool(gate["decomposition_identity_pass"])
    assert bool(gate["frozen_routes_only"])
    assert not bool(gate["universal_industry_law_claim_allowed"])
    assert summary["decomposition_identity_max_error_usd"].max() == 0.0
    assert summary["aggregate_signal_positive_before_cancellation"].sum() == 3
    assert summary["aggregate_outperformance_depends_on_cancellation"].sum() == 1

