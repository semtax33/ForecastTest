from __future__ import annotations

import json
from pathlib import Path
import re

import pandas as pd


_EARNINGS = re.compile(r"(?:q[1-4].*earnings|earnings.*q[1-4])", re.IGNORECASE)
_CONTRACT = re.compile(r"backlog|contract|award", re.IGNORECASE)


def _inventory_ir(ir_root: Path) -> tuple[int, int, int, int]:
    html = [path for path in ir_root.glob("*.htm*") if not path.name.endswith(".metadata.json")]
    releases: set[str] = set()
    contract_docs: set[str] = set()
    years: set[int] = set()
    for path in html:
        name = path.name
        if _EARNINGS.search(name) and "present" not in name.lower():
            releases.add(name)
            try:
                years.add(int(name[:4]))
            except ValueError:
                pass
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _CONTRACT.search(text):
            contract_docs.add(name)
    return len(html), len(releases), len(contract_docs), len(years)


def select_third_company(
    candidate_path: Path,
    arcana_ir_parent: Path,
    minimum_years: int = 6,
    minimum_oos: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select a third A&D company without reading any forecast outcome."""
    candidates = pd.read_csv(candidate_path, dtype={"cik": str})
    rows: list[dict[str, object]] = []
    for candidate in candidates.to_dict("records"):
        ir_root = arcana_ir_parent / str(candidate["arcana_ir_folder"])
        html_count, releases, contracts, ir_years = _inventory_ir(ir_root)
        criteria = {
            "periodic_and_ir_six_years": ir_years >= minimum_years,
            "stable_segment_perimeter": bool(candidate["stable_segment_perimeter"]),
            "contract_or_backlog_evidence": bool(candidate["contract_or_backlog_evidence"]),
            "fixed_pit_oos_feasible": bool(candidate["fixed_pit_oos_feasible"]) and releases >= minimum_oos,
            "different_program_mix_from_lmt_noc": bool(candidate["different_program_mix_from_lmt_noc"]),
        }
        rows.append({
            **candidate,
            "ir_html_documents": html_count,
            "unambiguous_quarterly_earnings_releases": releases,
            "contract_backlog_evidence_documents": contracts,
            "ir_calendar_years": ir_years,
            **criteria,
            "all_predeclared_criteria_pass": all(criteria.values()),
            "forecast_performance_inspected": False,
        })
    audit = pd.DataFrame(rows)
    eligible = audit.loc[audit["all_predeclared_criteria_pass"]].copy()
    if eligible.empty:
        raise ValueError("No third-company candidate passes the predeclared outcome-blind criteria")
    eligible = eligible.sort_values(
        ["unambiguous_quarterly_earnings_releases", "contract_backlog_evidence_documents", "ticker"],
        ascending=[False, False, True],
    )
    selected = eligible.iloc[[0]].copy()
    selected["selection_rule"] = (
        "MAX_UNAMBIGUOUS_QUARTERLY_IR_THEN_CONTRACT_EVIDENCE_THEN_TICKER"
    )
    selected["selection_outcome_blind"] = True
    selected["selection_status"] = "SELECTED_BEFORE_FORECAST_EVALUATION"
    audit["selected"] = audit["ticker"].eq(selected.iloc[0]["ticker"])
    return audit, selected


def selection_metadata(selected: pd.DataFrame) -> dict[str, object]:
    row = selected.iloc[0]
    return {
        "selected_ticker": row["ticker"],
        "selection_rule": row["selection_rule"],
        "selection_outcome_blind": bool(row["selection_outcome_blind"]),
        "performance_fields_read": [],
        "pdf_parsing_used": False,
        "assertion": "COMPANY_SELECTED_WITHOUT_FORECAST_OR_VALUATION_OUTCOMES",
    }
