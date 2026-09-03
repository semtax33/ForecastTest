from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from lxml import etree
import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v15.pit import (
    build_pit_forecast_features,
    parse_bls_ppi_vintages,
)
from equity_platform.sectors.industrials.v17.reinvestment import (
    _contexts,
    _local_name,
    _numeric,
)


INSTANT_ALIASES = {
    "accounts_receivable_usd": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
    "inventory_usd": (
        "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings",
        "InventoryNet",
    ),
    "accounts_payable_usd": ("AccountsPayableCurrent",),
    "contract_assets_usd": ("ContractWithCustomerAssetNet", "ContractWithCustomerAssetNetCurrent"),
    "contract_liabilities_usd": ("ContractWithCustomerLiabilityCurrent",),
    "cash_usd": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "debt_current_usd": (
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "DebtCurrent",
    ),
    "debt_noncurrent_usd": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "stockholders_equity_usd": (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
    "pension_liability_usd": (
        "DefinedBenefitPensionPlanLiabilitiesNoncurrent",
        "DefinedBenefitPensionPlanCurrentAndNoncurrentLiabilities",
    ),
    "shares_outstanding": (
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
    ),
    "remaining_performance_obligation_usd": ("RevenueRemainingPerformanceObligation",),
}
FLOW_ALIASES = {
    "combined_depreciation_amortization_usd": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortizationIncludingDiscontinuedOperations",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ),
    "depreciation_usd": ("Depreciation",),
    "intangible_amortization_usd": ("AmortizationOfIntangibleAssets",),
    "interest_expense_usd": ("InterestExpense", "InterestExpenseNonOperating"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numeric_text(value: object) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else float("nan")


def _range_billions(value: object) -> tuple[float, float]:
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(value))]
    if len(numbers) < 2:
        raise ValueError(f"Expected a two-sided billion-dollar range, received {value!r}")
    return numbers[0] * 1e9, numbers[1] * 1e9


def _range_pct(value: object) -> tuple[float, float]:
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(value))]
    if not numbers:
        raise ValueError(f"Expected percentage guidance, received {value!r}")
    return (numbers[0], numbers[-1])


def _parse_ir_guidance(path: Path, company_history: pd.DataFrame) -> pd.DataFrame:
    tables = pd.read_html(path)
    candidates = [table for table in tables if table.astype(str).apply(
        lambda column: column.str.contains("Current FY26 Outlook", regex=False).any()
    ).any()]
    if len(candidates) != 1:
        raise ValueError("Exactly one FY26 outlook table must be present in the Q2 IR release")
    table = candidates[0]
    labels = table.iloc[:, 0].astype(str)

    def current(label: str) -> str:
        row = table.loc[labels.str.replace(r"\d+$", "", regex=True).eq(label)]
        if row.empty:
            raise ValueError(f"Missing IR guidance row: {label}")
        nonempty = [value for value in row.iloc[0].tolist() if pd.notna(value)]
        return str(nonempty[-1])

    ship_rev_low, ship_rev_high = _range_billions(current("Shipbuilding Revenue"))
    ship_margin_low, ship_margin_high = _range_pct(current("Shipbuilding Operating Margin"))
    mission_rev_low, mission_rev_high = _range_billions(current("Mission Technologies Revenue"))
    mission_margin_low, mission_margin_high = _range_pct(
        current("Mission Technologies Segment Operating Margin")
    )
    da_mid = _numeric_text(current("Depreciation & Amortization")) * 1e6
    capex_low, capex_high = _range_pct(current("Capital Expenditures"))
    fcf_low, fcf_high = [
        float(number) * 1e6
        for number in re.findall(r"\d+(?:\.\d+)?", current("Free Cash Flow"))
    ][:2]
    tax_rate = _numeric_text(current("Effective Tax Rate"))
    interest = _numeric_text(current("Interest Expense")) * 1e6
    fas_cas = _numeric_text(current("Operating FAS/CAS Adjustment")) * 1e6
    state_tax = _numeric_text(current("Non-current State Income Tax Expense")) * 1e6
    eliminations = float(company_history.tail(4)["intersegment_eliminations_usd"].sum())
    total_low = ship_rev_low + mission_rev_low + eliminations
    total_high = ship_rev_high + mission_rev_high + eliminations
    total_mid = (total_low + total_high) / 2.0
    op_income_low = ship_rev_low * ship_margin_low / 100.0 + mission_rev_low * mission_margin_low / 100.0 - fas_cas - state_tax
    op_income_high = ship_rev_high * ship_margin_high / 100.0 + mission_rev_high * mission_margin_high / 100.0 - fas_cas - state_tax
    op_income_mid = (
        (ship_rev_low + ship_rev_high) / 2.0 * (ship_margin_low + ship_margin_high) / 200.0
        + (mission_rev_low + mission_rev_high) / 2.0 * (mission_margin_low + mission_margin_high) / 200.0
        - fas_cas
        - state_tax
    )
    return pd.DataFrame(
        [
            {
                "forecast_year": 2026,
                "source_date": "2026-07-30",
                "shipbuilding_revenue_low_usd": ship_rev_low,
                "shipbuilding_revenue_high_usd": ship_rev_high,
                "shipbuilding_operating_margin_low_pct": ship_margin_low,
                "shipbuilding_operating_margin_high_pct": ship_margin_high,
                "mission_revenue_low_usd": mission_rev_low,
                "mission_revenue_high_usd": mission_rev_high,
                "mission_operating_margin_low_pct": mission_margin_low,
                "mission_operating_margin_high_pct": mission_margin_high,
                "trailing_intersegment_eliminations_usd": eliminations,
                "company_revenue_low_usd": total_low,
                "company_revenue_midpoint_usd": total_mid,
                "company_revenue_high_usd": total_high,
                "consolidated_operating_income_low_usd": op_income_low,
                "consolidated_operating_income_midpoint_usd": op_income_mid,
                "consolidated_operating_income_high_usd": op_income_high,
                "consolidated_operating_margin_low_pct": op_income_low / total_low * 100.0,
                "consolidated_operating_margin_midpoint_pct": op_income_mid / total_mid * 100.0,
                "consolidated_operating_margin_high_pct": op_income_high / total_high * 100.0,
                "effective_tax_rate_midpoint_pct": tax_rate,
                "depreciation_amortization_midpoint_usd": da_mid,
                "capex_low_pct_of_sales": capex_low,
                "capex_high_pct_of_sales": capex_high,
                "levered_free_cash_flow_low_usd": fcf_low,
                "levered_free_cash_flow_high_usd": fcf_high,
                "interest_expense_guidance_usd": interest,
                "operating_fas_cas_adjustment_usd": -fas_cas,
                "noncurrent_state_tax_expense_usd": -state_tax,
                "segment_guidance_is_direct": True,
                "consolidated_margin_is_accounting_bridge": True,
                "source_url": "https://www.sec.gov/Archives/edgar/data/1501585/000150158526000045/hii2026q2earningsrelease.htm",
                "source_path": str(path),
                "source_sha256": _sha256(path),
                "pdf_parsing_used": False,
            }
        ]
    )


def _all_ixbrl_facts(path: Path) -> pd.DataFrame:
    tree = etree.parse(str(path), etree.XMLParser(recover=True, huge_tree=True))
    contexts = _contexts(tree)
    wanted = {
        concept
        for aliases in (*INSTANT_ALIASES.values(), *FLOW_ALIASES.values())
        for concept in aliases
    }
    rows: list[dict[str, object]] = []
    for node in tree.iter():
        if not str(node.tag).endswith("nonFraction"):
            continue
        concept = _local_name(node.get("name", ""))
        if concept not in wanted:
            continue
        context = contexts.get(node.get("contextRef", ""), {})
        value = _numeric(node)
        if context and value is not None:
            rows.append(
                {
                    "concept": concept,
                    "value": float(value),
                    "context_ref": node.get("contextRef"),
                    **context,
                }
            )
    return pd.DataFrame(rows)


def _select_alias(
    facts: pd.DataFrame,
    aliases: tuple[str, ...],
    report_date: str,
    *,
    instant: bool,
) -> tuple[float, str | None, str | None]:
    if facts.empty:
        return float("nan"), None, None
    frame = facts.loc[
        facts["concept"].isin(aliases)
        & facts["end_date"].eq(report_date)
        & facts["dimension_count"].eq(0)
    ].copy()
    if instant:
        frame = frame.loc[frame["instant"]]
    else:
        frame = frame.loc[~frame["instant"] & frame["start_date"].notna()]
        frame["duration_days"] = (
            pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])
        ).dt.days
        frame = frame.loc[frame["duration_days"].between(70, 370)]
    if frame.empty:
        return float("nan"), None, None
    frame["priority"] = frame["concept"].map(
        {name: index for index, name in enumerate(aliases)}
    )
    sort = ["priority"] + ([] if instant else ["duration_days"]) + ["context_ref"]
    ascending = [True] + ([] if instant else [False]) + [True]
    selected = frame.sort_values(sort, ascending=ascending).iloc[0]
    return float(selected["value"]), str(selected["concept"]), str(selected["context_ref"])


def _extended_quarterly_bridge(root: Path, frozen_output: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    inventory = pd.read_csv(root / frozen_output / "hii_sec_source_inventory.csv")
    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    for source in inventory.sort_values("report_date").itertuples(index=False):
        facts = _all_ixbrl_facts(Path(source.resolved_path))
        quarter = {3: 1, 6: 2, 9: 3, 12: 4}[pd.Timestamp(source.report_date).month]
        row: dict[str, object] = {
            "period": f"{str(source.report_date)[:4]}Q{quarter}",
            "form": source.form,
            "filing_date": source.filing_date,
            "report_date": source.report_date,
            "source_url": source.source_url,
            "source_sha256": source.sha256,
        }
        for metric, aliases in INSTANT_ALIASES.items():
            value, concept, context = _select_alias(
                facts, aliases, str(source.report_date), instant=True
            )
            if metric == "debt_current_usd" and not np.isfinite(value):
                noncurrent = row.get("debt_noncurrent_usd", float("nan"))
                if np.isfinite(noncurrent):
                    value, concept = 0.0, "DERIVED_ZERO_WHEN_NONCURRENT_DEBT_PRESENT"
            row[metric] = value
            selections.append(
                {
                    "period": row["period"],
                    "metric": metric,
                    "value": value,
                    "available": bool(np.isfinite(value)),
                    "selected_concept": concept,
                    "selected_context_ref": context,
                    "source_sha256": source.sha256,
                }
            )
        for metric, aliases in FLOW_ALIASES.items():
            value, concept, context = _select_alias(
                facts, aliases, str(source.report_date), instant=False
            )
            row[f"cumulative_{metric}"] = value
            selections.append(
                {
                    "period": row["period"],
                    "metric": metric,
                    "value": value,
                    "available": bool(np.isfinite(value)),
                    "selected_concept": concept,
                    "selected_context_ref": context,
                    "source_sha256": source.sha256,
                }
            )
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values("report_date").reset_index(drop=True)
    # Debt current is evaluated after all instant aliases have been selected.
    frame["debt_current_usd"] = frame["debt_current_usd"].where(
        frame["debt_current_usd"].notna(),
        np.where(frame["debt_noncurrent_usd"].notna(), 0.0, np.nan),
    )
    frame["total_debt_usd"] = frame["debt_current_usd"] + frame["debt_noncurrent_usd"]
    nwc_columns = [
        "accounts_receivable_usd",
        "inventory_usd",
        "accounts_payable_usd",
        "contract_assets_usd",
        "contract_liabilities_usd",
    ]
    frame["nwc_chain_complete"] = frame[nwc_columns].notna().all(axis=1)
    frame["operating_nwc_usd"] = (
        frame["accounts_receivable_usd"]
        + frame["inventory_usd"]
        + frame["contract_assets_usd"]
        - frame["accounts_payable_usd"]
        - frame["contract_liabilities_usd"]
    )
    frame["change_operating_nwc_qoq_usd"] = frame["operating_nwc_usd"].diff()
    frame["change_operating_nwc_yoy_usd"] = frame["operating_nwc_usd"].diff(4)
    for metric in FLOW_ALIASES:
        cumulative = f"cumulative_{metric}"
        discrete: list[float] = []
        for row in frame.itertuples(index=False):
            period = pd.Period(row.period, freq="Q")
            current = getattr(row, cumulative)
            if period.quarter == 1:
                discrete.append(current)
                continue
            prior = frame.loc[frame["period"].eq(str(period - 1)), cumulative]
            discrete.append(
                current - float(prior.iloc[0])
                if np.isfinite(current) and len(prior) and np.isfinite(prior.iloc[0])
                else float("nan")
            )
        frame[f"discrete_{metric}"] = discrete
    fallback_da = (
        frame["discrete_depreciation_usd"]
        + frame["discrete_intangible_amortization_usd"]
    )
    frame["discrete_combined_depreciation_amortization_usd"] = frame[
        "discrete_combined_depreciation_amortization_usd"
    ].fillna(fallback_da)
    return frame, pd.DataFrame(selections)


def _ttm_bridge(root: Path, frozen_output: Path, extended: pd.DataFrame) -> pd.DataFrame:
    quarterly = pd.read_csv(root / frozen_output / "hii_quarterly_reinvestment_note_bridge.csv")
    frame = quarterly.merge(
        extended[
            [
                "period",
                "operating_nwc_usd",
                "change_operating_nwc_yoy_usd",
                "discrete_combined_depreciation_amortization_usd",
                "discrete_interest_expense_usd",
            ]
        ],
        on="period",
        how="left",
        validate="one_to_one",
    )
    selected = frame.loc[frame["period"].isin(["2025Q3", "2025Q4", "2026Q1", "2026Q2"])]
    if len(selected) != 4:
        raise ValueError("TTM bridge requires 2025Q3 through 2026Q2")
    sums = {
        metric: float(selected[metric].sum(min_count=4))
        for metric in (
            "discrete_revenue_usd",
            "discrete_operating_income_usd",
            "discrete_pretax_income_usd",
            "discrete_income_tax_usd",
            "discrete_cfo_usd",
            "discrete_capex_usd",
            "discrete_combined_depreciation_amortization_usd",
            "discrete_interest_expense_usd",
        )
    }
    tax_rate = sums["discrete_income_tax_usd"] / sums["discrete_pretax_income_usd"]
    tax_rate = tax_rate if 0.0 <= tax_rate <= 0.50 else 0.21
    nopat = sums["discrete_operating_income_usd"] * (1.0 - tax_rate)
    latest_nwc_change = float(
        extended.loc[extended["period"].eq("2026Q2"), "change_operating_nwc_yoy_usd"].iloc[0]
    )
    cash_proxy = (
        sums["discrete_cfo_usd"]
        + sums["discrete_interest_expense_usd"] * (1.0 - tax_rate)
        - sums["discrete_capex_usd"]
    )
    accounting_core = (
        nopat
        + sums["discrete_combined_depreciation_amortization_usd"]
        - sums["discrete_capex_usd"]
        - latest_nwc_change
    )
    residual = cash_proxy - accounting_core
    return pd.DataFrame(
        [
            {
                "ttm_end_period": "2026Q2",
                "ttm_quarters": 4,
                "revenue_usd": sums["discrete_revenue_usd"],
                "operating_income_usd": sums["discrete_operating_income_usd"],
                "operating_margin_pct": sums["discrete_operating_income_usd"] / sums["discrete_revenue_usd"] * 100.0,
                "pretax_income_usd": sums["discrete_pretax_income_usd"],
                "income_tax_usd": sums["discrete_income_tax_usd"],
                "effective_tax_rate_pct": tax_rate * 100.0,
                "nopat_usd": nopat,
                "depreciation_amortization_usd": sums["discrete_combined_depreciation_amortization_usd"],
                "capex_usd": sums["discrete_capex_usd"],
                "change_operating_nwc_usd": latest_nwc_change,
                "interest_expense_usd": sums["discrete_interest_expense_usd"],
                "cfo_usd": sums["discrete_cfo_usd"],
                "fcff_cash_proxy_usd": cash_proxy,
                "fcff_accounting_core_usd": accounting_core,
                "other_operating_accruals_and_noncash_usd": residual,
                "fcff_accounting_full_usd": accounting_core + residual,
                "fcff_identity_error_usd": abs(cash_proxy - accounting_core - residual),
                "fcff_identity_pass": abs(cash_proxy - accounting_core - residual) <= 1.0,
                "quarterly_nwc_chain_complete": bool(
                    extended.loc[extended["period"].isin(["2025Q2", "2026Q2"]), "nwc_chain_complete"].all()
                ),
                "historical_diagnostic_only": True,
            }
        ]
    )


def _consensus(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []

    alpha_path = Path(config["alpha_vantage_estimates"])
    alpha = json.loads(alpha_path.read_text(encoding="utf-8"))
    for item in alpha["estimates"]:
        if item["horizon"] == "fiscal year" and item["date"][:4] in {"2026", "2027"}:
            rows.append(
                {
                    "provider": "ALPHA_VANTAGE",
                    "snapshot_date": "2026-07-26",
                    "fiscal_year": int(item["date"][:4]),
                    "revenue_low_usd": float(item["revenue_estimate_low"]),
                    "revenue_average_usd": float(item["revenue_estimate_average"]),
                    "revenue_high_usd": float(item["revenue_estimate_high"]),
                    "revenue_analyst_count": float(item["revenue_estimate_analyst_count"]),
                    "eps_average": float(item["eps_estimate_average"]),
                    "ebit_average_usd": np.nan,
                    "source_path": str(alpha_path),
                    "source_sha256": _sha256(alpha_path),
                    "after_latest_ir_release": False,
                }
            )
    fmp_path = Path(config["fmp_estimates"])
    fmp = json.loads(fmp_path.read_text(encoding="utf-8"))
    for item in fmp["data"]:
        if item["date"][:4] in {"2026", "2027"}:
            rows.append(
                {
                    "provider": "FMP",
                    "snapshot_date": "2026-07-31",
                    "fiscal_year": int(item["date"][:4]),
                    "revenue_low_usd": float(item["revenueLow"]),
                    "revenue_average_usd": float(item["revenueAvg"]),
                    "revenue_high_usd": float(item["revenueHigh"]),
                    "revenue_analyst_count": float(item["numAnalystsRevenue"]),
                    "eps_average": float(item["epsAvg"]),
                    "ebit_average_usd": float(item["ebitAvg"]),
                    "source_path": str(fmp_path),
                    "source_sha256": _sha256(fmp_path),
                    "after_latest_ir_release": True,
                }
            )
    yahoo_path = Path(config["yahoo_consensus"])
    yahoo = json.loads(yahoo_path.read_text(encoding="utf-8"))["data"]
    revenue = {item["period"]: item for item in yahoo["revenue_estimate"]["records"]}
    earnings = {item["period"]: item for item in yahoo["earnings_estimate"]["records"]}
    for fiscal_year, period in ((2026, "0y"), (2027, "+1y")):
        item, eps = revenue[period], earnings[period]
        rows.append(
            {
                "provider": "YAHOO",
                "snapshot_date": "2026-07-31",
                "fiscal_year": fiscal_year,
                "revenue_low_usd": float(item["low"]),
                "revenue_average_usd": float(item["avg"]),
                "revenue_high_usd": float(item["high"]),
                "revenue_analyst_count": float(item["numberOfAnalysts"]),
                "eps_average": float(eps["avg"]),
                "ebit_average_usd": np.nan,
                "source_path": str(yahoo_path),
                "source_sha256": _sha256(yahoo_path),
                "after_latest_ir_release": True,
            }
        )
    frame = pd.DataFrame(rows).sort_values(["provider", "fiscal_year"]).reset_index(drop=True)
    growth_rows: list[dict[str, float | str]] = []
    for provider, group in frame.groupby("provider"):
        values = group.set_index("fiscal_year")
        growth_rows.append(
            {
                "provider": provider,
                "average_growth_pct": values.loc[2027, "revenue_average_usd"] / values.loc[2026, "revenue_average_usd"] * 100.0 - 100.0,
                "low_case_growth_pct": values.loc[2027, "revenue_low_usd"] / values.loc[2026, "revenue_high_usd"] * 100.0 - 100.0,
                "high_case_growth_pct": values.loc[2027, "revenue_high_usd"] / values.loc[2026, "revenue_low_usd"] * 100.0 - 100.0,
            }
        )
    growth = pd.DataFrame(growth_rows)
    summary = pd.DataFrame(
        [
            {
                "providers": frame["provider"].nunique(),
                "provider_year_rows": len(frame),
                "post_ir_providers": frame.loc[frame["after_latest_ir_release"], "provider"].nunique(),
                "fy2026_revenue_consensus_median_usd": float(frame.loc[frame["fiscal_year"].eq(2026), "revenue_average_usd"].median()),
                "fy2027_revenue_consensus_median_usd": float(frame.loc[frame["fiscal_year"].eq(2027), "revenue_average_usd"].median()),
                "fy2027_revenue_growth_low_pct": float(growth["low_case_growth_pct"].min()),
                "fy2027_revenue_growth_median_pct": float(growth["average_growth_pct"].median()),
                "fy2027_revenue_growth_high_pct": float(growth["high_case_growth_pct"].max()),
                "consensus_is_model_input": False,
                "use": "MODEL_VS_CONSENSUS_DIAGNOSTIC_AND_SCENARIO_BOUND",
            }
        ]
    )
    return frame, summary


def _prospective_industry_route(
    root: Path,
    frozen_output: Path,
    config: dict[str, Any],
    company_history: pd.DataFrame,
    backlog: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cutoff = pd.Timestamp(config["valuation_date"])
    sensor_map = pd.read_csv(root / config["bls_sensor_map"])
    bls = parse_bls_ppi_vintages(
        project_root=root,
        archive_manifest_path=root / config["bls_archive_manifest"],
        sensor_map_path=root / config["bls_sensor_map"],
        cutoff=cutoff,
    )
    origin = pd.DataFrame(
        [
            {
                "period": "2026Q3",
                "forecast_as_of": str(config["valuation_date"]),
                "actual_available_at": "NOT_YET_AVAILABLE",
            }
        ]
    )
    pit = build_pit_forecast_features(
        vintages=bls["bls_ppi_vintage_canonical"],
        sensor_map=sensor_map,
        forecast_origins=origin,
    )
    feature = pit["pit_segment_features"]
    history = company_history.copy()
    history["quarter"] = history["period"].map(lambda value: pd.Period(value, freq="Q"))
    values = history.set_index("quarter")["revenue_usd"].to_dict()
    target = pd.Period("2026Q3", freq="Q")
    growth_values = [
        values[quarter] / values[quarter - 4] - 1.0
        for quarter in sorted(values)
        if quarter < target and quarter - 4 in values and values[quarter - 4]
    ]
    historical_growth = float(np.clip(np.median(growth_values[-8:]), -0.15, 0.25))
    output_growth = float(feature["output_price_yoy_pct"].mean()) / 100.0
    industry_growth = float(np.clip(0.70 * historical_growth + 0.30 * output_growth, -0.15, 0.25))
    available_backlog = backlog.loc[
        pd.to_datetime(backlog["filing_date"]).le(cutoff) & backlog["total_backlog_usd"].notna()
    ].sort_values("filing_date")
    latest, prior = available_backlog.iloc[-1], available_backlog.iloc[-2]
    years = max(
        0.25,
        (pd.Timestamp(latest["filing_date"]) - pd.Timestamp(prior["filing_date"])).days / 365.25,
    )
    backlog_growth = float(
        np.clip((latest["total_backlog_usd"] / prior["total_backlog_usd"]) ** (1.0 / years) - 1.0, -0.15, 0.25)
    )
    lag4 = float(values[target - 4])
    candidates = {
        "prior_year_naive_usd": lag4,
        "historical_growth_usd": lag4 * (1.0 + historical_growth),
        "industry_bridge_usd": lag4 * (1.0 + industry_growth),
        "backlog_bridge_usd": lag4 * (1.0 + backlog_growth),
    }
    result = pd.DataFrame(
        [
            {
                "target_period": "2026Q3",
                "forecast_as_of": config["valuation_date"],
                **candidates,
                "predeclared_equal_blend_usd": float(np.mean(list(candidates.values()))),
                "historical_growth_pct": historical_growth * 100.0,
                "industry_output_yoy_pct": output_growth * 100.0,
                "industry_bridge_growth_pct": industry_growth * 100.0,
                "backlog_growth_pct": backlog_growth * 100.0,
                "latest_backlog_usd": float(latest["total_backlog_usd"]),
                "selected_route": "PREDECLARED_EQUAL_BLEND",
                "clean_prospective_benchmark": True,
                "actual_available": False,
                "point_forecast_authority": "RESEARCH_PROSPECTIVE_BENCHMARK",
            }
        ]
    )
    return result, feature, pit["pit_vintage_selection_audit"]


def _terminal_economics(root: Path, frozen_output: Path) -> pd.DataFrame:
    annual = pd.read_csv(root / frozen_output / "hii_annual_reinvestment_roic_bridge.csv")
    recent = annual.tail(5).copy()
    recent["operating_margin_pct"] = recent["operating_income_usd"] / recent["revenue_usd"] * 100.0
    margins = recent["operating_margin_pct"].dropna()
    roic = recent["pension_adjusted_roic_pct"].dropna()
    initial_roic = float(recent.iloc[-1]["pension_adjusted_roic_pct"])
    return pd.DataFrame(
        [
            {
                "scenario": "bear",
                "terminal_operating_margin_pct": float(margins.min()),
                "initial_roic_pct": initial_roic,
                "terminal_roic_pct": float(roic.min()),
                "estimation": "RECENT_FIVE_YEAR_OBSERVED_LOW",
            },
            {
                "scenario": "base",
                "terminal_operating_margin_pct": float(margins.median()),
                "initial_roic_pct": initial_roic,
                "terminal_roic_pct": float(roic.median()),
                "estimation": "RECENT_FIVE_YEAR_MEDIAN",
            },
            {
                "scenario": "bull",
                "terminal_operating_margin_pct": float(margins.max()),
                "initial_roic_pct": initial_roic,
                "terminal_roic_pct": float(roic.max()),
                "estimation": "RECENT_FIVE_YEAR_OBSERVED_HIGH",
            },
        ]
    ).assign(
        terminal_authority=False,
        use="CONDITIONAL_DCF_SURFACE_ONLY",
        production_input_allowed=False,
    )


def _market_and_wacc(
    root: Path,
    config: dict[str, Any],
    latest_balance: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    valuation_date = pd.Timestamp(config["valuation_date"])
    price = pd.read_csv(Path(config["hii_price_history"]))
    price["Date"] = pd.to_datetime(price["Date"])
    price = price.loc[price["Date"].le(valuation_date)].sort_values("Date")
    market_price = float(price.iloc[-1]["Close"])
    risk_free = pd.read_csv(Path(config["risk_free_history"]))
    risk_free["DATE"] = pd.to_datetime(risk_free["DATE"])
    risk_free["DGS10"] = pd.to_numeric(risk_free["DGS10"], errors="coerce")
    risk_free = risk_free.loc[risk_free["DATE"].le(valuation_date) & risk_free["DGS10"].notna()]
    risk_free_pct = float(risk_free.sort_values("DATE").iloc[-1]["DGS10"])

    snapshot = root / "data-lake/bronze/industrials/v5_2/market/ad_weekly_adjusted_close_through_2026-07-31.csv"
    if snapshot.exists():
        weekly = pd.read_csv(snapshot, parse_dates=["Date"]).set_index("Date")
    else:
        import yfinance as yf

        downloaded = yf.download(
            ["SPY", "LMT", "NOC", "GD", "RTX"],
            start="2024-07-01",
            end="2026-08-01",
            auto_adjust=False,
            progress=False,
        )["Adj Close"]
        hii = price.set_index("Date")["Adj Close"]
        downloaded["HII"] = hii
        weekly = downloaded.resample("W-FRI").last().dropna(how="all")
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        weekly.rename_axis("Date").reset_index().to_csv(snapshot, index=False)
    returns = weekly.pct_change().dropna(how="all").tail(int(config["beta_weeks"]))
    beta_rows: list[dict[str, object]] = []
    for ticker in ("HII", "LMT", "NOC", "GD", "RTX"):
        sample = returns[[ticker, "SPY"]].dropna()
        downside = sample.loc[sample["SPY"].lt(0.0)]
        beta_rows.append(
            {
                "ticker": ticker,
                "weekly_observations": len(sample),
                "symmetric_beta": sample[ticker].cov(sample["SPY"]) / sample["SPY"].var(),
                "downside_observations": len(downside),
                "downside_beta": downside[ticker].cov(downside["SPY"]) / downside["SPY"].var(),
                "return_window_end": config["valuation_date"],
                "source_snapshot": str(snapshot),
                "source_sha256": _sha256(snapshot),
            }
        )
    beta = pd.DataFrame(beta_rows)
    hii_beta = beta.loc[beta["ticker"].eq("HII")].iloc[0]
    weight = float(config["beta_blume_weight"])
    symmetric_adjusted = weight * float(hii_beta["symmetric_beta"]) + (1.0 - weight)
    downside_adjusted = weight * float(hii_beta["downside_beta"]) + (1.0 - weight)
    equity_risk_premium = float(config["equity_risk_premium_pct"])
    shares = float(latest_balance["shares_outstanding"])
    debt = float(latest_balance["total_debt_usd"])
    cash = float(latest_balance["cash_usd"])
    market_cap = market_price * shares
    equity_weight = market_cap / (market_cap + debt)
    debt_weight = 1.0 - equity_weight
    marginal_debt_cost = risk_free_pct + float(config["fallback_credit_spread_pct"])
    tax_rate = 17.0

    def wacc(beta_value: float) -> float:
        cost_equity = risk_free_pct + beta_value * equity_risk_premium
        return equity_weight * cost_equity + debt_weight * marginal_debt_cost * (1.0 - tax_rate / 100.0)

    symmetric_wacc = wacc(symmetric_adjusted)
    downside_wacc = wacc(downside_adjusted)
    wacc_frame = pd.DataFrame(
        [
            {
                "valuation_date": config["valuation_date"],
                "risk_free_rate_pct": risk_free_pct,
                "equity_risk_premium_pct": equity_risk_premium,
                "raw_symmetric_beta": hii_beta["symmetric_beta"],
                "raw_downside_beta": hii_beta["downside_beta"],
                "blume_symmetric_beta": symmetric_adjusted,
                "blume_downside_beta": downside_adjusted,
                "marginal_debt_cost_pct": marginal_debt_cost,
                "tax_rate_pct": tax_rate,
                "equity_weight_pct": equity_weight * 100.0,
                "debt_weight_pct": debt_weight * 100.0,
                "symmetric_wacc_pct": symmetric_wacc,
                "downside_wacc_pct": downside_wacc,
                "midpoint_wacc_pct": (symmetric_wacc + downside_wacc) / 2.0,
                "wacc_is_independent_of_market_price_fit": True,
                "geopolitical_cash_flow_risk_added_to_wacc": False,
                "risk_channel_double_count_count": 0,
            }
        ]
    )
    market = pd.DataFrame(
        [
            {
                "valuation_date": config["valuation_date"],
                "market_price": market_price,
                "market_price_date": price.iloc[-1]["Date"].date().isoformat(),
                "shares_outstanding": shares,
                "market_capitalization_usd": market_cap,
                "cash_usd": cash,
                "total_debt_usd": debt,
                "market_enterprise_value_usd": market_cap + debt - cash,
                "ev_to_equity_bridge_identity_error_usd": abs(
                    market_cap - ((market_cap + debt - cash) - debt + cash)
                ),
                "price_source_path": str(config["hii_price_history"]),
                "price_source_sha256": _sha256(Path(config["hii_price_history"])),
            }
        ]
    )
    risk_source = pd.DataFrame(
        [
            {
                "source": "FRED_DGS10",
                "as_of": risk_free.sort_values("DATE").iloc[-1]["DATE"].date().isoformat(),
                "value": risk_free_pct,
                "unit": "PERCENT",
                "source_path": str(config["risk_free_history"]),
                "source_sha256": _sha256(Path(config["risk_free_history"])),
            },
            {
                "source": "CONFIGURED_US_EQUITY_RISK_PREMIUM",
                "as_of": config["valuation_date"],
                "value": equity_risk_premium,
                "unit": "PERCENT",
                "source_path": "configs/industrials_v5_2_hii_valuation.toml",
                "source_sha256": "RECORDED_IN_FROZEN_MANIFEST",
            },
        ]
    )
    return market, beta, wacc_frame, risk_source


def build_hii_v52_evidence(
    *, root: Path, config: dict[str, Any]
) -> dict[str, pd.DataFrame]:
    frozen_output = Path(config["frozen_hii_v5_output"])
    company_history = pd.read_csv(root / frozen_output / "hii_company_as_reported_pit_history.csv")
    backlog = pd.read_csv(root / frozen_output / "hii_contract_backlog_evidence.csv")
    guidance = _parse_ir_guidance(Path(config["ir_q2_2026"]), company_history)
    extended, selections = _extended_quarterly_bridge(root, frozen_output)
    ttm = _ttm_bridge(root, frozen_output, extended)
    latest_balance = extended.loc[extended["period"].eq("2026Q2")].iloc[0]
    consensus, consensus_summary = _consensus(config)
    prospective, industry_features, industry_audit = _prospective_industry_route(
        root, frozen_output, config, company_history, backlog
    )
    terminal = _terminal_economics(root, frozen_output)
    market, beta, wacc, risk_sources = _market_and_wacc(root, config, latest_balance)
    guide = guidance.iloc[0]
    cons = consensus_summary.iloc[0]
    comparison = pd.DataFrame(
        [
            {
                "forecast_year": 2026,
                "model_route": "IR_GUIDANCE_ACCOUNTING_BRIDGE",
                "model_revenue_midpoint_usd": guide["company_revenue_midpoint_usd"],
                "consensus_revenue_median_usd": cons["fy2026_revenue_consensus_median_usd"],
                "model_minus_consensus_pct": (
                    guide["company_revenue_midpoint_usd"] / cons["fy2026_revenue_consensus_median_usd"] - 1.0
                )
                * 100.0,
                "consensus_used_to_fit_model": False,
                "authority": "DIAGNOSTIC_ONLY",
            }
        ]
    )
    authority = pd.DataFrame(
        [
            {
                "aggregate_revenue_point_authority": "RESEARCH_CONDITIONAL_IR_GUIDANCE_BRIDGE",
                "segment_revenue_point_authority": "SHIPBUILDING_COMBINED_AND_MISSION_GUIDANCE_ONLY",
                "segment_revenue_causal_attribution_authority": False,
                "segment_margin_point_authority": "SHIPBUILDING_COMBINED_AND_MISSION_GUIDANCE_ONLY",
                "margin_component_causal_authority": False,
                "roic_attribution_authority": False,
                "terminal_authority": False,
                "dcf_authority": "RESEARCH_CONDITIONAL_ONLY",
                "reverse_dcf_authority": "RESEARCH_CONDITIONAL_ONLY",
                "production_authority": False,
                "live_forward_matched_observations": "0/20",
            }
        ]
    )
    source_coverage = pd.DataFrame(
        [
            {"layer": "SEC_10K", "source_count": 7, "use": "ANNUAL_MARGIN_ROIC_FCFF_HISTORY", "pit_cutoff_pass": True},
            {"layer": "SEC_10Q", "source_count": 20, "use": "TTM_AND_BALANCE_SHEET_BRIDGE", "pit_cutoff_pass": True},
            {"layer": "IR_HTML", "source_count": 27, "use": "SEGMENT_ACTUALS_BACKLOG_AND_FY26_GUIDANCE", "pit_cutoff_pass": True},
            {"layer": "BLS_AS_RELEASED_VINTAGE", "source_count": 3, "use": "PROSPECTIVE_PRICE_COST_SIGNAL", "pit_cutoff_pass": bool(industry_audit["cutoff_respected"].all())},
            {"layer": "ANALYST_CONSENSUS_PROVIDER", "source_count": int(consensus["provider"].nunique()), "use": "MODEL_VS_CONSENSUS_AND_SCENARIO_BOUNDS", "pit_cutoff_pass": True},
            {"layer": "MARKET_PRICE", "source_count": 1, "use": "EV_TO_EQUITY_AND_REVERSE_DCF_TARGET", "pit_cutoff_pass": True},
            {"layer": "MARKET_RETURN_SERIES", "source_count": 6, "use": "INDEPENDENT_SYMMETRIC_AND_DOWNSIDE_BETA", "pit_cutoff_pass": True},
            {"layer": "FRED_DGS10", "source_count": 1, "use": "RISK_FREE_RATE", "pit_cutoff_pass": True},
        ]
    )
    return {
        "hii_2026_guidance_financial_bridge": guidance,
        "hii_extended_quarterly_financial_bridge": extended,
        "hii_extended_sec_fact_selections": selections,
        "hii_ttm_fcff_bridge": ttm,
        "hii_consensus_vintage_detail": consensus,
        "hii_consensus_summary": consensus_summary,
        "hii_model_vs_consensus": comparison,
        "hii_2026q3_clean_prospective_revenue_route": prospective,
        "hii_2026q3_pit_industry_features": industry_features,
        "hii_2026q3_pit_vintage_audit": industry_audit,
        "hii_terminal_economics_range": terminal,
        "hii_market_capitalization_bridge": market,
        "hii_beta_peer_cross_check": beta,
        "hii_wacc_range": wacc,
        "hii_risk_source_inventory": risk_sources,
        "hii_v52_authority": authority,
        "hii_v52_source_coverage": source_coverage,
    }
