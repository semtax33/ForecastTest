# V3.6 macro-overlay research

V3.5.3 is the frozen grouped research benchmark. Every macro variable is
tested alone by group under the same TIME and LOCO splits. Gas macro remains prohibited.
Pairwise combinations are generated only from single variables that pass every TIME gate.

## Single-variable TIME gates

| group | features | candidate_median_mase | candidate_mean_mase | baseline_no_regression_share | severe_regression_count | candidate_pi80 | candidate_direction | minimum_candidate_forecasts | candidate_gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| oil_heavy | ovx_regime_z | 0.784 | 0.8172 | 0.2 | 2 | 0.925 | 0.7 | 8 | False |
| oil_heavy | wti_curve_slope_pct |  |  | 0.0 | 0 |  |  | 0 | False |
| oil_heavy | crude_inventory_z | 0.7364 | 0.7468 | 0.4 | 2 | 0.925 | 0.725 | 8 | False |
| oil_heavy | oil_rig_z | 0.7278 | 0.9045 | 0.4 | 2 | 0.925 | 0.675 | 8 | False |
| oil_heavy | dxy_regime_z | 0.685 | 0.6757 | 0.4 | 0 | 0.925 | 0.725 | 8 | False |
| mixed | ovx_regime_z | 0.5836 | 0.5506 | 0.3333 | 0 | 0.6667 | 0.7917 | 8 | False |
| mixed | wti_curve_slope_pct |  |  | 0.0 | 0 |  |  | 2 | False |
| mixed | henry_regime_z | 0.6139 | 0.5804 | 0.3333 | 0 | 0.5556 | 0.7917 | 8 | False |
| mixed | crude_inventory_z | 0.5428 | 0.5367 | 0.6667 | 0 | 0.6667 | 0.875 | 8 | False |
| mixed | oil_gas_regime_spread | 0.5721 | 0.5969 | 0.3333 | 0 | 0.5556 | 0.8333 | 8 | False |

## Eligible pairwise combinations

_No candidates were eligible for this stage._

## Group decision

| group | selected_macro | research_model | decision | production_model |
| --- | --- | --- | --- | --- |
| oil_heavy | NONE | V3.5.3_GROUPED | RETAIN_RESEARCH_BENCHMARK | V3.4_FROZEN |
| mixed | NONE | V3.5.3_GROUPED | RETAIN_RESEARCH_BENCHMARK | V3.4_FROZEN |
| gas_heavy | PROHIBITED | V3.5.3_LEGACY | GAS_MACRO_BLOCKED | V3.4_FROZEN |

## Selected research result

| validation | evaluable_company_count | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mean_candidate_mae_log_points | mase_below_1_count | mase_below_1_share | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | legacy_no_regression_count | legacy_no_regression_share | beats_legacy_pct | median_improvement_log_points | overall_revenue_wape_pct | overall_revenue_median_ape_pct | overall_revenue_mape_pct_diagnostic | small_denominator_observations | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TIME_HOLDOUT_8Q_PRIMARY_V36_SELECTED | 13 | 13 | 99 | 0.5655 | 0.6267 | 30.8418 | 13 | 1.0 | 9 | 7 | 100.0 | 13 | 1.0 | 100.0 | 4.769 | 9.217 | 6.9164 | 141.8014 | 1 | 0.7756 | 0.7853 |
| LOCO_TIME_SAFE_8Q_COLD_START_V36_SELECTED | 13 | 13 | 99 | 0.7425 | 0.6864 | 32.2101 | 13 | 1.0 | 8 | 4 | 100.0 | 10 | 0.7692 | 76.9231 | 0.0 | 9.834 | 7.8354 | 142.8909 | 1 | 0.8083 | 0.7468 |

## Point-in-time feature coverage

| group | feature | eligible_test_rows | baseline_test_rows | coverage_share | minimum_rows_per_baseline_ticker | stale_or_missing_test_rows | policy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| oil_heavy | ovx_regime_z | 40 | 40 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| oil_heavy | wti_curve_slope_pct | 0 | 40 | 0.0 | 0.0 | 40.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| oil_heavy | crude_inventory_z | 40 | 40 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| oil_heavy | oil_rig_z | 40 | 40 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| oil_heavy | dxy_regime_z | 40 | 40 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| mixed | ovx_regime_z | 24 | 24 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| mixed | wti_curve_slope_pct | 13 | 24 | 0.5417 | 2.0 | 11.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| mixed | henry_regime_z | 24 | 24 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| mixed | crude_inventory_z | 24 | 24 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| mixed | oil_gas_regime_spread | 24 | 24 | 1.0 | 8.0 | 0.0 | POINT_IN_TIME_FRESHNESS_REQUIRED |
| gas_heavy | ALL_MACRO_FEATURES | 0 | 32 | 0.0 |  |  | PROHIBITED_V3_5_3_GAS_GATE_FAILED |

V3.4 remains the frozen production champion. No live-model change is allowed at 0/20 matches.