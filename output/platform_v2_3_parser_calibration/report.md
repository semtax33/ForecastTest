# Platform V2.3 — Semantic Binding Calibration

## Gate

| version | registered_tickers | latest_ir_parsed | latest_ir_parse_errors | universe_auto_frames | universe_review_items | universe_abstentions | dev_examples | dev_exact_passed | blind_evaluation_issuers | blind_annotated_blocks | blind_annotation_coverage | selection_critical_concepts_covered | selection_required_critical_concepts | selection_concept_coverage | gold_critical_concepts_covered | gold_critical_concept_coverage | blind_critical_precision | blind_critical_recall | blind_narrative_precision | blind_narrative_recall | blind_auto_coverage | blind_review_rate | blind_abstention_rate | blind_table_route_accuracy | l0_source_ready | l1_parser_ready | l2_economics_ready | l3_valuation_ready | strict_dcf_runs | forecast_snapshot_changed | dcf_kernel_changed | terminal_input_ready | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_3_SEMANTIC_BINDING_CALIBRATION | 52 | 48 | 0 | 387 | 287 | 1288 | 15 | 15 | 10 | 39 | 1.0 | 10 | 10 | 1.0 | 7 | 0.7 | 1.0 | 0.16666666666666666 | 1.0 | 0.25 | 0.05128205128205128 | 0.2564102564102564 | 0.6923076923076923 | 0.9473684210526315 | 52 | 0 | 0 | 0 | 0 | False | False | False | False | HOLD_RESEARCH_UNFROZEN |

## Development corpus

| examples | expected_frames | auto_emitted | reviews | abstentions | auto_precision | auto_recall | auto_f1 | critical_precision | critical_recall | critical_f1 | narrative_precision | narrative_recall | narrative_f1 | auto_coverage | review_rate | abstention_rate | review_capture | review_plus_abstention_capture |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | 16 | 16 | 1 | 1 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8888888888888888 | 0.05555555555555555 | 0.05555555555555555 | 1.0 | 1.0 |

All 15 generic development examples pass exactly. The repair is company-neutral:
local metric/value binding, word-form percentages, point guidance, bullet offsets,
composition, and a small narrative-driver ontology.

## Outcome-blind sentence audit

| version | parser_snapshot_verified | candidate_artifact_verified | blindness_claim | evaluation_issuers | annotated_blocks | annotation_coverage | expected_frames | auto_emitted_frames | auto_precision | auto_recall | auto_f1 | critical_opportunities | critical_precision | critical_recall | critical_f1 | narrative_opportunities | narrative_precision | narrative_recall | narrative_status | auto_coverage | review_rate | abstention_rate | silent_rate | review_plus_abstention_miss_capture | table_route_accuracy | source_span_coverage | critical_precision_gate_99pct | critical_recall_gate_95pct | rule_changes_after_selection | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLATFORM_V2_3_OUTCOME_BLIND_SENTENCE_GOLD | True | True | SENTENCE_BLOCK_OUTCOME_BLIND_NOT_ISSUER_UNSEEN | 10 | 39 | 1.0 | 22 | 4 | 1.0 | 0.18181818181818182 | 0.3076923076923077 | 18 | 1.0 | 0.16666666666666666 | 0.2857142857142857 | 4 | 1.0 | 0.25 | MEASURED | 0.05128205128205128 | 0.2564102564102564 | 0.6923076923076923 | 0.0 | 1.0 | 0.9473684210526315 | 1.0 | True | False | False | HOLD_RESEARCH_UNFROZEN |

The parser source snapshot, deterministic selection procedure, 39 candidate
blocks, and source documents were hashed before sentence review. This is a
sentence-block outcome-blind test, not an issuer-unseen claim. All selected
blocks were exhaustively annotated.

Critical precision remains 100%, while critical recall improves from 8.33% to
16.67%. It still fails the 95% recall gate. Narrative precision is 100% but
recall is only 25%, so narrative evidence is not certified. Table routing rises
from 88.89% to 94.74%; one flattened XOM cash-capex table remains misrouted.

## V2.2 to V2.3

| metric | v2_2 | v2_3 | delta |
| --- | --- | --- | --- |
| critical_precision | 1.0 | 1.0 | 0.0 |
| critical_recall | 0.0833333333333333 | 0.16666666666666666 | 0.08333333333333336 |
| auto_coverage | 0.032258064516129 | 0.05128205128205128 | 0.019023986765922284 |
| review_rate | 0.0967741935483871 | 0.2564102564102564 | 0.1596360628618693 |
| abstention_rate | 0.8709677419354839 | 0.6923076923076923 | -0.17866004962779158 |
| table_route_accuracy | 0.8888888888888888 | 0.9473684210526315 | 0.05847953216374269 |

## Certification funnel

| level | tickers |
| --- | --- |
| REGISTERED | 52 |
| L0_SOURCE_READY | 52 |
| L1_PARSER_READY | 0 |
| L2_ECONOMICS_READY | 0 |
| L3_VALUATION_READY | 0 |

E&P source lineage is now hash-verified, moving all 52 registered issuers to L0.
L1 remains empty because recall and gold concept-scope gates fail. No forecast
snapshot, DCF/reverse-DCF kernel, terminal input, or production status changed;
no DCF was executed.
