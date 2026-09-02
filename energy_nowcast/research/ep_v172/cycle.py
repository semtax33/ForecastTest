from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v17.fnsd import _adsh_records, _select_text_record


BUYER_CIK = {
    "COP": "0001163165",
    "DVN": "0001090012",
    "EOG": "0000821189",
    "FANG": "0001539838",
}
ELIGIBLE_DENOMINATOR_RATIO = 0.02


def _record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _annual_company_fact(
    companyfacts_root: Path, ticker: str, year: int, tag: str
) -> tuple[float, str, str]:
    cik = BUYER_CIK.get(ticker)
    if not cik:
        return np.nan, "", ""
    path = companyfacts_root / f"CIK{cik}.json"
    facts = json.loads(path.read_text(encoding="utf-8"))
    records = (
        facts.get("facts", {})
        .get("us-gaap", {})
        .get(tag, {})
        .get("units", {})
        .get("USD", [])
    )
    candidates = [
        record
        for record in records
        if record.get("form") == "10-K"
        and record.get("end") == f"{year}-12-31"
        and record.get("start") == f"{year}-01-01"
    ]
    if not candidates:
        return np.nan, "", ""
    candidates.sort(key=lambda record: str(record.get("filed", "")), reverse=True)
    selected = candidates[0]
    return float(selected["val"]), tag, _record_hash(selected)


def _build_production_evidence(
    *,
    reserve_panel_path: Path,
    fang_panel_path: Path,
    supplement_registry_path: Path,
    fnsd_root: Path,
) -> pd.DataFrame:
    reserve = pd.read_csv(reserve_panel_path)
    reserve = reserve.loc[
        reserve["ticker"].isin(["DVN", "EOG"]),
        [
            "ticker",
            "year",
            "production_mboe",
            "production_independently_verified",
            "source_file",
        ],
    ].copy()
    reserve["production_source_semantics"] = "SEC_RESERVE_ROLLFORWARD_PRODUCTION"
    reserve["production_evidence_proven"] = True
    reserve["source_record_sha256"] = ""

    fang = pd.read_csv(fang_panel_path)[
        ["ticker", "year", "combined_mboe", "source_file"]
    ].rename(columns={"combined_mboe": "production_mboe"})
    fang["production_independently_verified"] = True
    fang["production_source_semantics"] = "IR_SELECTED_OPERATING_DATA_ACTUAL_COMPONENT_IDENTITY"
    fang["production_evidence_proven"] = True
    fang["source_record_sha256"] = ""

    supplement_rows: list[dict[str, Any]] = []
    supplements = pd.read_csv(supplement_registry_path, dtype={"adsh": str})
    for item in supplements.to_dict("records"):
        folder = fnsd_root / str(item["fnsd_folder"])
        disclosure, record_hash = _select_text_record(
            _adsh_records(folder / "txt.tsv", str(item["adsh"])),
            str(item["text_tag"]),
        )
        phrase_proven = str(item["proof_phrase"]).casefold() in disclosure.casefold()
        supplement_rows.append(
            {
                "ticker": item["ticker"],
                "year": int(item["year"]),
                "production_mboe": float(item["production_mboe"]),
                "production_independently_verified": phrase_proven,
                "source_file": str(folder / "txt.tsv"),
                "production_source_semantics": item["production_source_semantics"],
                "production_evidence_proven": phrase_proven,
                "source_record_sha256": record_hash,
            }
        )
    supplement = pd.DataFrame(supplement_rows)
    panel = pd.concat([reserve, fang, supplement], ignore_index=True)
    priority = {
        "IR_SELECTED_OPERATING_DATA_ACTUAL_COMPONENT_IDENTITY": 3,
        "SEC_RESERVE_ROLLFORWARD_PRODUCTION": 2,
        "SEC_RESERVE_TABLE_ROUNDED_COMBINED_PRODUCTION": 1,
    }
    panel["source_priority"] = panel["production_source_semantics"].map(priority)
    panel = (
        panel.sort_values(["ticker", "year", "source_priority"], ascending=[True, True, False])
        .drop_duplicates(["ticker", "year"], keep="first")
        .drop(columns="source_priority")
        .reset_index(drop=True)
    )
    panel["research_only"] = True
    return panel


def _build_cycle_reference(
    *,
    through_cycle_path: Path,
    price_mix_path: Path,
    v14_cross_check_path: Path,
    annual_organic: pd.DataFrame,
    production: pd.DataFrame,
    companyfacts_root: Path,
    fang_accounting_path: Path,
) -> pd.DataFrame:
    economics = pd.read_csv(through_cycle_path)[
        ["ticker", "normalized_margin_q50_pct", "normalization_confidence"]
    ]
    prices = pd.read_csv(price_mix_path)[
        [
            "ticker",
            "normalized_gross_price_q50_per_boe",
            "production_mix_status",
            "mix_method",
        ]
    ]
    v14 = pd.read_csv(v14_cross_check_path)[
        [
            "ticker",
            "v14_realized_basis_adjusted_price_q50_per_boe",
            "v14_known_cost_accounting_margin_q50_pct",
            "v14_cost_scope_status",
        ]
    ]
    reference = economics.merge(prices, on="ticker", how="left").merge(
        v14, on="ticker", how="left"
    )
    use_v14 = (
        reference["v14_realized_basis_adjusted_price_q50_per_boe"].notna()
        & reference["v14_known_cost_accounting_margin_q50_pct"].notna()
    )
    reference["normalized_price_per_boe"] = np.where(
        use_v14,
        reference["v14_realized_basis_adjusted_price_q50_per_boe"],
        reference["normalized_gross_price_q50_per_boe"],
    )
    reference["normalized_operating_margin_pct"] = np.where(
        use_v14,
        reference["v14_known_cost_accounting_margin_q50_pct"],
        reference["normalized_margin_q50_pct"],
    )
    reference["normalized_unit_cost_per_boe"] = reference[
        "normalized_price_per_boe"
    ] * (1.0 - reference["normalized_operating_margin_pct"] / 100.0)
    reference["normalized_unit_cost_observations"] = 0
    reference["unit_cost_source_bundle_sha256"] = ""
    reference["unit_cost_scope"] = (
        "V12_HIERARCHICAL_MARGIN_IMPLIED_ALL_IN_UNIT_COST_NOT_INDEPENDENT"
    )

    component_tags = (
        "ResultsOfOperationsProductionOrLiftingCosts",
        "ResultsOfOperationsExplorationExpense",
        "ResultsOfOperationsDepreciationDepletionAmortizationAndAccretion",
        "GeneralAndAdministrativeExpense",
    )
    for ticker in reference["ticker"]:
        ticker_production = production.loc[production["ticker"].eq(ticker)]
        unit_costs: list[float] = []
        hashes: list[str] = []
        for production_row in ticker_production.to_dict("records"):
            year = int(production_row["year"])
            components: list[float] = []
            year_hashes: list[str] = []
            for tag in component_tags:
                value, _, record_hash = _annual_company_fact(
                    companyfacts_root, ticker, year, tag
                )
                if pd.isna(value):
                    components = []
                    break
                components.append(value)
                year_hashes.append(record_hash)
            if components and float(production_row["production_mboe"]) > 0:
                unit_costs.append(
                    sum(components)
                    / (float(production_row["production_mboe"]) * 1_000.0)
                )
                hashes.extend(year_hashes)
        if len(unit_costs) >= 3:
            mask = reference["ticker"].eq(ticker)
            reference.loc[mask, "normalized_unit_cost_per_boe"] = float(
                np.median(unit_costs)
            )
            reference.loc[mask, "normalized_unit_cost_observations"] = len(unit_costs)
            reference.loc[mask, "unit_cost_source_bundle_sha256"] = hashlib.sha256(
                "|".join(sorted(hashes)).encode("ascii")
            ).hexdigest()
            reference.loc[mask, "unit_cost_scope"] = (
                "SEC_UPSTREAM_LIFTING_EXPLORATION_DDA_PLUS_COMPANY_GA_COMPONENT_SCOPE"
            )

    fang_accounting = pd.read_csv(fang_accounting_path)
    fang_production = production.loc[production["ticker"].eq("FANG"), ["year", "production_mboe"]]
    fang_cost = fang_accounting.merge(fang_production, on="year", how="inner")
    fang_components = [
        "lease_operating_usd_millions",
        "production_tax_usd_millions",
        "transport_usd_millions",
        "dda_usd_millions",
        "g_and_a_usd_millions",
        "other_operating_expense_usd_millions",
    ]
    if len(fang_cost) >= 3:
        fang_cost["all_in_unit_cost_per_boe"] = (
            fang_cost[fang_components].fillna(0.0).sum(axis=1) * 1_000_000.0
            / (fang_cost["production_mboe"] * 1_000.0)
        )
        mask = reference["ticker"].eq("FANG")
        reference.loc[mask, "normalized_unit_cost_per_boe"] = float(
            fang_cost["all_in_unit_cost_per_boe"].median()
        )
        reference.loc[mask, "normalized_unit_cost_observations"] = len(fang_cost)
        reference.loc[mask, "unit_cost_source_bundle_sha256"] = hashlib.sha256(
            "|".join(sorted(fang_accounting["source_sha256"].astype(str))).encode(
                "ascii"
            )
        ).hexdigest()
        reference.loc[mask, "unit_cost_scope"] = (
            "V161_ACCOUNTING_PROVEN_FANG_LIFTING_TAX_TRANSPORT_DDA_GA_OTHER_COMPONENT_SCOPE"
        )

    reference["normalized_pre_tax_unit_margin_per_boe"] = (
        reference["normalized_price_per_boe"]
        - reference["normalized_unit_cost_per_boe"]
    )
    reference["normalized_operating_margin_pct"] = (
        reference["normalized_pre_tax_unit_margin_per_boe"]
        / reference["normalized_price_per_boe"]
        * 100.0
    )
    tax = (
        annual_organic.groupby("ticker", as_index=False)["effective_tax_rate"]
        .median()
        .rename(columns={"effective_tax_rate": "normalized_tax_rate"})
    )
    tax["normalized_tax_rate"] = tax["normalized_tax_rate"].clip(0.0, 0.35)
    reference = reference.merge(tax, on="ticker", how="left")
    reference["normalized_after_tax_unit_margin_per_boe"] = reference[
        "normalized_pre_tax_unit_margin_per_boe"
    ] * (1.0 - reference["normalized_tax_rate"])
    reference["cycle_normalization_route"] = np.select(
        [
            reference["unit_cost_scope"].str.startswith("V161_ACCOUNTING_PROVEN"),
            reference["unit_cost_scope"].str.startswith("SEC_UPSTREAM"),
        ],
        [
            "V14_BASIS_ADJUSTED_PRICE_PLUS_V161_ACCOUNTING_PROVEN_COMPONENT_UNIT_COST",
            "V13_NORMALIZED_COMMODITY_PRICE_PLUS_SEC_COMPONENT_UNIT_COST",
        ],
        default="V13_NORMALIZED_COMMODITY_PRICE_AND_V12_HIERARCHICAL_MARGIN_IMPLIED_UNIT_COST",
    )
    reference["independent_complete_unit_cost_scope"] = reference[
        "normalized_unit_cost_observations"
    ].ge(3)
    reference["terminal_input_allowed"] = False
    reference["research_only"] = True
    return reference.sort_values("ticker").reset_index(drop=True)


def _reported_revenue_per_boe(
    *,
    ticker: str,
    year: int,
    production_mboe: float,
    companyfacts_root: Path,
    annual_cost_scope: pd.DataFrame,
    ttm_financial: pd.DataFrame,
) -> tuple[float, str, str]:
    cost_row = annual_cost_scope.loc[
        annual_cost_scope["ticker"].eq(ticker)
        & annual_cost_scope["year"].eq(year)
        & annual_cost_scope["upstream_revenue_per_boe"].notna()
    ]
    if len(cost_row) == 1:
        return (
            float(cost_row.iloc[0]["upstream_revenue_per_boe"]),
            "V14_EXACT_UPSTREAM_REVENUE_PER_BOE",
            "",
        )
    revenue, _, record_hash = _annual_company_fact(
        companyfacts_root,
        ticker,
        year,
        "ResultsOfOperationsRevenueFromOilAndGasProducingActivities",
    )
    if pd.notna(revenue) and production_mboe > 0:
        return (
            revenue / (production_mboe * 1_000.0),
            "SEC_RESULTS_OF_OPERATIONS_UPSTREAM_REVENUE_PER_BOE",
            record_hash,
        )
    financial = ttm_financial.loc[
        ttm_financial["ticker"].eq(ticker)
        & ttm_financial["quarter"].astype(str).eq(f"{year}Q4")
    ]
    if len(financial) == 1 and production_mboe > 0:
        return (
            float(financial.iloc[0]["ttm_revenue"]) / (production_mboe * 1_000.0),
            "CONSOLIDATED_TTM_REVENUE_PER_BOE_FALLBACK",
            "",
        )
    return np.nan, "LOCKED_NO_REVENUE_PER_BOE", ""


def build_cycle_normalized_cohorts(
    *,
    acquisition_proof: pd.DataFrame,
    acquiree_nopat: pd.DataFrame,
    v171_company_year: pd.DataFrame,
    v171_cohorts: pd.DataFrame,
    annual_organic: pd.DataFrame,
    through_cycle_path: Path,
    price_mix_path: Path,
    v14_cross_check_path: Path,
    annual_cost_scope_path: Path,
    fang_accounting_path: Path,
    reserve_panel_path: Path,
    fang_panel_path: Path,
    supplement_registry_path: Path,
    fnsd_root: Path,
    companyfacts_root: Path,
    ttm_financial_path: Path,
) -> dict[str, pd.DataFrame]:
    production = _build_production_evidence(
        reserve_panel_path=reserve_panel_path,
        fang_panel_path=fang_panel_path,
        supplement_registry_path=supplement_registry_path,
        fnsd_root=fnsd_root,
    )
    reference = _build_cycle_reference(
        through_cycle_path=through_cycle_path,
        price_mix_path=price_mix_path,
        v14_cross_check_path=v14_cross_check_path,
        annual_organic=annual_organic,
        production=production,
        companyfacts_root=companyfacts_root,
        fang_accounting_path=fang_accounting_path,
    )
    annual_cost_scope = pd.read_csv(annual_cost_scope_path)
    ttm_financial = pd.read_parquet(ttm_financial_path)
    event_lookup = acquisition_proof.set_index(["ticker", "fiscal_year"])
    nap_lookup = acquiree_nopat.set_index(["ticker", "fiscal_year"])
    v171_bridge_lookup = v171_company_year.set_index(["ticker", "year"])

    panel_rows: list[dict[str, Any]] = []
    business_events = acquisition_proof.loc[
        acquisition_proof["event_type"].eq("business_combination")
        & acquisition_proof["acquiree_net_income_since_close_usd"].notna()
    ]
    for event in business_events.to_dict("records"):
        ticker = str(event["ticker"])
        deal_year = int(event["fiscal_year"])
        ref = reference.loc[reference["ticker"].eq(ticker)]
        if len(ref) != 1:
            continue
        ref_row = ref.iloc[0]
        event_cycle_scope = bool(
            v171_bridge_lookup.loc[(ticker, deal_year)][
                "company_year_mna_scope_fully_bridged"
            ]
        )
        for year in range(deal_year - 1, deal_year + 3):
            prod = production.loc[
                production["ticker"].eq(ticker) & production["year"].eq(year)
            ]
            if len(prod) != 1:
                continue
            prod_row = prod.iloc[0]
            normalized_nopat = (
                float(prod_row["production_mboe"])
                * 1_000.0
                * float(ref_row["normalized_after_tax_unit_margin_per_boe"])
            )
            panel_rows.append(
                {
                    "ticker": ticker,
                    "event_name": event["event_name"],
                    "deal_year": deal_year,
                    "year": year,
                    "production_mboe": prod_row["production_mboe"],
                    "production_source_semantics": prod_row[
                        "production_source_semantics"
                    ],
                    "production_evidence_proven": prod_row[
                        "production_evidence_proven"
                    ],
                    "normalized_price_per_boe": ref_row[
                        "normalized_price_per_boe"
                    ],
                    "normalized_unit_cost_per_boe": ref_row[
                        "normalized_unit_cost_per_boe"
                    ],
                    "normalized_pre_tax_unit_margin_per_boe": ref_row[
                        "normalized_pre_tax_unit_margin_per_boe"
                    ],
                    "normalized_tax_rate": ref_row["normalized_tax_rate"],
                    "normalized_after_tax_unit_margin_per_boe": ref_row[
                        "normalized_after_tax_unit_margin_per_boe"
                    ],
                    "company_cycle_normalized_nopat_usd": normalized_nopat,
                    "cycle_normalization_route": ref_row[
                        "cycle_normalization_route"
                    ],
                    "event_company_year_scope_complete": event_cycle_scope,
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
    cycle_panel = pd.DataFrame(panel_rows).sort_values(
        ["deal_year", "ticker", "year"]
    ).reset_index(drop=True)
    cycle_panel["prior_year_company_cycle_normalized_nopat_usd"] = cycle_panel.groupby(
        ["ticker", "deal_year"]
    )["company_cycle_normalized_nopat_usd"].shift(1)
    cycle_panel["company_cycle_normalized_delta_nopat_usd"] = (
        cycle_panel["company_cycle_normalized_nopat_usd"]
        - cycle_panel["prior_year_company_cycle_normalized_nopat_usd"]
    )
    cycle_panel["acquiree_production_since_close_proxy_mboe"] = 0.0
    cycle_panel["acquiree_cycle_normalized_nopat_same_period_proxy_usd"] = 0.0
    cycle_panel["acquiree_production_proxy_status"] = "NOT_EVENT_YEAR"
    cycle_panel["reported_revenue_per_boe"] = np.nan
    cycle_panel["reported_revenue_per_boe_source"] = ""
    cycle_panel["reported_revenue_per_boe_record_sha256"] = ""
    for index, row in cycle_panel.loc[cycle_panel["year"].eq(cycle_panel["deal_year"])].iterrows():
        event = event_lookup.loc[(row["ticker"], int(row["deal_year"]))]
        revenue_per_boe, revenue_source, revenue_hash = _reported_revenue_per_boe(
            ticker=str(row["ticker"]),
            year=int(row["year"]),
            production_mboe=float(row["production_mboe"]),
            companyfacts_root=companyfacts_root,
            annual_cost_scope=annual_cost_scope,
            ttm_financial=ttm_financial,
        )
        acquiree_revenue = float(event["acquiree_revenue_since_close_usd"])
        acquired_production = (
            acquiree_revenue / revenue_per_boe / 1_000.0
            if pd.notna(revenue_per_boe) and revenue_per_boe > 0
            else np.nan
        )
        acquired_cycle_nopat = (
            acquired_production
            * 1_000.0
            * float(row["normalized_after_tax_unit_margin_per_boe"])
            if pd.notna(acquired_production)
            else np.nan
        )
        cycle_panel.loc[index, "reported_revenue_per_boe"] = revenue_per_boe
        cycle_panel.loc[index, "reported_revenue_per_boe_source"] = revenue_source
        cycle_panel.loc[index, "reported_revenue_per_boe_record_sha256"] = revenue_hash
        cycle_panel.loc[index, "acquiree_production_since_close_proxy_mboe"] = acquired_production
        cycle_panel.loc[
            index, "acquiree_cycle_normalized_nopat_same_period_proxy_usd"
        ] = acquired_cycle_nopat
        cycle_panel.loc[index, "acquiree_production_proxy_status"] = (
            "REVENUE_DIVIDED_BY_BUYER_REPORTED_REVENUE_PER_BOE_PROXY"
            if pd.notna(acquired_production)
            else "LOCKED_NO_REVENUE_PER_BOE"
        )
    cycle_panel["organic_cycle_normalized_delta_nopat_proxy_usd"] = (
        cycle_panel["company_cycle_normalized_delta_nopat_usd"]
        - cycle_panel["acquiree_cycle_normalized_nopat_same_period_proxy_usd"]
    )
    cycle_panel["cycle_normalized_annual_scope_complete"] = (
        cycle_panel["company_cycle_normalized_delta_nopat_usd"].notna()
        & cycle_panel["production_evidence_proven"]
        & (
            ~cycle_panel["year"].eq(cycle_panel["deal_year"])
            | (
                cycle_panel["event_company_year_scope_complete"]
                & cycle_panel["acquiree_production_since_close_proxy_mboe"].notna()
            )
        )
    )

    cohort_rows: list[dict[str, Any]] = []
    for (ticker, deal_year), group in v171_cohorts.groupby(["ticker", "deal_year"]):
        group = group.sort_values("cohort_offset")
        nap = nap_lookup.loc[(ticker, int(deal_year))]
        reported_all_scope = True
        cycle_all_scope = True
        reported_cumulative_numerator = 0.0
        cycle_cumulative_numerator = 0.0
        cumulative_denominator = 0.0
        observed = 0
        opening = float(
            v171_bridge_lookup.loc[(ticker, int(deal_year))][
                "opening_invested_capital_usd"
            ]
        )
        threshold = abs(opening) * ELIGIBLE_DENOMINATOR_RATIO
        for source in group.to_dict("records"):
            observed += 1
            offset = int(source["cohort_offset"])
            denominator = float(
                source["annual_organic_delta_invested_capital_proxy_usd"]
            )
            base_numerator = float(
                source["annual_organic_delta_nopat_after_tax_proxy_usd"]
            )
            if offset == 0:
                interest_adjustment = nap[
                    "acquired_current_period_after_tax_interest_proxy_usd"
                ]
                reported_numerator = (
                    base_numerator - float(interest_adjustment)
                    if bool(nap["acquiree_nopat_bridge_ready"])
                    else base_numerator
                )
                reported_scope = bool(
                    source["annual_scope_complete"]
                    and nap["acquiree_nopat_bridge_ready"]
                )
                reported_status = (
                    nap["acquiree_nopat_bridge_status"]
                    if bool(source["annual_scope_complete"])
                    else f"LOCKED_COMPANY_YEAR_MNA_SCOPE__{source['cohort_status']}"
                )
            else:
                interest_adjustment = 0.0
                reported_numerator = base_numerator
                reported_scope = bool(source["annual_scope_complete"])
                reported_status = (
                    "BUYER_REPORTED_NOPAT_SUBSEQUENT_YEAR"
                    if bool(source["annual_scope_complete"])
                    else f"LOCKED_COMPANY_YEAR_MNA_SCOPE__{source['cohort_status']}"
                )
            cycle = cycle_panel.loc[
                cycle_panel["ticker"].eq(ticker)
                & cycle_panel["deal_year"].eq(int(deal_year))
                & cycle_panel["year"].eq(int(source["observation_year"]))
            ]
            if len(cycle) == 1:
                cycle_row = cycle.iloc[0]
                cycle_numerator = float(
                    cycle_row["organic_cycle_normalized_delta_nopat_proxy_usd"]
                )
                cycle_scope = bool(
                    cycle_row["cycle_normalized_annual_scope_complete"]
                    and source["annual_scope_complete"]
                )
                cycle_status = (
                    cycle_row["cycle_normalization_route"]
                    if bool(source["annual_scope_complete"])
                    else f"LOCKED_COMPANY_YEAR_MNA_SCOPE__{source['cohort_status']}"
                )
            else:
                cycle_numerator = np.nan
                cycle_scope = False
                cycle_status = "LOCKED_MISSING_PRODUCTION_OR_NORMALIZED_ECONOMICS"
            reported_all_scope = reported_all_scope and reported_scope
            cycle_all_scope = cycle_all_scope and cycle_scope
            cumulative_denominator += denominator
            if reported_all_scope:
                reported_cumulative_numerator += reported_numerator
            if cycle_all_scope:
                cycle_cumulative_numerator += cycle_numerator
            reported_annual_roic = (
                reported_numerator / denominator * 100.0
                if reported_scope and denominator > threshold
                else np.nan
            )
            cycle_annual_roic = (
                cycle_numerator / denominator * 100.0
                if cycle_scope and denominator > threshold
                else np.nan
            )
            reported_cumulative_roic = (
                reported_cumulative_numerator / cumulative_denominator * 100.0
                if reported_all_scope and cumulative_denominator > threshold
                else np.nan
            )
            cycle_cumulative_roic = (
                cycle_cumulative_numerator / cumulative_denominator * 100.0
                if cycle_all_scope and cumulative_denominator > threshold
                else np.nan
            )
            is_t2 = offset == 2 and observed == 3
            cohort_rows.append(
                {
                    "ticker": ticker,
                    "event_name": source["event_name"],
                    "deal_year": int(deal_year),
                    "cohort_offset": offset,
                    "observation_year": int(source["observation_year"]),
                    "year_label": source["year_label"],
                    "parent_annual_scope_complete": bool(
                        source["annual_scope_complete"]
                    ),
                    "parent_cohort_status": source["cohort_status"],
                    "organic_invested_capital_proxy_usd": denominator,
                    "v171_net_income_based_organic_numerator_proxy_usd": base_numerator,
                    "acquiree_after_tax_interest_adjustment_usd": interest_adjustment,
                    "reported_organic_nopat_bridge_usd": reported_numerator,
                    "reported_organic_nopat_annual_scope_complete": reported_scope,
                    "reported_organic_nopat_bridge_status": reported_status,
                    "reported_organic_nopat_roic_pct": reported_annual_roic,
                    "cycle_normalized_organic_nopat_proxy_usd": cycle_numerator,
                    "cycle_normalized_annual_scope_complete": cycle_scope,
                    "cycle_normalization_status": cycle_status,
                    "cycle_normalized_organic_roic_proxy_pct": cycle_annual_roic,
                    "reported_cumulative_organic_nopat_roic_pct": reported_cumulative_roic,
                    "cycle_normalized_cumulative_organic_roic_proxy_pct": cycle_cumulative_roic,
                    "reported_nopat_cohort_complete": is_t2 and reported_all_scope,
                    "cycle_normalized_cohort_complete": is_t2 and cycle_all_scope,
                    "reported_vs_cycle_separated": True,
                    "organic_company_roic_validated": False,
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
    cohorts = pd.DataFrame(cohort_rows).sort_values(
        ["deal_year", "ticker", "cohort_offset"]
    ).reset_index(drop=True)
    return {
        "cycle_normalization_reference": reference,
        "cycle_production_evidence": production,
        "cycle_normalized_company_year_panel": cycle_panel,
        "reported_vs_cycle_normalized_deal_cohorts": cohorts,
    }
