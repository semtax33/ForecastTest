from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from energy_nowcast.operations.champion import verify_champion
from energy_nowcast.operations.decision import classify_disagreement
from energy_nowcast.operations.scorecard import build_live_scorecard
from energy_nowcast.operations.store import (
    connect_store,
    insert_actual_release,
    insert_forecast_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def _forecast_row() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-31",
        "ticker": "EOG",
        "quarter": "2026Q3",
        "timing_label": "T-30",
        "model_version": "3.4",
        "model_revenue": 110.0,
        "model_log_yoy": 10.0,
        "lower_80_revenue": 90.0,
        "upper_80_revenue": 120.0,
        "lower_95_revenue": 80.0,
        "upper_95_revenue": 130.0,
        "consensus_revenue": 100.0,
        "consensus_sources": "FMP",
        "decision": "WEAK_POSITIVE_DISAGREEMENT",
        "disagreement_gap_pct": 10.0,
        "champion_manifest_sha256": "manifest",
        "model_artifact_sha256": "artifact",
    }


def test_v34_champion_hashes_and_input_schemas_are_frozen():
    manifest = verify_champion(ROOT)
    assert manifest["immutable"] is True
    assert manifest["version"] == "3.4"
    assert manifest["manifest_sha256"]


def test_decision_layer_uses_consensus_location_inside_interval():
    weak = classify_disagreement(110.0, 100.0, 90.0, 120.0)
    strong = classify_disagreement(130.0, 100.0, 110.0, 150.0)
    no_edge = classify_disagreement(102.0, 100.0, 90.0, 120.0)
    assert weak["decision"] == "WEAK_POSITIVE_DISAGREEMENT"
    assert strong["decision"] == "STRONG_POSITIVE_DISAGREEMENT"
    assert no_edge["decision"] == "NO_EDGE"
    assert "not demonstrated investment alpha" in weak["interpretation"]


def test_snapshot_is_immutable_and_actual_release_builds_scorecard(tmp_path):
    with connect_store(tmp_path / "store.sqlite") as connection:
        row = _forecast_row()
        assert insert_forecast_snapshot(connection, row) == "INSERTED"
        assert insert_forecast_snapshot(connection, row) == "UNCHANGED"
        with pytest.raises(RuntimeError, match="Immutable forecast_snapshots"):
            insert_forecast_snapshot(connection, {**row, "model_revenue": 999.0})
        insert_actual_release(connection, {
            "ticker": "EOG",
            "quarter": "2026Q3",
            "actual_revenue": 115.0,
            "release_date": "2026-11-01",
            "source_path": str(tmp_path / "actual.csv"),
        })
        details, summary = build_live_scorecard(connection)
    assert details.loc[0, "model_ape_pct"] == pytest.approx(100 * 5 / 115)
    assert bool(details.loc[0, "covered_80"])
    assert bool(details.loc[0, "direction_correct"])
    assert summary.loc[0, "model_change_lock"] == "LOCKED"
    assert summary.loc[0, "observations_needed"] == 19


def test_timing_dates_can_be_recorded_as_t_minus_snapshots():
    from energy_nowcast.operations.snapshot import timing_label

    assert timing_label(date(2026, 10, 2), date(2026, 11, 1)) == "T-30"
    assert timing_label(date(2026, 10, 17), date(2026, 11, 1)) == "T-15"
    assert timing_label(date(2026, 10, 27), date(2026, 11, 1)) == "T-5"

