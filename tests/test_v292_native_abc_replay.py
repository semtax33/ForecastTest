from __future__ import annotations

from scripts.architecture.v292_native_abc_replay import evaluate_native_abc_v292


def test_v292_tuned_replay_meets_route_aware_research_targets() -> None:
    _, summary, _ = evaluate_native_abc_v292()
    row = summary.loc[
        (summary["group_type"] == "ALL") & (summary["group"] == "ALL")
    ].iloc[0]

    assert row.candidate_recall == 1.0
    assert row.critical_precision >= 0.99
    assert row.critical_recall >= 0.50
    assert row.table_route_accuracy >= 0.95
    assert row.source_span_accuracy == 1.0
    assert row.duplicate_auto_emission == 0
    assert row.illegal_cross_clause_auto_binding == 0
    assert row.silent_frame_miss == 0
    assert bool(row.v292_route_aware_recovery_targets)
    assert not bool(row.layer_all_quality_targets)
    assert not bool(row.certification_eligible)
