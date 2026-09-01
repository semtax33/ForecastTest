# V3.5.3 grouped-component report

The V3.5.2 clean component is evaluated independently by fixed E&P group.
Passing groups use the clean component; failing groups retain the legacy structural model.
No threshold was relaxed and no new feature was added to this experiment.

## Group promotion

| group | time_evaluable_tickers | time_median_mase | time_mean_mase | time_legacy_no_regression_count | time_severe_regression_count | group_component_gate | active_model | macro_research_unlocked |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| oil_heavy | 6 | 0.7304 | 0.6755 | 6 | 0 | True | CLEAN_COMPONENT | True |
| gas_heavy | 4 | 0.8986 | 0.9099 | 0 | 4 | False | LEGACY | False |
| mixed | 3 | 0.5436 | 0.5371 | 3 | 0 | True | CLEAN_COMPONENT | True |

## Active grouped-model results

| validation | evaluable_company_count | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mean_candidate_mae_log_points | mase_below_1_count | mase_below_1_share | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | legacy_no_regression_count | legacy_no_regression_share | beats_legacy_pct | median_improvement_log_points | overall_revenue_wape_pct | overall_revenue_median_ape_pct | overall_revenue_mape_pct_diagnostic | small_denominator_observations | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TIME_HOLDOUT_8Q_PRIMARY_GROUPED | 13 | 13 | 99 | 0.5655 | 0.6267 | 30.8418 | 13 | 1.0 | 9 | 7 | 100.0 | 13 | 1.0 | 100.0 | 4.769 | 9.217 | 6.9164 | 141.8014 | 1 | 0.7756 | 0.7853 |
| LOCO_TIME_SAFE_8Q_COLD_START_GROUPED | 13 | 13 | 99 | 0.7425 | 0.6864 | 32.2101 | 13 | 1.0 | 8 | 4 | 100.0 | 10 | 0.7692 | 76.9231 | 0.0 | 9.834 | 7.8354 | 142.8909 | 1 | 0.8083 | 0.7468 |

## V3.5.2 clean versus V3.5.3 selected

| metric | v3_5_2_clean | v3_5_3_grouped | change |
| --- | --- | --- | --- |
| median_ticker_mase | 0.7187 | 0.5655 | -0.1532 |
| mean_ticker_mase | 0.7157 | 0.6267 | -0.0889 |
| mase_below_1_share | 0.9231 | 1.0 | 0.0769 |
| legacy_no_regression_share | 0.6923 | 1.0 | 0.3077 |
| median_improvement_log_points | 4.769 | 4.769 | 0.0 |
| pi_80_coverage | 0.8397 | 0.7756 | -0.0641 |
| directional_hit_rate | 0.7083 | 0.7853 | 0.0769 |
| revenue_wape_pct | 10.184 | 9.217 | -0.967 |
| revenue_median_ape_pct | 8.814 | 6.9164 | -1.8975 |

## Grouped success gate

| condition | passed | detail | grouped_component_gate | production_eligible | production_champion_changed |
| --- | --- | --- | --- | --- | --- |
| time_median_mase_at_most_0_72 | True | 0.5655 | True | False | False |
| time_mean_mase_at_most_0_75 | True | 0.6267 | True | False | False |
| time_mase_below_1_share_at_least_85pct | True | 13/13 evaluable = 100.0% | True | False | False |
| time_legacy_no_regression_at_least_85pct | True | 13/13 evaluable = 100.0% | True | False | False |
| time_severe_regression_at_most_1 | True | 0/13 below -2.0 | True | False | False |
| time_pi_80_coverage_between_75_85pct | True | 77.6% | True | False | False |
| time_directional_hit_at_least_65pct | True | 78.5% | True | False | False |
| live_20_match_model_change_lock | False | 0/20 matched | True | False | False |
| v3_4_production_champion_frozen | True | Research selection does not mutate V3.4 | True | False | False |

## Decision

- Macro research is unlocked only for groups whose component gate passes.
- Gas-heavy retains legacy until a separate gas-basis model passes its own gate.
- The V3.4 production champion remains frozen and byte-verified.