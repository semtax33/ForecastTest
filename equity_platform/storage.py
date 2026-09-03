from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .domain import ForecastSnapshot


SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


class LiveForwardStore:
    def __init__(self, path: Path):
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> "LiveForwardStore":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.connection is None:
            return
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()
        self.connection = None

    def _db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("LiveForwardStore must be used as a context manager")
        return self.connection

    def _initialize(self) -> None:
        self._db().executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS forecast_snapshots (
                forecast_as_of TEXT NOT NULL,
                model_version TEXT NOT NULL,
                sector TEXT NOT NULL,
                subindustry TEXT NOT NULL,
                ticker TEXT NOT NULL,
                target_period TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                revenue_forecast_usd REAL,
                ebit_forecast_usd REAL,
                margin_forecast_pct REAL,
                fcff_forecast_usd REAL,
                roic_forecast_pct REAL,
                forward_dcf_value_per_share REAL,
                reverse_dcf_metric TEXT,
                reverse_dcf_value REAL,
                expectations_gap_pct REAL,
                consensus_value_usd REAL,
                consensus_as_of TEXT,
                source_manifest_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (forecast_as_of, ticker, target_period, model_version)
            );
            CREATE TABLE IF NOT EXISTS consensus_vintages (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                target_period TEXT NOT NULL,
                provider TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (
                    as_of_date, ticker, target_period, provider, metric, source_hash
                )
            );
            CREATE TABLE IF NOT EXISTS actual_outcomes (
                ticker TEXT NOT NULL,
                target_period TEXT NOT NULL,
                release_date TEXT NOT NULL,
                actual_revenue_usd REAL,
                actual_ebit_usd REAL,
                actual_fcff_usd REAL,
                actual_roic_pct REAL,
                market_price REAL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (ticker, target_period, release_date, source_hash)
            );
            CREATE TABLE IF NOT EXISTS error_attributions (
                forecast_as_of TEXT NOT NULL,
                model_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                target_period TEXT NOT NULL,
                actual_release_date TEXT NOT NULL,
                revenue_error_pct REAL,
                ebit_error_pct REAL,
                margin_error_pct_points REAL,
                fcff_error_pct REAL,
                roic_error_pct_points REAL,
                valuation_error_pct REAL,
                attribution_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (forecast_as_of, ticker, target_period, model_version)
            );
            """
        )
        self._db().execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )

    def _insert_immutable(
        self,
        table: str,
        row: dict[str, Any],
        key_columns: tuple[str, ...],
    ) -> str:
        payload = {key: _clean(value) for key, value in row.items()}
        where = " AND ".join(f"{column} = ?" for column in key_columns)
        key = tuple(payload[column] for column in key_columns)
        existing = self._db().execute(
            f"SELECT * FROM {table} WHERE {where}", key
        ).fetchone()
        if existing is not None:
            ignored = {"created_at"}
            comparable = {
                column: existing[column]
                for column in payload
                if column not in ignored
            }
            proposed = {
                column: value
                for column, value in payload.items()
                if column not in ignored
            }
            if comparable != proposed:
                raise RuntimeError(
                    f"Immutable {table} row already exists with different values: {key}"
                )
            return "UNCHANGED"
        columns = tuple(payload)
        placeholders = ",".join("?" for _ in columns)
        self._db().execute(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
            tuple(payload[column] for column in columns),
        )
        return "INSERTED"

    def add_snapshot(self, snapshot: ForecastSnapshot) -> str:
        return self._insert_immutable(
            "forecast_snapshots",
            {**snapshot.as_row(), "created_at": _utc_now()},
            ("forecast_as_of", "ticker", "target_period", "model_version"),
        )

    def add_consensus(self, row: dict[str, Any]) -> str:
        return self._insert_immutable(
            "consensus_vintages",
            {**row, "created_at": row.get("created_at", _utc_now())},
            ("as_of_date", "ticker", "target_period", "provider", "metric", "source_hash"),
        )

    def add_actual(self, row: dict[str, Any]) -> str:
        return self._insert_immutable(
            "actual_outcomes",
            {**row, "created_at": row.get("created_at", _utc_now())},
            ("ticker", "target_period", "release_date", "source_hash"),
        )

    def settle_available(self) -> pd.DataFrame:
        pairs = pd.read_sql_query(
            """
            SELECT s.*, a.release_date, a.actual_revenue_usd, a.actual_ebit_usd,
                   a.actual_fcff_usd, a.actual_roic_pct, a.market_price
            FROM forecast_snapshots s
            JOIN actual_outcomes a
              ON s.ticker = a.ticker AND s.target_period = a.target_period
            WHERE a.release_date > s.forecast_as_of
            ORDER BY s.forecast_as_of, s.ticker, a.release_date
            """,
            self._db(),
        )
        if pairs.empty:
            return pairs
        pairs = pairs.drop_duplicates(
            ["forecast_as_of", "ticker", "target_period", "model_version"],
            keep="first",
        )
        results: list[dict[str, Any]] = []
        for row in pairs.to_dict("records"):
            actual_margin = (
                row["actual_ebit_usd"] / row["actual_revenue_usd"] * 100.0
                if row["actual_revenue_usd"] not in (None, 0)
                and row["actual_ebit_usd"] is not None
                else None
            )
            attribution = {
                "forecast_as_of": row["forecast_as_of"],
                "model_version": row["model_version"],
                "ticker": row["ticker"],
                "target_period": row["target_period"],
                "actual_release_date": row["release_date"],
                "revenue_error_pct": _percentage_error(
                    row["revenue_forecast_usd"], row["actual_revenue_usd"]
                ),
                "ebit_error_pct": _percentage_error(
                    row["ebit_forecast_usd"], row["actual_ebit_usd"]
                ),
                "margin_error_pct_points": _difference(
                    row["margin_forecast_pct"], actual_margin
                ),
                "fcff_error_pct": _percentage_error(
                    row["fcff_forecast_usd"], row["actual_fcff_usd"]
                ),
                "roic_error_pct_points": _difference(
                    row["roic_forecast_pct"], row["actual_roic_pct"]
                ),
                "valuation_error_pct": _percentage_error(
                    row["forward_dcf_value_per_share"], row["market_price"]
                ),
                "attribution_status": "SETTLED_FROM_POST_FORECAST_ACTUAL",
                "created_at": _utc_now(),
            }
            self._insert_immutable(
                "error_attributions",
                attribution,
                ("forecast_as_of", "ticker", "target_period", "model_version"),
            )
            results.append(attribution)
        return pd.DataFrame(results)

    def table(self, name: str) -> pd.DataFrame:
        allowed = {
            "forecast_snapshots",
            "consensus_vintages",
            "actual_outcomes",
            "error_attributions",
            "metadata",
        }
        if name not in allowed:
            raise ValueError(f"Unsupported table: {name}")
        return pd.read_sql_query(f"SELECT * FROM {name}", self._db())


def _percentage_error(forecast: Any, actual: Any) -> float | None:
    if forecast is None or actual in (None, 0):
        return None
    return (float(forecast) / float(actual) - 1.0) * 100.0


def _difference(forecast: Any, actual: Any) -> float | None:
    if forecast is None or actual is None:
        return None
    return float(forecast) - float(actual)
