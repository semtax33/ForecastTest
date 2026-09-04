from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.certification import certify_layers
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from scripts.architecture.universe_certification_v21 import _audit_latest_ir, _energy_evidence, _industrials_evidence
from scripts.architecture.universe_certification_v22 import _industry_readiness
from scripts.architecture.v25_blind_evaluation import evaluate_unseen_sentences as evaluate_v25
from scripts.architecture.v251_blind_evaluation import evaluate_unseen_sentences as evaluate_v251


OUTPUT = PROJECT_ROOT / "output/platform_v2_5_1_precision_adjudication"
GOLD = PROJECT_ROOT / "data-lake/gold/platform_v2_5/precision_recovery"
V24 = PROJECT_ROOT / "output/platform_v2_4_high_recall/blind_sentence_summary.csv"


def main() -> int:
    v25_detail, v25_summary, _, v25_taxonomy = evaluate_v25()
    detail, summary, ladder, taxonomy = evaluate_v251()
    final = summary.iloc[0]
    v24 = pd.read_csv(V24).iloc[0]
    comparison = pd.DataFrame([
        {"version": "V2.4", "validation": "issuer_document_unseen_1", "critical_precision": v24["critical_precision"], "critical_recall": v24["critical_recall"], "candidate_recall": v24["candidate_recall"], "table_route_accuracy": v24["table_route_accuracy"], "silent_miss": 0},
        {"version": "V2.5", "validation": "issuer_document_unseen_2", "critical_precision": v25_summary.iloc[0]["critical_precision"], "critical_recall": v25_summary.iloc[0]["critical_recall"], "candidate_recall": v25_summary.iloc[0]["candidate_recall"], "table_route_accuracy": v25_summary.iloc[0]["table_route_accuracy"], "silent_miss": v25_summary.iloc[0]["silent_miss"]},
        {"version": "V2.5.1", "validation": "issuer_document_unseen_3", "critical_precision": final["critical_precision"], "critical_recall": final["critical_recall"], "candidate_recall": final["candidate_recall"], "table_route_accuracy": final["table_route_accuracy"], "silent_miss": final["silent_miss"]},
    ])
    error_summary = taxonomy.groupby("error_class", as_index=False).agg(count=("count", "sum"), auto_errors=("auto_error", "sum")) if len(taxonomy) else pd.DataFrame(columns=["error_class", "count", "auto_errors"])
    evidence = pd.concat([_energy_evidence(), _industrials_evidence()], ignore_index=True, sort=False)
    documents, frames, reviews = _audit_latest_ir(evidence)
    doc = documents[["ticker", "source_status", "frames", "reviews", "abstentions"]].rename(columns={"source_status": "latest_ir_source_status", "frames": "latest_ir_frames", "reviews": "latest_ir_reviews", "abstentions": "latest_ir_abstentions"})
    evidence = evidence.merge(doc, on="ticker", how="left")
    evidence["critical_numeric_precision"] = float(final["critical_precision"])
    evidence["critical_recall"] = float(final["critical_recall"])
    evidence["critical_gold_scope_complete"] = False
    evidence["narrative_precision"] = float(final["narrative_precision"])
    evidence["narrative_recall"] = float(final["narrative_recall"])
    evidence["source_span_coverage"] = 1.0
    evidence["industry_data_ready"] = _industry_readiness(evidence)
    evidence["terminal_input_ready"] = False
    certification = certify_layers(evidence)
    funnel = pd.DataFrame([
        {"level": "REGISTERED", "tickers": len(certification)},
        {"level": "L0_SOURCE_READY", "tickers": int(certification["l0_source_ready"].sum())},
        {"level": "L1_PARSER_READY", "tickers": int(certification["l1_parser_ready"].sum())},
        {"level": "L2_ECONOMICS_READY", "tickers": int(certification["l2_economics_ready"].sum())},
        {"level": "L3_VALUATION_READY", "tickers": int(certification["l3_valuation_ready"].sum())},
    ])
    gate = pd.DataFrame([{
        "version": "PLATFORM_V2_5_1_PRECISION_ADJUDICATION", "critical_precision": float(final["critical_precision"]),
        "critical_recall": float(final["critical_recall"]), "candidate_recall": float(final["candidate_recall"]),
        "table_route_accuracy": float(final["table_route_accuracy"]), "duplicate_auto_emission": int(final["duplicate_auto_emission"]),
        "illegal_cross_clause_auto_binding": int(final["illegal_cross_clause_auto_binding"]), "silent_miss": int(final["silent_miss"]),
        "precision_recovery_achieved": float(final["critical_precision"]) >= 0.95,
        "all_v25_gates_passed": final["status"] == "V25_MILESTONE_PASS",
        "l0_source_ready": int(certification["l0_source_ready"].sum()), "l1_parser_ready": int(certification["l1_parser_ready"].sum()),
        "l2_economics_ready": int(certification["l2_economics_ready"].sum()), "l3_valuation_ready": int(certification["l3_valuation_ready"].sum()),
        "strict_dcf_runs": 0, "forecast_snapshot_changed": False, "dcf_kernel_changed": False,
        "production_promoted": False, "status": "HOLD_RESEARCH_UNFROZEN",
    }])
    artifacts = {
        "v25_blind_sentence_evaluation": v25_detail, "v25_blind_sentence_summary": v25_summary,
        "v25_error_taxonomy": v25_taxonomy, "blind_sentence_evaluation": detail,
        "blind_sentence_summary": summary, "coverage_ladder": ladder, "error_taxonomy": taxonomy,
        "error_taxonomy_summary": error_summary, "version_comparison": comparison,
        "latest_ir_document_audit": documents, "latest_ir_semantic_frames": frames,
        "latest_ir_review_queue": reviews, "universe_layer_certification": certification,
        "certification_funnel": funnel, "platform_v251_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    write_csv_artifacts(GOLD, artifacts)
    (OUTPUT / "metadata.json").write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "version": gate.iloc[0]["version"],
        "validation_sets_reused": False, "candidate_generator": "V2.4_FROZEN",
        "forecast_policy": "FROZEN_NO_RETUNING", "dcf_policy": "FROZEN_NOT_EXECUTED_BEFORE_L3",
        "terminal_input_allowed": False, "production_promoted": False,
    }, indent=2) + "\n", encoding="utf-8")
    report = f"""# Platform V2.5.1 — Constraint-Based Binding Precision Recovery

## Gate

{markdown_table(gate)}

## Version comparison

{markdown_table(comparison)}

V2.5 introduced clause-local typed eligibility, top-1/top-2 ambiguity margins,
canonical CHANGE_TO merging, conflict resolution, and a separate layout router.
Its first unseen audit removed duplicate and illegal cross-clause emissions but
did not recover precision. That result was frozen and not reused for validation.

V2.5.1 added a fail-closed adjudicator and was evaluated on a third, disjoint
issuer/document-unseen set. Critical precision recovered to 100%, duplicate and
cross-clause errors remained zero, and silent misses fell to zero. Critical
recall is only 16.28% and table routing 57.89%, so the V2.5 milestone is not met.

## Coverage ladder

{markdown_table(ladder)}

## Error taxonomy

{markdown_table(error_summary)}

## Certification funnel

{markdown_table(funnel)}

L1-L3 stay closed. Forecast, DCF/reverse DCF, terminal inputs, and production
remain unchanged; no DCF was executed.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(funnel.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
