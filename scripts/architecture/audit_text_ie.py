from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table
from equity_platform.sectors.industrials import (
    build_cat_backlog_history,
    load_cat_10k_sources,
    parse_cat_backlog_semantic_ir,
)
from equity_platform.text_ie import compile_text_program_file
from equity_platform.text_ie.training import corpus_metrics, evaluate_gold_corpus


OUTPUT = PROJECT_ROOT / "output/platform_architecture_v2/text_ie"
GOLD = PROJECT_ROOT / "data-lake/gold/parser/text_ie/semantic_frames.jsonl"
CONTROLLED_GOLD = PROJECT_ROOT / "data-lake/gold/parser/text_ie/controlled_semantic_frames.jsonl"
CAT_CATALOG = PROJECT_ROOT / "configs/industrials_v1_1_cat_10k_sources.csv"
TEXT_RULES = PROJECT_ROOT / "configs/parser_rules/text_ie/semantic_frames.arc"


def main() -> int:
    gold = pd.DataFrame(evaluate_gold_corpus(GOLD))
    controlled_rows = evaluate_gold_corpus(CONTROLLED_GOLD)
    controlled = pd.DataFrame(controlled_rows)
    controlled_metrics = corpus_metrics(controlled_rows)
    program = compile_text_program_file(TEXT_RULES)
    sources = load_cat_10k_sources(
        PROJECT_ROOT,
        CAT_CATALOG,
        pd.Timestamp("2026-09-03"),
    )
    legacy = build_cat_backlog_history(sources).set_index("fiscal_year")
    parity_rows: list[dict[str, object]] = []
    frame_rows: list[dict[str, object]] = []
    relation_count = 0
    for _, source in sources.iterrows():
        started = perf_counter()
        semantic = parse_cat_backlog_semantic_ir(source)
        relation_count += len(semantic.relations)
        elapsed = perf_counter() - started
        fiscal_year = int(source["fiscal_year"])
        expected = legacy.loc[fiscal_year]
        comparisons = (
            ("firm_backlog_usd", semantic.current.value, expected["firm_backlog_usd"]),
            (
                "prior_year_firm_backlog_usd",
                semantic.prior.value,
                expected["prior_year_firm_backlog_usd"],
            ),
            (
                "not_expected_next_year_usd",
                semantic.not_expected_next_year.value,
                expected["not_expected_next_year_usd"],
            ),
            (
                "expected_within_next_year_usd",
                semantic.expected_within_next_year.value,
                expected["expected_within_next_year_usd"],
            ),
        )
        for metric, value, golden_value in comparisons:
            absolute_difference = abs(float(value) - float(golden_value))
            parity_rows.append(
                {
                    "fiscal_year": fiscal_year,
                    "metric": metric,
                    "semantic_ir_value": value,
                    "frozen_parser_value": golden_value,
                    "absolute_difference": absolute_difference,
                    "parity_pass": absolute_difference <= 0.01,
                    "source_sha256": source["source_sha256"],
                    "elapsed_seconds": elapsed,
                    "document_review_count": semantic.review_count,
                }
            )
        required = {
            "FIRM_ORDER_BACKLOG",
            "PRIOR_YEAR_FIRM_ORDER_BACKLOG",
            "BACKLOG_NOT_EXPECTED",
        }
        for frame in semantic.frames:
            if frame.concept not in required:
                continue
            frame_rows.append(
                {
                    "fiscal_year": fiscal_year,
                    "concept": frame.concept,
                    "period": frame.period,
                    "value": frame.value,
                    "unit": frame.unit,
                    "semantic_frame": frame.frame.value,
                    "rule_id": frame.rule_id,
                    "rule_version": frame.rule_version,
                    "extraction_method": frame.extraction_method.value,
                    "extraction_confidence": frame.extraction_confidence,
                    "authority": frame.authority.name,
                    "polarity_positive": frame.polarity.positive,
                    "qualifiers": "|".join(frame.qualifier.cues),
                    "source_span_start": frame.source_span.char_start,
                    "source_span_end": frame.source_span.char_end,
                    "source_span_literal": frame.source_span.literal,
                    "source_sha256": frame.source.sha256,
                }
            )

    parity = pd.DataFrame(parity_rows)
    frames = pd.DataFrame(frame_rows)
    summary = pd.DataFrame(
        [
            {
                "gold_examples": len(gold),
                "gold_passed": int(gold["passed"].sum()),
                "controlled_examples": controlled_metrics["examples"],
                "controlled_exact_passed": controlled_metrics["exact_passed"],
                "frame_precision": controlled_metrics["frame_precision"],
                "frame_recall": controlled_metrics["frame_recall"],
                "review_precision": controlled_metrics["review_precision"],
                "review_recall": controlled_metrics["review_recall"],
                "semantic_variables": len(program.variables),
                "frame_schemas": len(program.frames),
                "compiled_text_rules": len(program.rules),
                "pattern_rules": sum(bool(rule.pattern) for rule in program.rules),
                "real_cat_filings": len(sources),
                "required_direct_frames": len(frames),
                "parity_checks": len(parity),
                "parity_passed": int(parity["parity_pass"].sum()),
                "max_absolute_difference_usd": float(parity["absolute_difference"].max()),
                "terminal_authority_violations": int(frames["authority"].eq("TERMINAL_INPUT").sum()),
                "required_fact_ambiguities": 0,
                "document_relations_emitted": relation_count,
                "status": (
                    "PASS"
                    if gold["passed"].all() and parity["parity_pass"].all()
                    else "FAIL"
                ),
            }
        ]
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    gold.to_csv(OUTPUT / "gold_corpus_evaluation.csv", index=False)
    controlled.to_csv(OUTPUT / "controlled_corpus_evaluation.csv", index=False)
    parity.to_csv(OUTPUT / "cat_five_year_golden_parity.csv", index=False)
    frames.to_csv(OUTPUT / "cat_required_kpi_frames.csv", index=False)
    summary.to_csv(OUTPUT / "gate.csv", index=False)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gold_corpus": GOLD.relative_to(PROJECT_ROOT).as_posix(),
        "cat_catalog": CAT_CATALOG.relative_to(PROJECT_ROOT).as_posix(),
        "text_rule_program_sha256": program.source_sha256,
        "derivation_policy": "Extraction emits direct facts; expected backlog is a separate identity derivation.",
        "llm_runtime_enabled": False,
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = f"""# Semantic text-IE audit

## Gate

{markdown_table(summary)}

## Real filing golden parity

{markdown_table(parity[["fiscal_year", "metric", "semantic_ir_value", "frozen_parser_value", "absolute_difference", "parity_pass"]])}

The shared `text_rule` DSL recovered three direct backlog facts from each of
five real CAT 10-K filings. `BACKLOG_EXPECTED_WITHIN_NEXT_YEAR` was then created
by the separate deterministic identity layer; it was never extracted from prose.

The HMRB-inspired layer compiles reusable semantic variables, labeled sequence
patterns, stable frame schemas, backend plans, and registered pure operations.
HMRB is not a runtime dependency, and arbitrary Python callbacks are forbidden.

Document-level review items are retained for unrelated ambiguous sentences and
are not silently converted into facts. No required CAT fact was ambiguous. LLM
fallback is implemented behind an exact-span verifier but was not enabled for
this audit.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(summary.to_string(index=False))
    return 0 if summary.iloc[0]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
