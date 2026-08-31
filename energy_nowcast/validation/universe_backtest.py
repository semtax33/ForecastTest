from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_E_AND_P_UNIVERSE = (
    "EOG", "COP", "FANG", "DVN", "EQT", "AR", "RRC",
    "MTDR", "PR", "OVV", "CNX", "SM", "MGY", "NOG",
)

LEGACY_FEATURES = ("wti_log_yoy", "henry_log_yoy", "lag_revenue_log_yoy")
CANDIDATE_FEATURES = (
    "wti_log_yoy", "henry_log_yoy", "propane_log_yoy",
    "lag_revenue_log_yoy", "lag_implied_volume_basis_log_yoy",
)


def _quarter(value: str) -> str:
    year, month = value.split(".")
    return f"{int(year)}Q{(int(month) - 1) // 3 + 1}"


def _quarter_ordinal(value: str) -> int:
    return int(pd.Period(value, freq="Q").ordinal)


def _cutoff_date(value: str, day_of_quarter: int = 61) -> pd.Timestamp:
    return pd.Period(value, freq="Q").start_time + pd.Timedelta(days=day_of_quarter - 1)


def load_e_and_p_panel(
    arcana_root: Path,
    price_path: Path,
    tickers: Iterable[str] = DEFAULT_E_AND_P_UNIVERSE,
) -> pd.DataFrame:
    normalized_dir = arcana_root / "data-lake" / "silver" / "sec" / "normalized"
    metadata_path = arcana_root / "data-lake" / "silver" / "sec" / "us_report_metadata.csv"
    metadata = pd.read_csv(metadata_path, low_memory=False)
    metadata["stock_code"] = metadata["stock_code"].astype(str).str.upper()
    metadata["fiscal_year"] = pd.to_numeric(metadata["fiscal_year"], errors="coerce")
    metadata["fiscal_month"] = pd.to_numeric(metadata["fiscal_month"], errors="coerce")
    metadata["report_date"] = pd.to_datetime(metadata["report_date"], errors="coerce")
    metadata["fiscal_quarter"] = ((metadata["fiscal_month"] - 1) // 3 + 1).astype("Int64")
    report_dates = (
        metadata.loc[metadata["stock_code"].isin(tuple(tickers))]
        .groupby(["stock_code", "fiscal_year", "fiscal_quarter"], as_index=False)["report_date"]
        .min()
        .rename(columns={"stock_code": "ticker"})
    )
    pieces: list[pd.DataFrame] = []
    for ticker in tickers:
        path = normalized_dir / f"us_normalized_{ticker}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        frame = frame.loc[frame["canonical_account_id"].eq("REVENUE")].copy()
        frame["fiscal_year"] = pd.to_numeric(frame["fiscal_year"], errors="coerce")
        frame["fiscal_quarter"] = pd.to_numeric(frame["fiscal_quarter"], errors="coerce")
        frame["cumulative_revenue"] = pd.to_numeric(frame["normalized_amount"], errors="coerce")
        frame = frame.dropna(subset=["fiscal_year", "fiscal_quarter", "cumulative_revenue"])
        frame = frame.sort_values("period").drop_duplicates(["fiscal_year", "fiscal_quarter"], keep="last")
        frame["ticker"] = ticker
        frame["quarter"] = frame["period"].astype(str).map(_quarter)
        frame["prior_cumulative"] = frame.groupby("fiscal_year")["cumulative_revenue"].shift(1)
        frame["prior_fiscal_quarter"] = frame.groupby("fiscal_year")["fiscal_quarter"].shift(1)
        consecutive = frame["prior_fiscal_quarter"].eq(frame["fiscal_quarter"] - 1)
        frame["revenue"] = np.where(
            frame["fiscal_quarter"].eq(1),
            frame["cumulative_revenue"],
            np.where(consecutive, frame["cumulative_revenue"] - frame["prior_cumulative"], np.nan),
        )
        pieces.append(frame[["ticker", "quarter", "fiscal_year", "fiscal_quarter", "revenue"]])
    panel = pd.concat(pieces, ignore_index=True)
    panel = panel.merge(report_dates, on=["ticker", "fiscal_year", "fiscal_quarter"], how="left")
    prices = pd.read_csv(price_path)
    prices["quarter"] = prices["quarter"].astype(str)
    panel = panel.merge(
        prices[["quarter", "wti_price", "henry_price", "propane_price_bbl"]],
        on="quarter",
        how="left",
    )
    panel["quarter_ordinal"] = panel["quarter"].map(_quarter_ordinal)
    panel = panel.sort_values(["ticker", "quarter_ordinal"]).reset_index(drop=True)
    for column, output in (
        ("revenue", "actual_log_yoy"),
        ("wti_price", "wti_log_yoy"),
        ("henry_price", "henry_log_yoy"),
        ("propane_price_bbl", "propane_log_yoy"),
    ):
        lagged = panel.groupby("ticker")[column].shift(4)
        panel[output] = 100.0 * np.log(panel[column] / lagged)
    panel["basket_price_log_yoy"] = (
        0.55 * panel["wti_log_yoy"]
        + 0.25 * panel["henry_log_yoy"]
        + 0.20 * panel["propane_log_yoy"]
    )
    panel["implied_volume_basis_log_yoy"] = panel["actual_log_yoy"] - panel["basket_price_log_yoy"]
    panel["lag_revenue_log_yoy"] = panel.groupby("ticker")["actual_log_yoy"].shift(1)
    panel["lag_implied_volume_basis_log_yoy"] = panel.groupby("ticker")["implied_volume_basis_log_yoy"].shift(1)
    panel["lag_report_date"] = panel.groupby("ticker")["report_date"].shift(1)
    panel["forecast_cutoff_date"] = panel["quarter"].map(_cutoff_date)
    panel["pit_feature_available"] = panel["lag_report_date"].le(panel["forecast_cutoff_date"])
    required = ["revenue", "actual_log_yoy", *CANDIDATE_FEATURES]
    panel = panel.loc[
        panel[required].notna().all(axis=1)
        & panel["revenue"].gt(0)
        & panel["pit_feature_available"]
    ].copy()
    panel["prior_year_revenue"] = panel["revenue"] / np.exp(panel["actual_log_yoy"] / 100.0)
    return panel.reset_index(drop=True)


@dataclass(frozen=True)
class PooledRidge:
    alpha: float = 8.0

    def predict(self, train: pd.DataFrame, test: pd.DataFrame, features: tuple[str, ...]) -> np.ndarray:
        x_train = train.loc[:, features].to_numpy(dtype=float)
        y_train = train["actual_log_yoy"].to_numpy(dtype=float)
        x_test = test.loc[:, features].to_numpy(dtype=float)
        means = x_train.mean(axis=0)
        scales = x_train.std(axis=0)
        scales[scales < 1e-12] = 1.0
        z_train = (x_train - means) / scales
        z_test = (x_test - means) / scales
        design = np.column_stack([np.ones(len(z_train)), z_train])
        penalty = np.eye(design.shape[1]) * self.alpha
        penalty[0, 0] = 0.0
        coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y_train)
        return np.column_stack([np.ones(len(z_test)), z_test]) @ coefficients


@dataclass(frozen=True)
class UniverseBacktester:
    alpha: float = 8.0
    test_quarters: int = 4
    minimum_train_rows: int = 40

    @property
    def model(self) -> PooledRidge:
        return PooledRidge(self.alpha)

    def _test_mask(self, panel: pd.DataFrame) -> pd.Series:
        ranks = panel.groupby("ticker")["quarter_ordinal"].rank(method="first", ascending=False)
        return ranks <= self.test_quarters

    def _calibration_residuals(
        self, train: pd.DataFrame, features: tuple[str, ...]
    ) -> np.ndarray:
        ordered = train.sort_values("quarter_ordinal")
        residuals: list[float] = []
        quarters = sorted(ordered["quarter_ordinal"].unique())
        for quarter in quarters:
            history = ordered.loc[ordered["quarter_ordinal"].lt(quarter)]
            target = ordered.loc[ordered["quarter_ordinal"].eq(quarter)]
            if len(history) < self.minimum_train_rows or target.empty:
                continue
            predictions = self.model.predict(history, target, features)
            residuals.extend((target["actual_log_yoy"].to_numpy() - predictions).tolist())
        return np.asarray(residuals, dtype=float)

    def _forecast(self, train: pd.DataFrame, test: pd.DataFrame, validation: str) -> pd.DataFrame:
        if len(train) < self.minimum_train_rows:
            return pd.DataFrame()
        result = test[[
            "ticker", "quarter", "quarter_ordinal", "actual_log_yoy", "revenue",
            "prior_year_revenue", "forecast_cutoff_date", "lag_report_date",
        ]].copy()
        result["validation"] = validation
        result["training_observations"] = len(train)
        result["legacy_prediction"] = self.model.predict(train, test, LEGACY_FEATURES)
        result["candidate_prediction"] = self.model.predict(train, test, CANDIDATE_FEATURES)
        residuals = self._calibration_residuals(train, CANDIDATE_FEATURES)
        result["calibration_observations"] = len(residuals)
        for level in (0.80, 0.95):
            label = int(level * 100)
            radius = float(np.quantile(np.abs(residuals), level)) if len(residuals) else np.nan
            result[f"lower_{label}_log_yoy"] = result["candidate_prediction"] - radius
            result[f"upper_{label}_log_yoy"] = result["candidate_prediction"] + radius
            result[f"covered_{label}"] = result["actual_log_yoy"].between(
                result[f"lower_{label}_log_yoy"], result[f"upper_{label}_log_yoy"]
            )
        result["candidate_revenue"] = result["prior_year_revenue"] * np.exp(result["candidate_prediction"] / 100.0)
        result["candidate_revenue_ape_pct"] = (
            (result["candidate_revenue"] / result["revenue"] - 1.0).abs() * 100.0
        )
        result["direction_correct"] = np.sign(result["candidate_prediction"]) == np.sign(result["actual_log_yoy"])
        return result

    def run_time_holdout(self, panel: pd.DataFrame) -> pd.DataFrame:
        test_mask = self._test_mask(panel)
        test = panel.loc[test_mask].copy()
        first_test_quarter = int(test["quarter_ordinal"].min())
        train = panel.loc[panel["quarter_ordinal"].lt(first_test_quarter)].copy()
        return self._forecast(train, test, "TIME_HOLDOUT").sort_values(["quarter_ordinal", "ticker"]).reset_index(drop=True)

    def run_loco(self, panel: pd.DataFrame) -> pd.DataFrame:
        test_mask = self._test_mask(panel)
        outputs: list[pd.DataFrame] = []
        for ticker, company_test in panel.loc[test_mask].groupby("ticker", sort=True):
            for _, target in company_test.sort_values("quarter_ordinal").iterrows():
                train = panel.loc[
                    panel["ticker"].ne(ticker)
                    & panel["quarter_ordinal"].lt(int(target["quarter_ordinal"]))
                ].copy()
                output = self._forecast(train, target.to_frame().T, "LOCO_TIME_SAFE")
                if not output.empty:
                    outputs.append(output)
        if not outputs:
            return pd.DataFrame()
        return pd.concat(outputs, ignore_index=True).sort_values(["quarter_ordinal", "ticker"]).reset_index(drop=True)

