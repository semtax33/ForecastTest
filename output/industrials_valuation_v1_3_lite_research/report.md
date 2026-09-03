# Industrials V1.3-lite — CAT segment capture calibration

## Gate

| parent_v1_2_architecture_verified | arcana_ir_html_used | ir_parser_gate_pass | capture_validation_observations | minimum_capture_observations_met | historical_industry_pit_vintages_available | capture_forecast_performance_validated | margin_forecast_performance_validated | reinvestment_bridge_validated | cfsc_residual_bridge_reconciled | cfsc_residual_subcomponents_identified | cap_surface_complete | backlog_model_changed | backlog_oos_observations | pdf_parsing_deferred | research_complete | terminal_input_allowed | production_promoted | live_matched_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | True | True | 18 | True | False | False | False | False | True | False | True | False | 2 | True | True | False | False | 0/20 |

PDF parsing was explicitly deferred. CAT SEC-filed IR HTML supplies quarterly
segment actuals. Census/BLS history remains latest-revised rather than historical
PIT vintage, so all temporal results are calibration diagnostics only.

## IR parser

| ir_html_inventory_count | earnings_release_count | parsed_quarters | parsed_segments | cross_release_cells | cross_release_exact_matches | cross_release_mismatches | all_selected_source_hashes_match | cross_release_recast_or_scope_change_cells | within_release_comparable_basis_used | parser_gate_pass | pdf_parsing_deferred | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 118 | 23 | 23 | 4 | 152 | 125 | 27 | True | 27 | True | True | True | False |

## Segment capture

| segment | target | calibration_observations | validation_observations | raw_beta | pooled_beta | shrinkage_weight | shrunk_capture_beta | intercept_pct | residual_std_pct | temporal_validation_mae_pct | unit_capture_mae_pct | mae_improvement_vs_unit_capture_pct | mase | mean_revenue_level_ape_pct | historical_pit_vintages_available | capture_validated | validation_status | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | REVENUE | 14 | 6 | 1.3030953849490432 | 0.9596441204341561 | 0.6363636363636364 | 1.1782040160345388 | -0.3718903151264774 | 9.527650360909723 | 11.316607564599911 | 11.113994254061739 | -1.8230467454499966 | 1.3404744127009418 | 10.08415791392921 | False | False | CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT | False | False |
| construction | COST | 14 | 6 | 1.6521621318645208 | 1.286117516312415 | 0.6363636363636364 | 1.5190549989364823 | -2.184962254768113 | 8.6283434959607 | 10.360579170318621 | 9.340061958744156 | -10.926235993745825 | 1.534030819934067 |  | False | False | CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT | False | False |
| power_energy | REVENUE | 14 | 6 | 1.7043959271222253 | 0.9596441204341561 | 0.6363636363636364 | 1.4335770883265637 | 9.99458293301399 | 6.938270095114984 | 6.258718299452006 | 9.921881547004153 | 36.920046164612955 | 1.1561589212352372 | 5.807916715004102 | False | False | CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT | False | False |
| power_energy | COST | 14 | 6 | 2.591379321863214 | 1.286117516312415 | 0.6363636363636364 | 2.1167386652992874 | 4.954183885824173 | 6.0812599529377485 | 6.393744706579624 | 10.621292264016107 | 39.802572534031455 | 1.1518349697940333 |  | False | False | CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT | False | False |
| resource | REVENUE | 14 | 6 | 0.745961940873503 | 0.9596441204341561 | 0.6363636363636364 | 0.8236645516228314 | -0.6208459311258547 | 7.775249437062144 | 9.708487387957199 | 8.237744525587678 | -17.853708109072475 | 1.5692143861162566 | 9.102525645444347 | False | False | CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT | False | False |
| resource | COST | 14 | 6 | 1.0180279194537076 | 1.286117516312415 | 0.6363636363636364 | 1.1155150455841467 | -1.7868942989649983 | 6.372580880821087 | 8.037385260419901 | 5.59680332080433 | -43.606712612956876 | 1.5264680755369042 |  | False | False | CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT | False | False |

Revenue and cost capture are estimated separately and shrunk toward the pooled
CAT segment relationship. Unit capture of 1.0 is no longer assumed.

## Margin validation

| segment | validation_observations | margin_mae_pct_points | prior_year_margin_mae_pct_points | margin_mase_vs_prior_year | minimum_observations_met | historical_pit_vintages_available | margin_model_validated | status | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | 6.676200375957637 | 4.385057433358047 | 1.5224886965380173 | True | False | False | FAIL_CLOSED_NON_PIT_REVISED_MACRO_INPUT | False |
| power_energy | 6 | 3.5353742400705284 | 0.9303731048681243 | 3.7999531817631915 | True | False | False | FAIL_CLOSED_NON_PIT_REVISED_MACRO_INPUT | False |
| resource | 6 | 6.994947448207387 | 3.984756403604201 | 1.7554266157601193 | True | False | False | FAIL_CLOSED_NON_PIT_REVISED_MACRO_INPUT | False |

## FY2026 financial bridge

| ticker | forecast_origin_fiscal_year | target_fiscal_year | anchor_architecture | base_revenue_usd | forecast_revenue_usd | forecast_revenue_lower_usd | forecast_revenue_upper_usd | forecast_revenue_growth_pct | base_operating_cost_usd | forecast_operating_cost_usd | forecast_ebit_usd | forecast_operating_margin_pct | historical_operating_margin_median_pct | normalized_tax_rate_pct | forecast_nopat_usd | historical_sales_to_capital | required_reinvestment_usd | reinvestment_rate_on_base_nopat | forecast_invested_capital_usd | forecast_roic_pct | incremental_roic_pct | forecast_nopat_growth_pct | reinvestment_bridge_method | reinvestment_bridge_validated | snapshot_pit_status | historical_backtest_allowed | forecast_performance_claim_allowed | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | 2025 | 2026 | SEGMENT_IR_ACTUAL_PLUS_CAPTURE_CALIBRATED_INDUSTRY_BRIDGE | 63980000000.0 | 80574720207.56776 | 75572272058.78143 | 85577168356.35413 | 25.937355747995866 | 53096000000.0 | 65164909321.87244 | 15409810885.695328 | 19.124870487912663 | 17.011566114410755 | 20.499679692504806 | 12250849012.90705 | 3.260572433858854 | 5089511288.031128 | 0.6060668459171705 | 24186511288.031128 | 56.60746389720322 | 75.70946657478062 | 45.88499761304874 | PRIOR_REPORTED_SALES_TO_CAPITAL_CONDITIONAL_ON_CAPTURE_REVENUE | False | IR_ACTUAL_IS_PIT_BUT_INDUSTRY_HISTORY_IS_LATEST_REVISED_NOT_PIT | False | False | False | False |

## Valuation diagnostic

| ticker | valuation_status | year_one_anchor | terminal_anchor | mpe_enterprise_value_usd | explicit_forecast_pv_usd | pv_terminal_value_usd | terminal_value_share_pct | sotp_equity_value_usd | shares_outstanding | sotp_value_per_share | market_price | research_gap_pct | v1_1_value_per_share | v1_2_value_per_share | historical_industry_pit_vintages_available | terminal_replacement_allowed | production_promoted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | V1_3_LITE_CALIBRATION_DIAGNOSTIC_NOT_A_PERFORMANCE_OR_MISPRICING_SIGNAL | SEGMENT_IR_ACTUAL_PLUS_CAPTURE_CALIBRATED_INDUSTRY_BRIDGE | V1_1_FROZEN_NORMALIZED_ECONOMICS | 178390492071.01898 | 42713528909.69472 | 135676963161.32428 | 76.05616285161094 | 185704326258.3773 | 465287332.0 | 399.117520479533 | 827.9000244140625 | -51.79158005678231 | 248.62051963982543 | 363.8863803839645 | False | False | False |

## Reinvestment

| validation_observations | minimum_observations_required | minimum_observations_met | conditional_bridge_mae_usd | conditional_bridge_mase | realized_revenue_used_as_condition | full_forecast_oos_validated | reinvestment_bridge_validated | status | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 3 | True | 486454425.29446536 | 0.19670619704588166 | True | False | False | FAIL_CLOSED_CONDITIONAL_BRIDGE_ONLY | False | False |

| history_years | first_fiscal_year | latest_fiscal_year | latest_total_capex_usd | latest_financial_products_capex_usd | latest_mpe_capex_proxy_usd | net_reinvestment_identity_claim_allowed | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 2021 | 2025 | 4286000000.0 | 1341000000.0 | 2945000000.0 | False | False | False |

| forecast_required_reinvestment_usd | latest_mpe_capex_proxy_usd | required_reinvestment_to_latest_mpe_capex_pct | comparison_semantics | accounting_identity_claim_allowed | reinvestment_bridge_validated | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- |
| 5089511288.031128 | 2945000000.0 | 172.81871945776325 | NET_REINVESTMENT_REQUIREMENT_VS_GROSS_CAPEX_CONTEXT_ONLY | False | False | False |

## Financial Products residual

| fiscal_year | cat_financial_products_pretax_usd | cfsc_standalone_pretax_usd | pretax_perimeter_residual_usd | cat_financial_products_tax_usd | cfsc_standalone_tax_usd | tax_perimeter_residual_usd | cat_financial_products_net_profit_usd | cfsc_standalone_net_profit_usd | reported_net_perimeter_residual_usd | bridge_implied_net_residual_usd | rounding_and_affiliate_residual_usd | bridge_level_attribution_identified | economic_subcomponent_attribution_identified | perimeter_evidence | measurement_evidence | source_excerpt | source_path | status | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | 977000000.0 | 734000000.0 | 243000000.0 | 243000000.0 | 193000000.0 | 50000000.0 | 734000000.0 | 540000000.0 | 194000000.0 | 193000000.0 | 1000000.0 | True | False | CAT_FINANCE_AND_INSURANCE_SUBSIDIARIES_INCLUDING_CFSC_AND_INSURANCE_SERVICES | FINANCIAL_PRODUCTS_SEGMENT_PROFIT_IS_PRETAX | We determine Financial Products Segment profit on a pretax basis and include other income (expense) items. Our CODM evaluates the operating performance of the segments using segment profit as it provides insight into the financial health of each segment. The CODM reviews this metric regularly to compare the profitability of segments, identify trends, and eva \| Financial Products — Our finance and insurance subsidiaries, primarily Caterpillar Financial Services Corporation (Cat Financial) and Caterpillar Insurance Holdings Inc. (Insurance Services). Financial Products information relates to the financing to customers and dealers for the purchase and lease of Caterpillar and other equipment. Other information about  | D:\Programming\python_example\ForecastTest\data-lake\bronze\snapshots\industrials_cat_10k\fiscal_year=2025\cat-20251231.htm | BRIDGE_RECONCILED_SUBCOMPONENTS_STILL_UNIDENTIFIED | False | False |

## Competitive-advantage-period surface

| margin_cap_points | margin_roic_cap_points | market_match_points | nearest_absolute_gap_pct | non_identification_preserved | appropriate_cap_claim_allowed | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 24 | 96 | 3 | 0.19459386136313128 | True | False | False | False |

Backlog remains unchanged at 2/3 OOS. Terminal replacement and production stay
locked at 0/20.
