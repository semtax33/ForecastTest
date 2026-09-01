from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ...data.cutoff import quarter_cutoff_date
from .adapters import StandardizedKPIBundle
from .taxonomy import GROUP_PRICE_WEIGHTS, group_for_ticker


COMPONENTS = ("oil", "ngl", "gas")


def _safe_log_ratio(current: float, prior: float) -> float:
    if not np.isfinite(current) or not np.isfinite(prior) or current <= 0 or prior <= 0:
        return np.nan
    return float(100.0 * np.log(current / prior))


def _period_ord(value: str) -> int:
    return int(pd.Period(value, freq="Q").ordinal)


@dataclass(frozen=True)
class V35StrategyConfig:
    cutoff_day: int = 61
    volume_history_quarters: int = 8
    partial_pooling_k: float = 8.0
    basis_clip_log_points: float = 20.0
    use_company_basis: bool = True
    gas_heavy_price_mode: str = "BENCHMARK_RATIO"
    gas_basis_history_quarters: int = 4
    gas_basis_partial_pooling_k: float = 2.0


class KPIHierarchicalStrategy:
    def __init__(
        self,
        kpis: StandardizedKPIBundle,
        revenue_panel: pd.DataFrame,
        prices: pd.DataFrame,
        config: V35StrategyConfig | None = None,
    ) -> None:
        self.kpis = kpis
        self.revenue = revenue_panel.copy()
        self.revenue["quarter"] = self.revenue["quarter"].astype(str)
        self.prices = prices.copy()
        self.prices["quarter"] = self.prices["quarter"].astype(str)
        self.config = config or V35StrategyConfig()

    def _price(self, quarter: str) -> dict[str, float] | None:
        selected = self.prices.loc[self.prices["quarter"].eq(quarter)]
        if selected.empty:
            return None
        row = selected.iloc[-1]
        return {
            "oil": float(row["wti_price"]),
            "ngl": float(row["propane_price_bbl"]),
            "gas": float(row["henry_price"]) * 6.0,
        }

    def _actual_available(self, cutoff: pd.Timestamp) -> pd.DataFrame:
        frame = self.kpis.production_actuals.copy()
        return frame.loc[
            pd.to_datetime(frame["filing_date"], errors="coerce").le(cutoff)
            & frame["total_mboed"].notna()
        ].copy()

    @staticmethod
    def _mix(row: pd.Series, ticker: str) -> dict[str, float]:
        total = float(row["total_mboed"])
        raw = {
            "oil": pd.to_numeric(row.get("oil_mbpd"), errors="coerce"),
            "ngl": pd.to_numeric(row.get("ngl_mbpd"), errors="coerce"),
            "gas": pd.to_numeric(row.get("gas_mmcfd"), errors="coerce") / 6.0,
        }
        known = {key: float(value / total) for key, value in raw.items() if np.isfinite(value) and value >= 0}
        if len(known) == 3 and 0.75 <= sum(known.values()) <= 1.25:
            scale = sum(known.values())
            return {key: value / scale for key, value in known.items()}
        fixed = GROUP_PRICE_WEIGHTS[group_for_ticker(ticker)]
        missing = [key for key in COMPONENTS if key not in known]
        remaining = max(1.0 - sum(known.values()), 0.0)
        fixed_missing = sum(fixed[key] for key in missing)
        result = known.copy()
        for key in missing:
            result[key] = remaining * fixed[key] / fixed_missing if fixed_missing else 0.0
        scale = sum(result.values())
        return {key: result[key] / scale for key in COMPONENTS}

    def _production_growth_history(
        self,
        available: pd.DataFrame,
        target: str,
    ) -> pd.DataFrame:
        target_ord = _period_ord(target)
        lookup = {
            (str(row["ticker"]), str(row["quarter"])): float(row["total_mboed"])
            for _, row in available.iterrows()
        }
        rows = []
        for _, row in available.iterrows():
            ticker = str(row["ticker"])
            quarter = str(row["quarter"])
            if _period_ord(quarter) >= target_ord:
                continue
            prior = lookup.get((ticker, str(pd.Period(quarter, freq="Q") - 4)))
            growth = _safe_log_ratio(float(row["total_mboed"]), float(prior) if prior else np.nan)
            if np.isfinite(growth) and not bool(row.get("mna_flag", False)):
                rows.append({"ticker": ticker, "group": group_for_ticker(ticker), "quarter": quarter, "growth": growth})
        return pd.DataFrame(rows)

    def _volume_growth_forecast(
        self,
        ticker: str,
        target: str,
        available: pd.DataFrame,
        excluded_ticker: str | None,
    ) -> tuple[float, int, int]:
        # LOCO removes held-company revenue labels, not public point-in-time KPI
        # covariates. Production history remains a legitimate live feature.
        history = self._production_growth_history(available, target)
        group = group_for_ticker(ticker)
        company = history.loc[history["ticker"].eq(ticker)].sort_values("quarter").tail(
            self.config.volume_history_quarters
        ) if not history.empty else pd.DataFrame()
        group_values = history.loc[history["group"].eq(group), "growth"] if not history.empty else pd.Series(dtype=float)
        group_center = float(group_values.median()) if len(group_values) else 0.0
        if company.empty:
            return group_center, 0, int(len(group_values))
        company_center = float(company["growth"].median())
        n = len(company)
        reliability = n / (n + self.config.partial_pooling_k)
        return reliability * company_center + (1.0 - reliability) * group_center, n, int(len(group_values))

    def _guidance(
        self, ticker: str, target: str, cutoff: pd.Timestamp
    ) -> pd.Series | None:
        frame = self.kpis.production_guidance
        mask = (
            frame["ticker"].eq(ticker)
            & frame["target_quarter"].astype(str).eq(target)
            & pd.to_datetime(frame["filing_date"], errors="coerce").le(cutoff)
            & frame["total_mboed_mid"].notna()
        )
        if "period_semantics" in frame:
            mask &= frame["period_semantics"].astype(str).str.startswith("QUARTERLY")
        eligible = frame.loc[mask].sort_values("filing_date")
        return None if eligible.empty else eligible.iloc[-1]

    def _realized_price_multipliers(
        self,
        ticker: str,
        target: str,
        cutoff: pd.Timestamp,
        excluded_ticker: str | None,
    ) -> dict[str, float]:
        realized = self.kpis.realized_prices.copy()
        realized = realized.loc[
            pd.to_datetime(realized["filing_date"], errors="coerce").le(cutoff)
            & realized["quarter"].map(_period_ord).lt(_period_ord(target))
        ]
        records = []
        for _, row in realized.iterrows():
            benchmark = self._price(str(row["quarter"]))
            if benchmark is None:
                continue
            record = {"ticker": row["ticker"], "group": group_for_ticker(str(row["ticker"]))}
            for component in COMPONENTS:
                value = pd.to_numeric(row.get(f"realized_{component}_price"), errors="coerce")
                record[component] = float(value / benchmark[component]) if np.isfinite(value) and value > 0 else np.nan
            records.append(record)
        history = pd.DataFrame(records)
        result: dict[str, float] = {}
        for component in COMPONENTS:
            if history.empty:
                result[component] = 1.0
                continue
            group_values = history.loc[history["group"].eq(group_for_ticker(ticker)), component].dropna()
            group_center = float(group_values.median()) if len(group_values) else 1.0
            company_values = history.loc[history["ticker"].eq(ticker), component].dropna().tail(8)
            # Realized prices are point-in-time operational covariates, so they
            # remain available in LOCO just like production filings.
            if company_values.empty:
                result[component] = group_center
            else:
                reliability = len(company_values) / (len(company_values) + self.config.partial_pooling_k)
                result[component] = reliability * float(company_values.median()) + (1.0 - reliability) * group_center
            result[component] = float(np.clip(result[component], 0.35, 1.65))
        return result

    @staticmethod
    def _driver(total: float, mix: dict[str, float], prices: dict[str, float]) -> float:
        return float(total * sum(mix[key] * prices[key] for key in COMPONENTS))

    def _actual_realized_prices(
        self,
        ticker: str,
        quarter: str,
        cutoff: pd.Timestamp,
        benchmark: dict[str, float],
    ) -> dict[str, float]:
        frame = self.kpis.realized_prices
        eligible = frame.loc[
            frame["ticker"].eq(ticker)
            & frame["quarter"].astype(str).eq(quarter)
            & pd.to_datetime(frame["filing_date"], errors="coerce").le(cutoff)
        ].sort_values("filing_date")
        if eligible.empty:
            return benchmark.copy()
        row = eligible.iloc[-1]
        result = benchmark.copy()
        for component in COMPONENTS:
            value = pd.to_numeric(row.get(f"realized_{component}_price"), errors="coerce")
            if np.isfinite(value) and value > 0:
                if (
                    component == "gas"
                    and group_for_ticker(ticker) == "gas_heavy"
                    and self.config.gas_heavy_price_mode == "REALIZED_ADDITIVE_BASIS"
                ):
                    # Normalize $/Mcf to $/BOE before combining with BOE mix.
                    value = float(value) * 6.0
                result[component] = float(value)
        return result

    def _gas_realized_basis_forecast(
        self,
        ticker: str,
        target: str,
        cutoff: pd.Timestamp,
    ) -> tuple[float, float, int, int]:
        realized = self.kpis.realized_prices.copy()
        realized = realized.loc[
            pd.to_datetime(realized["filing_date"], errors="coerce").le(cutoff)
            & realized["quarter"].map(_period_ord).lt(_period_ord(target))
            & realized["ticker"].map(group_for_ticker).eq("gas_heavy")
        ]
        rows: list[dict[str, object]] = []
        for _, row in realized.iterrows():
            value = pd.to_numeric(row.get("realized_gas_price"), errors="coerce")
            benchmark = self._price(str(row["quarter"]))
            if not np.isfinite(value) or float(value) <= 0 or benchmark is None:
                continue
            rows.append({
                "ticker": str(row["ticker"]),
                "quarter_ordinal": _period_ord(str(row["quarter"])),
                "basis_per_mcf": float(value) - benchmark["gas"] / 6.0,
            })
        history = pd.DataFrame(rows)
        if history.empty:
            return np.nan, np.nan, 0, 0
        group_values = history.sort_values("quarter_ordinal").tail(16)["basis_per_mcf"]
        group_center = float(group_values.median())
        company = history.loc[history["ticker"].eq(ticker)].sort_values(
            "quarter_ordinal"
        ).tail(self.config.gas_basis_history_quarters)
        if company.empty:
            basis = group_center
            company_n = 0
        else:
            company_n = len(company)
            reliability = company_n / (
                company_n + self.config.gas_basis_partial_pooling_k
            )
            basis = (
                reliability * float(company["basis_per_mcf"].median())
                + (1.0 - reliability) * group_center
            )
        target_benchmark = self._price(target)
        if target_benchmark is None:
            return np.nan, basis, company_n, len(group_values)
        realized_price = max(target_benchmark["gas"] / 6.0 + basis, 0.10)
        return float(realized_price), float(basis), company_n, len(group_values)

    def _basis_history(
        self,
        target: str,
        cutoff: pd.Timestamp,
        excluded_ticker: str | None = None,
    ) -> pd.DataFrame:
        available = self._actual_available(cutoff)
        revenue = self.revenue.loc[
            self.revenue["quarter_ordinal"].lt(_period_ord(target))
            & pd.to_datetime(self.revenue["report_date"], errors="coerce").le(cutoff)
        ]
        if excluded_ticker is not None:
            revenue = revenue.loc[revenue["ticker"].ne(excluded_ticker)]
        joined = available.merge(revenue[["ticker", "quarter", "revenue"]], on=["ticker", "quarter"], how="inner")
        rows = []
        for _, row in joined.iterrows():
            benchmark = self._price(str(row["quarter"]))
            if benchmark is None:
                continue
            mix = self._mix(row, str(row["ticker"]))
            realized_prices = self._actual_realized_prices(
                str(row["ticker"]), str(row["quarter"]), cutoff, benchmark
            )
            driver = self._driver(float(row["total_mboed"]), mix, realized_prices)
            if driver > 0 and float(row["revenue"]) > 0:
                rows.append({
                    "ticker": str(row["ticker"]),
                    "group": group_for_ticker(str(row["ticker"])),
                    "quarter": str(row["quarter"]),
                    "basis": float(row["revenue"]) / driver,
                })
        return pd.DataFrame(rows)

    def _basis_forecast(
        self,
        ticker: str,
        target: str,
        cutoff: pd.Timestamp,
        excluded_ticker: str | None,
    ) -> tuple[float, int, int]:
        history = self._basis_history(target, cutoff, excluded_ticker)
        if history.empty:
            return np.nan, 0, 0
        group_values = history.loc[history["group"].eq(group_for_ticker(ticker)), "basis"]
        group_center = float(group_values.median()) if len(group_values) else float(history["basis"].median())
        company = history.loc[history["ticker"].eq(ticker)].sort_values("quarter").tail(8)
        if excluded_ticker == ticker or company.empty:
            return group_center, 0, int(len(group_values))
        reliability = len(company) / (len(company) + self.config.partial_pooling_k)
        estimate = reliability * float(company["basis"].median()) + (1.0 - reliability) * group_center
        return estimate, int(len(company)), int(len(group_values))

    def predict(
        self,
        ticker: str,
        target: str,
        excluded_ticker: str | None = None,
    ) -> dict[str, object] | None:
        cutoff = quarter_cutoff_date(target, self.config.cutoff_day)
        available = self._actual_available(cutoff)
        prior_quarter = str(pd.Period(target, freq="Q") - 4)
        prior_rows = available.loc[
            available["ticker"].eq(ticker) & available["quarter"].astype(str).eq(prior_quarter)
        ]
        if prior_rows.empty:
            return None
        prior = prior_rows.sort_values("filing_date").iloc[-1]
        current_price = self._price(target)
        prior_price = self._price(prior_quarter)
        if current_price is None or prior_price is None:
            return None
        guidance = self._guidance(ticker, target, cutoff)
        growth, company_volume_n, group_volume_n = self._volume_growth_forecast(
            ticker, target, available, excluded_ticker
        )
        if guidance is not None:
            target_total = float(guidance["total_mboed_mid"])
            volume_source = "POINT_IN_TIME_GUIDANCE"
            guidance_quality = float(guidance["quality_score"])
        else:
            target_total = float(prior["total_mboed"]) * np.exp(growth / 100.0)
            volume_source = "HIERARCHICAL_VOLUME_GROWTH"
            guidance_quality = 0.70 if company_volume_n else 0.55
        prior_mix = self._mix(prior, ticker)
        target_mix = prior_mix.copy()
        if guidance is not None:
            component_guidance = {
                "oil": pd.to_numeric(guidance.get("oil_mbpd_mid"), errors="coerce"),
                "ngl": pd.to_numeric(guidance.get("ngl_mbpd_mid"), errors="coerce"),
                "gas": pd.to_numeric(guidance.get("gas_mmcfd_mid"), errors="coerce") / 6.0,
            }
            known = {key: float(value / target_total) for key, value in component_guidance.items() if np.isfinite(value) and value >= 0}
            if known and sum(known.values()) < 1.25:
                missing = [key for key in COMPONENTS if key not in known]
                remaining = max(1.0 - sum(known.values()), 0.0)
                prior_missing = sum(prior_mix[key] for key in missing)
                target_mix = known.copy()
                for key in missing:
                    target_mix[key] = remaining * prior_mix[key] / prior_missing if prior_missing else 0.0
        multipliers = self._realized_price_multipliers(ticker, target, cutoff, excluded_ticker)
        forecast_prices = {key: current_price[key] * multipliers[key] for key in COMPONENTS}
        target_driver = self._driver(target_total, target_mix, forecast_prices)
        # Use the same estimated realized-price basis on both sides of the YoY
        # ratio when the company has no parsed prior-year realized price. This
        # avoids manufacturing a price drop solely from asymmetric fallback.
        prior_price_with_basis = {
            key: prior_price[key] * multipliers[key] for key in COMPONENTS
        }
        gas_price_mode = "BENCHMARK_RATIO"
        gas_basis_per_mcf = np.nan
        forecast_realized_gas_price = np.nan
        company_gas_basis_history_n = 0
        group_gas_basis_history_n = 0
        if (
            group_for_ticker(ticker) == "gas_heavy"
            and self.config.gas_heavy_price_mode == "REALIZED_ADDITIVE_BASIS"
        ):
            (
                forecast_realized_gas_price,
                gas_basis_per_mcf,
                company_gas_basis_history_n,
                group_gas_basis_history_n,
            ) = self._gas_realized_basis_forecast(ticker, target, cutoff)
            if np.isfinite(forecast_realized_gas_price):
                gas_price_mode = "REALIZED_ADDITIVE_BASIS"
                forecast_prices["gas"] = forecast_realized_gas_price * 6.0
                prior_price_with_basis["gas"] = max(
                    prior_price["gas"] / 6.0 + gas_basis_per_mcf,
                    0.10,
                ) * 6.0
        prior_realized_prices = self._actual_realized_prices(
            ticker, prior_quarter, cutoff, prior_price_with_basis
        )
        prior_driver = self._driver(
            float(prior["total_mboed"]), prior_mix, prior_realized_prices
        )
        component_growth = _safe_log_ratio(target_driver, prior_driver)
        # The evaluation row carries the already-known prior-year revenue even
        # when the normalized SEC panel filtered the standalone target-4 row.
        # Requiring that row again creates artificial coverage gaps.
        prior_revenue = self.revenue.loc[
            self.revenue["ticker"].eq(ticker) & self.revenue["quarter"].eq(target),
            "prior_year_revenue",
        ]
        if prior_revenue.empty or not np.isfinite(component_growth):
            return None
        if not self.config.use_company_basis:
            basis_adjustment = 0.0
            company_basis_n = 0
            group_basis_n = 0
            basis_overlay_mode = "DISABLED_CLEAN_COMPONENT"
        elif excluded_ticker == ticker:
            # Held-company historical revenue basis is a revenue-derived label
            # and is forbidden in LOCO. A stable group basis implies zero YoY
            # basis adjustment while the structural component remains testable.
            basis_adjustment = 0.0
            company_basis_n = 0
            _, _, group_basis_n = self._basis_forecast(
                ticker, target, cutoff, excluded_ticker
            )
            basis_overlay_mode = "DISABLED_LOCO"
        else:
            basis_forecast, company_basis_n, group_basis_n = self._basis_forecast(
                ticker, target, cutoff, excluded_ticker
            )
            if not np.isfinite(basis_forecast):
                return None
            prior_basis = float(prior_revenue.iloc[-1]) / prior_driver if prior_driver > 0 else np.nan
            basis_adjustment = float(np.clip(
                _safe_log_ratio(basis_forecast, prior_basis),
                -self.config.basis_clip_log_points,
                self.config.basis_clip_log_points,
            ))
            basis_overlay_mode = "COMPANY_GROUP_SHRUNK"
        prediction = component_growth + basis_adjustment
        return {
            "ticker": ticker,
            "quarter": target,
            "forecast_cutoff_date": cutoff,
            "prediction_log_yoy": prediction,
            "component_growth_log_points": component_growth,
            "basis_adjustment_log_points": basis_adjustment,
            "forecast_total_mboed": target_total,
            "volume_source": volume_source,
            "guidance_quality": guidance_quality,
            "company_volume_history_n": company_volume_n,
            "group_volume_history_n": group_volume_n,
            "company_basis_history_n": company_basis_n,
            "group_basis_history_n": group_basis_n,
            "heldout_company_revenue_excluded": excluded_ticker == ticker,
            "company_basis_overlay_applied": self.config.use_company_basis and excluded_ticker != ticker,
            "basis_overlay_mode": basis_overlay_mode,
            "macro_overlay_applied": False,
            "gas_price_mode": gas_price_mode,
            "forecast_realized_gas_price": forecast_realized_gas_price,
            "gas_basis_per_mcf": gas_basis_per_mcf,
            "company_gas_basis_history_n": company_gas_basis_history_n,
            "group_gas_basis_history_n": group_gas_basis_history_n,
        }
