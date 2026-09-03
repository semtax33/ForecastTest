# Industrials V1.5 — Historical PIT vintage and segment-route validation

## Freeze disposition

| historical_pit_archive_ready | historical_pit_features_ready | historical_pit_validation_ready | segments_with_margin_mase_below_one | minimum_segments_required | maximum_segment_margin_mase | worst_segment_margin_mase_threshold | no_worst_segment_margin_regression | all_segments_revenue_no_material_regression | component_cancellation_gate_pass | reinvestment_pit_oos_gate_pass | backlog_oos_gate_pass | terminal_unlocked | production_live_forward_gate_pass | freeze_ready | failed_gates | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | True | True | 2 | 2 | 1.3319582019471508 | 1.5 | True | True | False | False | False | False | False | False | COMPONENT_ERROR_CANCELLATION\|REINVESTMENT_PIT_OOS\|BACKLOG_OOS\|TERMINAL_UNLOCK\|PRODUCTION_LIVE_FORWARD | HOLD_RESEARCH_UNFROZEN |

V1.5 remains `HOLD_RESEARCH_UNFROZEN`.  Historical point-in-time validation is
now real rather than a schema placeholder, but the strengthened full-chain gate
still blocks DCF and Reverse DCF updates.  The V1.3-lite reference value of
$399.1175 per share is preserved.

## Historical PIT acquisition and cutoff

| archive_report_files | archive_report_hash_mismatches | release_schedule_files | release_schedule_hash_mismatches | required_series | parsed_series | missing_series | vintage_rows | release_date_coverage_pct | available_at_coverage_pct | source_hash_coverage_pct | pit_eligible_rows | historical_pit_ready | pdf_parsing_used | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 54 | 0 | 5 | 0 | 13 | 13 |  | 3509 | 100.0 | 100.0 | 100.0 | 3509 | True | False | HISTORICAL_PIT_ARCHIVE_READY |

| forecast_periods | segments | feature_rows | minimum_series_coverage_pct | maximum_feature_lag_quarters | cutoff_violations | historical_pit_ready |
| --- | --- | --- | --- | --- | --- | --- |
| 14 | 3 | 42 | 100.0 | 2 | 0 | True |

All BLS inputs are archived monthly XLSX releases with verified SHA-256 hashes.
CAT dealer retail inputs come from the Arcana SEC IR HTML archive.  PDF parsing
was not used.  Each target quarter uses the immediately preceding CAT earnings
release as forecast origin; the target release is settlement only.

## Segment champions and margin validation

| segment | validation_observations | first_validation_period | last_validation_period | champion_volume_route | champion_route_selection_share_pct | margin_mae_pct_points | prior_margin_mae_pct_points | margin_mase_vs_prior | revenue_level_mae_usd | naive_prior_year_revenue_mae_usd | revenue_mae_regression_vs_naive_pct | revenue_no_material_regression | mean_revenue_level_ape_pct | gross_component_mae_pct | mean_component_cancellation_ratio | component_cancellation_lock | historical_pit_input_pct | actual_after_forecast_pct | performance_claim_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | 2025Q1 | 2026Q2 | LAGGED_ACTUAL_VOLUME | 50.0 | 2.7849257217154446 | 4.385057433358047 | 0.6350944688956486 | 737381481.6794592 | 1200666666.6666667 | -38.585662269895124 | True | 11.301625413235369 | 28.251646140236364 | 0.8425749231668075 | True | 100.0 | 100.0 | True |
| power_energy | 6 | 2025Q1 | 2026Q2 | LAGGED_ACTUAL_VOLUME | 66.66666666666666 | 1.4220873292383633 | 1.0676666333518992 | 1.3319582019471508 | 696168062.1530129 | 739666666.6666666 | -5.880838825640433 | True | 8.605775326324151 | 17.3004855125272 | 0.7853622843182219 | False | 100.0 | 100.0 | True |
| resource | 6 | 2025Q1 | 2026Q2 | DEALER_RETAIL_PLUS_LAG_VOLUME | 50.0 | 4.7052650967203675 | 4.964438901213724 | 0.9477939381165527 | 501732219.92200655 | 562500000.0 | -10.803160902754394 | True | 12.717313990123102 | 31.459462813478495 | 0.8356177679838321 | True | 100.0 | 100.0 | True |

Routes are selected separately inside each segment and forecast origin using
training-only inner validation.  A route cannot defeat the lagged-volume anchor
unless its inner MAE is lower.

## Component-error and cancellation audit

| segment | component | validation_observations | v1_5_historical_pit_mae_pct | v1_4_calibration_mae_pct | mae_change_vs_v1_4_pct | actual_mean_pct | predicted_mean_pct | historical_pit_input |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | VOLUME | 6 | 9.575764719303606 | 10.967843719132045 | -12.692367209792831 | 11.080715107105917 | 4.599118210046335 | True |
| construction | PRICE | 6 | 4.010755589566336 | 5.296433238874728 | -24.27440489331166 | -0.9439757281252336 | 0.05081809430783705 | True |
| construction | COST | 6 | 14.665125831366419 | 10.048817239155344 | 45.93882526018653 | 14.474794712815187 | 2.537594490175826 | True |
| power_energy | VOLUME | 6 | 5.927980833827384 | 4.751387760553825 | 24.76314568643867 | 9.492493974533048 | 6.092037022761229 | True |
| power_energy | PRICE | 6 | 0.824366520348332 | 0.3658862248726169 | 125.30679328945351 | 2.183596222358705 | 2.840209304166501 | True |
| power_energy | COST | 6 | 10.548138158351483 | 7.060835190858287 | 49.389383454357215 | 8.339776756826057 | 7.403850419643966 | True |
| resource | VOLUME | 6 | 10.159335253141037 | 5.846036180326784 | 73.78160072511126 | 5.447359102702381 | -0.3516712985840214 | True |
| resource | PRICE | 6 | 1.8975072439324965 | 1.717361729882537 | 10.489666266307275 | -1.3138066673066802 | -0.3979633671420955 | True |
| resource | COST | 6 | 19.402620316404963 | 6.755375094947136 | 187.21751262809482 | 21.38135524138764 | 3.5422188493429787 | True |

The cancellation lock fails closed when a margin MASE below one coexists with
large gross component errors and a high offset ratio.  Therefore a seemingly
good margin cannot be promoted if price, volume, and cost are merely cancelling.

## Reinvestment full-chain validation

| validation_observations | minimum_observations_required | minimum_observations_met | full_chain_model_mae_usd | naive_prior_delta_mae_usd | full_chain_reinvestment_mase | maximum_reinvestment_mase | upstream_forecast_errors_propagated | historical_pit_vintages_available | perimeter_exact | full_forecast_oos_validated | reinvestment_bridge_validated | failed_gates | status | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | False | 452924129.1834245 | 1071000000.0 | 0.42289834657649344 | 1.0 | True | True | False | False | False | INSUFFICIENT_PIT_OOS_YEARS | FAIL_CLOSED_PIT_OOS_GATE | False | False |

Reinvestment parameters were not retuned.  Only complete historical-PIT fiscal
years count; fewer than three observations cannot unlock the bridge.

## Valuation authority

| valuation_update_allowed | reason | v1_3_lite_reference_preserved | reference_value_per_share_usd | new_dcf_value_per_share | new_reverse_dcf_result | roic_reestimate_allowed | terminal_replacement_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| False | V1_5_FREEZE_GATE_FAILED_AND_TERMINAL_ECONOMICS_REMAIN_LOCKED | True | 399.1175 |  | NOT_RUN_BY_DESIGN | False | False | False |

Backlog remains 2/3 OOS, terminal economics remain locked, and production remains
0/20.  No DCF or Reverse DCF was run by design.
