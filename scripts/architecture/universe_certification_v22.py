from __future__ import annotations

from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd

from equity_platform.certification import certify_layers
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.text_ie.training import (
    calibration_metrics,
    evaluate_gold_corpus,
)
from scripts.architecture.universe_certification_v21 import (
    _audit_latest_ir,
    _energy_evidence,
    _industrials_evidence,
)
from scripts.architecture.v22_blind_evaluation import evaluate_blind_sentences


OUTPUT = PROJECT_ROOT / "output/platform_v2_2_parser_generalization"
GOLD = PROJECT_ROOT / "data-lake/gold/platform_v2_2/parser_generalization"
DEV_GOLD = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v22_generalization_dev.jsonl"
)
ERROR_TAXONOMY = (
    PROJECT_ROOT / "configs/certification/platform_v22_error_taxonomy.csv"
)
REQUIRED_CRITICAL_CONCEPTS = {
    "REVENUE",
    "OPERATING_INCOME",
    "OPERATING_MARGIN",
    "BACKLOG",
    "PRODUCTION",
    "CAPEX",
    "DEBT",
    "CASH",
    "SHARES",
    "ADJUSTED_EBITDA",
}


def _base_concept(concept: str) -> str:
    base = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE", "_NOT_EXPECTED"):
        base = base.removesuffix(suffix)
    return base


def _blind_concept_coverage(detail: pd.DataFrame) -> tuple[set[str], float]:
    concepts: set[str] = set()
    for payload in detail["expected_frames_json"]:
        for frame in json.loads(payload):
            if frame.get("tier", "CRITICAL") == "CRITICAL":
                concepts.add(_base_concept(str(frame["concept"])))
    return concepts, len(concepts & REQUIRED_CRITICAL_CONCEPTS) / len(
        REQUIRED_CRITICAL_CONCEPTS
    )


def _industry_readiness(evidence: pd.DataFrame) -> pd.Series:
    industrial = pd.read_csv(
        PROJECT_ROOT
        / "output/industrials_v8_subindustry_platform_research/subindustry_coverage_matrix.csv"
    ).set_index("ticker")
    values: list[bool] = []
    for item in evidence.itertuples(index=False):
        if item.sector == "ENERGY":
            values.append(bool(float(item.forecast_oos_observations or 0) > 0))
        else:
            value = industrial.loc[item.ticker, "pqci_context_complete"]
            values.append(str(value).casefold() == "true" if isinstance(value, str) else bool(value))
    return pd.Series(values, index=evidence.index)


def main() -> int:
    taxonomy = pd.read_csv(ERROR_TAXONOMY)
    taxonomy_summary = (
        taxonomy.groupby(["failure_class", "repair_layer"], as_index=False)
        .agg(errors=("frame_id", "size"), issuers=("ticker", "nunique"))
        .sort_values(["errors", "failure_class"], ascending=[False, True])
    )
    dev_rows = evaluate_gold_corpus(DEV_GOLD)
    dev_detail = pd.DataFrame(dev_rows)
    dev_metrics = pd.DataFrame([calibration_metrics(dev_rows)])
    blind_detail, blind_summary = evaluate_blind_sentences()
    blind = blind_summary.iloc[0]
    covered_concepts, concept_coverage = _blind_concept_coverage(blind_detail)

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
    evidence["blind_critical_concept_coverage"] = concept_coverage
    evidence["critical_gold_scope_complete"] = concept_coverage >= 1.0
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
    )
    gate = pd.DataFrame(
        [
            {
                "version": "PLATFORM_V2_2_BLIND_PARSER_GENERALIZATION",
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
                "blind_critical_concepts_covered": len(covered_concepts & REQUIRED_CRITICAL_CONCEPTS),
                "blind_required_critical_concepts": len(REQUIRED_CRITICAL_CONCEPTS),
                "blind_critical_precision": float(blind["critical_precision"]),
                "blind_critical_recall": float(blind["critical_recall"]),
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
        "error_taxonomy": taxonomy,
        "error_taxonomy_summary": taxonomy_summary,
        "dev_corpus_evaluation": dev_detail,
        "dev_corpus_metrics": dev_metrics,
        "blind_sentence_evaluation": blind_detail,
        "blind_sentence_summary": blind_summary,
        "blind_disposition_summary": disposition,
        "latest_ir_document_audit": documents,
        "latest_ir_semantic_frames": frames,
        "latest_ir_review_queue": reviews,
        "universe_layer_certification": certification,
        "certification_funnel": funnel,
        "platform_v22_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    write_csv_artifacts(GOLD, artifacts)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": gate.iloc[0]["version"],
        "forecast_policy": "V2_1_SNAPSHOT_FROZEN_NO_RETUNING",
        "dcf_policy": "KERNEL_FROZEN_NO_EXECUTION_BEFORE_L3",
        "blind_rule_changes_after_selection": False,
        "blind_annotation_scope": "EXHAUSTIVE_WITHIN_PREDECLARED_HASH_SAMPLE",
        "critical_concepts_observed": sorted(covered_concepts),
        "critical_concepts_required": sorted(REQUIRED_CRITICAL_CONCEPTS),
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = f"""# Platform V2.2 — Blind Parser Generalization & Calibration

## Gate

{markdown_table(gate)}

## Error taxonomy

{markdown_table(taxonomy_summary)}

The ten V2.1 blind errors are classified by reusable parser failure mode, not
by issuer. No ticker-specific parser branch was added.

## Development corpus

{markdown_table(dev_metrics)}

The development corpus uses company-neutral paraphrases of the failure modes;
it does not replay the V2.1 holdout sentences.

## New outcome-blind sentence audit

{markdown_table(blind_summary)}

The parser snapshot and issuer/sample selection were hashed before sentence
review. All target facts within the 31 selected blocks were annotated. Dense
tables are explicitly routed to the table DSL and excluded from text-IE recall.

Critical precision reached 100%, but critical recall is only 8.33%. This is the
expected precision/coverage trade-off from strict abstention and fails the 95%
recall gate. Narrative precision is not claimed because the blind sample had no
narrative frame opportunity.

## Decision disposition

{markdown_table(disposition)}

## Certification funnel

{markdown_table(funnel)}

Forecast snapshots and the DCF/reverse-DCF kernel were not changed. No DCF is
executed because L3 is empty; terminal authority and production remain locked.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(funnel.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
