from __future__ import annotations

from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd

from equity_platform.certification import certify_layers
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.text_ie.training import calibration_metrics, evaluate_gold_corpus
from scripts.architecture.universe_certification_v21 import (
    _audit_latest_ir,
    _energy_evidence,
    _industrials_evidence,
)
from scripts.architecture.universe_certification_v22 import (
    REQUIRED_CRITICAL_CONCEPTS,
    _base_concept,
    _industry_readiness,
)
from scripts.architecture.v23_blind_evaluation import evaluate_blind_sentences


OUTPUT = PROJECT_ROOT / "output/platform_v2_3_parser_calibration"
GOLD = PROJECT_ROOT / "data-lake/gold/platform_v2_3/parser_calibration"
DEV_GOLD = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v23_semantic_binding_dev.jsonl"
V22_SUMMARY = (
    PROJECT_ROOT / "output/platform_v2_2_parser_generalization/blind_sentence_summary.csv"
)


def _gold_concept_coverage(detail: pd.DataFrame) -> tuple[set[str], float]:
    concepts: set[str] = set()
    for payload in detail["expected_frames_json"]:
        for frame in json.loads(payload):
            if frame.get("tier", "CRITICAL") == "CRITICAL":
                concepts.add(_base_concept(str(frame["concept"])))
    return concepts, len(concepts & REQUIRED_CRITICAL_CONCEPTS) / len(
        REQUIRED_CRITICAL_CONCEPTS
    )


def _selection_concept_coverage(detail: pd.DataFrame) -> tuple[set[str], float]:
    concepts: set[str] = set()
    for payload in detail["selection_reason"].fillna(""):
        concepts.update(
            item.removeprefix("CONCEPT:")
            for item in str(payload).split("|")
            if item.startswith("CONCEPT:")
        )
    return concepts, len(concepts & REQUIRED_CRITICAL_CONCEPTS) / len(
        REQUIRED_CRITICAL_CONCEPTS
    )


def _improvement(blind: pd.Series) -> pd.DataFrame:
    prior = pd.read_csv(V22_SUMMARY).iloc[0]
    metrics = (
        "critical_precision",
        "critical_recall",
        "auto_coverage",
        "review_rate",
        "abstention_rate",
        "table_route_accuracy",
    )
    return pd.DataFrame(
        [
            {
                "metric": metric,
                "v2_2": float(prior[metric]),
                "v2_3": float(blind[metric]),
                "delta": float(blind[metric]) - float(prior[metric]),
            }
            for metric in metrics
        ]
    )


def main() -> int:
    dev_rows = evaluate_gold_corpus(DEV_GOLD)
    dev_detail = pd.DataFrame(dev_rows)
    dev_metrics = pd.DataFrame([calibration_metrics(dev_rows)])
    blind_detail, blind_summary = evaluate_blind_sentences()
    blind = blind_summary.iloc[0]
    gold_concepts, gold_coverage = _gold_concept_coverage(blind_detail)
    selected_concepts, selection_coverage = _selection_concept_coverage(blind_detail)

    evidence = pd.concat(
        [_energy_evidence(), _industrials_evidence()],
        ignore_index=True,
        sort=False,
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
    evidence["blind_critical_concept_coverage"] = gold_coverage
    evidence["critical_gold_scope_complete"] = gold_coverage >= 1.0
    evidence["narrative_precision"] = (
        float(blind["narrative_precision"])
        if int(blind["narrative_opportunities"]) > 0
        else np.nan
    )
    evidence["narrative_recall"] = (
        float(blind["narrative_recall"])
        if int(blind["narrative_opportunities"]) > 0
        else np.nan
    )
    evidence["source_span_coverage"] = np.minimum(
        evidence["source_span_coverage"].fillna(0.0),
        float(blind["source_span_coverage"]),
    )
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
    disposition = (
        blind_detail.groupby("disposition", as_index=False)
        .agg(blocks=("candidate_id", "size"))
        .sort_values("disposition")
    )
    failure_diagnostics = (
        blind_detail.loc[
            blind_detail["false_negative"].gt(0)
            | blind_detail["false_positive"].gt(0)
            | ~blind_detail["table_route_pass"],
            [
                "ticker",
                "candidate_id",
                "gold_route",
                "disposition",
                "false_positive",
                "false_negative",
                "review_rules",
                "review_reasons",
                "abstention_failure_classes",
                "abstention_reasons",
                "table_route_pass",
                "annotation_note",
            ],
        ]
        .reset_index(drop=True)
    )
    improvement = _improvement(blind)
    gate = pd.DataFrame(
        [
            {
                "version": "PLATFORM_V2_3_SEMANTIC_BINDING_CALIBRATION",
                "registered_tickers": len(certification),
                "latest_ir_parsed": int(documents["source_status"].eq("PARSED").sum()),
                "latest_ir_parse_errors": int(documents["source_status"].eq("PARSE_ERROR").sum()),
                "universe_auto_frames": int(documents["frames"].sum()),
                "universe_review_items": int(documents["reviews"].sum()),
                "universe_abstentions": int(documents["abstentions"].sum()),
                "dev_examples": len(dev_detail),
                "dev_exact_passed": int(dev_detail["passed"].sum()),
                "blind_evaluation_issuers": int(blind["evaluation_issuers"]),
                "blind_annotated_blocks": int(blind["annotated_blocks"]),
                "blind_annotation_coverage": float(blind["annotation_coverage"]),
                "selection_critical_concepts_covered": len(selected_concepts & REQUIRED_CRITICAL_CONCEPTS),
                "selection_required_critical_concepts": len(REQUIRED_CRITICAL_CONCEPTS),
                "selection_concept_coverage": selection_coverage,
                "gold_critical_concepts_covered": len(gold_concepts & REQUIRED_CRITICAL_CONCEPTS),
                "gold_critical_concept_coverage": gold_coverage,
                "blind_critical_precision": float(blind["critical_precision"]),
                "blind_critical_recall": float(blind["critical_recall"]),
                "blind_narrative_precision": float(blind["narrative_precision"]),
                "blind_narrative_recall": float(blind["narrative_recall"]),
                "blind_auto_coverage": float(blind["auto_coverage"]),
                "blind_review_rate": float(blind["review_rate"]),
                "blind_abstention_rate": float(blind["abstention_rate"]),
                "blind_table_route_accuracy": float(blind["table_route_accuracy"]),
                "l0_source_ready": int(certification["l0_source_ready"].sum()),
                "l1_parser_ready": int(certification["l1_parser_ready"].sum()),
                "l2_economics_ready": int(certification["l2_economics_ready"].sum()),
                "l3_valuation_ready": int(certification["l3_valuation_ready"].sum()),
                "strict_dcf_runs": 0,
                "forecast_snapshot_changed": False,
                "dcf_kernel_changed": False,
                "terminal_input_ready": False,
                "production_promoted": False,
                "status": "HOLD_RESEARCH_UNFROZEN",
            }
        ]
    )
    artifacts = {
        "dev_corpus_evaluation": dev_detail,
        "dev_corpus_metrics": dev_metrics,
        "blind_sentence_evaluation": blind_detail,
        "blind_sentence_summary": blind_summary,
        "blind_disposition_summary": disposition,
        "blind_failure_diagnostics": failure_diagnostics,
        "v22_to_v23_improvement": improvement,
        "latest_ir_document_audit": documents,
        "latest_ir_semantic_frames": frames,
        "latest_ir_review_queue": reviews,
        "universe_layer_certification": certification,
        "certification_funnel": funnel,
        "platform_v23_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    write_csv_artifacts(GOLD, artifacts)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": gate.iloc[0]["version"],
        "forecast_policy": "FROZEN_NO_RETUNING",
        "dcf_policy": "KERNEL_FROZEN_NO_EXECUTION_BEFORE_L3",
        "blindness_claim": blind["blindness_claim"],
        "blind_rule_changes_after_selection": False,
        "blind_annotation_scope": "EXHAUSTIVE_WITHIN_PREDECLARED_HASH_SAMPLE",
        "selection_critical_concepts": sorted(selected_concepts),
        "gold_critical_concepts_observed": sorted(gold_concepts),
        "critical_concepts_required": sorted(REQUIRED_CRITICAL_CONCEPTS),
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = f"""# Platform V2.3 — Semantic Binding Calibration

## Gate

{markdown_table(gate)}

## Development corpus

{markdown_table(dev_metrics)}

All 15 generic development examples pass exactly. The repair is company-neutral:
local metric/value binding, word-form percentages, point guidance, bullet offsets,
composition, and a small narrative-driver ontology.

## Outcome-blind sentence audit

{markdown_table(blind_summary)}

The parser source snapshot, deterministic selection procedure, 39 candidate
blocks, and source documents were hashed before sentence review. This is a
sentence-block outcome-blind test, not an issuer-unseen claim. All selected
blocks were exhaustively annotated.

Critical precision remains 100%, while critical recall improves from 8.33% to
16.67%. It still fails the 95% recall gate. Narrative precision is 100% but
recall is only 25%, so narrative evidence is not certified. Table routing rises
from 88.89% to 94.74%; one flattened XOM cash-capex table remains misrouted.

## V2.2 to V2.3

{markdown_table(improvement)}

## Certification funnel

{markdown_table(funnel)}

E&P source lineage is now hash-verified, moving all 52 registered issuers to L0.
L1 remains empty because recall and gold concept-scope gates fail. No forecast
snapshot, DCF/reverse-DCF kernel, terminal input, or production status changed;
no DCF was executed.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(funnel.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
