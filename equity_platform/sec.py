from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd


class CompanyFactsReader:
    def __init__(self, path: Path):
        self.path = path
        self.payload = json.loads(path.read_text(encoding="utf-8"))

    @property
    def entity_name(self) -> str:
        return str(self.payload.get("entityName", ""))

    def annual_flow(
        self,
        concepts: Iterable[str],
        value_name: str,
        cutoff: pd.Timestamp,
        namespace: str = "us-gaap",
        unit: str = "USD",
    ) -> pd.DataFrame:
        candidates = self._candidates(concepts, namespace, unit, cutoff)
        if candidates.empty:
            return self._empty(value_name)
        duration = (candidates["end"] - candidates["start"]).dt.days + 1
        candidates = candidates.loc[
            candidates["start"].notna()
            & duration.between(330, 380)
        ].copy()
        return self._select_annual(candidates, value_name)

    def annual_instant(
        self,
        concepts: Iterable[str],
        value_name: str,
        cutoff: pd.Timestamp,
        namespace: str = "us-gaap",
        unit: str = "USD",
    ) -> pd.DataFrame:
        candidates = self._candidates(concepts, namespace, unit, cutoff)
        if candidates.empty:
            return self._empty(value_name)
        candidates = candidates.loc[candidates["start"].isna()].copy()
        return self._select_annual(candidates, value_name)

    def _candidates(
        self,
        concepts: Iterable[str],
        namespace: str,
        unit: str,
        cutoff: pd.Timestamp,
    ) -> pd.DataFrame:
        parts: list[pd.DataFrame] = []
        facts = self.payload.get("facts", {}).get(namespace, {})
        for priority, concept in enumerate(concepts):
            payload = facts.get(concept, {})
            rows = payload.get("units", {}).get(unit, [])
            if not rows:
                continue
            frame = pd.DataFrame(rows)
            frame["concept"] = concept
            frame["concept_priority"] = priority
            parts.append(frame)
        if not parts:
            return pd.DataFrame()
        result = pd.concat(parts, ignore_index=True, sort=False)
        for column in ("start", "end", "filed"):
            if column not in result:
                result[column] = pd.NaT
            result[column] = pd.to_datetime(result[column], errors="coerce")
        result["val"] = pd.to_numeric(result.get("val"), errors="coerce")
        result = result.loc[
            result["form"].astype(str).isin(("10-K", "10-K/A"))
            & result["end"].notna()
            & result["filed"].notna()
            & result["filed"].le(pd.Timestamp(cutoff).normalize())
            & result["val"].notna()
        ].copy()
        numeric_fy = pd.to_numeric(result.get("fy"), errors="coerce")
        result["fiscal_year"] = numeric_fy.fillna(result["end"].dt.year).astype(int)
        result["source_path"] = str(self.path.resolve())
        return result

    @staticmethod
    def _empty(value_name: str) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "fiscal_year",
                value_name,
                f"{value_name}_available_at",
                f"{value_name}_source_concept",
                f"{value_name}_source_path",
            ]
        )

    def _select_annual(
        self, candidates: pd.DataFrame, value_name: str
    ) -> pd.DataFrame:
        if candidates.empty:
            return self._empty(value_name)
        selected = (
            candidates.sort_values(
                ["fiscal_year", "concept_priority", "filed", "end", "accn"],
                ascending=[True, True, True, False, True],
            )
            .drop_duplicates("fiscal_year", keep="first")
            .rename(
                columns={
                    "val": value_name,
                    "filed": f"{value_name}_available_at",
                    "concept": f"{value_name}_source_concept",
                    "source_path": f"{value_name}_source_path",
                }
            )
        )
        return selected[
            [
                "fiscal_year",
                value_name,
                f"{value_name}_available_at",
                f"{value_name}_source_concept",
                f"{value_name}_source_path",
            ]
        ].reset_index(drop=True)
