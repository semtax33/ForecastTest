# V3.5.3 gas-basis research report

This isolated experiment replaces loose IR gas-price parsing with strict absolute-price labels,
normalizes $/Mcf to $/BOE, and forecasts a point-in-time additive company/regional gas basis.
The V3.5.3 grouped branch continues to use legacy unless this experiment passes every gate.

## Strict price coverage

| ticker | strict_price_quarters | first_quarter | last_quarter | hedge_adjusted_quarters |
| --- | --- | --- | --- | --- |
| AR | 5 | 2015Q4 | 2018Q4 | 0 |
| CNX | 24 | 2020Q3 | 2026Q2 | 0 |
| EQT | 43 | 2015Q4 | 2026Q2 | 0 |
| RRC | 8 | 2018Q4 | 2025Q4 | 0 |

## TIME and LOCO results

| validation | evaluable_company_count | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mean_candidate_mae_log_points | mase_below_1_count | mase_below_1_share | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | legacy_no_regression_count | legacy_no_regression_share | beats_legacy_pct | median_improvement_log_points | overall_revenue_wape_pct | overall_revenue_median_ape_pct | overall_revenue_mape_pct_diagnostic | small_denominator_observations | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAS_TIME_HOLDOUT_8Q_PRIMARY | 4 | 4 | 32 | 2.1815 | 2.1501 | 72.7431 | 0 | 0.0 | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 | -34.4405 | 47.6985 | 39.5609 | 55.9937 | 0 | 0.4062 | 0.25 |
| GAS_LOCO_TIME_SAFE_8Q_COLD_START | 4 | 4 | 32 | 2.1815 | 2.1501 | 72.7431 | 0 | 0.0 | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 | -30.4997 | 47.6985 | 39.5609 | 55.9937 | 0 | 0.4062 | 0.25 |

## Gas-price variant attribution

| validation | evaluable_company_count | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mean_candidate_mae_log_points | mase_below_1_count | mase_below_1_share | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | legacy_no_regression_count | legacy_no_regression_share | beats_legacy_pct | median_improvement_log_points | overall_revenue_wape_pct | overall_revenue_median_ape_pct | overall_revenue_mape_pct_diagnostic | small_denominator_observations | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V352_LOOSE_PARSER_BENCHMARK_RATIO_BASELINE | 4 | 4 | 32 | 0.8986 | 0.9099 | 44.5471 | 3 | 0.75 | 1 | 0 | 75.0 | 0 | 0.0 | 0.0 | -8.9823 | 29.523 | 20.4715 | 51.9927 | 0 | 0.625 | 0.5938 |
| STRICT_PARSER_BENCHMARK_RATIO_DIAGNOSTIC_ONLY | 4 | 4 | 32 | 0.85 | 0.8384 | 42.3571 | 4 | 1.0 | 1 | 0 | 100.0 | 0 | 0.0 | 0.0 | -4.6032 | 30.8741 | 18.6244 | 80.6901 | 0 | 0.7188 | 0.6875 |
| STRICT_REALIZED_ADDITIVE_BASIS_PROMOTION_CANDIDATE | 4 | 4 | 32 | 2.1815 | 2.1501 | 72.7431 | 0 | 0.0 | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 | -34.4405 | 47.6985 | 39.5609 | 55.9937 | 0 | 0.4062 | 0.25 |

The strict-parser ratio variant is diagnostic only because its old component equation
does not normalize $/Mcf into the BOE mix. It cannot be selected even if it looks better.

## Ticker comparison versus V3.5.2 clean component

| ticker | mase_v352_clean | candidate_mae_log_points_v352_clean | improvement_log_points_v352_clean | mase_gas_basis_research | candidate_mae_log_points_gas_basis_research | improvement_log_points_gas_basis_research | candidate_mae_change | mase_strict_parser_ratio_diagnostic | candidate_mae_log_points_strict_parser_ratio_diagnostic | improvement_log_points_strict_parser_ratio_diagnostic |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AR | 1.1236 | 16.1922 | -8.0422 | 2.5201 | 36.3164 | -28.1664 | 20.1242 | 0.8788 | 12.6638 | -4.5139 |
| CNX | 0.975 | 119.6865 | -9.9225 | 1.1127 | 136.5944 | -26.8303 | 16.9078 | 0.9324 | 114.4565 | -4.6924 |
| EQT | 0.8223 | 31.2792 | -10.2999 | 1.8429 | 70.1013 | -49.122 | 38.8221 | 0.8213 | 31.2398 | -10.2605 |
| RRC | 0.7187 | 11.0306 | -3.7849 | 3.1249 | 47.9601 | -40.7145 | 36.9296 | 0.7211 | 11.0681 | -3.8224 |

## Gas research gate

| condition | passed | detail | gas_research_gate | active_group_model | gas_macro_research_unlocked | production_champion_changed |
| --- | --- | --- | --- | --- | --- | --- |
| strict_realized_price_ticker_coverage | True | 4/4 gas-heavy tickers | False | LEGACY | False | False |
| minimum_8_forecasts_per_gas_ticker | True | 4/4 gas-heavy tickers | False | LEGACY | False | False |
| time_median_mase_below_0_80 | False | 2.1815 | False | LEGACY | False | False |
| time_mean_mase_below_0_90 | False | 2.1501 | False | LEGACY | False | False |
| time_mase_below_1_share_at_least_70pct | False | 0/4 evaluable = 0.0% | False | LEGACY | False | False |
| time_legacy_no_regression_at_least_70pct | False | 0/4 evaluable = 0.0% | False | LEGACY | False | False |
| time_median_improvement_positive | False | -34.4405 | False | LEGACY | False | False |
| time_no_severe_ticker_regression | False | 4/4 below -2.0 | False | LEGACY | False | False |

## Decision

- Gas-heavy active grouped model: **LEGACY**
- Gas macro research: **BLOCKED**
- No macro overlay was applied to these results.
- V3.4 production champion remains frozen.