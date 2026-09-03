from __future__ import annotations

import numpy as np
import pandas as pd


SEGMENT_MEMBERS = {
    "aeronautics": "lmt:AeronauticsMember",
    "missiles_fire_control": "lmt:MissilesAndFireControlMember",
    "rotary_mission_systems": "lmt:RotaryAndMissionSystemsMember",
    "space": "lmt:SpaceMember",
}
METRICS = {
    "Revenues": ("sales_usd", "SEGMENT_REVENUE"),
    "OperatingIncomeLoss": ("operating_profit_usd", "SEGMENT_OPERATING_PROFIT"),
}


def _period(report_date: str) -> str:
    stamp = pd.Timestamp(report_date)
    quarter = {3: 1, 6: 2, 9: 3, 12: 4}[stamp.month]
    return f"{stamp.year}Q{quarter}"


def build_lmt_sec_ir_segment_reconciliation(
    *,
    raw_facts: pd.DataFrame,
    sec_inventory: pd.DataFrame,
    ir_history: pd.DataFrame,
    ir_backlog: pd.DataFrame,
    ir_program_losses: pd.DataFrame,
    periodic_selections: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    selections: list[dict[str, object]] = []
    reconciliation: list[dict[str, object]] = []
    for _, source in sec_inventory.sort_values("report_date").iterrows():
        report_date = str(source["report_date"])
        period = _period(report_date)
        filing = raw_facts.loc[raw_facts["accession_number"].eq(source["accession_number"])].copy()
        for segment, member in SEGMENT_MEMBERS.items():
            for concept, (ir_column, metric) in METRICS.items():
                candidates = filing.loc[
                    filing["concept_local"].eq(concept)
                    & filing["end_date"].eq(report_date)
                    & filing["dimension_count"].eq(2)
                    & filing["dimensions"].fillna("").str.contains(member, regex=False)
                    & filing["dimensions"].fillna("").str.contains("OperatingSegmentsMember", regex=False)
                ].copy()
                candidates["duration_days"] = (
                    pd.to_datetime(candidates["end_date"])
                    - pd.to_datetime(candidates["start_date"])
                ).dt.days
                candidates = candidates.loc[
                    candidates["duration_days"].between(330, 370)
                    if source["form"] == "10-K"
                    else candidates["duration_days"].between(70, 110)
                ]
                unique = candidates.drop_duplicates("value_usd")
                sec_value = float(unique.iloc[0]["value_usd"]) if len(unique) == 1 else np.nan
                if source["form"] == "10-K":
                    comparable = ir_history.loc[
                        ir_history["period"].str.startswith(report_date[:4])
                        & ir_history["segment"].eq(segment),
                        ir_column,
                    ]
                    ir_value = float(comparable.sum()) if len(comparable) == 4 else np.nan
                    comparison_basis = "SEC_ANNUAL_VS_SUM_OF_FOUR_IR_QUARTERS"
                else:
                    comparable = ir_history.loc[
                        ir_history["period"].eq(period)
                        & ir_history["segment"].eq(segment),
                        ir_column,
                    ]
                    ir_value = float(comparable.iloc[0]) if len(comparable) == 1 else np.nan
                    comparison_basis = "SEC_CURRENT_QUARTER_VS_IR_CURRENT_QUARTER"
                difference = sec_value - ir_value
                selections.append(
                    {
                        "period": period,
                        "form": source["form"],
                        "filing_date": source["filing_date"],
                        "report_date": report_date,
                        "accession_number": source["accession_number"],
                        "segment": segment,
                        "metric": metric,
                        "concept": concept,
                        "candidate_facts": len(candidates),
                        "unique_candidate_values": len(unique),
                        "selected_value_usd": sec_value,
                        "selected_context_ref": unique.iloc[0]["context_ref"] if len(unique) == 1 else None,
                        "selection_rule": "EXACT_SEGMENT_MEMBER_PLUS_OPERATING_SEGMENTS_AXIS_CURRENT_PERIOD",
                        "source_url": source["source_url"],
                        "source_sha256": source["sha256"],
                    }
                )
                reconciliation.append(
                    {
                        "period": period,
                        "form": source["form"],
                        "segment": segment,
                        "metric": metric,
                        "sec_xbrl_value_usd": sec_value,
                        "ir_value_usd": ir_value,
                        "difference_usd": difference,
                        "absolute_difference_usd": abs(difference),
                        "identity_pass": bool(np.isfinite(difference) and abs(difference) <= 1.0),
                        "comparison_basis": comparison_basis,
                        "sec_filing_date": source["filing_date"],
                        "sec_source_url": source["source_url"],
                    }
                )
    selected = pd.DataFrame(selections)
    cross = pd.DataFrame(reconciliation)

    rpo = periodic_selections.loc[
        periodic_selections["metric"].eq("remaining_performance_obligation_usd")
        & periodic_selections["available"].astype(bool),
        ["period", "filing_date", "value_usd", "source_url", "source_sha256"],
    ].rename(columns={"value_usd": "sec_rpo_usd", "source_url": "sec_source_url"})
    backlog = ir_backlog.groupby("period", as_index=False).agg(
        ir_segment_backlog_sum_usd=("backlog_usd", "sum"),
        ir_segment_rows=("segment", "size"),
        ir_source_url=("source_url", "first"),
    )
    backlog_cross = backlog.merge(rpo, on="period", how="inner", validate="one_to_one")
    backlog_cross["difference_usd"] = backlog_cross["ir_segment_backlog_sum_usd"] - backlog_cross["sec_rpo_usd"]
    backlog_cross["difference_pct"] = backlog_cross["difference_usd"] / backlog_cross["sec_rpo_usd"] * 100.0
    backlog_cross["rounding_identity_pass"] = backlog_cross["difference_pct"].abs().le(0.05)
    backlog_cross["comparison_basis"] = "IR_SEGMENT_BACKLOG_SUM_VS_SEC_CONSOLIDATED_RPO"

    sec_program = periodic_selections.loc[
        periodic_selections["metric"].eq("program_gains_losses_usd")
        & periodic_selections["available"].astype(bool),
        ["period", "form", "filing_date", "value_usd", "source_url", "source_sha256"],
    ].rename(columns={"value_usd": "sec_program_gains_losses_usd", "source_url": "sec_source_url"})
    ir_program = ir_program_losses.groupby("period", as_index=False).agg(
        ir_segment_allocated_program_losses_usd=("pretax_program_loss_usd", "sum"),
        ir_program_loss_rows=("segment", "size"),
        ir_source_url=("source_url", "first"),
    )
    program_cross = ir_program.merge(sec_program, on="period", how="inner", validate="one_to_one")
    program_cross["unallocated_sec_program_losses_usd"] = (
        program_cross["sec_program_gains_losses_usd"]
        - program_cross["ir_segment_allocated_program_losses_usd"]
    )
    program_cross["ir_allocation_coverage_pct"] = (
        program_cross["ir_segment_allocated_program_losses_usd"]
        / program_cross["sec_program_gains_losses_usd"]
        * 100.0
    )
    program_cross["no_overallocation_pass"] = program_cross["unallocated_sec_program_losses_usd"].ge(0.0)
    program_cross["comparison_basis"] = "IR_EXPLICIT_SEGMENT_ALLOCATION_VS_SEC_CONSOLIDATED_PROGRAM_LOSSES"

    summary = pd.DataFrame(
        [
            {
                "sec_periodic_filings": sec_inventory["accession_number"].nunique(),
                "expected_segment_metric_cells": len(sec_inventory) * len(SEGMENT_MEMBERS) * len(METRICS),
                "selected_segment_metric_cells": int(selected["selected_value_usd"].notna().sum()),
                "sec_ir_segment_identity_pass_cells": int(cross["identity_pass"].sum()),
                "sec_ir_segment_identity_coverage_pct": float(cross["identity_pass"].mean() * 100.0),
                "maximum_segment_absolute_difference_usd": float(cross["absolute_difference_usd"].max()),
                "rpo_backlog_periods": len(backlog_cross),
                "rpo_backlog_identity_pass_periods": int(backlog_cross["rounding_identity_pass"].sum()),
                "rpo_backlog_maximum_absolute_difference_pct": float(backlog_cross["difference_pct"].abs().max()),
                "program_loss_matching_event_periods": len(program_cross),
                "program_loss_exact_identity_periods": int(
                    program_cross["unallocated_sec_program_losses_usd"].abs().le(1.0).sum()
                ),
                "program_loss_unallocated_residual_usd": float(
                    program_cross["unallocated_sec_program_losses_usd"].sum()
                ),
                "program_loss_ir_allocation_coverage_pct": float(
                    program_cross["ir_segment_allocated_program_losses_usd"].sum()
                    / program_cross["sec_program_gains_losses_usd"].sum()
                    * 100.0
                ),
                "program_loss_no_overallocation_gate_pass": bool(
                    len(program_cross) == 2 and program_cross["no_overallocation_pass"].all()
                ),
                "segment_and_backlog_reconciliation_gate_pass": bool(
                    len(cross) == 184
                    and cross["identity_pass"].all()
                    and len(backlog_cross) == 23
                    and backlog_cross["rounding_identity_pass"].all()
                ),
            }
        ]
    )
    return {
        "lmt_sec_segment_fact_selections": selected,
        "lmt_sec_ir_segment_reconciliation": cross,
        "lmt_sec_rpo_ir_backlog_reconciliation": backlog_cross,
        "lmt_sec_ir_program_loss_reconciliation": program_cross,
        "lmt_sec_ir_segment_reconciliation_summary": summary,
    }
