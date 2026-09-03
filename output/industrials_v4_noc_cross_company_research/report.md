# Industrials Platform V4 — NOC cross-company timing research

## Decision

| version | lmt_v31_evidence_parent_unchanged | source_gate_pass | ir_parser_gate_pass | sec_ir_reconciliation_gate_pass | historical_pit_industry_gate_pass | fixed_oos_window_pass | segment_model_validation_rows | segment_model_expected_rows | segment_model_full_coverage_pass | company_revenue_mase | company_revenue_champion | funded_backlog_revenue_champion_segments | total_backlog_revenue_champion_segments | funded_backlog_improved_segments | margin_champion_segments | joint_champion_segments | point_performance_gate_pass | evidence_parser_freeze_eligible | forecast_freeze_eligible | terminal_gate_pass | production_gate_pass | live_matched_observations | new_dcf_run | new_reverse_dcf_run | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INDUSTRIALS_PLATFORM_V4_NOC_CROSS_COMPANY_RESEARCH | True | True | True | True | True | True | 10 | 24 | False | 0.9374475239933094 | True | 1 | 1 | 1 | 1 | 1 | True | True | False | False | False | 0/20 | False | False | EVIDENCE_FREEZE_ELIGIBLE_FORECAST_UNFROZEN |

LMT V3.1 evidence remains byte-for-byte unchanged. This branch tests Northrop
Grumman independently and does not modify or tune the frozen LMT experiment.

## 10-K, 10-Q and IR evidence

| sec_filings | sec_10k_filings | sec_10q_filings | sec_hash_matches | ir_earnings_releases | ir_hash_matches | concept_families_audited | concept_family_minimum_coverage_pct | coverage_denominators_are_applicability_aware | source_gate_pass | html_only | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 6 | 17 | 23 | 26 | 26 | 13 | 100.0 | True | True | True | False |

| earnings_releases | hash_matches | segment_quarter_rows | segment_sales_coverage_pct | segment_operating_profit_coverage_pct | backlog_segment_quarter_rows | total_backlog_coverage_pct | funded_backlog_coverage_pct | funded_share_coverage_pct | scope_change_comparisons | material_scope_change_rows | parser_gate_pass | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26 | 26 | 104 | 100.0 | 100.0 | 104 | 100.0 | 100.0 | 100.0 | 88 | 18 | True | False |

NOC discloses total backlog and the funded/unfunded split for every segment and
quarter. The funded share is treated as a limited contract-maturity proxy, not
as disclosed delivery timing.

## SEC-to-IR reconciliation

| expected_segment_metric_cells | selected_segment_metric_cells | scope_comparable_cells | scope_recast_excluded_cells | sec_ir_segment_identity_pass_cells | sec_ir_segment_identity_coverage_pct | maximum_applicable_segment_absolute_difference_usd | segment_reconciliation_gate_pass | rpo_backlog_periods | rpo_backlog_identity_pass_periods | rpo_backlog_maximum_absolute_difference_pct | segment_and_backlog_reconciliation_gate_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 184 | 184 | 166 | 18 | 166 | 100.0 | 0.0 | True | 23 | 23 | 0.06155778894472362 | True |

Scope-recast annual cells are excluded from the reconciliation denominator and
remain visible in the detailed audit. The SEC RPO fact is rounded to $0.1bn, so
the backlog identity tolerance is 0.07%.

## Fixed OOS segment results

| segment | validation_observations | revenue_claim_observations | margin_claim_observations | scope_change_rows | program_adjustment_rows | revenue_route | funded_backlog_revenue_mase | total_backlog_revenue_mase | funded_vs_total_mase_improvement_pct | funded_backlog_revenue_level_ape_pct | funded_backlog_revenue_champion_eligible | total_backlog_revenue_champion_eligible | margin_route | margin_mase | margin_champion_eligible | joint_champion | margin_boundary_hits | margin_boundary_hit_pct | funded_backlog_anchor_coverage_pct | historical_pit_input_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics_systems | 2 | 2 | 1 | 0 | 1 | STRUCTURAL_FUNDED_BACKLOG_CONVERSION_PRICE | 0.061089000676626475 | 0.3447955838545596 | 82.28254550313649 | 0.8053606167627569 | False | False | CONDITIONAL_REVENUE_MIX_PRICE_COST | 20.021621621623268 | False | False | 1 | 50.0 | 100.0 | 100.0 |
| mission_systems | 6 | 6 | 5 | 0 | 1 | STRUCTURAL_FUNDED_BACKLOG_CONVERSION_PRICE | 0.6151087239906403 | 0.6030716367236408 | -1.995963088629802 | 4.154769135768542 | True | True | CONDITIONAL_REVENUE_MIX_PRICE_COST | 0.3776068347036638 | True | True | 0 | 0.0 | 100.0 | 100.0 |
| space_systems | 2 | 2 | 0 | 0 | 2 | STRUCTURAL_FUNDED_BACKLOG_CONVERSION_PRICE | 1.8478574835768284 | 1.3684324282987081 | -35.03461664337795 | 6.668580663923779 | False | False | CONDITIONAL_REVENUE_MIX_PRICE_COST |  | False | False | 0 | 0.0 | 100.0 | 100.0 |

| segment | expected_validation_rows | model_validation_rows | missing_model_rows | coverage_status | missing_rows_imputed |
| --- | --- | --- | --- | --- | --- |
| aeronautics_systems | 6 | 2 | 4 | INSUFFICIENT_SCOPE_STABLE_TRAINING_HISTORY | False |
| defense_systems | 6 | 0 | 6 | INSUFFICIENT_SCOPE_STABLE_TRAINING_HISTORY | False |
| mission_systems | 6 | 6 | 0 | COMPLETE | False |
| space_systems | 6 | 2 | 4 | INSUFFICIENT_SCOPE_STABLE_TRAINING_HISTORY | False |

The funded-backlog route was predeclared. The total-backlog route is retained as
an immutable comparison, not selected after observing OOS results.

## Fixed OOS company-level result

| company | validation_observations | revenue_claim_observations | margin_claim_observations | funded_backlog_revenue_mase | total_backlog_revenue_mase | funded_vs_total_mase_improvement_pct | funded_backlog_revenue_champion_eligible | total_backlog_revenue_champion_eligible | margin_mase | margin_champion_eligible | program_adjustment_periods | historical_pit_input_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NOC | 6 | 6 | 1 | 0.9374475239933094 | 0.9516529006325828 | 1.4927056524317583 | True | True | 14.606088104526664 | False | 5 | 100.0 |

Company aggregation is scope-stable across segment realignments. It is reported
separately and is not used to fill missing segment forecasts.

## Cross-company diagnosis

| company | segments | median_revenue_mase | revenue_champions | median_margin_mase | margin_champions | joint_champions | cross_company_timing_classification | two_company_sample_is_industry_conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LMT | 4 | 0.8644841507594752 | 2 | 0.18920620722747816 | 3 | 1 | MIXED_NOT_IDENTIFIED_WITH_TWO_COMPANIES | False |
| NOC | 3 | 0.6151087239906403 | 1 | 10.199614228163465 | 1 | 1 | MIXED_NOT_IDENTIFIED_WITH_TWO_COMPANIES | False |

| company | validation_observations | revenue_mase | revenue_champion_eligible | route | cross_company_timing_classification | two_company_sample_is_industry_conclusion |
| --- | --- | --- | --- | --- | --- | --- |
| LMT | 6 | 0.7459266942076621 | True | SUM_OF_PREDECLARED_SEGMENT_ROUTES | AGGREGATE_REVENUE_CHAMPION_BOTH_SEGMENT_TIMING_UNRESOLVED | False |
| NOC | 6 | 0.9374475239933094 | True | AGGREGATE_FUNDED_BACKLOG_CONVERSION_PRICE | AGGREGATE_REVENUE_CHAMPION_BOTH_SEGMENT_TIMING_UNRESOLVED | False |

Two companies can distinguish an obvious company-specific result from a first
replication, but cannot establish an industry-wide law.

## Historical reinvestment and ROIC evidence

| annual_10k_filings | metrics_audited | critical_annual_metric_minimum_coverage_pct | reported_roic_years | latest_reported_roic_pct | latest_core_reinvestment_rate_pct | latest_innovation_adjusted_reinvestment_rate_pct | research_evidence_ready | segment_roic_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 20 | 100.0 | 5 | 13.492247218966714 | 107.02841165879546 | 136.5794289340653 | True | False | False |

These company-level historical bridges are diagnostic only. Segment ROIC,
terminal economics, DCF and reverse DCF remain locked.

## Uncertainty and authority

| segments_targets_evaluated | point_champions | uncertainty_champions | insufficient_calibration_targets | point_champion_equals_uncertainty_champion_policy | uncertainty_terminal_input_allowed | status | company |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 2 | 0 | 6 | False | False | HOLD_UNCERTAINTY_CALIBRATION | NOC |

| company | research_evidence_authority | forecast_authority | terminal_input_allowed | production_promotable | dcf_result | reverse_dcf_result | reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NOC | True | False | False | False | NOT_RUN_BY_DESIGN | NOT_RUN_BY_DESIGN | SECOND_COMPANY_TIMING_RESEARCH_DOES_NOT_CLOSE_UNCERTAINTY_TERMINAL_OR_LIVE_GATES |
