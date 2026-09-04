from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.certification import certify_layers
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from scripts.architecture.universe_certification_v21 import (
    _audit_latest_ir,
    _energy_evidence,
    _industrials_evidence,
)
from scripts.architecture.universe_certification_v22 import _industry_readiness
from scripts.architecture.v24_blind_evaluation import evaluate_unseen_sentences


OUTPUT = PROJECT_ROOT / "output/platform_v2_4_high_recall"
GOLD = PROJECT_ROOT / "data-lake/gold/platform_v2_4/high_recall"


def main() -> int:
    detail, blind_summary, ladder = evaluate_unseen_sentences()
    blind = blind_summary.iloc[0]
    evidence = pd.concat(
        [_energy_evidence(), _industrials_evidence()], ignore_index=True, sort=False
    )
    documents, frames, reviews = _audit_latest_ir(evidence)
    document_summary = documents[
        ["ticker", "source_status", "frames", "reviews", "abstentions"]
    ].rename(
        columns={
            "source_status": "latest_ir_source_status",
            "frames": "latest_ir_frames",
            "reviews": "latest_ir_reviews",
            "abstentions": "latest_ir_abstentions",
        }
    )
    evidence = evidence.merge(document_summary, on="ticker", how="left")
    evidence["critical_numeric_precision"] = float(blind["critical_precision"])
    evidence["critical_recall"] = float(blind["critical_recall"])
    evidence["critical_gold_scope_complete"] = False
    evidence["narrative_precision"] = float(blind["narrative_precision"])
    evidence["narrative_recall"] = float(blind["narrative_recall"])
    evidence["source_span_coverage"] = float(blind["source_span_coverage"])
    evidence["industry_data_ready"] = _industry_readiness(evidence)
    evidence["terminal_input_ready"] = False
    certification = certify_layers(evidence)
    funnel = pd.DataFrame(
        [
            {"level": "REGISTERED", "tickers": len(certification)},
            {"level": "L0_SOURCE_READY", "tickers": int(certification["l0_source_ready"].sum())},
            {"level": "L1_PARSER_READY", "tickers": int(certification["l1_parser_ready"].sum())},
            {"level": "L2_ECONOMICS_READY", "tickers": int(certification["l2_economics_ready"].sum())},
            {"level": "L3_VALUATION_READY", "tickers": int(certification["l3_valuation_ready"].sum())},
        ]
    )
    gate = pd.DataFrame(
        [{
            "version": "PLATFORM_V2_4_HIGH_RECALL_CANDIDATE_GENERATION",
            "issuer_document_unseen": True,
            "registered_tickers": len(certification),
            "blind_issuers": int(blind["evaluation_issuers"]),
            "blind_blocks": int(blind["annotated_blocks"]),
            "mention_recall": float(blind["mention_recall"]),
            "candidate_recall": float(blind["candidate_recall"]),
            "candidate_precision": float(blind["candidate_precision"]),
            "binding_recall": float(blind["binding_recall"]),
            "critical_precision": float(blind["critical_precision"]),
            "critical_recall": float(blind["critical_recall"]),
            "table_route_accuracy": float(blind["table_route_accuracy"]),
            "v24_recall_milestone_50pct": bool(blind["v24_recall_milestone_50pct"]),
            "precision_gate_99pct": bool(blind["precision_gate_99pct"]),
            "l0_source_ready": int(certification["l0_source_ready"].sum()),
            "l1_parser_ready": int(certification["l1_parser_ready"].sum()),
            "l2_economics_ready": int(certification["l2_economics_ready"].sum()),
            "l3_valuation_ready": int(certification["l3_valuation_ready"].sum()),
            "strict_dcf_runs": 0,
            "forecast_snapshot_changed": False,
            "dcf_kernel_changed": False,
            "production_promoted": False,
            "status": "HOLD_RESEARCH_UNFROZEN",
        }]
    )
    artifacts = {
        "blind_sentence_evaluation": detail,
        "blind_sentence_summary": blind_summary,
        "coverage_ladder": ladder,
        "latest_ir_document_audit": documents,
        "latest_ir_semantic_frames": frames,
        "latest_ir_review_queue": reviews,
        "universe_layer_certification": certification,
        "certification_funnel": funnel,
        "platform_v24_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    write_csv_artifacts(GOLD, artifacts)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": gate.iloc[0]["version"],
        "blindness_claim": "ISSUER_AND_DOCUMENT_UNSEEN",
        "future_use": "ERROR_ANALYSIS_ONLY_NOT_RETUNING_VALIDATION",
        "forecast_policy": "FROZEN_NO_RETUNING",
        "dcf_policy": "KERNEL_FROZEN_NOT_EXECUTED_BEFORE_L3",
        "llm_backend_used": False,
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Platform V2.4 — High-Recall Candidate Generation

## Gate

{markdown_table(gate)}

## Issuer- and document-unseen audit

{markdown_table(blind_summary)}

## Coverage ladder

{markdown_table(ladder)}

The high-recall stage achieved 100% mention and candidate recall with 67.86%
candidate precision. Binding recall reached 71.93%, and final critical recall
passed the V2.4 interim 50% milestone at 51.79%. The strict verifier did not
preserve the required 99% precision: final critical precision was 53.70%.
Consequently this snapshot is frozen as a diagnostic benchmark, not promoted.

The errors concentrate in duplicate CHANGE_TO/CHANGE_BY emission, cross-clause
metric/value binding, and flattened financial-grid routing. Every missed block
was captured by auto/review/abstention rather than silently dropped.

## Certification funnel

{markdown_table(funnel)}

All 52 registered issuers remain source-ready at L0. L1-L3 remain closed. No
forecast, DCF/reverse-DCF, terminal input, or production state was changed, and
no DCF was executed.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(funnel.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
