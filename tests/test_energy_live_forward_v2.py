from datetime import date
from pathlib import Path

import pandas as pd

from energy_nowcast.operations.live_forward_v2 import build_energy_v11_live_snapshots
from energy_nowcast.research.ep_v19.benchmark import verify_v19
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]


def test_energy_live_snapshot_has_complete_canonical_evidence_fields() -> None:
    v11 = verify_v11(ROOT)
    v19 = verify_v19(ROOT)
    snapshots = build_energy_v11_live_snapshots(
        root=ROOT,
        as_of_date=date(2026, 9, 3),
        v11_manifest_sha256=v11["manifest_sha256"],
        v19_manifest_sha256=v19["manifest_sha256"],
        consensus=pd.DataFrame(),
    )
    assert len(snapshots) == 26
    assert len({snapshot.input_hash for snapshot in snapshots}) == 1
    assert all(snapshot.revenue_forecast_usd is not None for snapshot in snapshots)
    assert all(snapshot.ebit_forecast_usd is not None for snapshot in snapshots)
    assert all(snapshot.fcff_forecast_usd is not None for snapshot in snapshots)
    assert all(snapshot.forward_dcf_value_per_share is not None for snapshot in snapshots)
