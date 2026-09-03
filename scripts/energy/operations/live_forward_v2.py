from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.data.consensus import load_arcana_consensus
from energy_nowcast.operations.live_forward_v2 import (
    build_energy_v11_live_snapshots,
    consensus_store_rows,
)
from energy_nowcast.research.ep_v19.benchmark import verify_v19
from energy_nowcast.valuation.financials import ENERGY_TICKERS
from energy_nowcast.valuation_v11.benchmark import verify_v11
from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.storage import LiveForwardStore


ROOT = PROJECT_ROOT
DEFAULT_OUTPUT = ROOT / "output/energy_live_forward_v2"
CONSENSUS_ROOT = ROOT.parent / "Arcana/data-lake/bronze/consensus"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sector-neutral append-only live-forward runner for frozen Energy V1.1/V1.9"
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--db", type=Path, default=DEFAULT_OUTPUT / "live_forward.sqlite")
    parser.add_argument("--actuals", type=Path)
    return parser.parse_args()


def _load_actuals(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    frame = pd.read_csv(path)
    required = {"ticker", "target_period", "release_date"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Actual outcome file is missing columns: {sorted(missing)}")
    rows: list[dict[str, object]] = []
    source_hash = sha256_file(path)
    for source in frame.to_dict("records"):
        rows.append(
            {
                "ticker": str(source["ticker"]).upper(),
                "target_period": str(source["target_period"]),
                "release_date": date.fromisoformat(str(source["release_date"])).isoformat(),
                "actual_revenue_usd": source.get("actual_revenue_usd"),
                "actual_ebit_usd": source.get("actual_ebit_usd"),
                "actual_fcff_usd": source.get("actual_fcff_usd"),
                "actual_roic_pct": source.get("actual_roic_pct"),
                "market_price": source.get("market_price"),
                "source_path": str(path.resolve()),
                "source_hash": source_hash,
            }
        )
    return rows


def main() -> int:
    args = arguments()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    v11_before = verify_v11(ROOT)
    v19_before = verify_v19(ROOT)
    consensus, provider_coverage = load_arcana_consensus(
        CONSENSUS_ROOT, ENERGY_TICKERS
    )
    snapshots = build_energy_v11_live_snapshots(
        root=ROOT,
        as_of_date=args.as_of,
        v11_manifest_sha256=str(v11_before["manifest_sha256"]),
        v19_manifest_sha256=str(v19_before["manifest_sha256"]),
        consensus=consensus,
    )
    counts = {"snapshots": {"INSERTED": 0, "UNCHANGED": 0}, "consensus": {"INSERTED": 0, "UNCHANGED": 0}, "actuals": {"INSERTED": 0, "UNCHANGED": 0}}
    with LiveForwardStore(args.db) as store:
        for snapshot in snapshots:
            counts["snapshots"][store.add_snapshot(snapshot)] += 1
        for row in consensus_store_rows(consensus, args.as_of):
            counts["consensus"][store.add_consensus(row)] += 1
        for row in _load_actuals(args.actuals):
            counts["actuals"][store.add_actual(row)] += 1
        settled = store.settle_available()
        for table in (
            "forecast_snapshots",
            "consensus_vintages",
            "actual_outcomes",
            "error_attributions",
        ):
            store.table(table).to_csv(args.output_dir / f"{table}.csv", index=False)
        snapshot_count = len(store.table("forecast_snapshots"))
        matched_count = len(store.table("error_attributions"))
    provider_coverage.to_csv(
        args.output_dir / "consensus_provider_coverage.csv", index=False
    )
    provider_rows = {
        str(provider): int(count)
        for provider, count in consensus["provider"].value_counts().items()
    }
    v11_after = verify_v11(ROOT)
    v19_after = verify_v19(ROOT)
    if v11_before["manifest_sha256"] != v11_after["manifest_sha256"]:
        raise RuntimeError("Frozen Energy V1.1 changed during live run")
    if v19_before["manifest_sha256"] != v19_after["manifest_sha256"]:
        raise RuntimeError("Frozen E&P V1.9 changed during live run")
    metadata = {
        "version": "ENERGY_LIVE_FORWARD_V2",
        "as_of_date": args.as_of.isoformat(),
        "append_only": True,
        "snapshot_count": snapshot_count,
        "matched_observations": matched_count,
        "minimum_production_observations": 20,
        "production_promoted": False,
        "v1_1_manifest_sha256": v11_after["manifest_sha256"],
        "v1_9_manifest_sha256": v19_after["manifest_sha256"],
        "consensus_provider_rows": provider_rows,
        "finnworlds_ratings_coverage_rows": int(len(provider_coverage)),
        "finnworlds_revenue_consensus_policy": (
            "RATINGS_ONLY_NOT_USED_AS_REVENUE_CONSENSUS"
        ),
        "counts": counts,
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = f"""# Energy live-forward V2\n\nFrozen Energy V1.1 and E&P V1.9 were verified before and after the run.\nSnapshots are append-only; a conflicting replay fails closed.\n\n- Stored forecast snapshots: {snapshot_count}\n- Settled post-forecast observations: {matched_count}/20\n- Production promoted: False\n- Revenue consensus rows by provider: {provider_rows}\n- Finnworlds ratings-only coverage rows: {len(provider_coverage)}\n- Current run: {counts}\n\nEach snapshot stores the forecast date, version, input hash, Revenue, EBIT,\nmargin, FCFF, ROIC, Forward DCF, Reverse DCF diagnostic, expectations gap,\nand the matching consensus vintage when available. Historical snapshots are\nnever updated in place.\n"""
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
