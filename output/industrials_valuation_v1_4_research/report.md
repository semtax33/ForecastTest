# Industrials V1.4 — CAT segment cost-driver and margin validation

## Research gate

| parent_v1_2_architecture_verified | v1_3_lite_original_code_changed | dedicated_segment_sensor_roles_complete | ir_pq_bridge_gate_pass | pit_canonical_schema_ready | historical_pit_vintages_available | explicit_calibration_only | margin_freeze_gate_pass | reinvestment_full_chain_observations | reinvestment_bridge_validated | roic_model_changed | valuation_update_allowed | backlog_model_changed | backlog_oos_observations | pdf_parsing_deferred | research_complete | terminal_input_allowed | production_promoted | live_matched_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | False | True | True | True | False | True | False | 1 | False | False | False | False | 2 | True | True | False | False | 0/20 |

The CAT IR source is the Arcana SEC IR HTML archive. PDF parsing remains
explicitly deferred. BLS data are stored as a reproducible bronze snapshot, but
historical release vintages do not yet exist; all temporal statistics are
calibration diagnostics and cannot support an investment-performance claim.

## IR price/volume identity

| quarter_segment_rows | quarters | segments | bridge_identity_mismatches | reported_change_mismatches | pq_bridge_gate_pass | production_eligible |
| --- | --- | --- | --- | --- | --- | --- |
| 69 | 23 | 3 | 0 | 0 | True | False |

## Dedicated segment sensors

| segment | role | series_count | first_period | latest_period | full_quarter_observations |
| --- | --- | --- | --- | --- | --- |
| construction | component | 1 | 2021Q1 | 2026Q2 | 22 |
| construction | freight | 1 | 2021Q1 | 2026Q2 | 22 |
| construction | labor | 1 | 2021Q1 | 2026Q2 | 22 |
| construction | material | 2 | 2021Q1 | 2026Q2 | 22 |
| construction | output_price | 1 | 2021Q1 | 2026Q2 | 22 |
| power_energy | component | 1 | 2021Q1 | 2026Q2 | 22 |
| power_energy | freight | 2 | 2021Q1 | 2026Q2 | 22 |
| power_energy | labor | 1 | 2021Q1 | 2026Q2 | 22 |
| power_energy | material | 2 | 2021Q1 | 2026Q2 | 22 |
| power_energy | output_price | 3 | 2021Q1 | 2026Q2 | 22 |
| resource | component | 1 | 2021Q1 | 2026Q2 | 22 |
| resource | freight | 2 | 2021Q1 | 2026Q2 | 22 |
| resource | labor | 1 | 2021Q1 | 2026Q2 | 22 |
| resource | material | 2 | 2021Q1 | 2026Q2 | 22 |
| resource | output_price | 1 | 2021Q1 | 2026Q2 | 22 |

## Margin walk-forward

| segment | validation_observations | margin_mae_pct_points | prior_margin_mae_pct_points | margin_mase_vs_prior | common_v13_observations | v14_common_margin_mae_pct_points | v13_common_margin_mae_pct_points | margin_mae_improvement_vs_v13_pct | revenue_mae_pct | unit_capture_revenue_mae_pct | revenue_mae_improvement_vs_unit_pct | mean_revenue_level_ape_pct | historical_pit_vintages_available | margin_model_validated | performance_claim_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | 4.926936479667839 | 4.385057433358047 | 1.1235739906591884 | 6 | 4.926936479667839 | 6.676200375957637 | 26.201488837711562 | 13.274006383877827 | 11.113994254061739 | -19.43506610170045 | 11.333486877743674 | False | False | False |
| power_energy | 6 | 1.2173549513979214 | 0.9303731048681243 | 1.308458880666456 | 6 | 1.2173549513979214 | 3.5353742400705293 | 65.56644731977129 | 6.146694048483329 | 9.921881547004153 | 38.049108736444424 | 5.3643953025351605 | False | False | False |
| resource | 6 | 2.5822999491474143 | 3.984756403604201 | 0.6480446199450816 | 6 | 2.5822999491474143 | 6.994947448207387 | 63.08335454601325 | 5.683091051666153 | 8.237744525587678 | 31.01156470665466 | 5.353517674950712 | False | False | False |

## Component diagnostics

| segment | component | validation_observations | mae_pct | actual_mean_pct | predicted_mean_pct | historical_pit_vintages_available |
| --- | --- | --- | --- | --- | --- | --- |
| construction | VOLUME | 6 | 10.967843719132043 | 11.080715107105917 | 2.9046698480896804 | False |
| construction | PRICE | 6 | 5.2964332388747275 | -0.9439757281252336 | 1.38150223341903 | False |
| construction | COST | 6 | 10.048817239155344 | 14.474794712815187 | 6.847507748691389 | False |
| power_energy | VOLUME | 6 | 4.751387760553825 | 9.492493974533048 | 7.6762973255105225 | False |
| power_energy | PRICE | 6 | 0.36588622487261696 | 2.183596222358705 | 2.3705277369246023 | False |
| power_energy | COST | 6 | 7.060835190858287 | 13.648718258539027 | 11.15831544873062 | False |
| resource | VOLUME | 6 | 5.846036180326784 | 5.447359102702381 | 1.836190810798029 | False |
| resource | PRICE | 6 | 1.717361729882537 | -1.3138066673066802 | -0.04989360011386736 | False |
| resource | COST | 6 | 6.755375094947136 | 8.934742679828352 | 6.657307693835713 | False |

## V1.3-lite freeze readiness

| segments_with_margin_mase_below_one | minimum_segments_required | maximum_segment_margin_mase | catastrophic_margin_mase_threshold | no_catastrophic_segment_regression | median_revenue_capture_improvement_vs_unit_pct | minimum_capture_improvement_pct | capture_improved_vs_unit | historical_pit_resolved | explicit_calibration_only_disposition | v1_3_lite_freeze_ready | failed_gates | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 1.308458880666456 | 2.0 | True | 31.01156470665466 | 0.0 | True | False | True | False | MARGIN_MASE_SEGMENT_COUNT | HOLD_RESEARCH_UNFROZEN |

## PIT vintage infrastructure

| required_columns | schema_columns_complete | observation_rows | series_count | release_date_coverage_pct | available_at_coverage_pct | source_hash_coverage_pct | pit_eligible_rows | historical_pit_ready | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| source\|dataset\|series_id\|observation_period\|vintage_value\|release_date\|available_at\|revision_number\|source_hash\|vintage_status\|pit_eligible | True | 946 | 12 | 0.0 | 100.0 | 100.0 | 0 | False | SCHEMA_READY_VINTAGE_HISTORY_DEFERRED |

## Reinvestment full-chain validation

| validation_observations | minimum_observations_required | minimum_observations_met | full_chain_model_mae_usd | naive_prior_delta_mae_usd | full_chain_reinvestment_mase | upstream_forecast_errors_propagated | historical_pit_vintages_available | perimeter_exact | full_forecast_oos_validated | reinvestment_bridge_validated | status | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | False | 273965536.4155452 | 1071000000.0 | 0.2558034887166622 | True | False | False | False | False | FAIL_CLOSED_INSUFFICIENT_NON_PIT_FULL_CHAIN_OBSERVATIONS | False | False |

## Valuation authority

| valuation_update_allowed | reason | v1_3_lite_reference_preserved | new_dcf_value_per_share | new_reverse_dcf_result | roic_reestimate_allowed | terminal_replacement_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- |
| False | MARGIN_BRANCH_REMAINS_CALIBRATION_ONLY_AND_TERMINAL_INPUT_IS_LOCKED | True |  | NOT_RUN_BY_DESIGN | False | False | False |

ROIC and terminal economics were intentionally not re-estimated. The V1.3-lite
DCF reference remains unchanged until margin, PIT, and reinvestment gates pass.
Backlog remains 2/3 OOS and production remains locked at 0/20.
