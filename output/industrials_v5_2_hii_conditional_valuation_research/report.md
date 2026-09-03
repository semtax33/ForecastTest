# HII V5.2 conditional valuation research

This run preserves frozen V5 and corrects route-selection governance before valuation.
DCF values are conditional sensitivity outputs, not fair-value or production authority.

## Route-selection audit

| company | fixed_oos_window | routes_tested_on_same_oos | same_oos_minimum_was_reported_as_champion_in_v5 | v5_reported_route | v5_reported_mase | corrected_v51_class | clean_predeclared_route | clean_predeclared_mase | clean_predeclared_beats_naive | route_selection_leakage_present | prospective_champion_claim_allowed | forecast_reestimated_or_retuned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HII | 2025Q1-2026Q2 | 6 | True | PIT_INDUSTRY_BRIDGE | 0.678151992455764 | BEST_TESTED_DIAGNOSTIC | PREDECLARED_EQUAL_BLEND | 0.8001205898680689 | True | True | True | False |

## FY26 guidance financial bridge

| forecast_year | source_date | shipbuilding_revenue_low_usd | shipbuilding_revenue_high_usd | shipbuilding_operating_margin_low_pct | shipbuilding_operating_margin_high_pct | mission_revenue_low_usd | mission_revenue_high_usd | mission_operating_margin_low_pct | mission_operating_margin_high_pct | trailing_intersegment_eliminations_usd | company_revenue_low_usd | company_revenue_midpoint_usd | company_revenue_high_usd | consolidated_operating_income_low_usd | consolidated_operating_income_midpoint_usd | consolidated_operating_income_high_usd | consolidated_operating_margin_low_pct | consolidated_operating_margin_midpoint_pct | consolidated_operating_margin_high_pct | effective_tax_rate_midpoint_pct | depreciation_amortization_midpoint_usd | capex_low_pct_of_sales | capex_high_pct_of_sales | levered_free_cash_flow_low_usd | levered_free_cash_flow_high_usd | interest_expense_guidance_usd | operating_fas_cas_adjustment_usd | noncurrent_state_tax_expense_usd | segment_guidance_is_direct | consolidated_margin_is_accounting_bridge | source_url | source_path | source_sha256 | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 | 2026-07-30 | 10200000000.0 | 10400000000.0 | 6.0 | 6.5 | 3000000000.0 | 3200000000.0 | 5.0 | 5.0 | -150000000.0 | 13050000000.0 | 13250000000.0 | 13450000000.0 | 698000000.0 | 734750000.0 | 772000000.0 | 5.3486590038314175 | 5.5452830188679245 | 5.739776951672862 | 17.0 | 330000000.0 | 4.0 | 5.0 | 500000000.0 | 600000000.0 | 105000000.0 | -44000000.0 | -20000000.0 | True | True | https://www.sec.gov/Archives/edgar/data/1501585/000150158526000045/hii2026q2earningsrelease.htm | D:\Programming\python_example\Arcana\data-lake\bronze\sec\fillings\ir\HII\2026-07-30_0001501585-26-000045_EX-99.1_hii2026q2earningsrelease.htm | 7597b77e8082170248de963248d8e2ef5284b65aab82cdef97390d89abce8e09 | False |

## TTM FCFF identity

| ttm_end_period | ttm_quarters | revenue_usd | operating_income_usd | operating_margin_pct | pretax_income_usd | income_tax_usd | effective_tax_rate_pct | nopat_usd | depreciation_amortization_usd | capex_usd | change_operating_nwc_usd | interest_expense_usd | cfo_usd | fcff_cash_proxy_usd | fcff_accounting_core_usd | other_operating_accruals_and_noncash_usd | fcff_accounting_full_usd | fcff_identity_error_usd | fcff_identity_pass | quarterly_nwc_chain_complete | historical_diagnostic_only |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026Q2 | 4 | 13185000000.0 | 698000000.0 | 5.293894577171028 | 844000000.0 | 183000000.0 | 21.6824644549763 | 546656398.1042655 | 322000000.0 | 429000000.0 | 631000000.0 | 98000000.0 | 347000000.0 | -5248815.165876746 | -191343601.89573455 | 186094786.7298578 | -5248815.165876746 | 0.0 | True | True | True |

## Independent WACC range

| valuation_date | risk_free_rate_pct | equity_risk_premium_pct | raw_symmetric_beta | raw_downside_beta | blume_symmetric_beta | blume_downside_beta | marginal_debt_cost_pct | tax_rate_pct | equity_weight_pct | debt_weight_pct | symmetric_wacc_pct | downside_wacc_pct | midpoint_wacc_pct | wacc_is_independent_of_market_price_fit | geopolitical_cash_flow_risk_added_to_wacc | risk_channel_double_count_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-31 | 4.75 | 4.5 | 0.7921651410314289 | 0.9830524901353997 | 0.8607506444910573 | 0.9886451683907178 | 6.75 | 17.0 | 82.53343242695377 | 17.466567573046234 | 8.0957342204704 | 8.570735052542654 | 8.333234636506527 | True | False | 0 |

## Conditional DCF range

| valuation_date | market_price | conditional_bear_value_per_share | conditional_base_value_per_share | conditional_bull_value_per_share | scenario_weighted_conditional_value_per_share | weighted_expectations_gap_pct | maximum_terminal_value_share_pct | high_terminal_dependence | all_ev_to_equity_identities_pass | reverse_solver_fail_closed | terminal_authority | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-31 | 324.0150146484375 | 79.3420382143537 | 118.8797082351239 | 221.55599806964935 | 134.6643631885627 | -58.438850948103095 | 88.60624276919333 | True | True | True | False | False | CONDITIONAL_DCF_AND_REVERSE_DCF_RESEARCH_NOT_FAIR_VALUE_AUTHORITY |

## Reverse DCF diagnostics

| diagnostic | solved_field | status | implied_value_pct | residual_usd | lower_bound_pct | upper_bound_pct | conditional_on_other_base_assumptions | appropriate_parameter_claim_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MARKET_IMPLIED_NEAR_TERM_GROWTH | near_term_growth_pct | UNBRACKETED_NO_SOLUTION_IN_DOMAIN |  | 7653013709.847995 | -15.0 | 20.0 | True | False |
| MARKET_IMPLIED_TERMINAL_MARGIN | terminal_margin_pct | SOLVED | 11.715248949243687 | -0.1970958709716797 | 1.0 | 12.0 | True | False |
| MARKET_IMPLIED_WACC | wacc_pct | SOLVED | 5.157197003805777 | -0.8403949737548828 | 3.0 | 20.0 | True | False |

## Terminal margin conditional implied WACC

| terminal_margin_pct | market_implied_wacc_pct | status | residual_usd | conditional_on_base_growth_and_roic | appropriate_wacc_claim_allowed | terminal_authority |
| --- | --- | --- | --- | --- | --- | --- |
| 4.0 | 4.441350476292428 | SOLVED | 0.4021568298339844 | True | False | False |
| 5.0 | 4.997968821742688 | SOLVED | 0.09494209289550781 | True | False | False |
| 6.0 | 5.536716841888847 | SOLVED | -0.39585304260253906 | True | False | False |
| 7.0 | 6.058995913655963 | SOLVED | 0.7311058044433594 | True | False | False |
| 8.0 | 6.566037715470884 | SOLVED | 0.2987518310546875 | True | False | False |
| 9.0 | 7.058931428706273 | SOLVED | -0.5544872283935547 | True | False | False |
| 10.0 | 7.538645601598546 | SOLVED | -0.8964366912841797 | True | False | False |
| 12.0 | 8.461909633857431 | SOLVED | 0.24422454833984375 | True | False | False |

## Gate

| parent_hii_v5_unchanged | route_selection_leakage_audited | clean_predeclared_route_retained | quarterly_nwc_chain_complete | fcff_identity_pass | all_source_cutoffs_pass | dcf_run | reverse_dcf_run | solver_round_trip_pass | ev_to_equity_identity_pass | terminal_authority | production_promoted | live_forward_matched_observations | research_freeze_eligible | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | True | True | True | True | True | True | True | True | True | False | False | 0/20 | True | CONDITIONAL_VALUATION_RESEARCH_READY_TERMINAL_AND_PRODUCTION_LOCKED |
