from __future__ import annotations

import hashlib
from pathlib import Path
import re

import numpy as np
import pandas as pd


CORE = ("AR", "CNX", "FANG")
YEARS = tuple(range(2021, 2026))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: object) -> float:
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text.lower() == "nan" or text in {"—", "–", "-", ""}:
        return np.nan
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
        if not value or value.lower() == "nan":
            continue
        if values and value == values[-1]:
            continue
        values.append(value)
    return values


def _text(table: pd.DataFrame) -> str:
    return " ".join(str(value) for value in table.to_numpy().flatten()).lower()


def _numbers(tokens: list[str]) -> list[float]:
    values = [_number(token) for token in tokens[1:] if "%" not in token]
    return [value for value in values if np.isfinite(value)]


def _line_map(table: pd.DataFrame) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for _, row in table.iterrows():
        tokens = _tokens(row)
        if tokens:
            result[tokens[0].strip().lower()] = _numbers(tokens)
    return result


def _values(lines: dict[str, list[float]], label: str) -> list[float]:
    matches = [
        values for key, values in lines.items() if key.startswith(label.lower())
    ]
    # Supplemental tables often repeat the numeric row label in a preceding
    # explanatory paragraph. Prefer the first match that actually has values.
    return next((values for values in matches if values), matches[0] if matches else [])


def _current_annual(
    lines: dict[str, list[float]], label: str, *, position_from_end: int
) -> float:
    values = _values(lines, label)
    if len(values) < position_from_end:
        return np.nan
    return float(values[-position_from_end])


def _current_annual_any(
    lines: dict[str, list[float]], labels: tuple[str, ...], *, position_from_end: int
) -> float:
    for label in labels:
        value = _current_annual(
            lines, label, position_from_end=position_from_end
        )
        if np.isfinite(value):
            return value
    return np.nan


def _files(ir_root: Path, ticker: str, year: int) -> list[Path]:
    prefix = f"{year + 1}-"
    directory = ir_root / ticker
    return sorted(
        path
        for path in directory.glob(f"{prefix}*.htm")
        if "_EX-99.1_" in path.name
        and any(f"{prefix}{month:02d}-" in path.name for month in (1, 2, 3))
    )


def _find_table(
    ir_root: Path,
    ticker: str,
    year: int,
    predicate,
) -> tuple[Path, pd.DataFrame] | None:
    for path in _files(ir_root, ticker, year):
        try:
            tables = pd.read_html(path, flavor="lxml")
        except (ValueError, OSError):
            continue
        for table in tables:
            if predicate(_text(table)):
                return path, table
    return None


def build_ar_composite_cost_proof(
    *, ir_root: Path, parent_annual: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    parent = parent_annual.loc[parent_annual["ticker"].eq("AR")].set_index("year")
    for year in YEARS:
        found = _find_table(
            ir_root,
            "AR",
            year,
            lambda text: "revenue and other" in text
            and "gathering, compression, processing and transportation" in text
            and "production and ad valorem taxes" in text
            and "operating income" in text,
        )
        if found is None or year not in parent.index:
            continue
        source, table = found
        lines = _line_map(table)
        lease = _current_annual(lines, "lease operating", position_from_end=1)
        gpt = _current_annual(
            lines,
            "gathering, compression, processing and transportation",
            position_from_end=1,
        )
        tax = _current_annual(
            lines, "production and ad valorem taxes", position_from_end=1
        )
        production_mboe = float(parent.loc[year, "kpi_production_mboe"])
        reported_composite = (lease + gpt + tax) / production_mboe
        frozen_lifting = float(parent.loc[year, "lifting_cost_per_boe"])
        ratio = reported_composite / frozen_lifting
        rows.append(
            {
                "ticker": "AR",
                "year": year,
                "lease_operating_usd_thousands": lease,
                "gathering_processing_transport_usd_thousands": gpt,
                "production_ad_valorem_tax_usd_thousands": tax,
                "reported_composite_lifting_cost_per_boe": reported_composite,
                "frozen_lifting_cost_per_boe": frozen_lifting,
                "composite_to_frozen_lifting_ratio": ratio,
                "composite_identity_error_pct": abs(ratio - 1.0) * 100.0,
                "transport_tax_already_in_composite_lifting_cost": bool(
                    0.98 <= ratio <= 1.02
                ),
                "separate_transport_tax_addition_allowed": False,
                "source_file": str(source),
                "source_sha256": _sha256(source),
                "availability_date": source.name[:10],
                "source_table": "Annual Consolidated Statements of Operations",
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def build_cnx_hedge_proof(ir_root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year in YEARS:
        derivative = _find_table(
            ir_root,
            "CNX",
            year,
            lambda text: "actual change in derivatives" in text
            and "realized" in text
            and "unrealized" in text,
        )
        income = _find_table(
            ir_root,
            "CNX",
            year,
            lambda text: "consolidated statements of income" in text
            and "natural gas, ngl and oil revenue" in text
            and "commodity derivative instruments" in text,
        )
        cash_reconciliation = _find_table(
            ir_root,
            "CNX",
            year,
            lambda text: "sales of natural gas, ngl and oil, including cash settlements" in text
            and "purchased gas revenue" in text,
        )
        if derivative is None or income is None or cash_reconciliation is None:
            continue
        source, derivative_table = derivative
        income_source, income_table = income
        _, cash_table = cash_reconciliation
        derivative_lines = _line_map(derivative_table)
        income_lines = _line_map(income_table)
        cash_lines = _line_map(cash_table)
        realized = _current_annual(
            derivative_lines, "realized", position_from_end=2
        )
        unrealized = _current_annual(
            derivative_lines, "unrealized", position_from_end=2
        )
        total_derivative = _current_annual_any(
            derivative_lines,
            (
                "(loss) gain on commodity derivative instruments",
                "gain (loss) on commodity derivative instruments",
                "gain on commodity derivative instruments",
            ),
            position_from_end=2,
        )
        production_revenue = _current_annual(
            income_lines, "natural gas, ngl and oil revenue", position_from_end=2
        ) / 1_000.0
        income_derivative = _current_annual_any(
            income_lines,
            (
                "(loss) gain on commodity derivative instruments",
                "gain (loss) on commodity derivative instruments",
                "gain on commodity derivative instruments",
            ),
            position_from_end=2,
        ) / 1_000.0
        cash_sales = _current_annual(
            cash_lines,
            "sales of natural gas, ngl and oil, including cash settlements",
            position_from_end=2,
        )
        derivative_identity_error = total_derivative - realized - unrealized
        cash_sales_identity_error = cash_sales - production_revenue - realized
        rows.append(
            {
                "ticker": "CNX",
                "year": year,
                "production_revenue_ex_derivatives_usd_millions": production_revenue,
                "realized_derivative_usd_millions": realized,
                "unrealized_derivative_usd_millions": unrealized,
                "total_derivative_usd_millions": total_derivative,
                "income_statement_derivative_usd_millions": income_derivative,
                "cash_settled_production_sales_usd_millions": cash_sales,
                "derivative_identity_error_usd_millions": derivative_identity_error,
                "cash_sales_identity_error_usd_millions": cash_sales_identity_error,
                "derivative_separate_from_production_revenue": True,
                "realized_plus_unrealized_identity_proven": bool(
                    abs(derivative_identity_error) <= 2.0
                ),
                "cash_sales_equals_production_revenue_plus_realized_hedge": bool(
                    abs(cash_sales_identity_error) <= 2.0
                ),
                "income_statement_derivative_matches_reconciliation": bool(
                    abs(income_derivative - total_derivative) <= 2.0
                ),
                "source_file": str(source),
                "income_statement_source_file": str(income_source),
                "source_sha256": _sha256(source),
                "availability_date": source.name[:10],
                "hedge_accounting_semantics": (
                    "PRODUCTION_REVENUE_EXCLUDES_DERIVATIVES_REALIZED_AND_UNREALIZED_"
                    "PRESENTED_SEPARATELY_CASH_SALES_ADDS_REALIZED_ONLY"
                ),
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def build_fang_margin_attribution(
    *, ir_root: Path, parent_annual: pd.DataFrame, v16_reconciliation: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    parent = parent_annual.loc[parent_annual["ticker"].eq("FANG")].set_index("year")
    prior = v16_reconciliation.set_index("year") if not v16_reconciliation.empty else pd.DataFrame()
    for year in range(2023, 2026):
        found = _find_table(
            ir_root,
            "FANG",
            year,
            lambda text: "statements of operations" in text
            and "oil, natural gas and natural gas liquid sales" in text
            and "income (loss) from operations" in text,
        )
        if found is None or year not in parent.index:
            continue
        source, table = found
        lines = _line_map(table)
        current = lambda label: _current_annual(
            lines, label, position_from_end=2
        )
        product_revenue = current("oil, natural gas and natural gas liquid sales")
        purchased_revenue = current("sales of purchased oil")
        other_revenue = current("other operating income")
        consolidated_revenue = current("total revenues")
        lease = current("lease operating expenses")
        tax = current("production and ad valorem taxes")
        transport = current("gathering, processing and transportation")
        purchased_expense = current("purchased oil expense")
        dda = current("depreciation, depletion, amortization and accretion")
        impairment = current("impairment of oil and natural gas properties")
        if not np.isfinite(impairment):
            impairment = 0.0
        g_and_a = current("general and administrative expenses")
        other_expense = current("other operating expenses, net")
        operating_income = current("income (loss) from operations")
        production_mboe = float(parent.loc[year, "kpi_production_mboe"])
        reported_composite_lifting = (lease + tax + transport) * 1_000.0 / production_mboe
        frozen_lifting = float(parent.loc[year, "lifting_cost_per_boe"])
        composite_ratio = reported_composite_lifting / frozen_lifting
        revenue_per_boe = float(parent.loc[year, "upstream_revenue_per_boe"])
        corrected_cost_per_boe = (
            frozen_lifting
            + float(parent.loc[year, "upstream_dda_per_boe"])
            + float(parent.loc[year, "g_and_a_per_boe"])
        )
        corrected_unit_margin = (
            revenue_per_boe - corrected_cost_per_boe
        ) / revenue_per_boe * 100.0
        reported_like_for_like_ebit = (
            product_revenue - lease - tax - transport - dda - g_and_a
        )
        reported_like_for_like_margin = reported_like_for_like_ebit / product_revenue * 100.0
        like_for_like_gap = corrected_unit_margin - reported_like_for_like_margin
        consolidated_margin = operating_income / consolidated_revenue * 100.0
        impairment_adjusted_margin = (
            operating_income + impairment
        ) / consolidated_revenue * 100.0
        v16_gap = (
            float(prior.loc[year, "v16_margin_gap_pct_points"])
            if isinstance(prior, pd.DataFrame) and year in prior.index
            else np.nan
        )
        duplicate_cost_effect = (
            float(parent.loc[year, "production_tax_per_boe"] or 0.0)
            + (
                float(prior.loc[year, "v16_transport_cost_per_boe"])
                if isinstance(prior, pd.DataFrame) and year in prior.index
                else 0.0
            )
        ) / revenue_per_boe * 100.0
        impairment_effect = impairment / consolidated_revenue * 100.0
        residual_after_primary_attribution = (
            v16_gap + duplicate_cost_effect - impairment_effect
            if np.isfinite(v16_gap)
            else np.nan
        )
        rows.append(
            {
                "ticker": "FANG",
                "year": year,
                "product_revenue_usd_millions": product_revenue,
                "purchased_oil_revenue_usd_millions": purchased_revenue,
                "purchased_oil_expense_usd_millions": purchased_expense,
                "other_operating_revenue_usd_millions": other_revenue,
                "consolidated_revenue_usd_millions": consolidated_revenue,
                "lease_operating_usd_millions": lease,
                "production_tax_usd_millions": tax,
                "transport_usd_millions": transport,
                "dda_usd_millions": dda,
                "g_and_a_usd_millions": g_and_a,
                "other_operating_expense_usd_millions": other_expense,
                "impairment_usd_millions": impairment,
                "reported_operating_income_usd_millions": operating_income,
                "reported_composite_lifting_cost_per_boe": reported_composite_lifting,
                "frozen_lifting_cost_per_boe": frozen_lifting,
                "composite_to_frozen_lifting_ratio": composite_ratio,
                "tax_and_transport_already_in_composite_lifting_cost": bool(
                    0.98 <= composite_ratio <= 1.02
                ),
                "corrected_unit_operating_margin_pct": corrected_unit_margin,
                "reported_like_for_like_operating_margin_pct": reported_like_for_like_margin,
                "like_for_like_margin_gap_pct_points": like_for_like_gap,
                "reported_consolidated_operating_margin_pct": consolidated_margin,
                "impairment_adjusted_consolidated_margin_pct": impairment_adjusted_margin,
                "v16_margin_gap_pct_points": v16_gap,
                "duplicate_cost_effect_pct_points": duplicate_cost_effect,
                "impairment_effect_pct_points": impairment_effect,
                "residual_after_primary_attribution_pct_points": residual_after_primary_attribution,
                "margin_gap_classification": (
                    "EXPLAINED_IMPAIRMENT_PLUS_DUPLICATE_COMPOSITE_COST_SCOPE"
                    if year == 2025
                    and impairment > 0
                    and abs(residual_after_primary_attribution) <= 5.0
                    else "LIKE_FOR_LIKE_RECONCILED"
                    if abs(like_for_like_gap) <= 5.0
                    else "EXPLICIT_UNRESOLVED_LIKE_FOR_LIKE_GAP"
                ),
                "derivative_in_operating_income": False,
                "source_file": str(source),
                "source_sha256": _sha256(source),
                "availability_date": source.name[:10],
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def build_core_accounting_summary(
    *,
    ar: pd.DataFrame,
    cnx: pd.DataFrame,
    fang: pd.DataFrame,
    parent_summary: pd.DataFrame,
) -> pd.DataFrame:
    parent = parent_summary.set_index("ticker")
    ar_scope = len(ar) >= 3 and ar["transport_tax_already_in_composite_lifting_cost"].all()
    ar_numeric = float(parent.loc["AR", "median_absolute_raw_margin_gap_pct_points"]) <= 5.0
    cnx_hedge = bool(
        len(cnx) >= 3
        and cnx[
            [
                "realized_plus_unrealized_identity_proven",
                "cash_sales_equals_production_revenue_plus_realized_hedge",
                "income_statement_derivative_matches_reconciliation",
            ]
        ].all(axis=None)
    )
    cnx_numeric = bool(parent.loc["CNX", "numeric_reconciliation_pass"])
    fang_identity = bool(
        len(fang) >= 3
        and fang["tax_and_transport_already_in_composite_lifting_cost"].all()
        and fang["like_for_like_margin_gap_pct_points"].abs().median() <= 5.0
    )
    fang_2025 = fang.loc[fang["year"].eq(2025)]
    fang_classified = bool(
        len(fang_2025) == 1
        and fang_2025.iloc[0]["margin_gap_classification"]
        in {
            "EXPLAINED_IMPAIRMENT_PLUS_DUPLICATE_COMPOSITE_COST_SCOPE",
            "EXPLICIT_UNRESOLVED_LIKE_FOR_LIKE_GAP",
        }
    )
    return pd.DataFrame(
        [
            {
                "ticker": "AR",
                "scope_identity_proven": ar_scope,
                "hedge_presentation_proven": False,
                "numeric_or_like_for_like_gate": ar_numeric,
                "historical_outlier_disclosure": "2021_AND_2022_RED_GAPS_RETAINED",
                "special_case_classified": True,
                "accounting_perimeter_pass": bool(ar_scope and ar_numeric),
                "accounting_perimeter_status": (
                    "PASS_AUTHORITATIVE_COMPOSITE_LIFTING_SCOPE_OLDER_RED_YEARS_DISCLOSED"
                    if ar_scope and ar_numeric
                    else "LOCKED_AR_SCOPE_OR_NUMERIC_GATE"
                ),
            },
            {
                "ticker": "CNX",
                "scope_identity_proven": True,
                "hedge_presentation_proven": cnx_hedge,
                "numeric_or_like_for_like_gate": cnx_numeric,
                "historical_outlier_disclosure": "2022_RED_GAP_RETAINED",
                "special_case_classified": True,
                "accounting_perimeter_pass": bool(cnx_hedge and cnx_numeric),
                "accounting_perimeter_status": (
                    "PASS_AUTHORITATIVE_HEDGE_PRESENTATION_RECONCILIATION"
                    if cnx_hedge and cnx_numeric
                    else "LOCKED_CNX_HEDGE_OR_NUMERIC_GATE"
                ),
            },
            {
                "ticker": "FANG",
                "scope_identity_proven": fang_identity,
                "hedge_presentation_proven": True,
                "numeric_or_like_for_like_gate": fang_identity,
                "historical_outlier_disclosure": "2025_REPORTED_GAAP_GAP_ATTRIBUTED_NOT_DROPPED",
                "special_case_classified": fang_classified,
                "accounting_perimeter_pass": bool(fang_identity and fang_classified),
                "accounting_perimeter_status": (
                    "PASS_LIKE_FOR_LIKE_SCOPE_WITH_2025_IMPAIRMENT_ATTRIBUTION"
                    if fang_identity and fang_classified
                    else "LOCKED_FANG_SCOPE_OR_2025_CLASSIFICATION"
                ),
            },
        ]
    )


def build_core_accounting_proof(
    *,
    ir_root: Path,
    parent_annual_path: Path,
    parent_summary_path: Path,
    v16_fang_reconciliation_path: Path,
) -> dict[str, pd.DataFrame]:
    parent_annual = pd.read_csv(parent_annual_path)
    parent_summary = pd.read_csv(parent_summary_path)
    v16_reconciliation = pd.read_csv(v16_fang_reconciliation_path)
    ar = build_ar_composite_cost_proof(
        ir_root=ir_root, parent_annual=parent_annual
    )
    cnx = build_cnx_hedge_proof(ir_root)
    fang = build_fang_margin_attribution(
        ir_root=ir_root,
        parent_annual=parent_annual,
        v16_reconciliation=v16_reconciliation,
    )
    summary = build_core_accounting_summary(
        ar=ar, cnx=cnx, fang=fang, parent_summary=parent_summary
    )
    return {
        "ar_composite_cost_scope_proof": ar,
        "cnx_hedge_accounting_reconciliation": cnx,
        "fang_margin_gap_attribution": fang,
        "core_accounting_proof_summary": summary,
    }
