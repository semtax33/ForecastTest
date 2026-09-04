# Platform V2.5.1 — Constraint-Based Binding Precision Recovery

## Gate

| version | critical_precision | critical_recall | candidate_recall | table_route_accuracy | duplicate_auto_emission | illegal_cross_clause_auto_binding | silent_miss | precision_recovery_achieved | all_v25_gates_passed | l0_source_ready | l1_parser_ready | l2_economics_ready | l3_valuation_ready | strict_dcf_runs | forecast_snapshot_changed | dcf_kernel_changed | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_5_1_PRECISION_ADJUDICATION | 1.0 | 0.16279069767441862 | 1.0 | 0.5789473684210527 | 0 | 0 | 0 | True | False | 52 | 0 | 0 | 0 | 0 | False | False | False | HOLD_RESEARCH_UNFROZEN |

## Version comparison

| version | validation | critical_precision | critical_recall | candidate_recall | table_route_accuracy | silent_miss |
| --- | --- | --- | --- | --- | --- | --- |
| V2.4 | issuer_document_unseen_1 | 0.5370370370370371 | 0.5178571428571429 | 1.0 | 0.5882352941176471 | 0 |
| V2.5 | issuer_document_unseen_2 | 0.5714285714285714 | 0.21428571428571427 | 1.0 | 0.7692307692307693 | 4 |
| V2.5.1 | issuer_document_unseen_3 | 1.0 | 0.16279069767441862 | 1.0 | 0.5789473684210527 | 0 |

V2.5 introduced clause-local typed eligibility, top-1/top-2 ambiguity margins,
canonical CHANGE_TO merging, conflict resolution, and a separate layout router.
Its first unseen audit removed duplicate and illegal cross-clause emissions but
did not recover precision. That result was frozen and not reused for validation.

V2.5.1 added a fail-closed adjudicator and was evaluated on a third, disjoint
issuer/document-unseen set. Critical precision recovered to 100%, duplicate and
cross-clause errors remained zero, and silent misses fell to zero. Critical
recall is only 16.28% and table routing 57.89%, so the V2.5 milestone is not met.

## Coverage ladder

| stage | hits | opportunities | recall |
| --- | --- | --- | --- |
| MENTION | 44 | 44 | 1.0 |
| CANDIDATE | 44 | 44 | 1.0 |
| BINDING | 0 | 44 | 0.0 |
| FINAL_FACT | 7 | 44 | 0.1590909090909091 |

## Error taxonomy

| error_class | count | auto_errors |
| --- | --- | --- |
| TABLE_ROUTING | 8 | 0 |
| UNSUPPORTED_CAUSE_EFFECT | 5 | 0 |
| UNSUPPORTED_CHANGE_BY | 12 | 0 |
| UNSUPPORTED_CHANGE_TO | 15 | 0 |
| UNSUPPORTED_COMPARATIVE | 20 | 0 |
| UNSUPPORTED_RANGE_GUIDANCE | 1 | 0 |

## Certification funnel

| level | tickers |
| --- | --- |
| REGISTERED | 52 |
| L0_SOURCE_READY | 52 |
| L1_PARSER_READY | 0 |
| L2_ECONOMICS_READY | 0 |
| L3_VALUATION_READY | 0 |

L1-L3 stay closed. Forecast, DCF/reverse DCF, terminal inputs, and production
remain unchanged; no DCF was executed.
