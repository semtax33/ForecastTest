# Industrials Platform V2 — CMI cross-company portability research

## Gate

| version | cat_v1_7_parent_unchanged | source_gate_pass | ir_parser_gate_pass | historical_pit_industry_gate_pass | fixed_oos_window_pass | revenue_champion_segments | margin_champion_segments | joint_champion_segments | minimum_joint_champion_segments | reinvestment_roic_research_ready | uncertainty_champion_segments | research_freeze_eligible | terminal_gate_pass | production_gate_pass | live_matched_observations | new_dcf_run | new_reverse_dcf_run | pdf_parsing_deferred | status | failed_conditions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INDUSTRIALS_PLATFORM_V2_CMI_PORTABILITY_RESEARCH | True | True | True | True | True | 4 | 3 | 3 | 3 | True | 0 | True | False | False | 0/20 | False | False | True | FREEZE_ELIGIBLE_NOT_FROZEN |  |

CAT V1.7 remains byte-for-byte unchanged. CMI is a separate portability branch;
its research, terminal and production authorities are evaluated independently.

## 10-K, 10-Q and IR coverage

| sec_filings | sec_10k_filings | sec_10q_filings | sec_hash_matches | ir_earnings_releases | ir_hash_matches | all_sec_hashes_match | all_ir_hashes_match | periodic_filing_inventory_complete | source_gate_pass | html_only | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 6 | 17 | 23 | 27 | 27 | True | True | True | True | True | False |

| selected_ir_releases | parsed_quarters | parsed_segments | segment_quarter_rows | segment_sales_coverage_pct | segment_ebitda_coverage_pct | product_anchor_rows | product_anchor_groups | engine_unit_quarters | scope_change_cells | known_transaction_scope_events | all_selected_hashes_match | parser_gate_pass | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | 27 | 5 | 135 | 100.0 | 100.0 | 717 | 6 | 27 | 0 | 1 | True | True | False |

The HTML-only parser covers five reported segments and preserves every explicit
Atmus or cross-release perimeter break as an unforecastable scope change.

## Company anchor coverage

| segment | anchor_group | quarters | first_period | last_period | items |
| --- | --- | --- | --- | --- | --- |
| components | COMPONENTS_PRODUCT_SALES | 27 | 2019Q4 | 2026Q2 | 13 |
| distribution | DISTRIBUTION_PRODUCT_SALES | 27 | 2019Q4 | 2026Q2 | 5 |
| engine | ENGINE_APPLICATION_SALES | 27 | 2019Q4 | 2026Q2 | 5 |
| engine | ENGINE_UNIT_SHIPMENTS | 27 | 2019Q4 | 2026Q2 | 4 |
| power_systems | POWER_SYSTEMS_PRODUCT_SALES | 27 | 2019Q4 | 2026Q2 | 4 |
| power_systems | POWER_SYSTEMS_UNIT_SHIPMENTS | 22 | 2019Q4 | 2025Q1 | 3 |

Engine unit shipments and the disclosed application/product mix of Engine,
Components, Distribution and Power Systems are retained as PIT company evidence.
No undisclosed residual is relabelled as price, volume or mix.

## Industry data authority

| registry_machinery_sensors | bls_model_sensor_rows | bls_unique_series | census_context_only_sensors | bls_archive_vintage_rows | pit_feature_rows | minimum_series_coverage_pct | cutoff_violations | historical_pit_ready | revised_census_used_in_oos_claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 21 | 9 | 4 | 2429 | 70 | 100.0 | 0 | True | False |

BLS PPI values come from archived as-released workbooks and enter the model.
Census M3 sensors remain context-only until release-vintage history is archived.

## Revenue and EBITDA-margin portability

| segment | validation_observations | performance_claim_observations | scope_change_rows | revenue_route | realized_revenue_routes | structural_anchor_coverage_pct | revenue_mae_usd | revenue_mase | revenue_level_ape_pct | revenue_champion_eligible | margin_route | margin_mae_pct_points | margin_mase | margin_champion_eligible | joint_champion | historical_pit_input_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| accelera | 6 | 6 | 0 | REDUCED_FORM_REGIME | REDUCED_FORM_REGIME | 0.0 | 32886025.193640698 | 1.973161511618442 | 28.822363811693354 | False | REDUCED_FORM_LOSS_REGIME | 149.78780546866665 | 1.5172667098545414 | False | False | 100.0 |
| components | 6 | 5 | 1 | REDUCED_FORM_INDUSTRY | REDUCED_FORM_INDUSTRY | 0.0 | 218314493.03716403 | 0.9142147949629985 | 8.157171137427515 | True | REDUCED_FORM_COST_SPREAD | 0.6483667674571318 | 0.7739146020355006 | True | True | 100.0 |
| distribution | 6 | 6 | 0 | REDUCED_FORM_COMPANY | REDUCED_FORM_COMPANY | 0.0 | 119653994.15258765 | 0.47387720456470356 | 3.7993059878063264 | True | REDUCED_FORM_MARGIN | 1.5725217775714169 | 0.7691812436543083 | True | True | 100.0 |
| engine | 6 | 6 | 0 | STRUCTURAL_UNITS_PRICE | STRUCTURAL_UNITS_PRICE | 100.0 | 149829427.39426374 | 0.8019416274447657 | 5.314023407361183 | True | STRUCTURAL_VOLUME_PRICE_COST | 2.163370898140189 | 0.7171996888516411 | True | True | 100.0 |
| power_systems | 6 | 6 | 0 | CONDITIONAL_STRUCTURAL_OR_REDUCED_FORM | REDUCED_FORM_PRODUCT_MIX_FALLBACK\|STRUCTURAL_UNITS_PRICE_MIX | 33.33333333333333 | 80595291.06229027 | 0.2798447606329523 | 4.21740484844798 | True | REDUCED_FORM_PRODUCT_MIX | 4.2082719652484135 | 1.0067683436790624 | False | False | 100.0 |

Revenue and margin champion decisions are separate. Structural labels are only
used where a non-financial company anchor exists; reduced-form results do not
create component attribution or ROIC claims.

## Prediction interval calibration

| segments_evaluated | point_champions | uncertainty_champions | insufficient_calibration_segments | point_champion_equals_uncertainty_champion_policy | pi80_target_lower_pct | pi80_target_upper_pct | uncertainty_terminal_input_allowed | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | 5 | 0 | 8 | False | 75.0 | 85.0 | False | HOLD_UNCERTAINTY_CALIBRATION |

| company | segment | target | target_coverage_pct | evaluable_intervals | maximum_calibration_observations | empirical_coverage_pct | minimum_calibration_observations | uncertainty_champion | status | point_champion | point_and_uncertainty_authority_separate | point_champion_not_uncertainty_champion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | construction | MARGIN_PCT | 80.0 | 3 | 5 | 100.0 | 10 | False | INSUFFICIENT_CALIBRATION_N | False | True | False |
| CAT | power_energy | MARGIN_PCT | 80.0 | 3 | 4 | 33.33333333333333 | 10 | False | INSUFFICIENT_CALIBRATION_N | True | True | True |
| CAT | resource | MARGIN_PCT | 80.0 | 3 | 4 | 66.66666666666666 | 10 | False | INSUFFICIENT_CALIBRATION_N | True | True | True |
| CMI | accelera | EBITDA_MARGIN_PCT | 80.0 | 3 | 5 | 100.0 | 10 | False | INSUFFICIENT_CALIBRATION_N | False | True | False |
| CMI | components | EBITDA_MARGIN_PCT | 80.0 | 2 | 4 | 100.0 | 10 | False | INSUFFICIENT_CALIBRATION_N | True | True | True |
| CMI | distribution | EBITDA_MARGIN_PCT | 80.0 | 3 | 5 | 100.0 | 10 | False | INSUFFICIENT_CALIBRATION_N | True | True | True |
| CMI | engine | EBITDA_MARGIN_PCT | 80.0 | 3 | 5 | 100.0 | 10 | False | INSUFFICIENT_CALIBRATION_N | True | True | True |
| CMI | power_systems | EBITDA_MARGIN_PCT | 80.0 | 3 | 5 | 66.66666666666666 | 10 | False | INSUFFICIENT_CALIBRATION_N | False | True | False |

Point-model champion status never grants uncertainty-model authority. PI80 uses
strictly prior errors and fails closed while calibration samples are insufficient.

## Reinvestment and ROIC evidence

| periodic_filings_parsed | annual_10k_filings | quarterly_10q_filings | raw_relevant_xbrl_facts | critical_annual_metric_minimum_coverage_pct | quarterly_note_chain_complete_rows | quarterly_note_chain_coverage_pct | reported_roic_years | incremental_roic_years | latest_reported_roic_pct | latest_through_cycle_roic_median_pct | latest_innovation_adjusted_reinvestment_rate_pct | research_evidence_ready | segment_roic_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23 | 6 | 17 | 7656 | 100.0 | 22 | 95.65217391304348 | 5 | 4 | 18.90270278271392 | 18.90270278271392 | 79.71334048903854 | True | False | False |

| metric | annual_filings | years_available | coverage_pct |
| --- | --- | --- | --- |
| accounts_payable_usd | 6 | 6 | 100.0 |
| business_acquisitions_usd | 6 | 4 | 66.66666666666666 |
| capex_usd | 6 | 6 | 100.0 |
| cash_usd | 6 | 6 | 100.0 |
| cfo_usd | 6 | 6 | 100.0 |
| debt_current_usd | 6 | 6 | 100.0 |
| debt_noncurrent_usd | 6 | 0 | 0.0 |
| depreciation_amortization_usd | 6 | 6 | 100.0 |
| equipment_on_lease_capex_usd | 6 | 0 | 0.0 |
| equity_usd | 6 | 6 | 100.0 |
| goodwill_usd | 6 | 6 | 100.0 |
| income_tax_usd | 6 | 6 | 100.0 |
| intangibles_ex_goodwill_usd | 6 | 6 | 100.0 |
| inventory_finished_goods_usd | 6 | 0 | 0.0 |
| inventory_raw_material_usd | 6 | 0 | 0.0 |
| inventory_supplies_usd | 6 | 0 | 0.0 |
| inventory_usd | 6 | 6 | 100.0 |
| inventory_work_in_process_usd | 6 | 0 | 0.0 |
| operating_income_usd | 6 | 6 | 100.0 |
| pension_opeb_liability_usd | 6 | 0 | 0.0 |
| ppe_net_usd | 6 | 6 | 100.0 |
| pretax_income_usd | 6 | 6 | 100.0 |
| research_development_usd | 6 | 6 | 100.0 |
| restructuring_cost_usd | 6 | 2 | 33.33333333333333 |
| revenue_usd | 6 | 6 | 100.0 |
| total_debt_reported_usd | 6 | 6 | 100.0 |
| trade_receivables_usd | 6 | 6 | 100.0 |
| warranty_accrual_usd | 6 | 6 | 100.0 |

Quarterly and annual note facts are preserved separately. Reported, tangible,
incremental and through-cycle ROIC diagnostics remain research evidence only.

## Target authority

| segment | revenue_route | realized_revenue_routes | structural_anchor_coverage_pct | revenue_mase | revenue_champion_eligible | margin_route | margin_mase | margin_champion_eligible | joint_champion | scope_change_rows | economic_component_claim_allowed | reinvestment_forecast_claim_allowed | roic_forecast_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| accelera | REDUCED_FORM_REGIME | REDUCED_FORM_REGIME | 0.0 | 1.973161511618442 | False | REDUCED_FORM_LOSS_REGIME | 1.5172667098545414 | False | False | 0 | False | False | False | False |
| components | REDUCED_FORM_INDUSTRY | REDUCED_FORM_INDUSTRY | 0.0 | 0.9142147949629985 | True | REDUCED_FORM_COST_SPREAD | 0.7739146020355006 | True | True | 1 | False | False | False | False |
| distribution | REDUCED_FORM_COMPANY | REDUCED_FORM_COMPANY | 0.0 | 0.47387720456470356 | True | REDUCED_FORM_MARGIN | 0.7691812436543083 | True | True | 0 | False | False | False | False |
| engine | STRUCTURAL_UNITS_PRICE | STRUCTURAL_UNITS_PRICE | 100.0 | 0.8019416274447657 | True | STRUCTURAL_VOLUME_PRICE_COST | 0.7171996888516411 | True | True | 0 | True | False | False | False |
| power_systems | CONDITIONAL_STRUCTURAL_OR_REDUCED_FORM | REDUCED_FORM_PRODUCT_MIX_FALLBACK\|STRUCTURAL_UNITS_PRICE_MIX | 33.33333333333333 | 0.2798447606329523 | True | REDUCED_FORM_PRODUCT_MIX | 1.0067683436790624 | False | False | 0 | False | False | False | False |

## Valuation authority

| cat_v1_7_reference_value_per_share_usd | reference_preserved | cmi_dcf_value_per_share_usd | cmi_reverse_dcf_result | reason | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- |
| 399.1175 | True |  | NOT_RUN_BY_DESIGN | PORTABILITY_RESEARCH_REQUIRES_SEPARATE_TERMINAL_AND_LIVE_GATES | False |
