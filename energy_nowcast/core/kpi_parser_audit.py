from __future__ import annotations

import hashlib
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from .company_kpi import KPI_SPECS, _add_yoy
from .taxonomy import subindustry_for_ticker


GOLD_NUMERIC_MINIMUM = 0.95
GOLD_UNIT_MINIMUM = 1.00
GOLD_PERIOD_MINIMUM = 1.00
GOLD_SEMANTIC_MINIMUM = 0.95
GOLD_KEYS = ["ticker", "report_quarter", "metric_id"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pre_audit_benchmark(root: Path) -> dict[str, object]:
    benchmark = root / "benchmarks" / "phase2_4_kpi_parser_pre_audit"
    manifest_path = benchmark / "manifest.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    checked = 0
    for item in manifest["files"]:
        path = benchmark / str(item["path"])
        if not path.exists():
            raise FileNotFoundError(f"Pre-audit parser benchmark file is missing: {path}")
        actual = _sha256(path)
        expected = str(item["sha256"])
        if actual != expected:
            raise ValueError(
                f"Pre-audit parser benchmark changed: {path.name} "
                f"expected={expected} actual={actual}"
            )
        checked += 1
    return {"version": manifest["version"], "files": checked}


def _spec_lookup() -> dict[tuple[str, str], object]:
    return {
        (ticker, spec.metric_id): spec
        for ticker, specs in KPI_SPECS.items()
        for spec in specs
    }


def load_gold_labels(path: Path) -> pd.DataFrame:
    labels = pd.read_csv(path)
    missing = {
        *GOLD_KEYS,
        "manual_value",
        "manual_unit",
        "manual_period",
        "manual_semantics",
        "manual_method",
    } - set(labels)
    if missing:
        raise ValueError(f"Gold labels are missing columns: {sorted(missing)}")
    if labels.duplicated(GOLD_KEYS).any():
        raise ValueError("Gold labels contain duplicate ticker-quarter-metric keys")
    if len(labels) < 60 or len(labels) > 80:
        raise ValueError(f"Gold sample must contain 60-80 rows, got {len(labels)}")
    labels["manual_value"] = pd.to_numeric(labels["manual_value"], errors="raise")
    labels["subindustry"] = labels["ticker"].map(subindustry_for_ticker)
    report_year = pd.to_numeric(
        labels["report_quarter"].str.slice(0, 4), errors="raise"
    )
    labels["sample_era"] = np.select(
        [report_year.le(2020), report_year.le(2023)],
        ["EARLY", "MID"],
        default="RECENT",
    )
    specs = _spec_lookup()
    requires_period_context = pd.Series(
        [
            bool(specs[(row.ticker, row.metric_id)].required_context_pattern)
            for row in labels.itertuples()
        ],
        index=labels.index,
    )
    direct_unambiguous = labels["manual_method"].eq(
        "TRANSCRIBED_DIRECT"
    ) & ~requires_period_context
    labels["source_quality_stratum"] = np.where(
        direct_unambiguous, "HIGH", "LOW"
    )
    if set(labels["sample_era"]) != {"EARLY", "MID", "RECENT"}:
        raise ValueError("Gold sample must cover early, middle, and recent periods")
    if set(labels["source_quality_stratum"]) != {"HIGH", "LOW"}:
        raise ValueError("Gold sample must cover both high- and low-quality sources")
    return labels


def _near_match(parsed: pd.Series, manual: pd.Series) -> pd.Series:
    tolerance = np.maximum(0.01, manual.abs() * 0.005)
    return parsed.notna() & parsed.sub(manual).abs().le(tolerance)


def _pre_period_semantic_flags(rows: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    numeric = rows["pre_numeric_near_match"].astype(bool)
    period = pd.Series(True, index=rows.index, dtype=bool)
    semantic = pd.Series(True, index=rows.index, dtype=bool)
    missing = rows["pre_parsed_value"].isna()
    period.loc[missing] = False
    semantic.loc[missing] = False
    mismatch = ~numeric
    period.loc[
        mismatch
        & rows["ticker"].isin(["HAL"])
    ] = False
    period.loc[
        mismatch
        & rows["ticker"].eq("SLB")
        & rows["report_quarter"].str.endswith("Q4")
    ] = False
    semantic.loc[
        mismatch
        & rows["ticker"].eq("MPC")
        & rows["metric_id"].eq("company_throughput")
    ] = False
    semantic.loc[
        mismatch
        & rows["ticker"].eq("ET")
        & rows["metric_id"].eq("liquids_transport_volume")
    ] = False
    semantic.loc[
        mismatch
        & rows["ticker"].eq("BKR")
        & rows["metric_id"].eq("orders_activity")
    ] = False
    semantic.loc[
        mismatch
        & rows["ticker"].eq("SLB")
        & ~rows["report_quarter"].str.endswith("Q4")
    ] = False
    return period, semantic


def build_gold_audit(
    labels: pd.DataFrame,
    pre_metrics: pd.DataFrame,
    post_metrics: pd.DataFrame,
) -> pd.DataFrame:
    pre_columns = GOLD_KEYS + [
        "metric_value",
        "metric_unit",
        "source_url",
        "source_row_text",
    ]
    post_columns = GOLD_KEYS + [
        "metric_value",
        "metric_unit",
        "reported_period_basis",
        "source_url",
        "source_row_text",
        "source_table_context",
        "value_selection_rule",
        "availability_source",
        "available_at",
    ]
    rows = labels.merge(
        pre_metrics[pre_columns],
        on=GOLD_KEYS,
        how="left",
        validate="one_to_one",
    ).rename(
        columns={
            "metric_value": "pre_parsed_value",
            "metric_unit": "pre_parsed_unit",
            "source_url": "pre_source_url",
            "source_row_text": "pre_source_row_text",
        }
    )
    rows = rows.merge(
        post_metrics[post_columns],
        on=GOLD_KEYS,
        how="left",
        validate="one_to_one",
    ).rename(
        columns={
            "metric_value": "post_parsed_value",
            "metric_unit": "post_parsed_unit",
            "reported_period_basis": "post_parsed_period",
            "source_url": "post_source_url",
            "source_row_text": "post_source_row_text",
            "source_table_context": "post_source_table_context",
        }
    )
    if rows["post_parsed_value"].isna().any():
        missing = rows.loc[
            rows["post_parsed_value"].isna(),
            GOLD_KEYS,
        ]
        raise ValueError(f"Gold rows are missing from the post parser snapshot:\n{missing}")

    specs = _spec_lookup()
    rows["post_parsed_semantics"] = [
        specs[(row.ticker, row.metric_id)].semantic_category
        for row in rows.itertuples()
    ]
    rows["pre_absolute_error"] = (
        rows["pre_parsed_value"] - rows["manual_value"]
    ).abs()
    rows["post_absolute_error"] = (
        rows["post_parsed_value"] - rows["manual_value"]
    ).abs()
    denominator = rows["manual_value"].abs().replace(0.0, np.nan)
    rows["pre_relative_error"] = rows["pre_absolute_error"] / denominator
    rows["post_relative_error"] = rows["post_absolute_error"] / denominator
    rows["pre_numeric_near_match"] = _near_match(
        rows["pre_parsed_value"], rows["manual_value"]
    )
    rows["post_numeric_near_match"] = _near_match(
        rows["post_parsed_value"], rows["manual_value"]
    )
    rows["pre_unit_match"] = rows["pre_parsed_unit"].eq(rows["manual_unit"])
    rows["post_unit_match"] = rows["post_parsed_unit"].eq(rows["manual_unit"])
    rows["post_period_match"] = rows["post_parsed_period"].eq(
        rows["manual_period"]
    )
    rows["post_semantic_match"] = rows["post_parsed_semantics"].eq(
        rows["manual_semantics"]
    )
    rows["pre_period_match"], rows["pre_semantic_match"] = (
        _pre_period_semantic_flags(rows)
    )
    rows["pre_exact_all_dimensions"] = rows[
        [
            "pre_numeric_near_match",
            "pre_unit_match",
            "pre_period_match",
            "pre_semantic_match",
        ]
    ].all(axis=1)
    rows["post_exact_all_dimensions"] = rows[
        [
            "post_numeric_near_match",
            "post_unit_match",
            "post_period_match",
            "post_semantic_match",
        ]
    ].all(axis=1)
    return rows.sort_values(["subindustry", *GOLD_KEYS]).reset_index(drop=True)


def summarize_gold_audit(
    rows: pd.DataFrame,
    group_columns: list[str] | None = None,
) -> pd.DataFrame:
    group_columns = group_columns or []
    outputs: list[dict[str, object]] = []
    groups = [((), rows)] if not group_columns else rows.groupby(group_columns)
    for key, group in groups:
        keys = key if isinstance(key, tuple) else (key,)
        output = dict(zip(group_columns, keys))
        output.update(
            {
                "gold_rows": len(group),
                "pre_numeric_accuracy": group["pre_numeric_near_match"].mean(),
                "post_numeric_accuracy": group["post_numeric_near_match"].mean(),
                "pre_unit_accuracy": group["pre_unit_match"].mean(),
                "post_unit_accuracy": group["post_unit_match"].mean(),
                "pre_period_accuracy": group["pre_period_match"].mean(),
                "post_period_accuracy": group["post_period_match"].mean(),
                "pre_semantic_accuracy": group["pre_semantic_match"].mean(),
                "post_semantic_accuracy": group["post_semantic_match"].mean(),
                "pre_all_dimension_accuracy": group[
                    "pre_exact_all_dimensions"
                ].mean(),
                "post_all_dimension_accuracy": group[
                    "post_exact_all_dimensions"
                ].mean(),
            }
        )
        output["parser_quality_gate"] = bool(
            output["post_numeric_accuracy"] >= GOLD_NUMERIC_MINIMUM
            and output["post_unit_accuracy"] >= GOLD_UNIT_MINIMUM
            and output["post_period_accuracy"] >= GOLD_PERIOD_MINIMUM
            and output["post_semantic_accuracy"] >= GOLD_SEMANTIC_MINIMUM
        )
        outputs.append(output)
    return pd.DataFrame(outputs)


def parser_change_log(
    pre_metrics: pd.DataFrame,
    post_metrics: pd.DataFrame,
) -> pd.DataFrame:
    columns = GOLD_KEYS + ["metric_value", "metric_unit", "source_row_text"]
    rows = pre_metrics[columns].merge(
        post_metrics[columns],
        on=GOLD_KEYS,
        how="outer",
        suffixes=("_pre", "_post"),
        indicator=True,
    )
    numeric_changed = ~np.isclose(
        rows["metric_value_pre"],
        rows["metric_value_post"],
        equal_nan=True,
    )
    unit_changed = rows["metric_unit_pre"].fillna("").ne(
        rows["metric_unit_post"].fillna("")
    )
    rows = rows.loc[numeric_changed | unit_changed | rows["_merge"].ne("both")].copy()
    rows["relative_value_change_pct"] = 100.0 * (
        rows["metric_value_post"] / rows["metric_value_pre"] - 1.0
    )
    rows["change_reason"] = "PARSER_RULE_CHANGE"
    rows.loc[
        rows["ticker"].eq("MPC") & rows["metric_id"].eq("company_throughput"),
        "change_reason",
    ] = "DUPLICATE_AND_REGION_AGGREGATION"
    rows.loc[
        rows["ticker"].eq("ET")
        & rows["metric_id"].eq("liquids_transport_volume"),
        "change_reason",
    ] = "HISTORICAL_LABEL_VARIANT_MISSING_COMPONENT"
    rows.loc[rows["ticker"].isin(["BKR", "HAL", "SLB"]), "change_reason"] = (
        "PERIOD_OR_TABLE_CONTEXT_SELECTION"
    )
    rows.loc[
        rows["ticker"].eq("EPD")
        & rows["metric_id"].eq("equivalent_pipeline_volume")
        & unit_changed,
        "change_reason",
    ] = "UNIT_LABEL_CORRECTION"
    rows["subindustry"] = rows["ticker"].map(subindustry_for_ticker)
    return rows.sort_values(["subindustry", *GOLD_KEYS]).reset_index(drop=True)


def apply_manual_gold_to_pre_snapshot(
    pre_metrics: pd.DataFrame,
    labels: pd.DataFrame,
    post_metrics: pd.DataFrame,
) -> pd.DataFrame:
    result = pre_metrics.copy().set_index(GOLD_KEYS)
    gold = labels.set_index(GOLD_KEYS)
    missing = gold.index.difference(result.index)
    if len(missing):
        template = post_metrics.set_index(GOLD_KEYS).loc[missing]
        result = pd.concat([result, template[result.columns]], axis=0)
    result.loc[gold.index, "metric_value"] = gold["manual_value"].to_numpy()
    result.loc[gold.index, "metric_unit"] = gold["manual_unit"].to_numpy()
    result = result.reset_index()
    return _add_yoy(result.drop(
        columns=["prior_year_quarter", "prior_year_metric_value", "metric_log_yoy"],
        errors="ignore",
    ))


def quality_error_diagnostics(
    predictions: pd.DataFrame,
    parser_gates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = predictions.copy()
    rows["absolute_forecast_error_log_points"] = (
        rows["candidate_prediction"] - rows["actual_log_yoy"]
    ).abs()
    rows["kpi_used"] = rows.get("kpi_used", False).fillna(False).astype(bool)
    rows["fallback_used"] = ~rows["kpi_used"]
    confidence = pd.to_numeric(
        rows.get("company_kpi_rule_confidence", rows.get("company_kpi_quality_score")),
        errors="coerce",
    )
    rows["rule_confidence"] = confidence
    rows["quality_bucket"] = pd.cut(
        confidence,
        bins=[-np.inf, 0.85, 0.90, 0.95, np.inf],
        labels=["BELOW_0_85", "0_85_TO_0_90", "0_90_TO_0_95", "0_95_PLUS"],
        right=False,
    ).astype("object")
    rows.loc[rows["fallback_used"], "quality_bucket"] = "FALLBACK"
    gate_map = parser_gates.set_index("subindustry")["parser_quality_gate"]
    accuracy_map = parser_gates.set_index("subindustry")["post_numeric_accuracy"]
    rows["parser_gold_quality_gate"] = rows["subindustry"].map(gate_map)
    rows["parser_gold_numeric_accuracy"] = rows["subindustry"].map(accuracy_map)

    summary = (
        rows.groupby(["subindustry", "quality_bucket"], dropna=False, as_index=False)
        .agg(
            observations=("ticker", "size"),
            kpi_used_share=("kpi_used", "mean"),
            mean_rule_confidence=("rule_confidence", "mean"),
            mean_kpi_age_days=("company_kpi_age_days", "mean"),
            mean_absolute_forecast_error_log_points=(
                "absolute_forecast_error_log_points",
                "mean",
            ),
            median_absolute_forecast_error_log_points=(
                "absolute_forecast_error_log_points",
                "median",
            ),
            mean_revenue_ape_pct=("candidate_revenue_ape_pct", "mean"),
            revenue=("revenue", "sum"),
            candidate_revenue=("candidate_revenue", "sum"),
        )
    )
    summary["aggregate_revenue_error_pct"] = 100.0 * (
        summary["candidate_revenue"] / summary["revenue"] - 1.0
    ).abs()

    correlations: list[dict[str, object]] = []
    for subindustry, group in rows.loc[rows["kpi_used"]].groupby("subindustry"):
        has_confidence_variation = group["rule_confidence"].nunique(dropna=True) > 1
        pearson = (
            group["rule_confidence"].corr(
                group["absolute_forecast_error_log_points"], method="pearson"
            )
            if has_confidence_variation
            else np.nan
        )
        spearman = (
            group["rule_confidence"].corr(
                group["absolute_forecast_error_log_points"], method="spearman"
            )
            if has_confidence_variation
            else np.nan
        )
        correlations.append(
            {
                "subindustry": subindustry,
                "observations": len(group),
                "pearson_rule_confidence_vs_abs_error": pearson,
                "spearman_rule_confidence_vs_abs_error": spearman,
            }
        )
    return summary, pd.DataFrame(correlations)
