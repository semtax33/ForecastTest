from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from scripts.architecture.v26_route_evaluation import evaluate_v251_development_set


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_route_aware_recall"
BENCHMARK = PROJECT_ROOT / "benchmarks/platform_v2_6_route_aware_recall"


def main() -> int:
    dev_detail, dev_summary, dev_ladder = evaluate_v251_development_set()
    holdout = pd.read_csv(OUTPUT / "fourth_holdout_summary.csv")
    holdout_ladder = pd.read_csv(OUTPUT / "coverage_ladder.csv")
    evidence = pd.read_csv(OUTPUT / "evidence_source_coverage.csv").rename(
        columns={"source_count": "evidence_units"}
    )
    taxonomy = pd.DataFrame([
        {"split": "FOURTH_HOLDOUT", "error_class": "FP_NEGATION_SCOPE", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FP_NARRATIVE_AMOUNT_OWNERSHIP", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FP_SECURITIES_SALES_ALIAS", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FP_CROSS_METRIC_CLAUSE_OWNERSHIP", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FP_SECURITIES_PRICE_DOMAIN", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FN_ABSOLUTE_MONETARY_DELTA", "count": 4},
        {"split": "FOURTH_HOLDOUT", "error_class": "FN_POINTS_DELTA", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FN_INDIRECT_DEFERRED_REVENUE", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FN_TABLE_FALSE_POSITIVE_SUPPRESSION", "count": 10},
        {"split": "FOURTH_HOLDOUT", "error_class": "FN_MULTI_QUANTITY_PRODUCTION_LEVEL", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "FN_PARALLEL_CLAUSE_OWNERSHIP", "count": 1},
        {"split": "FOURTH_HOLDOUT", "error_class": "CANDIDATE_BARE_CASH_DEBT_ALIAS", "count": 2},
        {"split": "FOURTH_HOLDOUT", "error_class": "TABLE_CLASSIFICATION_ERROR", "count": 6},
    ])
    comparison = pd.DataFrame([
        {
            "version": "V2.5.1",
            "evaluation": "third_disjoint_holdout",
            "critical_precision": 1.0,
            "critical_recall": 0.1627906977,
            "candidate_recall": 1.0,
            "table_route_accuracy": 0.5789473684,
            "status": "HOLD_RESEARCH_UNFROZEN",
        },
        {
            "version": "V2.6",
            "evaluation": "v251_disclosed_development_set",
            "critical_precision": float(dev_summary.iloc[0]["critical_precision"]),
            "critical_recall": float(dev_summary.iloc[0]["critical_recall"]),
            "candidate_recall": 1.0,
            "table_route_accuracy": float(dev_summary.iloc[0]["table_route_accuracy"]),
            "status": "DEVELOPMENT_GATE_PASS_NOT_BLIND",
        },
        {
            "version": "V2.6",
            "evaluation": "fourth_disjoint_holdout",
            "critical_precision": float(holdout.iloc[0]["critical_precision"]),
            "critical_recall": float(holdout.iloc[0]["critical_recall"]),
            "candidate_recall": float(holdout.iloc[0]["candidate_recall"]),
            "table_route_accuracy": float(holdout.iloc[0]["table_route_accuracy"]),
            "status": str(holdout.iloc[0]["status"]),
        },
    ])
    write_csv_artifacts(OUTPUT, {
        "v251_disclosed_development_evaluation": dev_detail,
        "v251_disclosed_development_summary": dev_summary,
        "v251_disclosed_development_ladder": dev_ladder,
        "version_comparison": comparison,
        "holdout_error_taxonomy": taxonomy,
        "evidence_source_coverage": evidence,
    })
    report = f"""# Platform V2.6 — Route-Aware Semantic Recall Recovery

## Final verdict

`HOLD_RESEARCH_UNFROZEN`. V2.6 fixes the impossible provenance ladder and passes
the disclosed V2.5.1 development set, but it fails the newly frozen fourth
issuer/document-disjoint holdout. Forecast, DCF, reverse DCF, terminal inputs,
and production were not changed or executed.

## Version comparison

{markdown_table(comparison)}

The development result improves critical recall from 16.28% to 81.40% while
holding critical precision at 100% and table routing at 100%. This is a useful
implementation result, not a generalization claim. The fourth holdout falls to
75.00% critical precision, 33.33% critical recall, 92.59% candidate recall, and
94.00% table-route classification accuracy, so every substantive V2.6 gate fails.

## Fourth holdout coverage ladder

{markdown_table(holdout_ladder)}

Unlike V2.5.1's impossible `BINDING 0 -> FINAL 7`, all V2.6 final facts have an
explicit route binding. The holdout ladder is `ALL_BINDING_ROUTES 9 = FINAL_FACT
9`; no final fact appears from an unmeasured stage.

## Evidence used

{markdown_table(evidence)}

The 100-block holdout uses 30 hash-pinned local Arcana documents: ten 10-Ks, ten
10-Qs, and ten IR releases/presentations. Seventy selected blocks come from 10-K
or 10-Q documents that include financial statements and notes. Thirty-four
sector/subindustry public-statistic sensor mappings (EIA, BLS, Census, FDIC and
related registry sources) were loaded only as context; they cannot emit company
facts or enter valuation authority.

## Error taxonomy

{markdown_table(taxonomy)}

The largest recall loss is not the relation solver itself. Ten of eighteen false
negatives are valid bullet/comparison/CapEx facts suppressed by false table
routing. Critical false positives come from negation scope (`no debt ... other
than $25,000`), securities `sales` being treated as operating revenue, and a
parallel expense clause donating its 3.1% change to revenue. Narrative false
positives add tariff cost assigned to customer demand and public-offering price
assigned to operating price realization.

## What improved

- Every final KPI frame carries one of `TEXT_BINDING`, `TABLE_BINDING`,
  `XBRL_DIRECT`, or `ADJUDICATED_DIRECT` provenance.
- Every unbound semantic candidate receives exactly one primary rejection root
  cause plus optional secondary detail.
- DOM/flattened/prose/list/mixed routing is explicit and runs before semantic
  recovery.
- `KPIChange` and ordered `ComparisonFrame` intermediates recover change-to,
  parallel comparison, and explanatory-amount cases without duplicates on the
  development set.
- Source-span accuracy remains 100%; duplicates, illegal cross-clause emissions,
  silent misses, and LLM usage remain zero on the fourth holdout.

## Required next fixes

1. Split list bullets and parallel clauses before grid classification; dense
   numbers alone must not turn coherent KPI bullets into tables.
2. Add negative/exclusion scope and securities-domain guards before numeric
   binding.
3. Extend `KPIChange` to carry both absolute and relative deltas without treating
   either as the ending level.
4. Add position-aware aliases for `$X in Revenue`, bare `cash`, and bare `debt`
   while keeping securities and tax-language exclusions.
5. Represent multiple comparators explicitly (`prior_year`, `prior_quarter`) and
   preserve bullet-local metric ownership.

V2.6 therefore remains a research diagnostic layer. The fourth holdout is frozen
for future error analysis only and must not be reused as a tuning validation set.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "PLATFORM_V2_6_ROUTE_AWARE_SEMANTIC_RECALL",
        "status": "HOLD_RESEARCH_UNFROZEN",
        "development_set_reused": True,
        "fourth_holdout_reused_for_tuning": False,
        "candidate_generator": "V2.4_FROZEN",
        "semantic_runtime_changed_after_holdout_selection": False,
        "forecast_policy": "FROZEN_NOT_EXECUTED",
        "dcf_policy": "FROZEN_NOT_EXECUTED",
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    BENCHMARK.mkdir(parents=True, exist_ok=True)
    manifest_paths = [
        "configs/certification/platform_v26_fourth_holdout.toml",
        "configs/certification/platform_v26_fourth_holdout_sources.csv",
        "equity_platform/text_ie/v26/model.py",
        "equity_platform/text_ie/v26/router.py",
        "equity_platform/text_ie/v26/semantics.py",
        "equity_platform/text_ie/v26/runtime.py",
        "equity_platform/text_ie/v26/evidence.py",
        "scripts/architecture/v26_fourth_holdout_candidates.py",
        "scripts/architecture/v26_fourth_holdout_annotations.py",
        "scripts/architecture/v26_fourth_holdout_evaluation.py",
        "scripts/architecture/v26_route_evaluation.py",
        "scripts/architecture/v26_research_report.py",
        "tests/test_route_aware_recall_v26.py",
        "tests/test_v26_evidence_sources.py",
        "tests/test_v26_fourth_holdout.py",
        "data-lake/gold/parser/text_ie/v26_fourth_holdout_annotations.jsonl",
        "output/platform_v2_6_route_aware_recall/fourth_holdout_candidates.csv",
        "output/platform_v2_6_route_aware_recall/fourth_holdout_summary.csv",
        "output/platform_v2_6_route_aware_recall/fourth_holdout_evaluation.csv",
        "output/platform_v2_6_route_aware_recall/coverage_ladder.csv",
        "output/platform_v2_6_route_aware_recall/holdout_error_taxonomy.csv",
        "output/platform_v2_6_route_aware_recall/evidence_source_coverage.csv",
        "output/platform_v2_6_route_aware_recall/version_comparison.csv",
        "output/platform_v2_6_route_aware_recall/report.md",
    ]
    manifest = {
        "benchmark_id": "PLATFORM_V2_6_ROUTE_AWARE_RECALL_2026_09_04",
        "status": "FOURTH_DISJOINT_HOLDOUT_FAILED",
        "platform_status": "HOLD_RESEARCH_UNFROZEN",
        "artifact_sha256": {
            path: sha256_file(PROJECT_ROOT / path) for path in manifest_paths
        },
        "policy": {
            "future_use": "ERROR_ANALYSIS_ONLY_NOT_RETUNING_VALIDATION",
            "forecast_dcf": "FROZEN_NOT_EXECUTED",
            "production": "LOCKED",
        },
    }
    (BENCHMARK / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(comparison.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
