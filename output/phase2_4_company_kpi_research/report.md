# Phase 2-4 company KPI and conformal refinement

The original structural proxy benchmark is frozen and verified. Company KPI
candidates use official SEC 8-K earnings exhibits released by the day-61
cutoff. Missing or stale KPIs fall back to the original proxy.

## Point forecast comparison

| subindustry | proxy_median_mase | company_kpi_median_mase | proxy_mean_mase | company_kpi_mean_mase | proxy_wape_pct | company_kpi_wape_pct | benchmark_no_regression_share | median_company_kpi_improvement_log_points |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| integrated | 1.0506 | 1.2229 | 1.0506 | 1.2229 | 5.3825 | 6.513 | 0.0 | -0.852 |
| midstream | 0.7473 | 0.8038 | 0.6896 | 0.6992 | 8.3224 | 8.5827 | 0.25 | -0.2056 |
| refining | 0.5371 | 0.531 | 0.5943 | 0.5863 | 4.3417 | 4.3011 | 1.0 | 0.0452 |
| services | 0.6949 | 0.7015 | 0.7462 | 0.7665 | 3.0374 | 3.1032 | 0.3333 | -0.0166 |

## Manual-gold parser quality gate

| subindustry | gold_rows | post_numeric_accuracy | post_unit_accuracy | post_period_accuracy | post_semantic_accuracy | parser_quality_gate |
| --- | --- | --- | --- | --- | --- | --- |
| integrated | 18 | 1.0 | 1.0 | 1.0 | 1.0 | True |
| midstream | 27 | 1.0 | 1.0 | 1.0 | 1.0 | True |
| refining | 15 | 1.0 | 1.0 | 1.0 | 1.0 | True |
| services | 15 | 1.0 | 1.0 | 1.0 | 1.0 | True |

## Integrated component ablation

| subindustry | variant | median_ticker_mase | mean_ticker_mase | overall_revenue_wape_pct | mean_directional_hit_rate | point_model_gate |
| --- | --- | --- | --- | --- | --- | --- |
| integrated | UPSTREAM_ONLY | 1.0102 | 1.0102 | 5.2886 | 0.75 | False |
| integrated | DOWNSTREAM_ONLY | 1.0506 | 1.0506 | 5.3825 | 0.6875 | False |
| integrated | CHEMICALS_ONLY | 1.0506 | 1.0506 | 5.3825 | 0.6875 | False |
| integrated | ALL_COMPANY_KPIS | 1.2229 | 1.2229 | 6.513 | 0.6875 | False |

## Prediction interval recalibration

| subindustry | original_pi_80_coverage | recalibrated_pi_80_coverage | original_pi_95_coverage | recalibrated_pi_95_coverage | original_interval_80_score | recalibrated_interval_80_score |
| --- | --- | --- | --- | --- | --- | --- |
| integrated | 0.8125 | 0.75 | 1.0 | 0.9375 | 26.3983 | 28.491 |
| midstream | 0.9375 | 0.8125 | 1.0 | 0.9375 | 39.5366 | 32.5814 |
| refining | 1.0 | 0.8333 | 1.0 | 0.875 | 30.4282 | 22.0501 |
| services | 1.0 | 0.875 | 1.0 | 0.9583 | 15.4336 | 12.2357 |

## Split gates

| experiment | subindustry | point_model_gate | uncertainty_gate | combined_research_gate | macro_research_unlocked | production_promotion_eligible |
| --- | --- | --- | --- | --- | --- | --- |
| PROXY_RECALIBRATED | integrated | False | True | False | False | False |
| COMPANY_KPI | integrated | False | False | False | False | False |
| PROXY_RECALIBRATED | refining | True | False | False | True | False |
| COMPANY_KPI | refining | True | True | True | True | False |
| PROXY_RECALIBRATED | midstream | False | True | False | False | False |
| COMPANY_KPI | midstream | False | True | False | False | False |
| PROXY_RECALIBRATED | services | True | False | False | True | False |
| COMPANY_KPI | services | True | False | False | True | False |

## Latest local-snapshot predictions

| phase | subindustry | ticker | quarter | company_kpi_report_quarter | company_kpi_feature_count | research_selected_model | candidate_prediction | candidate_revenue_usd_bn | lower_80_log_yoy | upper_80_log_yoy | selected_model | selected_prediction | selected_revenue_usd_bn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | integrated | CVX | 2026Q2 | 2026Q1 | 3 | STRUCTURAL_PROXY_RECALIBRATED | 28.7706 | 59.7641 | 19.9455 | 37.5957 | LAG_REVENUE_BASELINE | 2.0725 | 45.7606 |
| 2 | integrated | XOM | 2026Q2 | 2026Q1 | 3 | STRUCTURAL_PROXY_RECALIBRATED | 30.142 | 110.178 | 21.5646 | 38.7194 | LAG_REVENUE_BASELINE | 2.3868 | 83.4748 |
| 2 | refining | MPC | 2026Q2 | 2026Q1 | 1 | P2.1_REFINING_COMPANY_KPI | 39.9281 | 50.3859 | 32.2756 | 47.5805 | LAG_REVENUE_BASELINE | 8.1699 | 36.6763 |
| 2 | refining | PSX | 2026Q2 | 2026Q1 | 1 | P2.1_REFINING_COMPANY_KPI | 44.2617 | 51.8764 | 37.4997 | 51.0236 | LAG_REVENUE_BASELINE | 6.7041 | 35.6336 |
| 2 | refining | VLO | 2026Q2 | 2026Q1 | 1 | P2.1_REFINING_COMPANY_KPI | 39.8102 | 44.5046 | 32.3082 | 47.3123 | LAG_REVENUE_BASELINE | 6.7811 | 31.9861 |
| 3 | midstream | EPD | 2026Q2 | 2026Q1 | 2 | STRUCTURAL_PROXY_RECALIBRATED | 1.6002 | 11.5463 | -10.503 | 13.7035 | LAG_REVENUE_BASELINE | -6.9215 | 10.6031 |
| 3 | midstream | ET | 2026Q2 | 2026Q1 | 2 | STRUCTURAL_PROXY_RECALIBRATED | 15.1336 | 22.3859 | 3.3766 | 26.8906 | LAG_REVENUE_BASELINE | 27.8518 | 25.422 |
| 3 | midstream | KMI | 2026Q2 | 2026Q1 | 1 | STRUCTURAL_PROXY_RECALIBRATED | 7.486 | 4.3562 | -0.2311 | 15.2031 | LAG_REVENUE_BASELINE | 12.9633 | 4.6015 |
| 3 | midstream | WMB | 2026Q2 | 2026Q1 | 2 | STRUCTURAL_PROXY_RECALIBRATED | 1.9553 | 2.8359 | -7.1626 | 11.0731 | LAG_REVENUE_BASELINE | -0.5923 | 2.7646 |
| 4 | services | BKR | 2026Q2 | 2026Q1 | 1 | STRUCTURAL_PROXY_RECALIBRATED | 1.544 | 7.0175 | -3.001 | 6.089 | LAG_REVENUE_BASELINE | 2.459 | 7.082 |
| 4 | services | HAL | 2026Q2 | 2026Q1 | 1 | STRUCTURAL_PROXY_RECALIBRATED | 0.2297 | 5.5227 | -3.239 | 3.6984 | LAG_REVENUE_BASELINE | -0.2773 | 5.4947 |
| 4 | services | SLB | 2026Q2 | 2026Q1 | 1 | STRUCTURAL_PROXY_RECALIBRATED | 1.4244 | 8.6686 | -2.9206 | 5.7693 | LAG_REVENUE_BASELINE | 2.6845 | 8.7785 |

## Standardized KPI coverage

| ticker | metric_id | first_report_quarter | last_report_quarter | observations | yoy_observations | mean_quality_score |
| --- | --- | --- | --- | --- | --- | --- |
| BKR | international_activity | 2022Q4 | 2026Q2 | 15 | 11 | 0.95 |
| BKR | orders_activity | 2018Q1 | 2026Q2 | 34 | 30 | 0.95 |
| CVX | downstream_product_sales | 2023Q1 | 2026Q2 | 14 | 10 | 0.85 |
| CVX | downstream_throughput | 2024Q1 | 2026Q2 | 10 | 6 | 0.85 |
| CVX | upstream_total_boe | 2023Q1 | 2026Q2 | 14 | 10 | 0.9 |
| EPD | equivalent_pipeline_volume | 2018Q1 | 2026Q2 | 34 | 30 | 0.9 |
| EPD | fee_gas_processing_volume | 2018Q1 | 2026Q2 | 34 | 30 | 0.9 |
| ET | gas_gathering_volume | 2018Q3 | 2026Q2 | 32 | 28 | 0.9 |
| ET | gas_transport_volume | 2018Q3 | 2026Q2 | 32 | 28 | 0.85 |
| ET | liquids_transport_volume | 2018Q3 | 2026Q2 | 32 | 28 | 0.85 |
| HAL | completion_production_activity | 2023Q1 | 2026Q2 | 14 | 10 | 0.95 |
| HAL | north_america_activity | 2023Q1 | 2026Q2 | 14 | 10 | 0.95 |
| KMI | gas_gathering_volume | 2020Q2 | 2026Q2 | 25 | 21 | 0.9 |
| KMI | gas_transport_volume | 2018Q1 | 2025Q4 | 32 | 28 | 0.9 |
| MPC | company_throughput | 2018Q1 | 2026Q2 | 34 | 30 | 0.85 |
| MPC | company_utilization | 2018Q1 | 2026Q2 | 34 | 30 | 0.9 |
| PSX | company_throughput | 2018Q1 | 2026Q2 | 33 | 28 | 0.9 |
| PSX | company_utilization | 2018Q1 | 2026Q2 | 33 | 28 | 0.9 |
| SLB | international_activity | 2019Q1 | 2026Q2 | 30 | 26 | 0.95 |
| SLB | north_america_activity | 2019Q1 | 2026Q2 | 30 | 26 | 0.95 |
| VLO | company_throughput | 2018Q1 | 2026Q2 | 34 | 30 | 0.9 |
| WMB | gas_gathering_volume | 2020Q1 | 2026Q2 | 26 | 22 | 0.85 |
| WMB | gas_transport_volume | 2018Q1 | 2026Q2 | 34 | 30 | 0.8529 |
| XOM | chemicals_product_sales | 2022Q2 | 2026Q1 | 16 | 12 | 0.9 |
| XOM | downstream_product_sales | 2022Q2 | 2026Q1 | 16 | 12 | 0.9 |
| XOM | upstream_total_boe | 2019Q4 | 2026Q1 | 26 | 22 | 0.9 |

Macro research unlock follows the point-model gate only. Production promotion
still requires point, uncertainty, and 20 matched live-forward observations;
therefore the lag-revenue baseline remains selected.