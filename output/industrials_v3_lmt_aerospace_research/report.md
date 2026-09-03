# Industrials Platform V3 — LMT Aerospace & Defense portability research

## Gate

| version | cmi_v2_parent_unchanged | source_gate_pass | ir_parser_gate_pass | historical_pit_industry_gate_pass | fixed_oos_window_pass | revenue_champion_segments | margin_champion_segments | margin_boundary_saturation_pass | joint_champion_segments | minimum_joint_champion_segments | reinvestment_roic_research_ready | sec_ir_segment_reconciliation_pass | sec_ir_segment_identity_pass_cells | sec_ir_segment_identity_expected_cells | sec_rpo_ir_backlog_identity_pass_periods | sec_rpo_ir_backlog_expected_periods | program_loss_no_overallocation_pass | program_loss_unallocated_residual_usd | conditional_financial_bridge_periods | uncertainty_champion_targets | research_freeze_eligible | terminal_gate_pass | production_gate_pass | live_matched_observations | new_dcf_run | new_reverse_dcf_run | pdf_parsing_deferred | status | failed_conditions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INDUSTRIALS_PLATFORM_V3_LMT_AEROSPACE_DEFENSE_RESEARCH | True | True | True | True | True | 2 | 3 | True | 1 | 2 | True | True | 184 | 184 | 23 | 23 | True | 245000000.0 | 0 | 0 | False | False | False | 0/20 | False | False | True | HOLD_RESEARCH_UNFROZEN | PORTABILITY_POINT_PERFORMANCE |

CMI V2 remains byte-for-byte unchanged. LMT is a separate Aerospace & Defense
research branch. Research, uncertainty, terminal and production authorities are separate.

## 10-K, 10-Q, IR and note coverage

| sec_filings | sec_10k_filings | sec_10q_filings | sec_hash_matches | ir_earnings_releases | ir_hash_matches | financial_statement_family_minimum_coverage_pct | note_family_minimum_coverage_pct | note_families_audited | event_conditional_note_families | coverage_denominators_are_applicability_aware | all_sec_hashes_match | all_ir_hashes_match | periodic_filing_inventory_complete | source_gate_pass | html_only | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 6 | 17 | 23 | 27 | 27 | 100.0 | 100.0 | 16 | 2 | True | True | True | True | True | True | False |

| selected_ir_releases | parsed_quarters | parsed_segments | segment_quarter_rows | segment_sales_coverage_pct | segment_operating_profit_coverage_pct | backlog_segment_quarter_rows | backlog_coverage_pct | delivery_program_quarter_rows | delivery_period_coverage_pct | program_loss_rows | material_scope_change_cells | all_selected_hashes_match | parser_gate_pass | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | 27 | 4 | 108 | 100.0 | 100.0 | 108 | 100.0 | 144 | 100.0 | 5 | 0 | True | True | False |

The HTML-only IR parser preserves four reported segments, backlog and deliveries.
Explicit program losses stay in raw actuals but are excluded from margin performance claims.

## SEC-to-IR reconciliation

| sec_periodic_filings | expected_segment_metric_cells | selected_segment_metric_cells | sec_ir_segment_identity_pass_cells | sec_ir_segment_identity_coverage_pct | maximum_segment_absolute_difference_usd | rpo_backlog_periods | rpo_backlog_identity_pass_periods | rpo_backlog_maximum_absolute_difference_pct | program_loss_matching_event_periods | program_loss_exact_identity_periods | program_loss_unallocated_residual_usd | program_loss_ir_allocation_coverage_pct | program_loss_no_overallocation_gate_pass | segment_and_backlog_reconciliation_gate_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 184 | 184 | 184 | 100.0 | 0.0 | 23 | 23 | 0.03560830860532992 | 2 | 1 | 245000000.0 | 93.15642458100558 | True | True |

Every 10-K/10-Q segment sales and operating-profit cell is independently selected
from SEC XBRL and reconciled to the IR history. Consolidated SEC remaining performance
obligations are also reconciled to the sum of reported segment backlog, allowing only
the disclosed rounding tolerance.

| period | ir_segment_allocated_program_losses_usd | ir_program_loss_rows | ir_source_url | form | filing_date | sec_program_gains_losses_usd | sec_source_url | source_sha256 | unallocated_sec_program_losses_usd | ir_allocation_coverage_pct | no_overallocation_pass | comparison_basis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q4 | 1720000000.0 | 2 | https://www.sec.gov/Archives/edgar/data/936468/000093646825000006/ex991q42024.htm | 10-K | 2025-01-28 | 1965000000.0 | https://www.sec.gov/Archives/edgar/data/936468/000093646825000009/lmt-20241231.htm | 2f0cfc64cf462d85a072f100e716b375eff60ee13d7f9eb35759b311fa22cb20 | 245000000.0 | 87.53180661577609 | True | IR_EXPLICIT_SEGMENT_ALLOCATION_VS_SEC_CONSOLIDATED_PROGRAM_LOSSES |
| 2025Q2 | 1615000000.0 | 3 | https://www.sec.gov/Archives/edgar/data/936468/000162828025035502/ex991q22025.htm | 10-Q | 2025-07-22 | 1615000000.0 | https://www.sec.gov/Archives/edgar/data/936468/000162828025035565/lmt-20250629.htm | ad7e85a6b0c5ecf24716d1111956b94c2c1121deea6e6803601db1d476755e74 | 0.0 | 100.0 | True | IR_EXPLICIT_SEGMENT_ALLOCATION_VS_SEC_CONSOLIDATED_PROGRAM_LOSSES |

Only program losses explicitly allocated to a segment by IR evidence are normalized.
The SEC total above that allocation remains an unallocated residual; it is never
silently assigned to a segment.

## Industry data authority

| bls_model_series | bls_archive_vintage_rows | bls_historical_pit_ready | pit_feature_rows | census_aerospace_defense_context_rows | census_context_categories | census_context_measures | census_source_sha256 | bea_io_source_sha256 | revised_census_used_in_oos_claim | bea_latest_snapshot_used_in_oos_claim | historical_pit_ready | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 1080 | True | 56 | 486 | 3 | 3 | 576572cec29eba3327c25aa8abf5fe270807ffb5975300dc81b6cf0ac89bfc00 | 373a13394c81c9d672c4e177b9bab31227f5d8cee990241234e25b1b0fa9484b | False | False | True | False |

BLS PPI values are selected from 54 archived as-released workbooks and enter the model.
Census DAP/NAP/DEF and BEA input-output snapshots are retained as context only because
their historical release vintages are not available in the local lake.

## Segment Revenue and operating margin

| segment | validation_observations | revenue_claim_observations | margin_claim_observations | scope_change_rows | program_loss_rows | revenue_route | margin_boundary_hits | margin_boundary_hit_pct | structural_anchor_coverage_pct | delivery_anchor_coverage_pct | revenue_mae_usd | revenue_mase | revenue_level_ape_pct | revenue_champion_eligible | margin_route | margin_mae_pct_points | margin_mase | margin_champion_eligible | joint_champion | historical_pit_input_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics | 6 | 6 | 5 | 0 | 1 | STRUCTURAL_BACKLOG_DELIVERIES_PRICE | 0 | 0.0 | 100.0 | 100.0 | 433373004.40875036 | 1.0678595591180708 | 5.829424087323801 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.921648923505845 | 0.2745055806096747 | True | False | 100.0 |
| missiles_fire_control | 6 | 6 | 6 | 0 | 0 | STRUCTURAL_BACKLOG_PRICE | 0 | 0.0 | 100.0 | 0.0 | 141581892.57404765 | 0.3132342756063001 | 3.7064673601003797 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.29453747855896495 | 0.042353365190104075 | True | True | 100.0 |
| rotary_mission_systems | 6 | 6 | 5 | 0 | 1 | STRUCTURAL_BACKLOG_HELICOPTER_DELIVERIES | 1 | 16.666666666666664 | 100.0 | 100.0 | 447628742.9772549 | 1.4517688961424484 | 10.61107312380907 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.40964303708307703 | 0.10390683384528168 | True | False | 100.0 |
| space | 6 | 6 | 6 | 0 | 0 | STRUCTURAL_BACKLOG_PRICE | 0 | 0.0 | 100.0 | 0.0 | 120101421.53615975 | 0.6611087424008795 | 3.6613312302533214 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 1.3671939448491972 | 1.0293042449306267 | False | False | 100.0 |

## Reinvestment and ROIC evidence

| periodic_filings_parsed | annual_10k_filings | quarterly_10q_filings | raw_relevant_xbrl_facts | financial_statement_metric_mean_coverage_pct | note_metric_mean_coverage_pct | coverage_denominators_are_applicability_aware | critical_annual_metric_minimum_coverage_pct | quarterly_statement_chain_complete_rows | quarterly_note_contract_chain_complete_rows | reported_roic_years | latest_reported_roic_pct | latest_pension_adjusted_roic_pct | latest_through_cycle_roic_median_pct | latest_innovation_adjusted_reinvestment_rate_pct | research_evidence_ready | segment_roic_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 6 | 17 | 9444 | 100.0 | 100.0 | True | 100.0 | 22 | 23 | 5 | 27.053071591155902 | 22.93018461722804 | 27.053071591155902 | 8.443329930854421 | True | False | False |

| evidence_layer | metric | annual_filings | years_available | coverage_pct |
| --- | --- | --- | --- | --- |
| FINANCIAL_STATEMENT | accounts_payable_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | capex_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | cash_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | cfo_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | debt_current_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | debt_noncurrent_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | depreciation_amortization_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | equity_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | goodwill_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | income_tax_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | intangibles_ex_goodwill_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | inventory_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | operating_income_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | pretax_income_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | receivables_usd | 6 | 6 | 100.0 |
| FINANCIAL_STATEMENT | revenue_usd | 6 | 6 | 100.0 |
| NOTE | business_acquisitions_usd | 6 | 1 | 16.666666666666664 |
| NOTE | contract_assets_usd | 6 | 6 | 100.0 |
| NOTE | contract_liabilities_usd | 6 | 6 | 100.0 |
| NOTE | fas_cas_pension_adjustment_usd | 6 | 4 | 66.66666666666666 |
| NOTE | pension_liability_usd | 6 | 6 | 100.0 |
| NOTE | program_gains_losses_usd | 6 | 2 | 33.33333333333333 |
| NOTE | remaining_performance_obligation_usd | 6 | 6 | 100.0 |
| NOTE | research_development_usd | 6 | 6 | 100.0 |

## Conditional company financial bridge

| forecast_periods | forecast_first_period | forecast_last_period | revenue_margin_joint_champion_segments | financial_bridge_claim_periods | mean_revenue_ape_pct | mean_operating_margin_error_pct_points | reinvestment_forecast_is_conditional_bridge | roic_forecast_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 2025Q1 | 2026Q2 | 1 | 0 | 4.00069712170067 | 1.8757166839869754 | True | False | False |

Reinvestment and annualized ROIC are diagnostics conditioned on segment point forecasts
and trailing, origin-available financial-statement ratios. They are not terminal inputs.

## Prediction interval calibration

| segments_targets_evaluated | point_champions | uncertainty_champions | insufficient_calibration_targets | point_champion_equals_uncertainty_champion_policy | uncertainty_terminal_input_allowed | status |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | 5 | 0 | 8 | False | False | HOLD_UNCERTAINTY_CALIBRATION |

## Target and valuation authority

| segment | revenue_route | structural_anchor_coverage_pct | delivery_anchor_coverage_pct | revenue_mase | revenue_champion_eligible | margin_route | margin_mase | margin_champion_eligible | joint_champion | scope_change_rows | program_loss_rows | margin_boundary_hits | margin_boundary_hit_pct | research_performance_claim_allowed | economic_component_claim_allowed | reinvestment_forecast_claim_allowed | roic_forecast_claim_allowed | terminal_input_allowed | production_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics | STRUCTURAL_BACKLOG_DELIVERIES_PRICE | 100.0 | 100.0 | 1.0678595591180708 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.2745055806096747 | True | False | 0 | 1 | 0 | 0.0 | False | False | False | False | False | False |
| missiles_fire_control | STRUCTURAL_BACKLOG_PRICE | 100.0 | 0.0 | 0.3132342756063001 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.042353365190104075 | True | True | 0 | 0 | 0 | 0.0 | True | True | False | False | False | False |
| rotary_mission_systems | STRUCTURAL_BACKLOG_HELICOPTER_DELIVERIES | 100.0 | 100.0 | 1.4517688961424484 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.10390683384528168 | True | False | 0 | 1 | 1 | 16.666666666666664 | False | False | False | False | False | False |
| space | STRUCTURAL_BACKLOG_PRICE | 100.0 | 0.0 | 0.6611087424008795 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 1.0293042449306267 | False | False | 0 | 0 | 0 | 0.0 | True | True | False | False | False | False |

| lmt_dcf_value_per_share_usd | lmt_reverse_dcf_result | reason | research_financial_bridge_available | terminal_input_allowed | production_promotable |
| --- | --- | --- | --- | --- | --- |
|  | NOT_RUN_BY_DESIGN | AEROSPACE_PORTABILITY_RESEARCH_REQUIRES_SEPARATE_UNCERTAINTY_TERMINAL_AND_LIVE_GATES | True | False | False |
