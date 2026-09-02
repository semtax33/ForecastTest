from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS


def _number(value: object) -> float:
    text = str(value).strip().replace(",", "").replace("$", "")
    negative = text.startswith("(") or text.endswith(")")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return np.nan
    result = float(match.group())
    return -abs(result) if negative else result


def _tokens(row: pd.Series) -> list[str]:
    values: list[str] = []
    for raw in row.tolist():
        value = str(raw).strip()
        if not value or value.lower() == "nan" or value in {"—", ""}:
            continue
        if values and value == values[-1]:
            continue
        values.append(value)
    return values


def _table_text(table: pd.DataFrame) -> str:
    return " ".join(str(value) for value in table.to_numpy().flatten()).lower()


def _release_files(ir_root: Path, reserve_year: int) -> list[Path]:
    directory = ir_root / "FANG"
    prefix = f"{reserve_year + 1}-"
    return sorted(
        path
        for path in directory.glob(f"{prefix}*.htm")
        if "_EX-99.1_" in path.name
        and any(f"{prefix}{month:02d}-" in path.name for month in (1, 2, 3))
    )


def _numeric_values(tokens: list[str]) -> list[float]:
    result = []
    for token in tokens[1:]:
        if "%" in token or "/" in token:
            continue
        value = _number(token)
        if np.isfinite(value):
            result.append(value)
    return result


def build_fang_actual_cost_mix_panel(ir_root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year in range(2021, 2026):
        selected: tuple[Path, pd.DataFrame] | None = None
        for path in _release_files(ir_root, year):
            try:
                tables = pd.read_html(path, flavor="lxml")
            except (ValueError, OSError):
                continue
            for table in tables:
                text = _table_text(table)
                if (
                    "selected operating data" in text
                    and "natural gas liquids (mbbls)" in text
                    and "gathering, processing and transportation expense" in text
                ):
                    selected = path, table
                    break
            if selected is not None:
                break
        if selected is None:
            continue
        source, table = selected
        line_map = {
            tokens[0].strip().lower(): _numeric_values(tokens)
            for _, row in table.iterrows()
            if (tokens := _tokens(row))
        }
        required = {
            "oil (mbbls)": "oil_mboe",
            "natural gas (mmcf)": "gas_mmcf",
            "natural gas liquids (mbbls)": "ngl_mboe",
            "combined volumes (mboe)(1)": "combined_mboe",
            "production and ad valorem taxes": "production_tax_per_boe",
            "gathering, processing and transportation expense": "transport_cost_per_boe",
        }
        values: dict[str, float] = {}
        for label, column in required.items():
            candidates = next(
                (numbers for key, numbers in line_map.items() if key.startswith(label)),
                [],
            )
            if len(candidates) < 3:
                break
            values[column] = float(candidates[2])
        if len(values) != len(required):
            continue
        component_total = values["oil_mboe"] + values["ngl_mboe"] + values["gas_mmcf"] / 6.0
        combined = values["combined_mboe"]
        rows.append(
            {
                "ticker": "FANG",
                "year": year,
                **values,
                "component_identity_ratio": component_total / combined,
                "oil_mix_pct": values["oil_mboe"] / combined * 100.0,
                "ngl_mix_pct": values["ngl_mboe"] / combined * 100.0,
                "gas_boe_mix_pct": values["gas_mmcf"] / 6.0 / combined * 100.0,
                "mix_method": "IR_SELECTED_OPERATING_DATA_ACTUAL_ALL_COMPONENTS",
                "cost_scope": "EXACT_REPORTED_PER_BOE_TRANSPORT_AND_PRODUCTION_TAX",
                "source_file": str(source),
                "availability_date": source.name[:10],
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def build_v16_accounting_proof(
    *,
    ir_root: Path,
    parent_annual_path: Path,
    parent_summary_path: Path,
    parent_mix_path: Path,
) -> dict[str, pd.DataFrame]:
    actual = build_fang_actual_cost_mix_panel(ir_root)
    annual = pd.read_csv(parent_annual_path)
    proof_rows: list[dict[str, object]] = []
    if not actual.empty:
        fang = annual.loc[annual["ticker"].eq("FANG")].merge(
            actual[["year", "transport_cost_per_boe", "production_tax_per_boe"]],
            on="year",
            how="inner",
            suffixes=("_v15", "_v16"),
        )
        for item in fang.itertuples(index=False):
            revenue_per_boe = float(item.upstream_revenue_per_boe)
            parent_margin = float(item.unit_reconstructed_operating_margin_pct)
            transport = float(item.transport_cost_per_boe_v16)
            v16_margin = parent_margin - transport / revenue_per_boe * 100.0
            consolidated = float(item.consolidated_operating_margin_pct)
            proof_rows.append(
                {
                    "ticker": "FANG",
                    "year": int(item.year),
                    "v15_raw_margin_gap_pct_points": float(item.raw_margin_gap_pct_points),
                    "v16_transport_cost_per_boe": transport,
                    "v16_production_tax_per_boe": float(item.production_tax_per_boe_v16),
                    "v16_unit_reconstructed_operating_margin_pct": v16_margin,
                    "consolidated_operating_margin_pct": consolidated,
                    "v16_margin_gap_pct_points": v16_margin - consolidated,
                    "v16_absolute_margin_gap_pct_points": abs(v16_margin - consolidated),
                    "transport_supplement_applied": True,
                    "hedge_adjustment_applied": False,
                    "research_only": True,
                }
            )
    fang_proof = pd.DataFrame(proof_rows)
    parent_summary = pd.read_csv(parent_summary_path).set_index("ticker")
    parent_mix = pd.read_csv(parent_mix_path).set_index("ticker")
    summary_rows: list[dict[str, object]] = []
    fang_years = len(fang_proof)
    fang_median = (
        float(fang_proof["v16_absolute_margin_gap_pct_points"].median())
        if fang_years
        else np.nan
    )
    fang_red_share = (
        float(fang_proof["v16_absolute_margin_gap_pct_points"].gt(10.0).mean())
        if fang_years
        else np.nan
    )
    fang_numeric_pass = bool(
        fang_years >= 3 and fang_median <= 5.0 and fang_red_share <= 0.25
    )
    actual_mix_ready = len(actual) >= 3 and actual["component_identity_ratio"].between(0.99, 1.01).all()
    for ticker in EP_TICKERS:
        parent = parent_summary.loc[ticker]
        if ticker == "FANG":
            cost_scope = fang_years >= 3
            perimeter_pass = fang_numeric_pass
            perimeter_gate = (
                "PASS_V16_IR_COST_SUPPLEMENT_RECONCILIATION"
                if perimeter_pass
                else "REVIEW_V16_IR_COST_SUPPLEMENT_ANNUAL_GAPS"
                if cost_scope
                else "LOCKED_FEWER_THAN_3_EXACT_IR_COST_YEARS"
            )
            mix_ready = actual_mix_ready
            median_gap = fang_median
            hedge_clear = False
            blocker = "DERIVATIVE_PRESENTATION_AND_2025_MARGIN_GAP_REMAIN_UNPROVEN"
        else:
            cost_scope = str(parent["v14_cost_scope_status"]) == (
                "COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK"
            )
            perimeter_gate = str(parent["accounting_perimeter_reconciliation_gate"])
            perimeter_pass = perimeter_gate == "PASS_RESEARCH_PERIMETER_RECONCILIATION"
            mix_ready = bool(parent_mix.loc[ticker, "actual_mix_ready"])
            median_gap = float(parent["median_absolute_raw_margin_gap_pct_points"])
            hedge_clear = "HEDGE_PRESENTATION_NOT_PROVEN" not in perimeter_gate
            if ticker == "AR":
                blocker = "TRANSPORT_AND_PRODUCTION_TAX_SCOPE_NOT_PROVEN"
            elif ticker == "CNX":
                blocker = "HEDGE_PRESENTATION_NOT_PROVEN"
            else:
                blocker = "COMPANY_ACCOUNTING_PERIMETER_NOT_RECONCILED"
        summary_rows.append(
            {
                "ticker": ticker,
                "complete_standardized_cost_scope": cost_scope,
                "accounting_perimeter_pass": perimeter_pass,
                "accounting_perimeter_gate": perimeter_gate,
                "median_absolute_margin_gap_pct_points": median_gap,
                "actual_three_component_mix_ready": mix_ready,
                "hedge_presentation_proven": hedge_clear,
                "primary_accounting_blocker": blocker,
                "terminal_anchor_ready": False,
                "research_only": True,
            }
        )
    return {
        "fang_actual_cost_mix_panel": actual,
        "fang_v16_accounting_reconciliation": fang_proof,
        "v16_accounting_proof_summary": pd.DataFrame(summary_rows),
    }
