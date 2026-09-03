from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.metrics import absolute_percentage_error, mean_absolute_scaled_error
from equity_platform.parsing import compile_rule_file, execute_rules
from equity_platform.paths import PROJECT_ROOT


CAT_RULES = PROJECT_ROOT / "configs/parser_rules/industrials/cat.arc"


def parse_cat_order_backlog(source: pd.Series) -> dict[str, object]:
    path = Path(str(source["resolved_path"]))
    document = adapt_html_document(
        path=path,
        metadata=DocumentMetadata(
            entity="CAT",
            source_kind="SEC_10K",
            document_kind="ANNUAL_REPORT",
            available_at=pd.Timestamp(source["filing_date"]).date().isoformat(),
            report_period=str(int(source["fiscal_year"])),
        ),
        expected_sha256=str(source["source_sha256"]),
        source_uri=str(source["source_url"]),
        include_tables=False,
        include_inline_facts=False,
    )
    executions = execute_rules(document, compile_rule_file(CAT_RULES))
    failures = [execution for execution in executions if execution.status != "EMITTED"]
    if failures:
        detail = [(item.rule_id, item.status, item.error) for item in failures]
        raise ValueError(f"CAT backlog DSL failed for {path}: {detail}")
    facts = {
        execution.fact.metric: execution.fact
        for execution in executions
        if execution.fact is not None
    }
    current_backlog_b = facts["FIRM_ORDER_BACKLOG"].value
    current_year = int(facts["FIRM_ORDER_BACKLOG_CURRENT_YEAR"].value)
    prior_backlog_b = facts["PRIOR_YEAR_FIRM_ORDER_BACKLOG"].value
    prior_year = int(facts["FIRM_ORDER_BACKLOG_PRIOR_YEAR"].value)
    not_expected_year = int(facts["BACKLOG_NOT_EXPECTED_REFERENCE_YEAR"].value)
    not_expected_b = facts["BACKLOG_NOT_EXPECTED_NEXT_YEAR"].value
    fill_year = int(facts["EXPECTED_FILL_YEAR"].value)
    if current_year != int(source["fiscal_year"]):
        raise ValueError(f"Backlog year mismatch in {path}: {current_year}")
    if prior_year != current_year - 1 or not_expected_year != current_year:
        raise ValueError(f"Backlog period semantics mismatch in {path}")
    expected_b = current_backlog_b - not_expected_b
    if expected_b < 0 or fill_year != current_year + 1:
        raise ValueError(f"Invalid next-year backlog bridge in {path}")
    firm_excerpt = facts["FIRM_ORDER_BACKLOG"].lineage.match_trace["matches"][0][
        "source_excerpt"
    ]
    not_expected_excerpt = facts[
        "BACKLOG_NOT_EXPECTED_NEXT_YEAR"
    ].lineage.match_trace["matches"][0]["source_excerpt"]
    excerpt = str(firm_excerpt) + ". " + str(not_expected_excerpt) + "."
    return {
        "fiscal_year": current_year,
        "filing_date": pd.Timestamp(source["filing_date"]).date().isoformat(),
        "firm_backlog_usd": current_backlog_b * 1e9,
        "prior_year_firm_backlog_usd": prior_backlog_b * 1e9,
        "not_expected_next_year_usd": not_expected_b * 1e9,
        "expected_within_next_year_usd": expected_b * 1e9,
        "expected_within_next_year_pct": expected_b / current_backlog_b * 100.0,
        "expected_fill_year": fill_year,
        "semantic_label": "FIRM_ORDER_BACKLOG_DIRECT_DISCLOSURE",
        "parser_confidence": "HIGH_DIRECT_TEXT_MATCH",
        "source_url": source["source_url"],
        "source_path": str(path),
        "source_sha256": source["source_sha256"],
        "source_excerpt": excerpt,
        "next_year_identity_pass": bool(
            abs(current_backlog_b - not_expected_b - expected_b) <= 1e-12
        ),
    }


def build_cat_backlog_history(sources: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        [parse_cat_order_backlog(row) for _, row in sources.iterrows()]
    ).sort_values("fiscal_year")
    if frame["fiscal_year"].duplicated().any():
        raise ValueError("Duplicate CAT backlog fiscal years")
    if not frame["next_year_identity_pass"].all():
        raise ValueError("CAT next-year backlog identity failed")
    return frame.reset_index(drop=True)


def build_backlog_semantic_audit(
    backlog: pd.DataFrame,
    consolidated_financials: pd.DataFrame,
) -> pd.DataFrame:
    rpo = consolidated_financials[
        ["fiscal_year", "backlog_usd", "backlog_usd_source_concept"]
    ].rename(columns={"backlog_usd": "xbrl_rpo_usd"})
    audit = backlog.merge(rpo, on="fiscal_year", how="left", validate="one_to_one")
    audit["rpo_minus_firm_backlog_usd"] = (
        audit["xbrl_rpo_usd"] - audit["firm_backlog_usd"]
    )
    audit["rpo_to_firm_backlog_ratio"] = (
        audit["xbrl_rpo_usd"] / audit["firm_backlog_usd"]
    )
    audit["same_economic_semantics"] = False
    audit["v1_rpo_anchor_status"] = "RETIRED_WRONG_KPI_SEMANTICS"
    audit["direct_backlog_anchor_status"] = "RESEARCH_ONLY_PENDING_OOS_GATE"
    return audit


def build_next_year_backlog_bridge(
    backlog: pd.DataFrame,
    segment_history: pd.DataFrame,
    *,
    minimum_history_observations: int,
    minimum_validation_observations: int,
) -> dict[str, pd.DataFrame]:
    revenue = segment_history[["fiscal_year", "mpe_revenue_usd"]].copy()
    current = revenue.rename(columns={"mpe_revenue_usd": "current_mpe_revenue_usd"})
    target = revenue.assign(fiscal_year=revenue["fiscal_year"] - 1).rename(
        columns={"mpe_revenue_usd": "actual_next_year_mpe_revenue_usd"}
    )
    bridge = (
        backlog.merge(current, on="fiscal_year", how="left")
        .merge(target, on="fiscal_year", how="left")
        .sort_values("fiscal_year")
        .reset_index(drop=True)
    )
    bridge["realized_near_term_backlog_coverage_pct"] = (
        bridge["expected_within_next_year_usd"]
        / bridge["actual_next_year_mpe_revenue_usd"]
        * 100.0
    )
    bridge["realized_non_backlog_and_timing_revenue_usd"] = (
        bridge["actual_next_year_mpe_revenue_usd"]
        - bridge["expected_within_next_year_usd"]
    )
    bridge["naive_next_year_mpe_revenue_usd"] = bridge["current_mpe_revenue_usd"]
    bridge["backlog_candidate_next_year_mpe_revenue_usd"] = np.nan
    bridge["training_observations"] = 0
    for index in bridge.index:
        training = bridge.loc[: index - 1].dropna(
            subset=["realized_near_term_backlog_coverage_pct"]
        )
        if len(training) < minimum_history_observations:
            continue
        coverage = float(
            training["realized_near_term_backlog_coverage_pct"].median()
        )
        if coverage <= 0:
            continue
        bridge.at[index, "backlog_candidate_next_year_mpe_revenue_usd"] = (
            float(bridge.at[index, "expected_within_next_year_usd"])
            / (coverage / 100.0)
        )
        bridge.at[index, "training_observations"] = len(training)
    validation = bridge.dropna(
        subset=[
            "actual_next_year_mpe_revenue_usd",
            "naive_next_year_mpe_revenue_usd",
            "backlog_candidate_next_year_mpe_revenue_usd",
        ]
    ).copy()
    validation["backlog_candidate_ape_pct"] = absolute_percentage_error(
        validation["actual_next_year_mpe_revenue_usd"],
        validation["backlog_candidate_next_year_mpe_revenue_usd"],
    )
    validation["naive_ape_pct"] = absolute_percentage_error(
        validation["actual_next_year_mpe_revenue_usd"],
        validation["naive_next_year_mpe_revenue_usd"],
    )
    mase = mean_absolute_scaled_error(
        validation["actual_next_year_mpe_revenue_usd"],
        validation["backlog_candidate_next_year_mpe_revenue_usd"],
        validation["naive_next_year_mpe_revenue_usd"],
    )
    promoted = bool(
        len(validation) >= minimum_validation_observations
        and np.isfinite(mase)
        and mase < 1.0
    )
    observed = bridge["realized_near_term_backlog_coverage_pct"].dropna()
    latest = bridge.iloc[-1]
    if observed.empty:
        raise ValueError("No realized CAT next-year backlog coverage observations")
    coverage_q25, coverage_median, coverage_q75 = (
        float(observed.quantile(quantile)) for quantile in (0.25, 0.50, 0.75)
    )
    candidate = pd.DataFrame(
        [
            {
                "forecast_origin_fiscal_year": int(latest["fiscal_year"]),
                "target_fiscal_year": int(latest["expected_fill_year"]),
                "firm_backlog_usd": latest["firm_backlog_usd"],
                "not_expected_next_year_usd": latest["not_expected_next_year_usd"],
                "expected_within_next_year_usd": latest[
                    "expected_within_next_year_usd"
                ],
                "historical_coverage_q25_pct": coverage_q25,
                "historical_coverage_median_pct": coverage_median,
                "historical_coverage_q75_pct": coverage_q75,
                "candidate_revenue_low_usd": latest["expected_within_next_year_usd"]
                / (coverage_q75 / 100.0),
                "candidate_revenue_mid_usd": latest[
                    "expected_within_next_year_usd"
                ]
                / (coverage_median / 100.0),
                "candidate_revenue_high_usd": latest[
                    "expected_within_next_year_usd"
                ]
                / (coverage_q25 / 100.0),
                "selected_for_valuation": promoted,
                "conditional_bridge": (
                    "NEAR_TERM_BACKLOG_DIVIDED_BY_EMPIRICAL_REVENUE_COVERAGE"
                ),
            }
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "anchor": "CAT_FIRM_ORDER_BACKLOG_DIRECT_10_K",
                "direct_firm_backlog_years": len(backlog),
                "next_year_conversion_years": int(
                    backlog["not_expected_next_year_usd"].notna().sum()
                ),
                "walk_forward_validation_observations": len(validation),
                "minimum_validation_observations": minimum_validation_observations,
                "anchor_revenue_mase_vs_prior_year_naive": mase,
                "anchor_promoted": promoted,
                "rpo_anchor_retired": True,
                "selected_forecast_route": (
                    "DIRECT_BACKLOG_CONVERSION_BRIDGE"
                    if promoted
                    else "PRIOR_YEAR_MPE_REVENUE_BASELINE"
                ),
                "promotion_reason": (
                    "PROMOTED_STRICT_MASE_IMPROVEMENT"
                    if promoted
                    else "LOCKED_INSUFFICIENT_OOS_EVIDENCE_OR_NO_MASE_IMPROVEMENT"
                ),
            }
        ]
    )
    return {
        "next_year_backlog_bridge": bridge,
        "backlog_anchor_validation": validation,
        "backlog_anchor_gate": gate,
        "backlog_conversion_candidate": candidate,
    }
