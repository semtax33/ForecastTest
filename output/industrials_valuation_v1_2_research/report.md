# Industrials Valuation V1.2 — CAT expectations and economics audit

## Research gate

| parent_v1_1_verified | industry_sensor_bridge_complete | expectations_surfaces_complete | mpe_roic_perimeter_audited | cfsc_exact_economics_complete | backlog_model_changed | backlog_oos_observations | parser_quality_gate_pass | historical_industry_pit_vintages_available | research_complete | terminal_input_allowed | production_promoted | live_matched_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | True | True | True | True | False | 2 | True | False | True | False | False | 0/20 |

## Industry P/Q/C/I bridge

| ticker | forecast_origin_fiscal_year | target_fiscal_year | anchor_architecture | industry_revenue_growth_signal_pct | industry_cost_growth_signal_pct | industry_inventory_growth_signal_pct | base_revenue_usd | forecast_revenue_usd | forecast_revenue_growth_pct | base_operating_cost_usd | forecast_operating_cost_usd | forecast_ebit_usd | forecast_operating_margin_pct | historical_operating_margin_median_pct | margin_vs_history_pct_points | normalized_tax_rate_pct | forecast_nopat_usd | historical_sales_to_capital | inventory_adjusted_sales_to_capital | required_reinvestment_usd | reinvestment_rate_on_base_nopat | forecast_invested_capital_usd | forecast_roic_pct | incremental_roic_pct | forecast_nopat_growth_pct | reinvestment_x_incremental_roic_pct | growth_identity_error_pct_points | reinvestment_bridge_method | reinvestment_bridge_validated | economics_scope_flag | valuation_use | snapshot_pit_status | historical_backtest_allowed | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | 2025 | 2026 | INDUSTRY_PQCI_TO_FINANCIAL_BRIDGE | 17.027819130582095 | 3.9381717021405134 | 4.447090568622798 | 63980000000.0 | 74874398679.74641 | 17.027819130582095 | 53096000000.0 | 55187011646.96852 | 19687387032.777893 | 26.29388332984816 | 17.011566114410755 | 9.282317215437406 | 20.499679692504806 | 15651535751.2347 | 3.260572433858854 | 3.1217455805689722 | 3489841948.5423894 | 0.41557575625708726 | 22586841948.54239 | 75.09641635507643 | 207.85836988374297 | 86.38089925880186 | 86.38089925880185 | 1.1102230246251565e-14 | INVENTORY_ADJUSTED_HISTORICAL_SALES_TO_CAPITAL | False | REQUIRES_COST_SCOPE_AND_COMPANY_CAPTURE_VALIDATION | YEAR_ONE_RESEARCH_ONLY_FADE_TO_V1_1_FROZEN_TERMINAL | CURRENT_AS_OF_CUTOFF_BUT_NO_HISTORICAL_VINTAGES | False | False | False |

Public Census M3 and BLS observations are available at the research cutoff, but
the current Arcana snapshots do not preserve historical release dates/vintages.
They may drive this current research nowcast, not a historical PIT backtest or
production model.

## Research DCF

| ticker | valuation_status | year_one_anchor | terminal_anchor | mpe_enterprise_value_usd | explicit_forecast_pv_usd | pv_terminal_value_usd | terminal_value_share_pct | less_mpe_debt_usd | add_mpe_cash_usd | financial_products_equity_value_usd | sotp_equity_value_usd | shares_outstanding | sotp_value_per_share | market_price | research_gap_pct | v1_1_value_per_share | change_vs_v1_1_pct | component_identity_error_usd | financial_products_funding_debt_double_counted | terminal_replacement_allowed | production_promoted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | V1_2_RESEARCH_DIAGNOSTIC_NOT_A_MISPRICING_SIGNAL | CENSUS_M3_PLUS_BLS_PQCI | V1_1_FROZEN_NORMALIZED_ECONOMICS | 161997888892.63367 | 49956203909.37357 | 112041684983.26009 | 69.16243523242285 | 10990000000.0 | 9333000000.0 | 8970834187.35831 | 169311723079.99197 | 465287332.0 | 363.8863803839645 | 827.9000244140625 | -56.0470624890365 | 248.62051963982543 | 46.36216709349807 | 0.0 | False | False | False |

The industry bridge controls year one. Later years fade to V1.1 frozen normalized
margin and ROIC, so V1.2 does not silently replace terminal economics.

## Expectations surfaces

| surface_points | market_match_points | iso_conditions | iso_solved_conditions | iso_unbracketed_conditions | non_identification_preserved | appropriate_parameter_claim_allowed | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 75 | 0 | 10 | 8 | 2 | True | False | False | False |

| condition | fixed_wacc_pct | fixed_margin_pct | solved_parameter | status | solution_pct | residual_usd |
| --- | --- | --- | --- | --- | --- | --- |
| WACC_FIXED_SOLVE_MARGIN | 7.0 |  | operating_margin_pct | SOLVED | 39.598445892333984 | -693870.7268676758 |
| WACC_FIXED_SOLVE_MARGIN | 8.0 |  | operating_margin_pct | SOLVED | 47.45828628540039 | 587071.3753051758 |
| WACC_FIXED_SOLVE_MARGIN | 9.0 |  | operating_margin_pct | SOLVED | 55.30029296875 | -516123.7258911133 |
| WACC_FIXED_SOLVE_MARGIN | 10.0 |  | operating_margin_pct | UNBRACKETED_NO_SOLUTION_IN_DOMAIN |  | 18712964867.284058 |
| WACC_FIXED_SOLVE_MARGIN | 11.0 |  | operating_margin_pct | UNBRACKETED_NO_SOLUTION_IN_DOMAIN |  | 58258001186.07257 |
| MARGIN_FIXED_SOLVE_WACC |  | 14.0 | wacc_pct | SOLVED | 3.759951114654541 | 656977.4304199219 |
| MARGIN_FIXED_SOLVE_WACC |  | 17.0 | wacc_pct | SOLVED | 4.13824462890625 | 410294.70178222656 |
| MARGIN_FIXED_SOLVE_WACC |  | 20.0 | wacc_pct | SOLVED | 4.516935348510742 | -425750.37170410156 |
| MARGIN_FIXED_SOLVE_WACC |  | 23.0 | wacc_pct | SOLVED | 4.895998954772949 | 609692.213684082 |
| MARGIN_FIXED_SOLVE_WACC |  | 26.0 | wacc_pct | SOLVED | 5.27545166015625 | 194577.14392089844 |

## MP&E ROIC perimeter

| ticker | measurement_years | historical_roic_median_pct | historical_roic_latest_pct | annual_incremental_roic_median_pct | endpoint_incremental_roic_pct | through_cycle_aggregate_roic_pct | roic_perimeter | nopat_perimeter | financial_products_excluded | goodwill_separately_identified | intercompany_adjustments_embedded | historical_equals_incremental | incremental_equals_terminal | terminal_roic_identified | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | 5 | 49.37189223562976 | 44.2794999497782 | -8.782166923421304 | 74.54466583631783 | 48.233877509679076 | MPE_EQUITY_PLUS_MPE_DEBT_MINUS_MPE_CASH | MPE_OPERATING_PROFIT_AFTER_EFFECTIVE_TAX | True | False | True | False | False | False | False | False |

Historical, annual incremental, through-cycle, and terminal ROIC are kept as
different concepts. The audit does not identify a terminal ROIC.

## Financial Products exact economics

| fiscal_year | cfsc_standalone_profit_usd | cat_financial_products_profit_usd | broader_fp_reconciling_profit_usd | reconciling_profit_attribution_identified | cfsc_standalone_equity_usd | cat_financial_products_equity_usd | perimeter_equity_difference_usd | financing_yield_pct | funding_cost_pct | net_finance_spread_pct | credit_loss_rate_pct | standalone_roe_pct | payout_ratio_pct | exact_cfsc_economics_available | whole_fp_exact_economics_available | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | 540000000.0 | 734000000.0 | 194000000.0 | False | 3227000000.0 | 4841000000.0 | 1614000000.0 | 8.261707052558313 | 4.447577544219431 | 3.8141295083388815 | 0.3431586785153531 | 17.655713585090734 | 92.5925925925926 | True | False | False | False |

CFSC standalone economics are exact to its SEC statements. CAT's broader
Financial Products segment includes an explicit residual perimeter and is not
misrepresented as identical to CFSC.

## Parser quality

| cross_filing_cells | cross_filing_exact_matches | cross_filing_mismatches | gold_cells | gold_matches | parser_quality_gate_pass | manual_source_excerpt_review_required | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 196 | 196 | 0 | 8 | 8 | True | True | False | False |

Backlog logic remains unchanged with only 2/3 OOS validations. V1.1 remains
manifest-verified, terminal promotion is prohibited, and production stays 0/20.
