from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .champion import sha256_file


SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect_store(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        initialize_store(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_store(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consensus_vintages (
            as_of_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            provider TEXT NOT NULL,
            consensus_revenue REAL NOT NULL,
            consensus_revenue_low REAL,
            consensus_revenue_high REAL,
            analyst_count REAL,
            source_path TEXT NOT NULL,
            source_sha256 TEXT,
            ingested_at TEXT NOT NULL,
            PRIMARY KEY (as_of_date, ticker, quarter, provider, source_path)
        );
        CREATE TABLE IF NOT EXISTS consensus_source_coverage (
            as_of_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            provider TEXT NOT NULL,
            dataset TEXT,
            revenue_consensus_available INTEGER NOT NULL,
            status TEXT NOT NULL,
            source_path TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            PRIMARY KEY (as_of_date, ticker, provider, source_path)
        );
        CREATE TABLE IF NOT EXISTS forecast_snapshots (
            as_of_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            timing_label TEXT NOT NULL,
            model_version TEXT NOT NULL,
            model_revenue REAL NOT NULL,
            model_log_yoy REAL,
            lower_80_revenue REAL,
            upper_80_revenue REAL,
            lower_95_revenue REAL,
            upper_95_revenue REAL,
            consensus_revenue REAL,
            consensus_sources TEXT,
            decision TEXT NOT NULL,
            disagreement_gap_pct REAL,
            champion_manifest_sha256 TEXT NOT NULL,
            model_artifact_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (as_of_date, ticker, quarter, model_version)
        );
        CREATE TABLE IF NOT EXISTS actual_releases (
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            actual_revenue REAL NOT NULL,
            release_date TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_sha256 TEXT,
            ingested_at TEXT NOT NULL,
            PRIMARY KEY (ticker, quarter)
        );
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )


def _clean(value: Any) -> Any:
    if value is None or (isinstance(value, (float, np.floating)) and not np.isfinite(value)):
        return None
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date().isoformat()
    return value


def _immutable_insert(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    key_columns: tuple[str, ...],
) -> str:
    where = " AND ".join(f"{column} = ?" for column in key_columns)
    key = tuple(_clean(row[column]) for column in key_columns)
    existing = connection.execute(f"SELECT * FROM {table} WHERE {where}", key).fetchone()
    payload = {column: _clean(value) for column, value in row.items()}
    if existing is not None:
        comparable = {column: existing[column] for column in payload if column != "ingested_at" and column != "created_at"}
        proposed = {column: value for column, value in payload.items() if column in comparable}
        if comparable != proposed:
            raise RuntimeError(f"Immutable {table} row already exists with different values: {key}")
        return "UNCHANGED"
    columns = list(payload)
    placeholders = ",".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        tuple(payload[column] for column in columns),
    )
    return "INSERTED"


def ingest_consensus_vintages(
    connection: sqlite3.Connection,
    consensus: pd.DataFrame,
    coverage: pd.DataFrame | None = None,
) -> dict[str, int]:
    counts = {"inserted": 0, "unchanged": 0, "coverage_inserted": 0}
    for _, source in consensus.iterrows():
        source_path = Path(str(source["source_path"]))
        status = _immutable_insert(
            connection,
            "consensus_vintages",
            {
                "as_of_date": pd.Timestamp(source["snapshot_date"]).date().isoformat(),
                "ticker": str(source["ticker"]),
                "quarter": str(source["quarter"]),
                "provider": str(source["provider"]),
                "consensus_revenue": source["consensus_revenue"],
                "consensus_revenue_low": source.get("consensus_revenue_low"),
                "consensus_revenue_high": source.get("consensus_revenue_high"),
                "analyst_count": source.get("analyst_count"),
                "source_path": str(source_path),
                "source_sha256": sha256_file(source_path) if source_path.exists() else None,
                "ingested_at": _utc_now(),
            },
            ("as_of_date", "ticker", "quarter", "provider", "source_path"),
        )
        counts[status.lower()] += 1
    if coverage is not None:
        for _, source in coverage.iterrows():
            status = _immutable_insert(
                connection,
                "consensus_source_coverage",
                {
                    "as_of_date": pd.Timestamp(source["snapshot_date"]).date().isoformat(),
                    "ticker": str(source["ticker"]),
                    "provider": str(source["provider"]),
                    "dataset": source.get("dataset"),
                    "revenue_consensus_available": int(bool(source["revenue_consensus_available"])),
                    "status": str(source["status"]),
                    "source_path": str(source["source_path"]),
                    "ingested_at": _utc_now(),
                },
                ("as_of_date", "ticker", "provider", "source_path"),
            )
            if status == "INSERTED":
                counts["coverage_inserted"] += 1
    return counts


def insert_forecast_snapshot(connection: sqlite3.Connection, row: dict[str, Any]) -> str:
    return _immutable_insert(
        connection,
        "forecast_snapshots",
        {**row, "created_at": row.get("created_at", _utc_now())},
        ("as_of_date", "ticker", "quarter", "model_version"),
    )


def insert_actual_release(connection: sqlite3.Connection, row: dict[str, Any]) -> str:
    source_path = Path(str(row["source_path"]))
    return _immutable_insert(
        connection,
        "actual_releases",
        {
            **row,
            "source_sha256": sha256_file(source_path) if source_path.exists() else row.get("source_sha256"),
            "ingested_at": row.get("ingested_at", _utc_now()),
        },
        ("ticker", "quarter"),
    )


def read_table(connection: sqlite3.Connection, table: str) -> pd.DataFrame:
    allowed = {
        "consensus_vintages", "consensus_source_coverage", "forecast_snapshots", "actual_releases"
    }
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    return pd.read_sql_query(f"SELECT * FROM {table}", connection)


def write_store_metadata(connection: sqlite3.Connection, key: str, value: Any) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
        (key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
    )

