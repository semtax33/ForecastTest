from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.data.consensus import load_arcana_consensus
from energy_nowcast.operations.store import (
    connect_store,
    ingest_consensus_vintages,
    insert_fcff_attribution,
    insert_valuation_settlement,
    insert_valuation_snapshot,
    read_table,
    write_store_metadata,
)
from energy_nowcast.valuation.financials import ENERGY_TICKERS
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11
from energy_nowcast.valuation_monitoring.attribution import build_fcff_attribution
from energy_nowcast.valuation_monitoring.scorecard import (
    build_valuation_live_scorecard,
)
from energy_nowcast.valuation_monitoring.snapshot import (
    MODEL_VERSION,
    build_hypothesis_monitors,
    build_valuation_snapshots,
    model_change_policy,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output" / "energy_valuation_v1_1_live"
COMPANYFACTS = (
    ROOT.parent / "Arcana" / "data-lake" / "bronze" / "sec" / "companyfacts"
)
CONSENSUS = ROOT.parent / "Arcana" / "data-lake" / "bronze" / "consensus"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append-only live monitoring for frozen Energy Valuation V1.1"
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--db", type=Path, default=OUTPUT / "live_store.sqlite")
    parser.add_argument("--market-prices", type=Path, default=None)
    parser.add_argument("--settlements", type=Path, default=None)
    return parser.parse_args()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def _ingest_settlements(
    connection: object,
    path: Path | None,
) -> dict[str, int]:
    counts = {"inserted": 0, "unchanged": 0}
    if path is None:
        return counts
    frame = pd.read_csv(path)
    required = {
        "snapshot_as_of_date", "ticker", "target_quarter",
        "actual_ttm_fcff_usd", "settlement_market_price", "release_date",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Settlement CSV missing columns: {sorted(missing)}")
    snapshots = read_table(connection, "valuation_snapshots")
    valid_keys = set(zip(
        snapshots["as_of_date"], snapshots["ticker"],
        snapshots["target_quarter"], snapshots["model_version"], strict=False,
    ))
    for _, source in frame.iterrows():
        ticker = str(source["ticker"]).upper()
        snapshot_date = date.fromisoformat(str(source["snapshot_as_of_date"]))
        release_date = date.fromisoformat(str(source["release_date"]))
        key = (
            snapshot_date.isoformat(), ticker, str(source["target_quarter"]),
            MODEL_VERSION,
        )
        if key not in valid_keys:
            raise ValueError(f"Settlement has no immutable snapshot: {key}")
        if release_date <= snapshot_date:
            raise ValueError(f"Settlement is not forward-looking: {key}")
        status = insert_valuation_settlement(connection, {
            "snapshot_as_of_date": snapshot_date.isoformat(),
            "ticker": ticker,
            "target_quarter": str(source["target_quarter"]),
            "model_version": MODEL_VERSION,
            "actual_ttm_fcff_usd": float(source["actual_ttm_fcff_usd"]),
            "settlement_market_price": float(source["settlement_market_price"]),
            "release_date": release_date.isoformat(),
            "source_path": str(source.get("source_path", path)),
        })
        counts[status.lower()] += 1
    return counts


def _write_report(
    output: Path,
    score: pd.DataFrame,
    monitors: pd.DataFrame,
    attribution: pd.DataFrame,
    snapshot_status: dict[str, int],
    attribution_status: dict[str, int],
    consensus_status: dict[str, int],
    manifest_sha: str,
) -> None:
    ep = monitors.loc[monitors["hypothesis"].eq("E&P_SYSTEMATIC_SKEW")].iloc[0]
    incomplete = int(attribution["attribution_status"].ne(
        "COMPLETE_D_AND_A_NWC_OTHER_SEPARATED"
    ).sum())
    report = f"""# Energy Valuation V1.1 live-forward monitoring

The V1.1 benchmark was verified before and after this append-only run.
Benchmark manifest SHA-256: `{manifest_sha}`. No frozen assumption, bridge,
parser, WACC, scenario bound, terminal growth, or weight was changed.

## Live gate

{_markdown(score)}

Snapshots: {snapshot_status}. FCFF attributions: {attribution_status}.
Consensus vintages: {consensus_status}. Production remains separately locked.

## Frozen research hypotheses

{_markdown(monitors)}

E&P skew remains `MONITOR_DO_NOT_RETUNE` at {float(ep['value']):.2f}% with
{ep['secondary_value']} outliers. This is evidence to collect, not a reason to
change V1.1.

## FCFF attribution

`NOPAT + D&A - Cash CapEx - Delta operating NWC + Other cash conversion = FCFF`.
`Other cash conversion` is reported explicitly so missing/non-working-capital
cash-flow items are never mislabeled as Delta NWC. {incomplete} ticker rows use
the fail-closed combined CFO bridge because standardized D&A or NWC components
are unavailable. All rows remain diagnostics and cannot feed back into V1.1.

This monitoring output is not an investment recommendation.
"""
    (output / "report.md").write_text(report, encoding="utf-8")


def main() -> int:
    args = _arguments()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    parent_before = verify_v1(ROOT)
    benchmark_before = verify_v11(ROOT)
    manifest_sha = benchmark_before["manifest_sha256"]

    consensus, coverage = load_arcana_consensus(CONSENSUS, ENERGY_TICKERS)
    cutoff = pd.Timestamp(args.as_of)
    consensus = consensus.loc[
        pd.to_datetime(consensus["snapshot_date"], errors="coerce").le(cutoff)
    ].copy()
    if not coverage.empty:
        coverage = coverage.loc[
            pd.to_datetime(coverage["snapshot_date"], errors="coerce").le(cutoff)
        ].copy()
    snapshots = build_valuation_snapshots(
        ROOT,
        args.as_of,
        manifest_sha,
        args.market_prices,
    )
    attribution, capex_audit = build_fcff_attribution(
        COMPANYFACTS,
        cutoff,
    )
    monitors = build_hypothesis_monitors(ROOT)
    policy = model_change_policy()

    snapshot_status = {"inserted": 0, "unchanged": 0}
    attribution_status = {"inserted": 0, "unchanged": 0}
    with connect_store(args.db) as connection:
        consensus_status = ingest_consensus_vintages(
            connection, consensus, coverage
        )
        for _, row in snapshots.iterrows():
            status = insert_valuation_snapshot(connection, row.to_dict())
            snapshot_status[status.lower()] += 1
        for _, row in attribution.iterrows():
            status = insert_fcff_attribution(connection, row.to_dict())
            attribution_status[status.lower()] += 1
        settlement_status = _ingest_settlements(connection, args.settlements)
        details, score = build_valuation_live_scorecard(connection)
        write_store_metadata(connection, "energy_v1_1_manifest_sha256", manifest_sha)
        write_store_metadata(connection, "energy_v1_1_read_only", True)
        write_store_metadata(connection, "minimum_live_observations", 20)
        tables = (
            "consensus_vintages", "consensus_source_coverage",
            "valuation_snapshots", "fcff_attributions", "valuation_settlements",
        )
        for table in tables:
            read_table(connection, table).to_csv(
                args.output_dir / f"{table}.csv", index=False
            )

    details.to_csv(args.output_dir / "live_settlement_scorecard.csv", index=False)
    score.to_csv(args.output_dir / "live_scorecard_summary.csv", index=False)
    monitors.to_csv(args.output_dir / "hypothesis_monitors.csv", index=False)
    policy.to_csv(args.output_dir / "model_change_policy.csv", index=False)
    capex_audit.to_csv(args.output_dir / "live_capex_semantics_audit.csv", index=False)

    parent_after = verify_v1(ROOT)
    benchmark_after = verify_v11(ROOT)
    if parent_after["manifest_sha256"] != parent_before["manifest_sha256"]:
        raise RuntimeError("Immutable V1.0 parent changed during monitoring run")
    if benchmark_after["manifest_sha256"] != manifest_sha:
        raise RuntimeError("Frozen V1.1 changed during monitoring run")
    metadata = {
        "monitoring_version": "ENERGY_VALUATION_V1_1_LIVE_MONITORING_V1",
        "as_of_date": args.as_of.isoformat(),
        "benchmark_status": "SANITY_AUDITED_RESEARCH_FROZEN",
        "benchmark_manifest_sha256": manifest_sha,
        "parent_manifest_sha256": parent_after["manifest_sha256"],
        "benchmark_verified_before_and_after": True,
        "frozen_benchmark_mutated": False,
        "live_matched_observations": int(score.iloc[0]["matched_observations"]),
        "minimum_live_observations": 20,
        "model_change_lock": score.iloc[0]["model_change_lock"],
        "production_promoted": False,
        "consensus_sources": {
            "alpha_vantage": str(CONSENSUS / "alpha-vantage"),
            "fmp": str(CONSENSUS / "fmp"),
            "finnworlds": str(CONSENSUS / "finnworlds"),
            "finnworlds_treatment": "RATINGS_ONLY_NOT_REVENUE_CONSENSUS",
        },
        "snapshot_status": snapshot_status,
        "attribution_status": attribution_status,
        "settlement_status": settlement_status,
        "policy": (
            "V1.1_READ_ONLY; PROVEN_BUG_TO_V1.1.1; "
            "NEW_ECONOMIC_IDEA_TO_V1.2"
        ),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    _write_report(
        args.output_dir,
        score,
        monitors,
        attribution,
        snapshot_status,
        attribution_status,
        consensus_status,
        manifest_sha,
    )
    print(
        f"Energy V1.1 live monitoring complete: snapshots={snapshot_status}; "
        f"attribution={attribution_status}; settlements={settlement_status}"
    )
    print(score.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
