# Energy platform Phase 2-4 structural research

Phase 2 keeps Integrated and Refining as separate economic models. Phase 3
uses contract-aware midstream volume/fee drivers. Phase 4 uses OFS activity
and CapEx/pricing signals. TIME is primary; LOCO is a cold-start diagnostic.

No paid CME, CMA, or CME DataMine data is used. Product-price and throughput
forecasts come from point-in-time EIA STEO archives; rig history is the free
EIA republication of Baker Hughes data.

## TIME performance

| subindustry | median_ticker_mase | mean_ticker_mase | legacy_no_regression_share | mean_pi_80_coverage | mean_directional_hit_rate | overall_revenue_wape_pct | overall_revenue_median_ape_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| integrated | 1.0506 | 1.0506 | 1.0 | 0.8125 | 0.6875 | 5.3825 | 5.3002 |
| refining | 0.5371 | 0.5943 | 1.0 | 1.0 | 0.8333 | 4.3417 | 3.8618 |
| midstream | 0.7473 | 0.6896 | 0.75 | 0.9375 | 0.6562 | 8.3224 | 5.7455 |
| services | 0.6949 | 0.7462 | 1.0 | 1.0 | 0.75 | 3.0374 | 2.8428 |

## Strict research gates

| phase | subindustry | minimum_8_forecasts_per_ticker | median_time_mase_below_0_80 | mean_time_mase_below_0_90 | baseline_no_regression_at_least_80pct | severe_regression_count_zero | pi80_between_75_85pct | directional_hit_at_least_65pct | research_gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | integrated | True | False | False | True | True | True | True | False |
| 2 | refining | True | True | True | True | True | False | True | False |
| 3 | midstream | True | True | True | False | True | False | True | False |
| 4 | services | True | True | True | True | True | False | True | False |

## Latest unobserved local-SEC-snapshot predictions

| phase | subindustry | ticker | quarter | issue | available_at | raw_structural_prediction | structural_shrinkage_weight | candidate_prediction | candidate_revenue_usd_bn | legacy_prediction | selected_model | selected_prediction | selected_revenue_usd_bn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | integrated | CVX | 2026Q2 | may26 | 2026-05-14 00:00:00 | 34.6805 | 0.8188 | 28.7706 | 59.7641 | 2.0725 | LAG_REVENUE_BASELINE | 2.0725 | 45.7606 |
| 2 | integrated | XOM | 2026Q2 | may26 | 2026-05-14 00:00:00 | 36.2859 | 0.8188 | 30.142 | 110.178 | 2.3868 | LAG_REVENUE_BASELINE | 2.3868 | 83.4748 |
| 2 | refining | MPC | 2026Q2 | may26 | 2026-05-14 00:00:00 | 53.9195 | 0.6924 | 39.8449 | 50.3441 | 8.1699 | LAG_REVENUE_BASELINE | 8.1699 | 36.6763 |
| 2 | refining | PSX | 2026Q2 | may26 | 2026-05-14 00:00:00 | 53.9195 | 0.6924 | 39.394 | 49.4117 | 6.7041 | LAG_REVENUE_BASELINE | 6.7041 | 35.6336 |
| 2 | refining | VLO | 2026Q2 | may26 | 2026-05-14 00:00:00 | 53.9195 | 0.6924 | 39.4177 | 44.3303 | 6.7811 | LAG_REVENUE_BASELINE | 6.7811 | 31.9861 |
| 3 | midstream | EPD | 2026Q2 | may26 | 2026-05-14 00:00:00 | 7.3704 | 0.5963 | 1.6002 | 11.5463 | -6.9215 | LAG_REVENUE_BASELINE | -6.9215 | 10.6031 |
| 3 | midstream | ET | 2026Q2 | may26 | 2026-05-14 00:00:00 | 6.522 | 0.5963 | 15.1336 | 22.3859 | 27.8518 | LAG_REVENUE_BASELINE | 27.8518 | 25.422 |
| 3 | midstream | KMI | 2026Q2 | may26 | 2026-05-14 00:00:00 | 3.7772 | 0.5963 | 7.486 | 4.3562 | 12.9633 | LAG_REVENUE_BASELINE | 12.9633 | 4.6015 |
| 3 | midstream | WMB | 2026Q2 | may26 | 2026-05-14 00:00:00 | 3.6803 | 0.5963 | 1.9553 | 2.8359 | -0.5923 | LAG_REVENUE_BASELINE | -0.5923 | 2.7646 |
| 4 | services | BKR | 2026Q2 | may26 | 2026-05-14 00:00:00 | -0.3986 | 0.3202 | 1.544 | 7.0175 | 2.459 | LAG_REVENUE_BASELINE | 2.459 | 7.082 |
| 4 | services | HAL | 2026Q2 | may26 | 2026-05-14 00:00:00 | 1.306 | 0.3202 | 0.2297 | 5.5227 | -0.2773 | LAG_REVENUE_BASELINE | -0.2773 | 5.4947 |
| 4 | services | SLB | 2026Q2 | may26 | 2026-05-14 00:00:00 | -1.2509 | 0.3202 | 1.4244 | 8.6686 | 2.6845 | LAG_REVENUE_BASELINE | 2.6845 | 8.7785 |

## Analyst consensus audit

Arcana Alpha Vantage and FMP revenue estimates are included only when their
snapshot date passes the same release-date cutoff. Finnworlds is recorded as
ratings-only coverage and is never treated as revenue consensus.

| status | observations | model_mape_pct | consensus_mape_pct | model_win_rate | surprise_direction_accuracy | statistical_test_status |
| --- | --- | --- | --- | --- | --- | --- |
| NO_MATCHED_OBSERVATIONS | 0 |  |  |  |  | NEEDS_20_OBSERVATIONS |

The current Arcana snapshots are after the 2026Q2 cutoff, so this next table
is diagnostic only and cannot enter backtests, gates, or promotion decisions.

| ticker | quarter | candidate_revenue_usd_bn | consensus_revenue_usd_bn | candidate_minus_consensus_pct | providers | snapshot_date | comparison_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CVX | 2026Q2 | 59.7641 | 62.0899 | -3.7459 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| XOM | 2026Q2 | 110.178 | 103.8597 | 6.0834 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| MPC | 2026Q2 | 50.3441 | 41.1153 | 22.4462 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| PSX | 2026Q2 | 49.4117 | 43.5973 | 13.3366 | FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| VLO | 2026Q2 | 44.3303 | 39.469 | 12.3167 | FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| EPD | 2026Q2 | 11.5463 | 13.8765 | -16.7927 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| ET | 2026Q2 | 22.3859 |  |  |  |  | NO_REVENUE_CONSENSUS_SNAPSHOT |
| KMI | 2026Q2 | 4.3562 | 4.2088 | 3.5013 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| WMB | 2026Q2 | 2.8359 | 2.8284 | 0.2639 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| BKR | 2026Q2 | 7.0175 | 6.5217 | 7.602 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| HAL | 2026Q2 | 5.5227 | 5.4956 | 0.4926 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |
| SLB | 2026Q2 | 8.6686 | 8.676 | -0.0849 | ALPHA_VANTAGE,FMP | 2026-07-31 00:00:00 | POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION |

## Operating KPI and proxy coverage

| subindustry | ticker | primary_operating_driver | active_proxy | proxy_scope | configuration_status |
| --- | --- | --- | --- | --- | --- |
| integrated | CVX | SEGMENT_PRICE_AND_VOLUME_SUM_OF_PARTS | EIA_STEO_PRICE_AND_US_PRODUCTION_WITH_FIXED_SEGMENT_WEIGHTS | US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| integrated | XOM | SEGMENT_PRICE_AND_VOLUME_SUM_OF_PARTS | EIA_STEO_PRICE_AND_US_PRODUCTION_WITH_FIXED_SEGMENT_WEIGHTS | US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| refining | MPC | FORWARD_PRODUCT_PRICE_X_THROUGHPUT | EIA_STEO_US_REFINERY_CRUDE_INPUT | US_GROUP_PROXY_NOT_COMPANY_GUIDANCE | COMPANY_THROUGHPUT_GUIDANCE_UNAVAILABLE_IN_STRUCTURED_INPUT |
| refining | PSX | FORWARD_PRODUCT_PRICE_X_THROUGHPUT | EIA_STEO_US_REFINERY_CRUDE_INPUT | US_GROUP_PROXY_NOT_COMPANY_GUIDANCE | COMPANY_THROUGHPUT_GUIDANCE_UNAVAILABLE_IN_STRUCTURED_INPUT |
| refining | VLO | FORWARD_PRODUCT_PRICE_X_THROUGHPUT | EIA_STEO_US_REFINERY_CRUDE_INPUT | US_GROUP_PROXY_NOT_COMPANY_GUIDANCE | COMPANY_THROUGHPUT_GUIDANCE_UNAVAILABLE_IN_STRUCTURED_INPUT |
| midstream | EPD | CONTRACT_FEE_X_GAS_AND_LIQUID_VOLUME | EIA_STEO_PRODUCTION_WITH_FIXED_FEE_AND_VOLUME_MIX | US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| midstream | ET | CONTRACT_FEE_X_GAS_AND_LIQUID_VOLUME | EIA_STEO_PRODUCTION_WITH_FIXED_FEE_AND_VOLUME_MIX | US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| midstream | KMI | CONTRACT_FEE_X_GAS_AND_LIQUID_VOLUME | EIA_STEO_PRODUCTION_WITH_FIXED_FEE_AND_VOLUME_MIX | US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| midstream | WMB | CONTRACT_FEE_X_GAS_AND_LIQUID_VOLUME | EIA_STEO_PRODUCTION_WITH_FIXED_FEE_AND_VOLUME_MIX | US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| services | BKR | RIG_ACTIVITY_X_SERVICE_INTENSITY_X_PRICING | EIA_BAKER_HUGHES_RIGS_AND_STEO_PRODUCTION_PRICE | US_AND_GLOBAL_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| services | HAL | RIG_ACTIVITY_X_SERVICE_INTENSITY_X_PRICING | EIA_BAKER_HUGHES_RIGS_AND_STEO_PRODUCTION_PRICE | US_AND_GLOBAL_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |
| services | SLB | RIG_ACTIVITY_X_SERVICE_INTENSITY_X_PRICING | EIA_BAKER_HUGHES_RIGS_AND_STEO_PRODUCTION_PRICE | US_AND_GLOBAL_MACRO_PLUS_COMPANY_RESEARCH_PRIOR | FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED |

A failed research gate retains the lag-revenue baseline as the selected model.
V3.4 remains the frozen production champion and live promotion remains 0/20.