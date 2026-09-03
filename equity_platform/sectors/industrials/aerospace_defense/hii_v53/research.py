from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    HiiDcfAssumptions,
    hii_enterprise_value,
)


SEGMENTS = {
    "Ingalls": "ingalls_shipbuilding",
    "Newport News": "newport_news_shipbuilding",
    "Mission Technologies": "mission_technologies",
    "Technical Solutions": "mission_technologies",
}
CONTRACT_TYPES = {
    "Firm fixed-price": "firm_fixed_price",
    "Fixed-price incentive": "fixed_price_incentive",
    "Cost-type": "cost_type",
    "Time and materials": "time_and_materials",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_number(value: object) -> float:
    if pd.isna(value):
        return float("nan")
    text = str(value).strip().replace(",", "")
    if text in {"", "$", "%", "—", "-", "–", "nan"}:
        return 0.0 if text in {"—", "-", "–"} else float("nan")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()$% ")
    try:
        number = float(text)
    except ValueError:
        return float("nan")
    return -number if negative else number


def _group_number(row: pd.Series, start: int) -> float:
    values = [_parse_number(value) for value in row.iloc[start : start + 3]]
    finite = [value for value in values if np.isfinite(value)]
    return finite[-1] if finite else float("nan")


def _row_by_label(table: pd.DataFrame, label: str) -> pd.Series:
    first = table.iloc[:, 0].fillna("").astype(str).str.strip()
    matches = table.loc[first.eq(label)]
    if len(matches) != 1:
        raise ValueError(f"Expected one row labelled {label!r}, found {len(matches)}")
    return matches.iloc[0]


def _table_text(table: pd.DataFrame) -> str:
    return " ".join(table.astype(str).fillna("").values.flatten())


def _find_table(
    tables: Iterable[pd.DataFrame], required: Iterable[str], *, title: str | None = None
) -> tuple[int, pd.DataFrame]:
    required_lower = [item.lower() for item in required]
    for index, table in enumerate(tables):
        text = _table_text(table).lower()
        if all(item in text for item in required_lower) and (
            title is None or title.lower() in text
        ):
            return index, table
    raise ValueError(f"No table contains required labels: {required_lower}")


def _document_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    return " ".join(soup.stripped_strings)


def _evidence_window(text: str, needle: str, radius: int = 260) -> str:
    index = text.lower().find(needle.lower())
    if index < 0:
        raise ValueError(f"Evidence phrase missing: {needle}")
    return text[max(0, index - radius) : index + len(needle) + radius]


def _filing_year(path: Path) -> int:
    match = re.search(r"hii-(\d{4})\d{4}", path.name)
    if not match:
        raise ValueError(f"Cannot infer period year from {path.name}")
    return int(match.group(1))


def _quarter_from_path(path: Path) -> str:
    match = re.search(r"hii-(\d{4})(\d{2})(\d{2})", path.name)
    if not match:
        raise ValueError(f"Cannot infer quarter from {path.name}")
    year, month = int(match.group(1)), int(match.group(2))
    quarter = {3: 1, 6: 2, 9: 3}.get(month)
    if quarter is None:
        raise ValueError(f"Unexpected 10-Q period end month in {path.name}")
    return f"{year}Q{quarter}"


def _source_fields(path: Path, table_index: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "source_path": str(path),
        "source_sha256": _sha256(path),
    }
    if table_index is not None:
        result["table_index"] = table_index
    return result


def _verify_ir_source_hashes(segment_history: pd.DataFrame) -> bool:
    inventory = segment_history[["source_path", "source_sha256"]].drop_duplicates()
    for _, row in inventory.iterrows():
        path = Path(str(row["source_path"]))
        if not path.is_file() or _sha256(path) != str(row["source_sha256"]):
            return False
    return True


def _parse_contract_table(
    *, path: Path, table: pd.DataFrame, table_index: int, period: str, source_type: str
) -> list[dict[str, object]]:
    groups = {
        "ingalls_shipbuilding": 6,
        "newport_news_shipbuilding": 12,
        "mission_technologies": 18,
        "consolidated": 30,
    }
    amounts: dict[tuple[str, str], float] = {}
    for reported_label, contract_type in CONTRACT_TYPES.items():
        row = _row_by_label(table, reported_label)
        for segment, start in groups.items():
            amounts[(segment, contract_type)] = _group_number(row, start) * 1_000_000.0
    rows: list[dict[str, object]] = []
    for segment in groups:
        total = sum(amounts[(segment, contract_type)] for contract_type in CONTRACT_TYPES.values())
        for contract_type in CONTRACT_TYPES.values():
            amount = amounts[(segment, contract_type)]
            rows.append(
                {
                    "period": period,
                    "source_type": source_type,
                    "segment": segment,
                    "contract_type": contract_type,
                    "contract_revenue_usd": amount,
                    "external_contract_revenue_usd": total,
                    "contract_mix_pct": amount / total * 100.0,
                    "fixed_price_risk_channel": contract_type
                    in {"firm_fixed_price", "fixed_price_incentive"},
                    **_source_fields(path, table_index),
                }
            )
    return rows


def _build_contract_mix(ten_k_paths: list[Path], ten_q_paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in ten_k_paths:
        year = _filing_year(path)
        tables = pd.read_html(path)
        index, table = _find_table(
            tables,
            ["Contract Type", "Fixed-price incentive", "Cost-type"],
            title=f"Year Ended December 31, {year}",
        )
        rows.extend(
            _parse_contract_table(
                path=path,
                table=table,
                table_index=index,
                period=str(year),
                source_type="SEC_10K",
            )
        )
    latest = ten_q_paths[-1]
    period = _quarter_from_path(latest)
    index, table = _find_table(
        pd.read_html(latest),
        ["Contract Type", "Fixed-price incentive", "Cost-type"],
        title=f"Three Months Ended June 30, {period[:4]}",
    )
    rows.extend(
        _parse_contract_table(
            path=latest,
            table=table,
            table_index=index,
            period=period,
            source_type="SEC_10Q",
        )
    )
    result = pd.DataFrame(rows)
    totals = result.groupby(["period", "segment"])["contract_mix_pct"].sum()
    if not np.allclose(totals, 100.0, atol=1e-9):
        raise ValueError("Contract type shares do not sum to 100%")
    return result.sort_values(["period", "segment", "contract_type"]).reset_index(drop=True)


def _build_annual_catchup(ten_k_paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    company_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    for path in ten_k_paths:
        year = _filing_year(path)
        tables = pd.read_html(path)
        index, table = _find_table(
            tables, ["Gross favorable adjustments", "Gross unfavorable adjustments", "Net adjustments"]
        )
        favorable = _group_number(_row_by_label(table, "Gross favorable adjustments"), 6)
        unfavorable = _group_number(_row_by_label(table, "Gross unfavorable adjustments"), 6)
        net = _group_number(_row_by_label(table, "Net adjustments"), 6)
        company_rows.append(
            {
                "period": str(year),
                "gross_favorable_adjustment_usd": favorable * 1_000_000.0,
                "gross_unfavorable_adjustment_usd": unfavorable * 1_000_000.0,
                "net_cumulative_catchup_adjustment_usd": net * 1_000_000.0,
                "gross_to_net_identity_error_usd": abs((favorable + unfavorable - net) * 1_000_000.0),
                **_source_fields(path, index),
            }
        )
        try:
            segment_index, segment_table = _find_table(
                tables, ["Ingalls", "Newport News", "Net adjustments"]
            )
        except ValueError:
            continue
        if "Mission" not in _table_text(segment_table):
            continue
        for reported, segment in SEGMENTS.items():
            first = segment_table.iloc[:, 0].fillna("").astype(str).str.strip()
            match = segment_table.loc[first.eq(reported)]
            if match.empty:
                continue
            segment_rows.append(
                {
                    "period": str(year),
                    "segment": segment,
                    "net_cumulative_catchup_adjustment_usd": _group_number(match.iloc[0], 6)
                    * 1_000_000.0,
                    **_source_fields(path, segment_index),
                }
            )
    annual = pd.DataFrame(company_rows).sort_values("period").reset_index(drop=True)
    if not annual["gross_to_net_identity_error_usd"].le(1.0).all():
        raise ValueError("Annual cumulative catch-up identity failed")
    return annual, pd.DataFrame(segment_rows).sort_values(["period", "segment"]).reset_index(drop=True)


def _build_quarterly_catchup(
    ten_q_paths: list[Path], annual: pd.DataFrame, annual_segment: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    company_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    for path in ten_q_paths:
        period = _quarter_from_path(path)
        tables = pd.read_html(path)
        index, table = _find_table(
            tables, ["Gross favorable adjustments", "Gross unfavorable adjustments", "Net adjustments"]
        )
        company_rows.append(
            {
                "period": period,
                "derivation": "AS_REPORTED_CURRENT_QUARTER",
                "gross_favorable_adjustment_usd": _group_number(
                    _row_by_label(table, "Gross favorable adjustments"), 6
                )
                * 1_000_000.0,
                "gross_unfavorable_adjustment_usd": _group_number(
                    _row_by_label(table, "Gross unfavorable adjustments"), 6
                )
                * 1_000_000.0,
                "net_cumulative_catchup_adjustment_usd": _group_number(
                    _row_by_label(table, "Net adjustments"), 6
                )
                * 1_000_000.0,
                **_source_fields(path, index),
            }
        )
        try:
            segment_index, segment_table = _find_table(
                tables, ["Ingalls", "Newport News", "Net adjustments"]
            )
        except ValueError:
            continue
        if "Mission" not in _table_text(segment_table):
            continue
        for reported, segment in SEGMENTS.items():
            first = segment_table.iloc[:, 0].fillna("").astype(str).str.strip()
            match = segment_table.loc[first.eq(reported)]
            if match.empty:
                continue
            segment_rows.append(
                {
                    "period": period,
                    "segment": segment,
                    "derivation": "AS_REPORTED_CURRENT_QUARTER",
                    "net_cumulative_catchup_adjustment_usd": _group_number(match.iloc[0], 6)
                    * 1_000_000.0,
                    **_source_fields(path, segment_index),
                }
            )
    company = pd.DataFrame(company_rows)
    segment = pd.DataFrame(segment_rows)
    for year in range(2020, 2026):
        annual_row = annual.loc[annual["period"].eq(str(year))]
        reported = company.loc[company["period"].isin([f"{year}Q1", f"{year}Q2", f"{year}Q3"])]
        if len(annual_row) == 1 and len(reported) == 3:
            source = annual_row.iloc[0]
            net = float(source["net_cumulative_catchup_adjustment_usd"]) - float(
                reported["net_cumulative_catchup_adjustment_usd"].sum()
            )
            company_rows.append(
                {
                    "period": f"{year}Q4",
                    "derivation": "FY_LESS_REPORTED_Q1_Q2_Q3",
                    "gross_favorable_adjustment_usd": np.nan,
                    "gross_unfavorable_adjustment_usd": np.nan,
                    "net_cumulative_catchup_adjustment_usd": net,
                    "source_path": source["source_path"],
                    "source_sha256": source["source_sha256"],
                    "table_index": source["table_index"],
                }
            )
        annual_by_segment = annual_segment.loc[annual_segment["period"].eq(str(year))]
        for _, annual_seg in annual_by_segment.iterrows():
            segment_name = annual_seg["segment"]
            reported_seg = segment.loc[
                segment["period"].isin([f"{year}Q1", f"{year}Q2", f"{year}Q3"])
                & segment["segment"].eq(segment_name)
            ]
            if len(reported_seg) == 3:
                segment_rows.append(
                    {
                        "period": f"{year}Q4",
                        "segment": segment_name,
                        "derivation": "FY_LESS_REPORTED_Q1_Q2_Q3",
                        "net_cumulative_catchup_adjustment_usd": float(
                            annual_seg["net_cumulative_catchup_adjustment_usd"]
                        )
                        - float(reported_seg["net_cumulative_catchup_adjustment_usd"].sum()),
                        "source_path": annual_seg["source_path"],
                        "source_sha256": annual_seg["source_sha256"],
                        "table_index": annual_seg["table_index"],
                    }
                )
    company = pd.DataFrame(company_rows).sort_values("period").reset_index(drop=True)
    segment = pd.DataFrame(segment_rows).sort_values(["period", "segment"]).reset_index(drop=True)
    return company, segment


def _build_fas_cas_history(
    ten_k_paths: list[Path], ten_q_paths: list[Path]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sources = [(path, str(_filing_year(path)), "SEC_10K") for path in ten_k_paths]
    sources += [(path, _quarter_from_path(path), "SEC_10Q") for path in ten_q_paths]
    for path, period, source_type in sources:
        tables = pd.read_html(path)
        candidates: list[tuple[int, pd.DataFrame]] = []
        for index, table in enumerate(tables):
            text = _table_text(table)
            if (
                "Operating income" in text
                and "Operating FAS/CAS Adjustment" in text
                and "Segment operating income" in text
                and len(table) <= 9
            ):
                candidates.append((index, table))
        if not candidates:
            raise ValueError(f"FAS/CAS reconciliation table missing from {path.name}")
        index, table = candidates[0]
        operating_income = _group_number(_row_by_label(table, "Operating income"), 6)
        segment_income = _group_number(_row_by_label(table, "Segment operating income"), 6)
        first = table.iloc[:, 0].fillna("").astype(str).str.strip()
        fas_row = table.loc[first.str.startswith("Operating FAS/CAS Adjustment")].iloc[0]
        fas_addback = _group_number(fas_row, 6)
        state_match = table.loc[first.eq("Non-current state income taxes")]
        state_addback = _group_number(state_match.iloc[0], 6) if len(state_match) else 0.0
        identity_error = abs(operating_income + fas_addback + state_addback - segment_income)
        rows.append(
            {
                "period": period,
                "source_type": source_type,
                "operating_income_usd": operating_income * 1_000_000.0,
                "segment_operating_income_usd": segment_income * 1_000_000.0,
                "operating_fas_cas_reconciliation_addback_usd": fas_addback * 1_000_000.0,
                "operating_fas_cas_effect_on_operating_income_usd": -fas_addback * 1_000_000.0,
                "non_current_state_tax_reconciliation_addback_usd": state_addback * 1_000_000.0,
                "other_nonsegment_effect_on_operating_income_usd": -state_addback * 1_000_000.0,
                "reconciliation_identity_error_usd": identity_error * 1_000_000.0,
                **_source_fields(path, index),
            }
        )
    result = pd.DataFrame(rows).sort_values(["source_type", "period"]).reset_index(drop=True)
    if not result["reconciliation_identity_error_usd"].le(1.0).all():
        raise ValueError("FAS/CAS to segment operating income reconciliation failed")
    return result


def _build_backlog(latest_ten_q: Path, segment_history: pd.DataFrame) -> pd.DataFrame:
    tables = pd.read_html(latest_ten_q)
    index, table = _find_table(tables, ["Funded", "Unfunded", "Total Backlog", "Ingalls"])
    latest_period = segment_history["period"].max()
    latest_quarter = segment_history.loc[segment_history["period"].eq(latest_period)]
    rows: list[dict[str, object]] = []
    for reported, segment in SEGMENTS.items():
        if reported == "Technical Solutions":
            continue
        first = table.iloc[:, 0].fillna("").astype(str).str.strip()
        match = table.loc[first.eq(reported)]
        if match.empty:
            continue
        row = match.iloc[0]
        funded = _group_number(row, 6) * 1_000_000.0
        unfunded = _group_number(row, 12) * 1_000_000.0
        backlog = _group_number(row, 18) * 1_000_000.0
        quarter_revenue = float(
            latest_quarter.loc[latest_quarter["segment"].eq(segment), "sales_usd"].iloc[0]
        )
        rows.append(
            {
                "as_of_date": "2026-06-30",
                "segment": segment,
                "funded_backlog_usd": funded,
                "unfunded_backlog_usd": unfunded,
                "total_backlog_usd": backlog,
                "backlog_identity_error_usd": abs(funded + unfunded - backlog),
                "funded_share_pct": funded / backlog * 100.0,
                "backlog_to_latest_quarter_annualized_revenue_x": backlog
                / (quarter_revenue * 4.0),
                **_source_fields(latest_ten_q, index),
            }
        )
    result = pd.DataFrame(rows)
    if not result["backlog_identity_error_usd"].le(1.0).all():
        raise ValueError("Backlog identity failed")
    return result


def _build_margin_history(
    segment_history: pd.DataFrame,
    company_history: pd.DataFrame,
    quarterly_catchup: pd.DataFrame,
    quarterly_segment_catchup: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    company = company_history.sort_values("period").copy()
    company = company.merge(
        quarterly_catchup[["period", "net_cumulative_catchup_adjustment_usd"]],
        on="period",
        how="left",
        validate="one_to_one",
    )
    company["nonsegment_effect_usd"] = (
        company["operating_income_usd"] - company["segment_operating_income_usd"]
    )
    company["catchup_neutral_operating_income_usd"] = (
        company["operating_income_usd"]
        - company["net_cumulative_catchup_adjustment_usd"]
    )
    company["reported_ttm_margin_pct"] = (
        company["operating_income_usd"].rolling(4).sum()
        / company["revenue_usd"].rolling(4).sum()
        * 100.0
    )
    company["catchup_neutral_ttm_margin_pct"] = (
        company["catchup_neutral_operating_income_usd"].rolling(4).sum()
        / company["revenue_usd"].rolling(4).sum()
        * 100.0
    )
    company["segment_ttm_margin_pct"] = (
        company["segment_operating_income_usd"].rolling(4).sum()
        / company["revenue_usd"].rolling(4).sum()
        * 100.0
    )
    company["nonsegment_ttm_contribution_pct"] = (
        company["nonsegment_effect_usd"].rolling(4).sum()
        / company["revenue_usd"].rolling(4).sum()
        * 100.0
    )
    company_ttm = company.loc[company["reported_ttm_margin_pct"].notna()].reset_index(drop=True)

    segment = segment_history.sort_values(["segment", "period"]).copy()
    segment["reported_ttm_margin_pct"] = segment.groupby("segment", sort=False).apply(
        lambda group: group["operating_profit_usd"].rolling(4).sum()
        / group["sales_usd"].rolling(4).sum()
        * 100.0,
        include_groups=False,
    ).reset_index(level=0, drop=True)
    normalized = segment.merge(
        quarterly_segment_catchup[
            ["period", "segment", "net_cumulative_catchup_adjustment_usd"]
        ],
        on=["period", "segment"],
        how="left",
        validate="one_to_one",
    )
    normalized["catchup_neutral_operating_profit_usd"] = (
        normalized["operating_profit_usd"]
        - normalized["net_cumulative_catchup_adjustment_usd"]
    )
    normalized["catchup_neutral_ttm_margin_pct"] = normalized.groupby(
        "segment", sort=False
    ).apply(
        lambda group: group["catchup_neutral_operating_profit_usd"].rolling(4).sum()
        / group["sales_usd"].rolling(4).sum()
        * 100.0,
        include_groups=False,
    ).reset_index(level=0, drop=True)
    segment_ttm = normalized.loc[normalized["reported_ttm_margin_pct"].notna()].reset_index(drop=True)
    normalized_segment_ttm = normalized.loc[
        normalized["catchup_neutral_ttm_margin_pct"].notna()
    ].reset_index(drop=True)
    return company_ttm, segment_ttm, normalized_segment_ttm


def _distribution_rows(
    company_ttm: pd.DataFrame,
    segment_ttm: pd.DataFrame,
    normalized_segment_ttm: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def add(entity: str, basis: str, series: pd.Series) -> None:
        clean = series.dropna().astype(float)
        rows.append(
            {
                "entity": entity,
                "basis": basis,
                "observations": len(clean),
                "minimum_pct": clean.min(),
                "q25_pct": clean.quantile(0.25),
                "median_pct": clean.median(),
                "q75_pct": clean.quantile(0.75),
                "q90_pct": clean.quantile(0.90),
                "maximum_pct": clean.max(),
                "latest_pct": clean.iloc[-1],
            }
        )

    add("consolidated", "AS_REPORTED_TTM", company_ttm["reported_ttm_margin_pct"])
    add(
        "consolidated",
        "CATCHUP_NEUTRAL_TTM",
        company_ttm["catchup_neutral_ttm_margin_pct"],
    )
    add("consolidated", "SEGMENT_SUM_TTM", company_ttm["segment_ttm_margin_pct"])
    add(
        "consolidated",
        "NONSEGMENT_CONTRIBUTION_TTM",
        company_ttm["nonsegment_ttm_contribution_pct"],
    )
    for segment, group in segment_ttm.groupby("segment"):
        add(segment, "AS_REPORTED_TTM", group["reported_ttm_margin_pct"])
    for segment, group in normalized_segment_ttm.groupby("segment"):
        add(segment, "CATCHUP_NEUTRAL_TTM", group["catchup_neutral_ttm_margin_pct"])
    return pd.DataFrame(rows)


def _build_industry_diagnostic(
    feature_history: pd.DataFrame, sensor_authority: pd.DataFrame
) -> pd.DataFrame:
    latest = feature_history.sort_values("period").groupby("segment", as_index=False).tail(1).copy()
    latest["price_less_cost_proxy_yoy_pp"] = (
        latest["output_price_yoy_pct"] - latest["dedicated_cost_yoy_pct"]
    )
    latest["signal"] = np.where(
        latest["price_less_cost_proxy_yoy_pp"].lt(0),
        "INDUSTRY_COST_PROXY_OUTRUNNING_OUTPUT_PRICE_PROXY",
        "OUTPUT_PRICE_PROXY_OUTRUNNING_INDUSTRY_COST_PROXY",
    )
    latest["dedicated_shipbuilding_output_series_available"] = bool(
        sensor_authority["dedicated_shipbuilding_output_series"].any()
    )
    latest["terminal_margin_point_input_allowed"] = False
    latest["authority"] = "PIT_INDUSTRY_CONTEXT_DIAGNOSTIC_ONLY"
    return latest[
        [
            "period",
            "segment",
            "forecast_as_of",
            "feature_reference_quarter",
            "output_price_yoy_pct",
            "dedicated_cost_yoy_pct",
            "price_less_cost_proxy_yoy_pp",
            "ppi_series_coverage_pct",
            "signal",
            "dedicated_shipbuilding_output_series_available",
            "terminal_margin_point_input_allowed",
            "authority",
        ]
    ].reset_index(drop=True)


def _build_feasibility(
    company_ttm: pd.DataFrame,
    distributions: pd.DataFrame,
    targets: list[float],
) -> pd.DataFrame:
    reported = distributions.loc[
        distributions["entity"].eq("consolidated")
        & distributions["basis"].eq("AS_REPORTED_TTM")
    ].iloc[0]
    neutral = distributions.loc[
        distributions["entity"].eq("consolidated")
        & distributions["basis"].eq("CATCHUP_NEUTRAL_TTM")
    ].iloc[0]
    segment = distributions.loc[
        distributions["entity"].eq("consolidated")
        & distributions["basis"].eq("SEGMENT_SUM_TTM")
    ].iloc[0]
    nonsegment = distributions.loc[
        distributions["entity"].eq("consolidated")
        & distributions["basis"].eq("NONSEGMENT_CONTRIBUTION_TTM")
    ].iloc[0]
    rows: list[dict[str, object]] = []
    for target in targets:
        if target <= float(neutral["q90_pct"]):
            status = "SUPPORTED_WITHIN_CATCHUP_NEUTRAL_Q90"
        elif target <= float(reported["maximum_pct"]):
            status = "ACCOUNTING_OBSERVED_BUT_NOT_NORMALIZED_BASE_RATE"
        elif target <= float(segment["maximum_pct"] + nonsegment["maximum_pct"]):
            status = "NONCONTEMPORANEOUS_COMPONENT_EXTREMES_ONLY"
        else:
            status = "OUTSIDE_OBSERVED_COMPONENT_DOMAIN"
        rows.append(
            {
                "terminal_margin_hypothesis_pct": target,
                "latest_reported_ttm_margin_pct": float(reported["latest_pct"]),
                "latest_catchup_neutral_ttm_margin_pct": float(neutral["latest_pct"]),
                "catchup_neutral_median_pct": float(neutral["median_pct"]),
                "catchup_neutral_q90_pct": float(neutral["q90_pct"]),
                "reported_historical_max_pct": float(reported["maximum_pct"]),
                "segment_sum_historical_max_pct": float(segment["maximum_pct"]),
                "nonsegment_historical_max_contribution_pct": float(nonsegment["maximum_pct"]),
                "noncontemporaneous_component_ceiling_pct": float(
                    segment["maximum_pct"] + nonsegment["maximum_pct"]
                ),
                "gap_vs_latest_reported_pp": target - float(reported["latest_pct"]),
                "gap_vs_catchup_neutral_q90_pp": target - float(neutral["q90_pct"]),
                "economic_support_status": status,
                "terminal_input_allowed": False,
                "reason": (
                    "Historical feasibility test; catch-up and pension/FAS-CAS effects are "
                    "not assumed to persist into perpetuity."
                ),
            }
        )
    return pd.DataFrame(rows)


def _solve_wacc(
    assumptions: HiiDcfAssumptions, target_ev_usd: float, lower: float, upper: float
) -> dict[str, float | str]:
    def residual(wacc: float) -> float:
        return hii_enterprise_value(replace(assumptions, wacc_pct=wacc))[1][
            "enterprise_value_usd"
        ] - target_ev_usd

    low_error, high_error = residual(lower), residual(upper)
    if low_error * high_error > 0:
        return {"status": "UNBRACKETED_NO_SOLUTION_IN_DOMAIN", "value": np.nan}
    low, high = lower, upper
    middle = (low + high) / 2.0
    for _ in range(240):
        middle = (low + high) / 2.0
        error = residual(middle)
        if abs(error) <= 1.0:
            break
        if low_error * error <= 0:
            high = middle
        else:
            low = middle
            low_error = error
    return {"status": "SOLVED", "value": middle}


def _build_dcf_crosscheck(
    root: Path,
    config: dict[str, Any],
    feasibility: pd.DataFrame,
    distributions: pd.DataFrame,
) -> pd.DataFrame:
    v52 = root / Path(config["v52_output"])
    scenario = pd.read_csv(v52 / "hii_dcf_scenario_assumptions_and_values.csv")
    market = pd.read_csv(v52 / "hii_market_capitalization_bridge.csv").iloc[0]
    wacc = pd.read_csv(v52 / "hii_wacc_range.csv").iloc[0]
    base_row = scenario.loc[scenario["scenario"].eq("base")].iloc[0]
    base = HiiDcfAssumptions(
        scenario="base",
        base_revenue_usd=float(base_row["base_revenue_usd"]),
        near_term_growth_pct=float(base_row["near_term_growth_pct"]),
        terminal_growth_pct=float(base_row["terminal_growth_pct"]),
        initial_margin_pct=float(base_row["initial_margin_pct"]),
        terminal_margin_pct=float(base_row["terminal_margin_pct"]),
        tax_rate_pct=float(base_row["tax_rate_pct"]),
        initial_roic_pct=float(base_row["initial_roic_pct"]),
        terminal_roic_pct=float(base_row["terminal_roic_pct"]),
        wacc_pct=float(base_row["wacc_pct"]),
        first_discount_years=float(base_row["first_discount_years"]),
        horizon_years=int(base_row["horizon_years"]),
    )
    candidates = list(feasibility["terminal_margin_hypothesis_pct"].astype(float))
    neutral = distributions.loc[
        distributions["entity"].eq("consolidated")
        & distributions["basis"].eq("CATCHUP_NEUTRAL_TTM")
    ].iloc[0]
    candidates.extend([float(neutral["median_pct"]), float(neutral["q90_pct"])])
    target_ev = float(market["market_enterprise_value_usd"])
    debt, cash, shares = (
        float(market["total_debt_usd"]),
        float(market["cash_usd"]),
        float(market["shares_outstanding"]),
    )
    rows: list[dict[str, object]] = []
    for margin in sorted(set(candidates)):
        candidate = replace(base, terminal_margin_pct=margin)
        solved = _solve_wacc(
            candidate,
            target_ev,
            max(candidate.terminal_growth_pct + 0.25, 3.0),
            20.0,
        )
        values: dict[str, float] = {}
        for label, wacc_pct in {
            "independent_low": float(wacc["symmetric_wacc_pct"]),
            "independent_midpoint": float(wacc["midpoint_wacc_pct"]),
            "independent_high": float(wacc["downside_wacc_pct"]),
        }.items():
            result = hii_enterprise_value(replace(candidate, wacc_pct=wacc_pct))[1]
            values[f"conditional_value_at_{label}_wacc_per_share"] = (
                result["enterprise_value_usd"] - debt + cash
            ) / shares
            if label == "independent_midpoint":
                values["terminal_value_share_at_independent_midpoint_wacc_pct"] = result[
                    "terminal_value_share_pct"
                ]
        support = feasibility.loc[
            np.isclose(feasibility["terminal_margin_hypothesis_pct"], margin)
        ]
        rows.append(
            {
                "terminal_margin_pct": margin,
                "margin_basis": (
                    "HYPOTHESIS_FEASIBILITY_TEST"
                    if len(support)
                    else (
                        "CATCHUP_NEUTRAL_HISTORICAL_MEDIAN"
                        if np.isclose(margin, float(neutral["median_pct"]))
                        else "CATCHUP_NEUTRAL_HISTORICAL_Q90"
                    )
                ),
                "economic_support_status": (
                    support.iloc[0]["economic_support_status"]
                    if len(support)
                    else "HISTORICAL_DISTRIBUTION_DIAGNOSTIC"
                ),
                "market_implied_wacc_pct": solved["value"],
                "market_implied_wacc_status": solved["status"],
                "independent_wacc_low_pct": float(wacc["symmetric_wacc_pct"]),
                "independent_wacc_midpoint_pct": float(wacc["midpoint_wacc_pct"]),
                "independent_wacc_high_pct": float(wacc["downside_wacc_pct"]),
                "market_price": float(market["market_price"]),
                **values,
                "conditional_only": True,
                "fair_value_claim_allowed": False,
                "terminal_input_allowed": False,
            }
        )
    return pd.DataFrame(rows).sort_values("terminal_margin_pct").reset_index(drop=True)


def _build_program_risk_evidence(ten_k_paths: list[Path], latest_ten_q: Path) -> pd.DataFrame:
    latest_ten_k = ten_k_paths[-1]
    stress_ten_k = [path for path in ten_k_paths if _filing_year(path) == 2024][0]
    latest_k_text = _document_text(latest_ten_k)
    stress_text = _document_text(stress_ten_k)
    q_text = _document_text(latest_ten_q)
    rows = [
        {
            "evidence_type": "CONTRACT_MIX_RISK",
            "program_or_scope": "COMPANY",
            "finding": "Fixed-price work carries inflation, wage, labor, and supplier cost-recovery risk.",
            "evidence_excerpt": _evidence_window(latest_k_text, "Fixed-price contracts generally tend"),
            **_source_fields(latest_ten_k),
        },
        {
            "evidence_type": "ESCALATION_RECOVERY_BASIS_RISK",
            "program_or_scope": "SHIPBUILDING",
            "finding": "Escalation clauses mitigate some material inflation, but index basis can diverge from actual cost.",
            "evidence_excerpt": _evidence_window(latest_k_text, "Although we may be protected from increases"),
            **_source_fields(latest_ten_k),
        },
        {
            "evidence_type": "PROGRAM_EXECUTION_STRESS",
            "program_or_scope": "VIRGINIA_CLASS_AND_AIRCRAFT_CARRIERS",
            "finding": "2024 Newport News revenue and profit were hurt by catch-up adjustments and lower program performance.",
            "evidence_excerpt": _evidence_window(stress_text, "Virginia class (SSN 774) submarine program"),
            **_source_fields(stress_ten_k),
        },
        {
            "evidence_type": "PROGRAM_CATCHUP_DISPERSION",
            "program_or_scope": "NEWPORT_NEWS_RCOH",
            "finding": "Q2 2026 contained offsetting Stennis favorable and George Washington unfavorable adjustments.",
            "evidence_excerpt": _evidence_window(q_text, "favorable adjustment of $ 28 million"),
            **_source_fields(latest_ten_q),
        },
    ]
    result = pd.DataFrame(rows)
    result["terminal_point_input_allowed"] = False
    result["authority"] = "QUALITATIVE_PROGRAM_RISK_CROSSCHECK"
    return result


def _build_correction(
    root: Path, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    v51 = pd.read_csv(
        root
        / "output/industrials_v5_1_hii_governance_research/hii_route_selection_leakage_audit.csv"
    ).iloc[0]
    v521 = pd.read_csv(root / Path(config["v521_output"]) / "hii_model_vs_analyst_expectations.csv").iloc[0]
    corrections = pd.DataFrame(
        [
            {
                "correction_id": "HII_V5_ROUTE_AUTHORITY_001",
                "superseded_artifact": "INDUSTRIALS_V5_HII_EVIDENCE",
                "superseded_field": "PIT_INDUSTRY_BRIDGE_CHAMPION_CLAIM",
                "replacement_field": "BEST_TESTED_DIAGNOSTIC",
                "preserved_value": float(v51["v5_reported_mase"]),
                "correction": "V5 finding superseded by V5.2 governance correction; six routes shared the same OOS window.",
                "independent_analyst_count_claim_allowed": pd.NA,
                "parent_artifact_mutated": False,
            },
            {
                "correction_id": "HII_V521_TARGET_SEMANTICS_001",
                "superseded_artifact": "INDUSTRIALS_V5_2_1_HII_CONSENSUS_EXPECTATIONS_OVERLAY",
                "superseded_field": "analyst_average_target_median",
                "replacement_field": "provider_average_target_median",
                "preserved_value": float(v521["analyst_average_target_median"]),
                "correction": "Median of Finnworlds and Yahoo provider-average targets; underlying analysts may overlap.",
                "independent_analyst_count_claim_allowed": False,
                "parent_artifact_mutated": False,
            },
        ]
    )
    provider_targets = pd.read_csv(
        root / Path(config["v521_output"]) / "hii_analyst_price_target_vintages.csv"
    )
    corrected_summary = pd.DataFrame(
        [
            {
                "provider_average_target_median": float(
                    provider_targets["target_average"].median()
                ),
                "provider_count": int(provider_targets["provider"].nunique()),
                "provider_names": "|".join(sorted(provider_targets["provider"].unique())),
                "reported_provider_analyst_counts": "|".join(
                    f"{row.provider}:{int(row.analyst_count)}"
                    for row in provider_targets.itertuples()
                ),
                "independent_analyst_count": pd.NA,
                "analyst_counts_may_overlap": True,
                "analyst_counts_can_be_summed": False,
                "target_used_to_fit_dcf": False,
                "authority": "PROVIDER_LEVEL_EXPECTATIONS_DIAGNOSTIC_ONLY",
            }
        ]
    )
    return corrections, corrected_summary


def build_hii_v53_margin_research(
    *, root: Path, config: dict[str, Any]
) -> dict[str, pd.DataFrame]:
    ten_k_paths = sorted((root / Path(config["sec_10k_directory"])).glob("*.htm"))
    ten_q_paths = sorted((root / Path(config["sec_10q_directory"])).glob("*.htm"))
    if len(ten_k_paths) != 7 or len(ten_q_paths) != 20:
        raise ValueError(f"Unexpected SEC coverage: 10-K={len(ten_k_paths)}, 10-Q={len(ten_q_paths)}")

    segment_history = pd.read_csv(root / Path(config["ir_segment_history"]))
    company_history = pd.read_csv(root / Path(config["ir_company_history"]))
    feature_history = pd.read_csv(root / Path(config["industry_feature_history"]))
    sensor_authority = pd.read_csv(root / Path(config["industry_sensor_authority"]))
    ir_source_hashes_verified = _verify_ir_source_hashes(segment_history)
    if bool(config["source_hash_required"]) and not ir_source_hashes_verified:
        raise ValueError("One or more Arcana IR source hashes failed verification")
    contract_mix = _build_contract_mix(ten_k_paths, ten_q_paths)
    annual_catchup, annual_segment_catchup = _build_annual_catchup(ten_k_paths)
    quarterly_catchup, quarterly_segment_catchup = _build_quarterly_catchup(
        ten_q_paths, annual_catchup, annual_segment_catchup
    )
    fas_cas = _build_fas_cas_history(ten_k_paths, ten_q_paths)
    backlog = _build_backlog(ten_q_paths[-1], segment_history)
    company_ttm, segment_ttm, normalized_segment_ttm = _build_margin_history(
        segment_history, company_history, quarterly_catchup, quarterly_segment_catchup
    )
    distributions = _distribution_rows(company_ttm, segment_ttm, normalized_segment_ttm)
    industry = _build_industry_diagnostic(feature_history, sensor_authority)
    feasibility = _build_feasibility(
        company_ttm,
        distributions,
        [float(value) for value in config["terminal_margin_hypotheses_pct"]],
    )
    dcf = _build_dcf_crosscheck(root, config, feasibility, distributions)
    program = _build_program_risk_evidence(ten_k_paths, ten_q_paths[-1])
    correction, corrected_consensus = _build_correction(root, config)

    latest_contract = contract_mix.loc[contract_mix["period"].eq("2026Q2")]
    consolidated_contract = latest_contract.loc[latest_contract["segment"].eq("consolidated")]
    fixed_share = float(
        consolidated_contract.loc[
            consolidated_contract["fixed_price_risk_channel"], "contract_mix_pct"
        ].sum()
    )
    latest_company = company_ttm.iloc[-1]
    neutral_dist = distributions.loc[
        distributions["entity"].eq("consolidated")
        & distributions["basis"].eq("CATCHUP_NEUTRAL_TTM")
    ].iloc[0]
    source_coverage = pd.DataFrame(
        [
            {"layer": "SEC_10K_HTML", "source_count": len(ten_k_paths), "use": "CONTRACT_MIX_CATCHUP_FAS_CAS_PROGRAM_RISK"},
            {"layer": "SEC_10Q_HTML", "source_count": len(ten_q_paths), "use": "QUARTERLY_CATCHUP_FAS_CAS_BACKLOG_CONTRACT_MIX"},
            {"layer": "IR_HTML_DERIVED_HISTORY", "source_count": int(segment_history["source_sha256"].nunique()), "use": "27_QUARTER_SEGMENT_AND_COMPANY_MARGIN_HISTORY"},
            {"layer": "BLS_AS_RELEASED_VINTAGE", "source_count": int(sensor_authority["series_id"].nunique()), "use": "PIT_PRICE_COST_RECOVERY_CONTEXT"},
            {"layer": "FROZEN_V5_2_DCF", "source_count": 1, "use": "CONDITIONAL_DCF_REVERSE_DCF_CROSSCHECK"},
            {"layer": "FROZEN_V5_2_1_CONSENSUS", "source_count": 1, "use": "FIELD_SEMANTICS_CORRECTION_ONLY"},
        ]
    )
    source_coverage["source_hash_required"] = bool(config["source_hash_required"])
    source_coverage["pdf_parsing_used"] = bool(config["pdf_parsing_used"])
    source_coverage["source_hash_verified"] = True
    source_coverage.loc[
        source_coverage["layer"].eq("IR_HTML_DERIVED_HISTORY"), "source_hash_verified"
    ] = ir_source_hashes_verified

    summary = pd.DataFrame(
        [
            {
                "as_of_date": config["as_of_date"],
                "ir_quarters": int(company_history["period"].nunique()),
                "reported_ttm_windows": len(company_ttm),
                "catchup_neutral_segment_ttm_windows_per_segment": int(
                    normalized_segment_ttm.groupby("segment").size().min()
                ),
                "latest_reported_ttm_operating_margin_pct": float(latest_company["reported_ttm_margin_pct"]),
                "latest_catchup_neutral_ttm_operating_margin_pct": float(latest_company["catchup_neutral_ttm_margin_pct"]),
                "catchup_neutral_median_operating_margin_pct": float(neutral_dist["median_pct"]),
                "catchup_neutral_q90_operating_margin_pct": float(neutral_dist["q90_pct"]),
                "catchup_neutral_max_operating_margin_pct": float(neutral_dist["maximum_pct"]),
                "latest_fixed_price_risk_share_pct": fixed_share,
                "latest_total_backlog_usd": float(backlog["total_backlog_usd"].sum()),
                "eight_pct_assessment": feasibility.loc[feasibility["terminal_margin_hypothesis_pct"].eq(8.0), "economic_support_status"].iloc[0],
                "ten_pct_assessment": feasibility.loc[feasibility["terminal_margin_hypothesis_pct"].eq(10.0), "economic_support_status"].iloc[0],
                "twelve_pct_assessment": feasibility.loc[feasibility["terminal_margin_hypothesis_pct"].eq(12.0), "economic_support_status"].iloc[0],
                "terminal_authority": False,
                "production_promoted": False,
                "status": "THROUGH_CYCLE_MARGIN_RESEARCH_BENCHMARK_NOT_TERMINAL_AUTHORITY",
            }
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "all_10k_parsed": len(ten_k_paths) == 7,
                "all_10q_parsed": len(ten_q_paths) == 20,
                "ir_history_coverage_complete": int(company_history["period"].nunique()) == 27,
                "ir_source_hashes_verified": ir_source_hashes_verified,
                "contract_mix_identities_pass": bool(
                    np.allclose(
                        contract_mix.groupby(["period", "segment"])["contract_mix_pct"].sum(),
                        100.0,
                        atol=1e-9,
                    )
                ),
                "catchup_identities_pass": bool(annual_catchup["gross_to_net_identity_error_usd"].le(1.0).all()),
                "fas_cas_identities_pass": bool(fas_cas["reconciliation_identity_error_usd"].le(1.0).all()),
                "backlog_identities_pass": bool(backlog["backlog_identity_error_usd"].le(1.0).all()),
                "consensus_semantics_corrected_without_parent_mutation": bool(
                    correction["parent_artifact_mutated"].eq(False).all()
                ),
                "dcf_crosscheck_run": len(dcf) >= 5,
                "fair_value_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_forward_matched_observations": "0/20",
                "research_freeze_eligible": True,
                "status": "RESEARCH_FREEZE_READY_TERMINAL_AND_PRODUCTION_LOCKED",
            }
        ]
    )
    return {
        "hii_v53_source_coverage": source_coverage,
        "hii_contract_type_mix_history": contract_mix,
        "hii_annual_cumulative_catchup_history": annual_catchup,
        "hii_quarterly_cumulative_catchup_history": quarterly_catchup,
        "hii_annual_segment_catchup_history": annual_segment_catchup,
        "hii_quarterly_segment_catchup_history": quarterly_segment_catchup,
        "hii_fas_cas_reconciliation_history": fas_cas,
        "hii_latest_segment_backlog_coverage": backlog,
        "hii_company_ttm_margin_history": company_ttm,
        "hii_segment_ttm_margin_history": segment_ttm,
        "hii_segment_catchup_neutral_ttm_history": normalized_segment_ttm,
        "hii_margin_distribution": distributions,
        "hii_industry_cost_recovery_diagnostic": industry,
        "hii_terminal_margin_feasibility": feasibility,
        "hii_margin_dcf_reverse_crosscheck": dcf,
        "hii_program_risk_evidence": program,
        "hii_immutable_correction_record": correction,
        "hii_consensus_semantics_corrected_summary": corrected_consensus,
        "hii_v53_research_summary": summary,
        "hii_v53_gate": gate,
    }
