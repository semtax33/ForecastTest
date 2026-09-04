# Platform V2.4 — High-Recall Candidate Generation

## Gate

| version | issuer_document_unseen | registered_tickers | blind_issuers | blind_blocks | mention_recall | candidate_recall | candidate_precision | binding_recall | critical_precision | critical_recall | table_route_accuracy | v24_recall_milestone_50pct | precision_gate_99pct | l0_source_ready | l1_parser_ready | l2_economics_ready | l3_valuation_ready | strict_dcf_runs | forecast_snapshot_changed | dcf_kernel_changed | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_4_HIGH_RECALL_CANDIDATE_GENERATION | True | 52 | 10 | 54 | 1.0 | 1.0 | 0.6785714285714286 | 0.7192982456140351 | 0.5370370370370371 | 0.5178571428571429 | 0.5882352941176471 | True | False | 52 | 0 | 0 | 0 | 0 | False | False | False | HOLD_RESEARCH_UNFROZEN |

## Issuer- and document-unseen audit

| version | issuer_unseen | document_unseen | parser_snapshot_verified | candidate_artifact_verified | evaluation_issuers | annotated_blocks | annotation_coverage | expected_frames | candidate_precision | mention_recall | candidate_recall | binding_recall | auto_precision | auto_recall | auto_f1 | critical_opportunities | critical_precision | critical_recall | critical_f1 | narrative_opportunities | narrative_precision | narrative_recall | auto_coverage | review_rate | abstention_rate | silent_rate | review_plus_abstention_miss_capture | table_route_accuracy | source_span_coverage | precision_gate_99pct | v24_recall_milestone_50pct | final_recall_gate_95pct | rule_changes_after_selection | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_4_ISSUER_DOCUMENT_UNSEEN | True | True | True | True | 10 | 54 | 1.0 | 57 | 0.6785714285714286 | 1.0 | 1.0 | 0.7192982456140351 | 0.5370370370370371 | 0.5087719298245614 | 0.5225225225225226 | 56 | 0.5370370370370371 | 0.5178571428571429 | 0.5272727272727272 | 1 | 1.0 | 0.0 | 0.46296296296296297 | 0.12962962962962962 | 0.4074074074074074 | 0.0 | 1.0 | 0.5882352941176471 | 1.0 | False | True | False | False | HOLD_RESEARCH_UNFROZEN |

## Coverage ladder

| stage | hits | opportunities | recall |
| --- | --- | --- | --- |
| MENTION | 57 | 57 | 1.0 |
| CANDIDATE | 57 | 57 | 1.0 |
| BINDING | 41 | 57 | 0.7192982456140351 |
| FINAL_FACT | 29 | 57 | 0.5087719298245614 |

The high-recall stage achieved 100% mention and candidate recall with 67.86%
candidate precision. Binding recall reached 71.93%, and final critical recall
passed the V2.4 interim 50% milestone at 51.79%. The strict verifier did not
preserve the required 99% precision: final critical precision was 53.70%.
Consequently this snapshot is frozen as a diagnostic benchmark, not promoted.

The errors concentrate in duplicate CHANGE_TO/CHANGE_BY emission, cross-clause
metric/value binding, and flattened financial-grid routing. Every missed block
was captured by auto/review/abstention rather than silently dropped.

## Certification funnel

| level | tickers |
| --- | --- |
| REGISTERED | 52 |
| L0_SOURCE_READY | 52 |
| L1_PARSER_READY | 0 |
| L2_ECONOMICS_READY | 0 |
| L3_VALUATION_READY | 0 |

All 52 registered issuers remain source-ready at L0. L1-L3 remain closed. No
forecast, DCF/reverse-DCF, terminal input, or production state was changed, and
no DCF was executed.
