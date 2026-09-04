# Platform V2.2 — Blind Parser Generalization & Calibration

## Gate

| version | registered_tickers | latest_ir_parsed | latest_ir_parse_errors | universe_auto_frames | universe_review_items | universe_abstentions | dev_examples | dev_exact_passed | blind_evaluation_issuers | blind_annotated_blocks | blind_annotation_coverage | blind_critical_concepts_covered | blind_required_critical_concepts | blind_critical_precision | blind_critical_recall | blind_auto_coverage | blind_review_rate | blind_abstention_rate | blind_table_route_accuracy | l0_source_ready | l1_parser_ready | l2_economics_ready | l3_valuation_ready | strict_dcf_runs | forecast_snapshot_changed | dcf_kernel_changed | terminal_input_ready | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_2_BLIND_PARSER_GENERALIZATION | 52 | 48 | 0 | 84 | 194 | 801 | 16 | 16 | 8 | 31 | 1.0 | 4 | 10 | 1.0 | 0.08333333333333333 | 0.03225806451612903 | 0.0967741935483871 | 0.8709677419354839 | 0.8888888888888888 | 38 | 0 | 0 | 0 | 0 | False | False | False | False | HOLD_RESEARCH_UNFROZEN |

## Error taxonomy

| failure_class | repair_layer | errors | issuers |
| --- | --- | --- | --- |
| RELATION_ERROR | CONTEXT_VALIDATOR | 7 | 3 |
| ONTOLOGY_ERROR | ONTOLOGY | 2 | 2 |
| DOCUMENT_CONTEXT_ERROR | CONTEXT_VALIDATOR | 1 | 1 |

The ten V2.1 blind errors are classified by reusable parser failure mode, not
by issuer. No ticker-specific parser branch was added.

## Development corpus

| examples | expected_frames | auto_emitted | reviews | abstentions | auto_precision | auto_recall | auto_f1 | critical_precision | critical_recall | critical_f1 | narrative_precision | narrative_recall | narrative_f1 | auto_coverage | review_rate | abstention_rate | review_capture | review_plus_abstention_capture |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 14 | 14 | 1 | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7368421052631579 | 0.05263157894736842 | 0.21052631578947367 | 1.0 | 1.0 |

The development corpus uses company-neutral paraphrases of the failure modes;
it does not replay the V2.1 holdout sentences.

## New outcome-blind sentence audit

| version | parser_snapshot_verified | evaluation_issuers | annotated_blocks | annotation_coverage | expected_frames | auto_emitted_frames | auto_precision | auto_recall | auto_f1 | critical_opportunities | critical_precision | critical_recall | critical_f1 | narrative_opportunities | narrative_precision | narrative_recall | narrative_status | auto_coverage | review_rate | abstention_rate | silent_rate | review_plus_abstention_miss_capture | table_route_accuracy | source_span_coverage | critical_precision_gate_99pct | critical_recall_gate_95pct | rule_changes_after_selection | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_2_BLIND_B_SENTENCE_GOLD | True | 8 | 31 | 1.0 | 12 | 1 | 1.0 | 0.08333333333333333 | 0.15384615384615385 | 12 | 1.0 | 0.08333333333333333 | 0.15384615384615385 | 0 | 1.0 | 1.0 | NOT_MEASURED_NO_OPPORTUNITIES | 0.03225806451612903 | 0.0967741935483871 | 0.8709677419354839 | 0.0 | 1.0 | 0.8888888888888888 | 1.0 | True | False | False | HOLD_RESEARCH_UNFROZEN |

The parser snapshot and issuer/sample selection were hashed before sentence
review. All target facts within the 31 selected blocks were annotated. Dense
tables are explicitly routed to the table DSL and excluded from text-IE recall.

Critical precision reached 100%, but critical recall is only 8.33%. This is the
expected precision/coverage trade-off from strict abstention and fails the 95%
recall gate. Narrative precision is not claimed because the blind sample had no
narrative frame opportunity.

## Decision disposition

| disposition | blocks |
| --- | --- |
| ABSTAINED | 27 |
| AUTO_EMITTED | 1 |
| REVIEW | 3 |

## Certification funnel

| level | tickers |
| --- | --- |
| REGISTERED | 52 |
| L0_SOURCE_READY | 38 |
| L1_PARSER_READY | 0 |
| L2_ECONOMICS_READY | 0 |
| L3_VALUATION_READY | 0 |

Forecast snapshots and the DCF/reverse-DCF kernel were not changed. No DCF is
executed because L3 is empty; terminal authority and production remain locked.
