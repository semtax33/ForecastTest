from __future__ import annotations

from pathlib import Path
from lxml import etree
import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v17.reinvestment import (
    FACTS,
    FLOW_METRICS,
    _contexts,
    _local_name,
    _numeric,
    _select_metric,
)


CMI_FACTS = {
    **FACTS,
    "trade_receivables_usd": (
        *FACTS["trade_receivables_usd"],
        "AccountsNotesAndLoansReceivableNetCurrent",
        "AccountsReceivableNet",
    ),
    "total_debt_reported_usd": (
        "LongTermDebtAndCapitalLeaseObligations",
        "DebtAndCapitalLeaseObligations",
    ),
}


def _parse_cmi_filing(path: Path, source: pd.Series) -> pd.DataFrame:
    parser = etree.XMLParser(recover=True, huge_tree=True)
    tree = etree.parse(str(path), parser)
    contexts = _contexts(tree)
    wanted = {concept for candidates in CMI_FACTS.values() for concept in candidates}
    rows: list[dict[str, object]] = []
    for node in tree.xpath("//*[local-name()='nonFraction']"):
        concept = node.get("name", "")
        if _local_name(concept) not in wanted:
            continue
        value = _numeric(node)
        context = contexts.get(node.get("contextRef", ""), {})
        if value is None or not context:
            continue
        rows.append(
            {
                "form": source["form"],
                "filing_date": source["filing_date"],
                "report_date": source["report_date"],
                "accession_number": source["accession_number"],
                "concept": concept,
                "concept_local": _local_name(concept),
                "value_usd": value,
                "context_ref": node.get("contextRef"),
                **context,
                "source_url": source["source_url"],
                "source_sha256": source["sha256"],
            }
        )
    return pd.DataFrame(rows)


def _select_cmi_metric(
    facts: pd.DataFrame, metric: str, report_date: str, form: str
) -> tuple[float, str | None, str | None]:
    if metric in FACTS and CMI_FACTS[metric] == FACTS[metric]:
        return _select_metric(facts, metric, report_date, form)
    candidates = CMI_FACTS[metric]
    frame = facts.loc[
        facts["concept_local"].isin(candidates)
        & facts["end_date"].eq(report_date)
        & facts["dimension_count"].eq(0)
    ].copy()
    if metric in FLOW_METRICS:
        frame["duration_days"] = (
            pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])
        ).dt.days
        frame = frame.loc[
            frame["duration_days"].between(330, 370)
            if form == "10-K"
            else frame["duration_days"].between(70, 290)
        ]
    else:
        frame = frame.loc[frame["instant"]]
    if frame.empty:
        return np.nan, None, None
    frame["concept_priority"] = frame["concept_local"].map(
        {name: index for index, name in enumerate(candidates)}
    )
    sort = ["concept_priority"] + (["duration_days"] if metric in FLOW_METRICS else [])
    ascending = [True] + ([False] if metric in FLOW_METRICS else [])
    selected = frame.sort_values(sort, ascending=ascending).iloc[0]
    return float(selected["value_usd"]), str(selected["concept"]), str(selected["context_ref"])


def _quarter(report_date: str) -> int:
    month = pd.Timestamp(report_date).month
    if month in {3, 4}:
        return 1
    if month in {6, 7}:
        return 2
    if month in {9, 10}:
        return 3
    return 4


def _select_periodic(sec_inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_frames = [
        _parse_cmi_filing(Path(str(source["resolved_path"])), source)
        for _, source in sec_inventory.iterrows()
    ]
    raw = pd.concat(raw_frames, ignore_index=True)
    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    for _, source in sec_inventory.sort_values("report_date").iterrows():
        report_date = str(source["report_date"])
        filing = raw.loc[raw["accession_number"].eq(source["accession_number"])]
        row: dict[str, object] = {
            "form": source["form"],
            "fiscal_year": int(report_date[:4]),
            "fiscal_quarter": _quarter(report_date),
            "period": f"{report_date[:4]}Q{_quarter(report_date)}",
            "filing_date": source["filing_date"],
            "report_date": report_date,
            "source_url": source["source_url"],
            "source_sha256": source["sha256"],
        }
        for metric in CMI_FACTS:
            value, concept, context_ref = _select_cmi_metric(
                filing, metric, report_date, str(source["form"])
            )
            row[metric] = value
            selections.append(
                {
                    "form": source["form"],
                    "period": row["period"],
                    "filing_date": source["filing_date"],
                    "metric": metric,
                    "value_usd": value,
                    "available": bool(np.isfinite(value)),
                    "selected_concept": concept,
                    "selected_context_ref": context_ref,
                    "source_url": source["source_url"],
                    "source_sha256": source["sha256"],
                    "selection_rule": "CONSOLIDATED_NO_DIMENSION_REPORT_DATE_CONTEXT",
                }
            )
        rows.append(row)
    periodic = pd.DataFrame(rows).sort_values(["fiscal_year", "fiscal_quarter"]).reset_index(drop=True)
    return raw, periodic, pd.DataFrame(selections)


def _annual_bridge(periodic: pd.DataFrame) -> pd.DataFrame:
    annual = periodic.loc[periodic["form"].eq("10-K")].copy().reset_index(drop=True)
    for column in [
        "equipment_on_lease_capex_usd",
        "business_acquisitions_usd",
        "research_development_usd",
        "restructuring_cost_usd",
        "goodwill_usd",
        "intangibles_ex_goodwill_usd",
    ]:
        annual[column] = annual[column].fillna(0.0)
    tax_rate = annual["income_tax_usd"] / annual["pretax_income_usd"]
    annual["effective_tax_rate_pct"] = tax_rate.where(tax_rate.between(0.0, 0.50), 0.21) * 100.0
    annual["nopat_usd"] = annual["operating_income_usd"] * (
        1.0 - annual["effective_tax_rate_pct"] / 100.0
    )
    annual["operating_nwc_usd"] = (
        annual["inventory_usd"]
        + annual["trade_receivables_usd"]
        - annual["accounts_payable_usd"]
    )
    annual["change_operating_nwc_usd"] = annual["operating_nwc_usd"].diff()
    annual["gross_productive_asset_capex_usd"] = (
        annual["capex_usd"] + annual["equipment_on_lease_capex_usd"]
    )
    annual["net_capex_usd"] = (
        annual["gross_productive_asset_capex_usd"]
        - annual["depreciation_amortization_usd"]
    )
    annual["core_reinvestment_usd"] = (
        annual["net_capex_usd"] + annual["change_operating_nwc_usd"]
    )
    annual["innovation_adjusted_reinvestment_usd"] = (
        annual["core_reinvestment_usd"] + annual["research_development_usd"]
    )
    annual["total_including_mna_reinvestment_usd"] = (
        annual["innovation_adjusted_reinvestment_usd"]
        + annual["business_acquisitions_usd"]
    )
    annual["total_debt_usd"] = annual["total_debt_reported_usd"].where(
        annual["total_debt_reported_usd"].notna(),
        annual["debt_current_usd"].fillna(0.0) + annual["debt_noncurrent_usd"].fillna(0.0),
    )
    annual["invested_capital_usd"] = (
        annual["total_debt_usd"] + annual["equity_usd"] - annual["cash_usd"]
    )
    annual["average_invested_capital_usd"] = (
        annual["invested_capital_usd"] + annual["invested_capital_usd"].shift(1)
    ) / 2.0
    annual["reported_roic_pct"] = (
        annual["nopat_usd"] / annual["average_invested_capital_usd"] * 100.0
    )
    annual["tangible_invested_capital_usd"] = (
        annual["invested_capital_usd"]
        - annual["goodwill_usd"]
        - annual["intangibles_ex_goodwill_usd"]
    )
    annual["average_tangible_invested_capital_usd"] = (
        annual["tangible_invested_capital_usd"]
        + annual["tangible_invested_capital_usd"].shift(1)
    ) / 2.0
    annual["tangible_roic_sensitivity_pct"] = (
        annual["nopat_usd"] / annual["average_tangible_invested_capital_usd"] * 100.0
    )
    annual["core_reinvestment_rate_pct"] = annual["core_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    annual["innovation_adjusted_reinvestment_rate_pct"] = (
        annual["innovation_adjusted_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    )
    annual["total_including_mna_reinvestment_rate_pct"] = (
        annual["total_including_mna_reinvestment_usd"] / annual["nopat_usd"] * 100.0
    )
    annual["incremental_nopat_usd"] = annual["nopat_usd"].diff()
    annual["incremental_roic_on_prior_innovation_reinvestment_pct"] = (
        annual["incremental_nopat_usd"]
        / annual["innovation_adjusted_reinvestment_usd"].shift(1)
        * 100.0
    )
    annual["through_cycle_reported_roic_median_pct"] = annual["reported_roic_pct"].rolling(
        3, min_periods=3
    ).median()
    annual["terminal_input_allowed"] = False
    return annual


def _quarterly_bridge(periodic: pd.DataFrame) -> pd.DataFrame:
    frame = periodic.copy()
    for column in [
        "equipment_on_lease_capex_usd",
        "business_acquisitions_usd",
        "research_development_usd",
    ]:
        frame[column] = frame[column].fillna(0.0)
    frame["operating_nwc_usd"] = (
        frame["inventory_usd"] + frame["trade_receivables_usd"] - frame["accounts_payable_usd"]
    )
    frame["change_operating_nwc_usd"] = frame["operating_nwc_usd"].diff()
    result = frame[
        [
            "period", "fiscal_year", "fiscal_quarter", "form", "filing_date", "report_date",
            "source_url", "source_sha256", "operating_nwc_usd", "change_operating_nwc_usd",
        ]
    ].copy()
    for metric in sorted(FLOW_METRICS):
        discrete: list[float] = []
        for _, row in frame.iterrows():
            current = row[metric]
            quarter = int(row["fiscal_quarter"])
            if quarter == 1:
                discrete.append(current)
                continue
            prior = frame.loc[
                frame["fiscal_year"].eq(row["fiscal_year"])
                & frame["fiscal_quarter"].eq(quarter - 1),
                metric,
            ]
            discrete.append(
                current - prior.iloc[0]
                if pd.notna(current) and not prior.empty and pd.notna(prior.iloc[0])
                else np.nan
            )
        result[f"discrete_{metric}"] = discrete
    result["discrete_effective_tax_rate_pct"] = (
        result["discrete_income_tax_usd"] / result["discrete_pretax_income_usd"]
    ).where(lambda values: values.between(0.0, 0.50), 0.21) * 100.0
    result["discrete_nopat_usd"] = result["discrete_operating_income_usd"] * (
        1.0 - result["discrete_effective_tax_rate_pct"] / 100.0
    )
    result["discrete_gross_productive_asset_capex_usd"] = (
        result["discrete_capex_usd"] + result["discrete_equipment_on_lease_capex_usd"]
    )
    result["discrete_net_capex_usd"] = (
        result["discrete_gross_productive_asset_capex_usd"]
        - result["discrete_depreciation_amortization_usd"]
    )
    result["discrete_core_reinvestment_usd"] = (
        result["discrete_net_capex_usd"] + result["change_operating_nwc_usd"]
    )
    result["discrete_innovation_adjusted_reinvestment_usd"] = (
        result["discrete_core_reinvestment_usd"] + result["discrete_research_development_usd"]
    )
    critical = [
        "discrete_operating_income_usd",
        "discrete_income_tax_usd",
        "discrete_capex_usd",
        "discrete_depreciation_amortization_usd",
        "discrete_research_development_usd",
        "change_operating_nwc_usd",
    ]
    result["quarterly_note_chain_complete"] = result[critical].notna().all(axis=1)
    result["historical_pit_input"] = True
    result["terminal_input_allowed"] = False
    return result


def build_cmi_reinvestment_roic_evidence(
    *, sec_inventory: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    raw, periodic, selections = _select_periodic(sec_inventory)
    annual = _annual_bridge(periodic)
    quarterly = _quarterly_bridge(periodic)
    coverage = (
        selections.groupby("metric", as_index=False)
        .agg(periodic_filings=("available", "size"), filings_available=("available", "sum"))
    )
    coverage["coverage_pct"] = coverage["filings_available"] / coverage["periodic_filings"] * 100.0
    annual_selections = selections.loc[selections["form"].eq("10-K")]
    annual_coverage = (
        annual_selections.groupby("metric", as_index=False)
        .agg(annual_filings=("available", "size"), years_available=("available", "sum"))
    )
    annual_coverage["coverage_pct"] = annual_coverage["years_available"] / annual_coverage["annual_filings"] * 100.0
    critical = {
        "operating_income_usd", "income_tax_usd", "pretax_income_usd", "capex_usd",
        "depreciation_amortization_usd", "research_development_usd", "inventory_usd",
        "trade_receivables_usd", "accounts_payable_usd", "cash_usd", "equity_usd",
    }
    critical_coverage = annual_coverage.loc[annual_coverage["metric"].isin(critical), "coverage_pct"]
    summary = pd.DataFrame(
        [
            {
                "periodic_filings_parsed": len(periodic),
                "annual_10k_filings": int(periodic["form"].eq("10-K").sum()),
                "quarterly_10q_filings": int(periodic["form"].eq("10-Q").sum()),
                "raw_relevant_xbrl_facts": len(raw),
                "critical_annual_metric_minimum_coverage_pct": float(critical_coverage.min()),
                "quarterly_note_chain_complete_rows": int(quarterly["quarterly_note_chain_complete"].sum()),
                "quarterly_note_chain_coverage_pct": float(quarterly["quarterly_note_chain_complete"].mean() * 100.0),
                "reported_roic_years": int(annual["reported_roic_pct"].notna().sum()),
                "incremental_roic_years": int(annual["incremental_roic_on_prior_innovation_reinvestment_pct"].notna().sum()),
                "latest_reported_roic_pct": float(annual.iloc[-1]["reported_roic_pct"]),
                "latest_through_cycle_roic_median_pct": float(annual.iloc[-1]["through_cycle_reported_roic_median_pct"]),
                "latest_innovation_adjusted_reinvestment_rate_pct": float(
                    annual.iloc[-1]["innovation_adjusted_reinvestment_rate_pct"]
                ),
                "research_evidence_ready": bool(
                    len(periodic) == 23
                    and len(annual) == 6
                    and critical_coverage.min() >= 80.0
                    and annual["reported_roic_pct"].notna().sum() >= 5
                ),
                "segment_roic_claim_allowed": False,
                "terminal_input_allowed": False,
            }
        ]
    )
    return {
        "cmi_periodic_relevant_xbrl_facts": raw,
        "cmi_periodic_note_fact_selections": selections,
        "cmi_periodic_note_fact_coverage": coverage,
        "cmi_annual_note_fact_coverage": annual_coverage,
        "cmi_annual_reinvestment_roic_bridge": annual,
        "cmi_quarterly_reinvestment_note_bridge": quarterly,
        "cmi_reinvestment_roic_summary": summary,
    }
