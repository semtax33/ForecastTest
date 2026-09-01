# Phase 2.5 target-aligned research

P2.1 Refining KPI and the Services proxy are fixed input benchmarks.
Macro variables are tested one at a time; combinations are forbidden unless
every constituent first passes the full TIME gate. Production remains frozen
at 0/20 live observations.

## Refining and Services macro decisions

| subindustry   | benchmark                     | selected_macro   | research_route_model          | decision                | production_model     |
|:--------------|:------------------------------|:-----------------|:------------------------------|:------------------------|:---------------------|
| refining      | P2.1_REFINING_COMPANY_KPI     | NONE             | P2.1_REFINING_COMPANY_KPI     | RETAIN_FROZEN_BENCHMARK | LAG_REVENUE_BASELINE |
| services      | STRUCTURAL_PROXY_RECALIBRATED | NONE             | STRUCTURAL_PROXY_RECALIBRATED | RETAIN_FROZEN_BENCHMARK | LAG_REVENUE_BASELINE |

## Single/passing-combination TIME gates

| subindustry   | features               |   baseline_median_mase |   candidate_median_mase |   baseline_no_regression_share |   candidate_pi80 |   candidate_direction | candidate_gate   |
|:--------------|:-----------------------|-----------------------:|------------------------:|-------------------------------:|-----------------:|----------------------:|:-----------------|
| refining      | crack_spread_log_yoy   |                 0.531  |                  0.5464 |                         0      |           1      |                0.8333 | False            |
| refining      | gasoline_inventory_z   |                 0.531  |                  0.503  |                         0.6667 |           1      |                0.875  | False            |
| refining      | distillate_inventory_z |                 0.531  |                  0.5436 |                         0      |           1      |                0.8333 | False            |
| refining      | refinery_utilization_z |                 0.531  |                  0.5389 |                         0      |           1      |                0.8333 | False            |
| refining      | brent_wti_spread_pct   |                 0.531  |                  0.5836 |                         0      |           1      |                0.8333 | False            |
| refining      | product_demand_log_yoy |                 0.531  |                  0.5779 |                         0      |           1      |                0.8333 | False            |
| services      | ovx_regime_z           |                 0.6949 |                  1.3239 |                         0      |           0.9583 |                0.6667 | False            |
| services      | wti_regime_z           |                 0.6949 |                  1.2976 |                         0      |           1      |                0.6667 | False            |
| services      | henry_regime_z         |                 0.6949 |                  0.7944 |                         0      |           1      |                0.75   | False            |
| services      | oil_rig_z              |                 0.6949 |                  0.6872 |                         0.3333 |           1      |                0.75   | False            |

## Services orders lag diagnostic

| validation            | subindustry   | features           |   baseline_median_mase |   candidate_median_mase |   baseline_mean_mase |   candidate_mean_mase |   baseline_no_regression_share |   severe_regression_count |   baseline_pi80 |   candidate_pi80 |   baseline_direction |   candidate_direction |   macro_applied_share | minimum_8_forecasts_per_baseline_ticker   | median_mase_improves   | mean_mase_no_worse   | baseline_no_regression_share_at_least_80pct   | severe_regression_count_zero   | pi80_between_75_85pct   | direction_no_worse   | feature_available_and_applied_all_rows   | parser_quality_gate   | candidate_gate   |   orders_report_lag_quarters | industry_ticker_coverage   | industry_coverage_gate   |   loco_overlay_applied_share | loco_cold_start_gate   | decision                              |
|:----------------------|:--------------|:-------------------|-----------------------:|------------------------:|---------------------:|----------------------:|-------------------------------:|--------------------------:|----------------:|-----------------:|---------------------:|----------------------:|----------------------:|:------------------------------------------|:-----------------------|:---------------------|:----------------------------------------------|:-------------------------------|:------------------------|:---------------------|:-----------------------------------------|:----------------------|:-----------------|-----------------------------:|:---------------------------|:-------------------------|-----------------------------:|:-----------------------|:--------------------------------------|
| TIME_BKR_ORDERS_LAG_1 | services      | orders_lag_feature |                 0.9336 |                  0.8353 |               0.9336 |                0.8353 |                              1 |                         0 |               1 |              nan |                 0.75 |                 0.625 |                     1 | True                                      | True                   | True                 | True                                          | True                           | False                   | False                | True                                     | True                  | False            |                            1 | 1/3                        | False                    |                            0 | False                  | DIAGNOSTIC_ONLY_RETAIN_SERVICES_PROXY |
| TIME_BKR_ORDERS_LAG_2 | services      | orders_lag_feature |                 0.9336 |                  0.9854 |               0.9336 |                0.9854 |                              0 |                         0 |               1 |              nan |                 0.75 |                 0.75  |                     1 | True                                      | False                  | False                | False                                         | True                           | False                   | True                 | True                                     | True                  | False            |                            2 | 1/3                        | False                    |                            0 | False                  | DIAGNOSTIC_ONLY_RETAIN_SERVICES_PROXY |

Orders are available only for BKR. TIME lag results are diagnostic and LOCO
must fail cold-start; neither lag can replace the three-company Services proxy.

## Integrated forward-signal unlock

| ticker   |   text_candidate_quarters |   numeric_candidate_quarters |   manual_gold_verified_quarters |   minimum_required_quarters | forward_candidate_unlocked   | status                                     |
|:---------|--------------------------:|-----------------------------:|--------------------------------:|----------------------------:|:-----------------------------|:-------------------------------------------|
| XOM      |                        26 |                           17 |                               0 |                           8 | False                        | LOCKED_UNTIL_MANUAL_GOLD_AND_8Q_PER_TICKER |
| CVX      |                        30 |                           29 |                               0 |                           8 | False                        | LOCKED_UNTIL_MANUAL_GOLD_AND_8Q_PER_TICKER |

Historical Integrated KPI expansion remains disabled. Text candidates do not
enter a model until numeric meaning and target quarter pass manual gold review.

## Midstream Adjusted EBITDA target

|   gold_rows |   numeric_accuracy |   unit_accuracy |   period_accuracy |   semantic_accuracy |   all_dimension_accuracy | parser_quality_gate   |
|------------:|-------------------:|----------------:|------------------:|--------------------:|-------------------------:|:----------------------|
|          20 |                  1 |               1 |                 1 |                   1 |                        1 | True                  |

| validation                  |   evaluable_company_count |   company_count |   quarter_forecasts |   median_ticker_mase |   mean_ticker_mase |   mean_candidate_mae_log_points |   mase_below_1_count |   mase_below_1_share |   mase_below_0_8_count |   mase_below_0_6_count |   beats_naive_pct |   legacy_no_regression_count |   legacy_no_regression_share |   beats_legacy_pct |   median_improvement_log_points |   overall_revenue_wape_pct |   overall_revenue_median_ape_pct |   overall_revenue_mape_pct_diagnostic |   small_denominator_observations |   mean_pi_80_coverage |   mean_directional_hit_rate |
|:----------------------------|--------------------------:|----------------:|--------------------:|---------------------:|-------------------:|--------------------------------:|---------------------:|---------------------:|-----------------------:|-----------------------:|------------------:|-----------------------------:|-----------------------------:|-------------------:|--------------------------------:|---------------------------:|---------------------------------:|--------------------------------------:|---------------------------------:|----------------------:|----------------------------:|
| TIME_HOLDOUT_8Q_MIDSTREAM   |                         4 |               4 |                  28 |               0.5728 |             0.6439 |                          3.7522 |                    3 |                 0.75 |                      3 |                      2 |                75 |                            2 |                          0.5 |                 50 |                          0.0674 |                     4.2778 |                           3.171  |                                3.7812 |                                0 |                0.8929 |                      0.8929 |
| LOCO_TIME_SAFE_8Q_MIDSTREAM |                         4 |               4 |                  28 |               0.509  |             0.6156 |                          3.5075 |                    3 |                 0.75 |                      3 |                      2 |                75 |                            2 |                          0.5 |                 50 |                          0.47   |                     3.9145 |                           2.9244 |                                3.5286 |                                0 |                0.8214 |                      0.8929 |

|   phase | subindustry   |   registered_tickers |   evaluable_tickers |   mase_below_1_count |   baseline_no_regression_count |   severe_regression_count | minimum_8_forecasts_per_ticker   | median_time_mase_below_0_80   | mean_time_mase_below_0_90   | mase_below_1_share_at_least_70pct   | baseline_no_regression_at_least_80pct   | severe_regression_count_zero   | pi80_between_75_85pct   | directional_hit_at_least_65pct   | research_gate   | production_eligible   |   live_matched_observations | adjusted_ebitda_parser_quality_gate   | target_research_gate   |
|--------:|:--------------|---------------------:|--------------------:|---------------------:|-------------------------------:|--------------------------:|:---------------------------------|:------------------------------|:----------------------------|:------------------------------------|:----------------------------------------|:-------------------------------|:------------------------|:---------------------------------|:----------------|:----------------------|----------------------------:|:--------------------------------------|:-----------------------|
|       3 | midstream     |                    4 |                   4 |                    3 |                              2 |                         0 | False                            | True                          | True                        | True                                | False                                   | True                           | False                   | True                             | False           | False                 |                           0 | True                                  | False                  |

## Phase 5 static router scorecard

| forecast_target          | subindustry   | research_route_model           | validation                   |   tickers |   forecasts |   median_ticker_mase |   mean_ticker_mase |   aggregate_wape_pct |   median_ape_pct |
|:-------------------------|:--------------|:-------------------------------|:-----------------------------|----------:|------------:|---------------------:|-------------------:|---------------------:|-----------------:|
| ADJUSTED_EBITDA_NON_GAAP | midstream     | LAG_ADJUSTED_EBITDA_BASELINE   | LOCO_TIME_SAFE_PHASE5_ROUTER |         4 |          32 |               0.5857 |             0.5633 |               4.7542 |           4.6302 |
| ADJUSTED_EBITDA_NON_GAAP | midstream     | LAG_ADJUSTED_EBITDA_BASELINE   | TIME_HOLDOUT_PHASE5_ROUTER   |         4 |          32 |               0.5857 |             0.5633 |               4.7542 |           4.6302 |
| GAAP_REVENUE             | ep_gas_heavy  | V3.5.3_GROUPED_LEGACY          | LOCO_TIME_SAFE_PHASE5_ROUTER |         4 |          32 |               0.8028 |             0.8148 |              26.8494 |          15.6593 |
| GAAP_REVENUE             | ep_gas_heavy  | V3.5.3_GROUPED_LEGACY          | TIME_HOLDOUT_PHASE5_ROUTER   |         4 |          32 |               0.5585 |             0.6208 |              22.1354 |           9.6613 |
| GAAP_REVENUE             | ep_mixed      | V3.5.3_GROUPED_CLEAN_COMPONENT | LOCO_TIME_SAFE_PHASE5_ROUTER |         3 |          24 |               0.5436 |             0.5371 |               6.2015 |           5.0187 |
| GAAP_REVENUE             | ep_mixed      | V3.5.3_GROUPED_CLEAN_COMPONENT | TIME_HOLDOUT_PHASE5_ROUTER   |         3 |          24 |               0.5436 |             0.5371 |               6.2015 |           5.0187 |
| GAAP_REVENUE             | ep_oil_heavy  | V3.5.3_GROUPED_CLEAN_COMPONENT | LOCO_TIME_SAFE_PHASE5_ROUTER |         6 |          43 |               0.7304 |             0.6755 |               8.8367 |           6.5016 |
| GAAP_REVENUE             | ep_oil_heavy  | V3.5.3_GROUPED_CLEAN_COMPONENT | TIME_HOLDOUT_PHASE5_ROUTER   |         6 |          43 |               0.7304 |             0.6755 |               8.8367 |           6.5016 |
| GAAP_REVENUE             | integrated    | STRUCTURAL_PROXY_RECALIBRATED  | LOCO_TIME_SAFE_PHASE5_ROUTER |         2 |          16 |               1.0744 |             1.0744 |               5.4475 |           5.541  |
| GAAP_REVENUE             | integrated    | STRUCTURAL_PROXY_RECALIBRATED  | TIME_HOLDOUT_PHASE5_ROUTER   |         2 |          16 |               1.0506 |             1.0506 |               5.3825 |           5.3002 |
| GAAP_REVENUE             | midstream     | STRUCTURAL_PROXY_RECALIBRATED  | LOCO_TIME_SAFE_PHASE5_ROUTER |         4 |          32 |               0.7649 |             0.6965 |               8.3243 |           5.8387 |
| GAAP_REVENUE             | midstream     | STRUCTURAL_PROXY_RECALIBRATED  | TIME_HOLDOUT_PHASE5_ROUTER   |         4 |          32 |               0.7473 |             0.6896 |               8.3224 |           5.7455 |
| GAAP_REVENUE             | refining      | P2.1_REFINING_COMPANY_KPI      | LOCO_TIME_SAFE_PHASE5_ROUTER |         3 |          24 |               0.5994 |             0.6262 |               4.6128 |           4.104  |
| GAAP_REVENUE             | refining      | P2.1_REFINING_COMPANY_KPI      | TIME_HOLDOUT_PHASE5_ROUTER   |         3 |          24 |               0.531  |             0.5863 |               4.3011 |           3.9055 |
| GAAP_REVENUE             | services      | STRUCTURAL_PROXY_RECALIBRATED  | LOCO_TIME_SAFE_PHASE5_ROUTER |         3 |          24 |               0.6955 |             0.7362 |               2.9904 |           2.8721 |
| GAAP_REVENUE             | services      | STRUCTURAL_PROXY_RECALIBRATED  | TIME_HOLDOUT_PHASE5_ROUTER   |         3 |          24 |               0.6949 |             0.7462 |               3.0374 |           2.8428 |

The router dispatches by ticker taxonomy only. It does not train an energy-wide
meta-model or re-optimize child forecasts.

## Target expansion registry

| subindustry   | forecast_target                   | status                           | unlock_requirement                                          |
|:--------------|:----------------------------------|:---------------------------------|:------------------------------------------------------------|
| ep            | CAPEX                             | LOCKED_NO_STANDARDIZED_TARGET    | PIT quarterly target labels plus 8Q per ticker              |
| ep            | OPERATING_MARGIN                  | LOCKED_NO_STANDARDIZED_TARGET    | PIT quarterly target labels plus 8Q per ticker              |
| integrated    | SEGMENT_OPERATING_EARNINGS_MARGIN | LOCKED_FORWARD_GUIDANCE_REQUIRED | manual-gold target-quarter guidance plus 8Q per ticker      |
| refining      | REFINING_MARGIN_OR_EBITDA         | LOCKED_NO_STANDARDIZED_TARGET    | audited quarterly target labels before crack residual study |
| midstream     | ADJUSTED_EBITDA_NON_GAAP          | ACTIVE_RESEARCH_GATE_FAILED      | pass parser, 8Q TIME, performance, and interval gates       |
| services      | OPERATING_MARGIN                  | LOCKED_NO_STANDARDIZED_TARGET    | PIT quarterly target labels plus 8Q per ticker              |
| services      | ORDERS_OR_BACKLOG                 | DIAGNOSTIC_ONLY_BKR_1_OF_3       | standardized cross-sectional coverage beyond BKR            |

Unstandardized margin and CapEx targets fail closed. They do not enter a
forecast merely because a plausible structural driver exists.