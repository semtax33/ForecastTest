# Industrials V1.7 — Segment profit driver and comparable-margin bridge

## Result

| version | revenue_champion_parent_verified | sec_ir_source_gate_pass | profit_driver_parser_gate_pass | power_energy_product_mix_gate_pass | reinvestment_roic_note_evidence_ready | fixed_oos_window_unchanged | historical_pit_coverage_pct | margin_champion_segments | minimum_margin_champion_segments | maximum_selected_margin_mase | maximum_allowed_worst_margin_mase | unforecastable_scope_change_rows | unforecastable_scope_changes_used_as_component_claims | research_freeze_eligible | terminal_input_allowed | new_dcf_run | new_reverse_dcf_run | live_matched_observations | production_promotable | pdf_parsing_deferred | status | failed_conditions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INDUSTRIALS_CAT_MARGIN_V1_7 | True | True | True | True | True | True | 100.0 | 2 | 2 | 1.0986630381463152 | 1.5 | 4 | False | True | False | False | False | 0/20 | False | True | RESEARCH_FROZEN |  |

Revenue remains the separately frozen `INDUSTRIALS_CAT_REVENUE_CHAMPION_V1`.
This branch evaluates margin evidence only; terminal valuation and production
promotion remain independent and locked.

## Source and parser audit

| sec_filings | sec_10k_filings | sec_10q_filings | sec_hash_matches | ir_earnings_releases | ir_quarters | ir_hash_matches | all_sec_hashes_match | all_ir_hashes_match | expected_periodic_filing_count | periodic_filing_inventory_complete | html_only | pdf_parsing_used | source_gate_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 6 | 17 | 23 | 23 | 23 | 23 | True | True | 23 | True | True | False | True |

All 23 official CAT 10-K/10-Q HTML filings from 2021 through the cutoff and all
23 matching Arcana earnings-release HTML files were hash-checked. PDFs were not
parsed by design.

## Company-reported profit-driver evidence

| segment | quarters | profit_passages_found | quarters_with_numeric_driver | fully_explained_quarters | median_absolute_unallocated_residual_usd | maximum_bridge_identity_error_usd | passage_coverage_pct | numeric_driver_coverage_pct | profit_driver_parser_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 23 | 23 | 7 | 5 | 158000000.0 | 0.0 | 100.0 | 30.434782608695656 | True |
| power_energy | 23 | 23 | 9 | 6 | 79000000.0 | 0.0 | 100.0 | 39.130434782608695 | True |
| resource | 23 | 23 | 6 | 5 | 49000000.0 | 0.0 | 100.0 | 26.08695652173913 | True |

Only explicitly quantified price, volume/mix, manufacturing cost, SG&A/R&D and
currency effects are assigned to a named driver. Every undisclosed remainder is
kept as `unallocated_other_residual_usd`; it is never reverse-labelled.

## P&E application mix

| quarters | tables_found | full_four_application_quarters | scope_change_rows | latest_scope | product_mix_history_ready | unexpected_scope_forecasted |
| --- | --- | --- | --- | --- | --- | --- |
| 23 | 23 | 21 | 1 | oil_gas\|power_generation\|industrial | True | False |

The product-mix route uses only the most recently released application mix at
each forecast origin. The 2026 removal of Transportation from the segment is an
explicit scope change.

## Reported versus comparable margin

The current reported margin, originally reported prior-year margin, and the
current filing's recast comparable prior margin satisfy an exact additive
perimeter identity. Material unexpected changes are labelled
`UNFORECASTABLE_SCOPE_CHANGE` and cannot support component attribution.

## Fixed six-quarter margin validation

| segment | validation_observations | predeclared_route | structural_margin_mae_pct_points | structural_margin_mase | reduced_form_margin_mae_pct_points | reduced_form_margin_mase | selected_margin_mae_pct_points | selected_margin_mase | naive_margin_mae_pct_points | unforecastable_scope_change_rows | interval_coverage_pct | historical_pit_input_pct | margin_champion_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | STRUCTURAL_PROFIT_DRIVER | 4.817700522179235 | 1.0986630381463152 | 4.133434586082799 | 0.9426181182118389 | 4.817700522179235 | 1.0986630381463152 | 4.385057433358047 | 0 | 66.66666666666666 | 100.0 | False |
| power_energy | 6 | REDUCED_FORM_PRODUCT_MIX | 2.35674391227707 | 2.207378069761497 | 0.8604973929224139 | 0.8059607428405954 | 0.8604973929224139 | 0.8059607428405954 | 1.0676666333518987 | 2 | 83.33333333333334 | 100.0 | True |
| resource | 6 | REDUCED_FORM_MARGIN | 4.460688317112509 | 0.8985281933919951 | 4.085353415594166 | 0.8229234958648325 | 4.085353415594166 | 0.8229234958648325 | 4.964438901213724 | 2 | 50.0 | 100.0 | True |

Construction keeps the predeclared structural route even though it fails the
MASE<1 champion threshold. P&E and Resource use reduced-form routes; their
statistical forecasts do not create economic component or ROIC claims.

## Reinvestment and ROIC note evidence

| annual_10k_filings | annual_periods | raw_relevant_xbrl_facts | periodic_filings_parsed | quarterly_discrete_complete_rows | selected_metrics | critical_metric_minimum_coverage_pct | inventory_identity_pass_years | latest_reported_roic_pct | latest_tangible_roic_sensitivity_pct | latest_core_reinvestment_rate_pct | latest_innovation_adjusted_reinvestment_rate_pct | latest_total_including_mna_reinvestment_rate_pct | mpe_and_consolidated_perimeters_kept_separate | research_evidence_ready | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 6 | 10250 | 23 | 20 | 27 | 100.0 | 6 | 17.70094037416702 | 20.045494003237984 | 43.37855947030475 | 68.71909407520403 | 69.2735657355533 | True | True | False | False |

| metric | years | years_available | coverage_pct |
| --- | --- | --- | --- |
| accounts_payable_usd | 6 | 6 | 100.0 |
| business_acquisitions_usd | 6 | 6 | 100.0 |
| capex_usd | 6 | 6 | 100.0 |
| cash_usd | 6 | 6 | 100.0 |
| cfo_usd | 6 | 6 | 100.0 |
| debt_current_usd | 6 | 6 | 100.0 |
| debt_noncurrent_usd | 6 | 6 | 100.0 |
| depreciation_amortization_usd | 6 | 6 | 100.0 |
| equipment_on_lease_capex_usd | 6 | 6 | 100.0 |
| equity_usd | 6 | 6 | 100.0 |
| goodwill_usd | 6 | 6 | 100.0 |
| income_tax_usd | 6 | 6 | 100.0 |
| intangibles_ex_goodwill_usd | 6 | 6 | 100.0 |
| inventory_finished_goods_usd | 6 | 6 | 100.0 |
| inventory_raw_material_usd | 6 | 6 | 100.0 |
| inventory_supplies_usd | 6 | 6 | 100.0 |
| inventory_usd | 6 | 6 | 100.0 |
| inventory_work_in_process_usd | 6 | 6 | 100.0 |
| operating_income_usd | 6 | 6 | 100.0 |
| pension_opeb_liability_usd | 6 | 6 | 100.0 |
| ppe_net_usd | 6 | 6 | 100.0 |
| pretax_income_usd | 6 | 6 | 100.0 |
| research_development_usd | 6 | 6 | 100.0 |
| restructuring_cost_usd | 6 | 6 | 100.0 |
| revenue_usd | 6 | 6 | 100.0 |
| trade_receivables_usd | 6 | 6 | 100.0 |
| warranty_accrual_usd | 6 | 6 | 100.0 |

Capex includes both PP&E purchases and equipment acquired for lease. Net capex,
operating working capital, R&D, cash acquisitions, goodwill/intangibles,
restructuring, warranty and pension/OPEB evidence are retained separately.
Consolidated and MP&E ROIC perimeters are cross-checked but never blended.

## Route authority

| segment | predeclared_route | selected_margin_mase | margin_champion_eligible | unforecastable_scope_change_rows | component_attribution_allowed | reduced_form_route | roic_attribution_allowed | terminal_input_allowed | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | STRUCTURAL_PROFIT_DRIVER | 1.0986630381463152 | False | 0 | False | False | False | False | RESEARCH_ONLY_NOT_CHAMPION |
| power_energy | REDUCED_FORM_PRODUCT_MIX | 0.8059607428405954 | True | 2 | False | True | False | False | MARGIN_RESEARCH_CHAMPION |
| resource | REDUCED_FORM_MARGIN | 0.8229234958648325 | True | 2 | False | True | False | False | MARGIN_RESEARCH_CHAMPION |

## Valuation authority

| v1_3_lite_reference_value_per_share_usd | reference_preserved | new_dcf_value_per_share_usd | new_reverse_dcf_result | reinvestment_bridge_used_in_terminal | margin_champion_used_in_terminal | reason |
| --- | --- | --- | --- | --- | --- | --- |
| 399.1175 | True |  | NOT_RUN_BY_DESIGN | False | False | MARGIN_RESEARCH_FREEZE_IS_SEPARATE_FROM_TERMINAL_EVIDENCE_AND_PRODUCTION |
