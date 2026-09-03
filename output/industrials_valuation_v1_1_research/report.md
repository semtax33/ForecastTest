# Industrials Valuation V1.1 — CAT semantic and SOTP audit

## Research gate

| version | direct_firm_backlog_years | rpo_anchor_retired | direct_backlog_anchor_promoted | backlog_oos_validation_observations | segment_history_years | segment_reconciliation_pass | mpe_debt_used_usd | fp_funding_debt_excluded_from_mpe_bridge_usd | financial_products_separately_valued | sotp_component_identity_pass | year_one_revenue_identity_error_usd | year_one_revenue_identity_pass | reverse_dcf_fail_closed | research_audit_complete | terminal_input_allowed | production_promoted | live_matched_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INDUSTRIALS_V1_1_CAT_SEMANTIC_SOTP_AUDIT | 5 | True | False | 2 | 5 | True | 10990000000.0 | 33617000000.0 | True | True | 0.0 | True | True | True | False | False | 0/20 |

## Backlog semantic result

| anchor | direct_firm_backlog_years | next_year_conversion_years | walk_forward_validation_observations | minimum_validation_observations | anchor_revenue_mase_vs_prior_year_naive | anchor_promoted | rpo_anchor_retired | selected_forecast_route | promotion_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT_FIRM_ORDER_BACKLOG_DIRECT_10_K | 5 | 5 | 2 | 3 | 0.5924059869891197 | False | True | PRIOR_YEAR_MPE_REVENUE_BASELINE | LOCKED_INSUFFICIENT_OOS_EVIDENCE_OR_NO_MASE_IMPROVEMENT |

The retired V1 `RevenueRemainingPerformanceObligation` field is not treated as
CAT's firm order backlog. V1.1 directly parses firm backlog and the disclosed
amount not expected to be filled in the next year from each official 10-K.
Although the conditional bridge beats the naive baseline on the currently
available MASE sample, only two walk-forward validations exist versus the
predeclared minimum of three, so it remains locked and is not used in value.

## MP&E financial bridge

| ticker | forecast_origin_fiscal_year | target_fiscal_year | business | primary_anchor | selected_forecast_route | anchor_promoted | base_revenue_usd | near_term_growth_pct | year_one_revenue_usd | normalized_operating_margin_pct | year_one_ebit_usd | normalized_tax_rate_pct | year_one_nopat_usd | normalized_roic_pct | year_one_reinvestment_usd | year_one_fcff_usd | mpe_cost_of_debt_pct | mpe_cost_of_debt_method | mpe_wacc_pct | terminal_growth_pct | mpe_debt_used_usd | mpe_cash_used_usd | fp_funding_debt_excluded_usd | mpe_enterprise_value_usd | mpe_equity_value_usd | terminal_input_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | 2025 | 2026 | MP&E | FIRM_ORDER_BACKLOG_DIRECT_10_K | PRIOR_YEAR_MPE_REVENUE_BASELINE | False | 63980000000.0 | 0.0 | 63980000000.0 | 17.011566114410755 | 10884000000.000002 | 20.499679692504806 | 8652814862.267778 | 49.37189223562976 | 0.0 | 8652814862.267778 | 5.2208225830930335 | DIRECT_INTEREST_EX_FP_OVER_AVERAGE_MPE_DEBT | 9.513809736590686 | 2.0 | 10990000000.0 | 9333000000.0 | 33617000000.0 | 108366144076.30968 | 106709144076.30968 | False | False |

## Financial Products standalone value

| scenario | valuation_method | book_equity_usd | normalized_roe_pct | cost_of_equity_pct | terminal_growth_pct | residual_income_value_usd | justified_price_to_book_value_usd | valuation_identity_error_usd | latest_profit_usd | finance_receivables_usd | funding_debt_usd | funding_cost_proxy_pct | revenue_yield_proxy_pct | funding_spread_proxy_pct | credit_loss_provision_pct_receivables | credit_loss_allowance_pct_receivables | production_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BEAR | STABLE_GROWTH_RESIDUAL_INCOME | 4841000000.0 | 16.06722939361935 | 10.670470138588223 | 2.0 | 7854182807.392685 | 7854182807.392684 | 9.5367431640625e-07 | 734000000.0 | 25150000000.0 | 33617000000.0 | 4.38059795635171 | 18.190497934784865 | 13.809899978433155 | 0.43339960238568587 | 1.1013916500994037 | False |
| BASE | STABLE_GROWTH_RESIDUAL_INCOME | 4841000000.0 | 16.214111909183693 | 9.670470138588223 | 2.0 | 8970834187.35831 | 8970834187.358309 | 1.9073486328125e-06 | 734000000.0 | 25150000000.0 | 33617000000.0 | 4.38059795635171 | 18.190497934784865 | 13.809899978433155 | 0.43339960238568587 | 1.1013916500994037 | False |
| BULL | STABLE_GROWTH_RESIDUAL_INCOME | 4841000000.0 | 16.392349449300927 | 8.670470138588223 | 2.0 | 10445045437.053988 | 10445045437.053986 | 1.9073486328125e-06 | 734000000.0 | 25150000000.0 | 33617000000.0 | 4.38059795635171 | 18.190497934784865 | 13.809899978433155 | 0.43339960238568587 | 1.1013916500994037 | False |

Financial Products is valued from disclosed book equity, normalized ROE and a
stable-growth residual-income model. Funding debt stays inside the finance
business economics and is not subtracted again from MP&E equity value.

## SOTP result

| ticker | valuation_status | mpe_enterprise_value_usd | less_mpe_debt_usd | add_mpe_cash_usd | mpe_equity_value_usd | financial_products_equity_value_usd | sotp_equity_value_usd | shares_outstanding | sotp_value_per_share | market_price | research_gap_pct | component_identity_error_usd | financial_products_funding_debt_double_counted | terminal_input_allowed | production_promoted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | RESEARCH_ONLY_NOT_A_MISPRICING_SIGNAL | 108366144076.30968 | 10990000000.0 | 9333000000.0 | 106709144076.30968 | 8970834187.35831 | 115679978263.66798 | 465287332.0 | 248.62051963982546 | 827.9000244140625 | -69.96974123587157 | -3.814697265625e-06 | False | False | False |

## Reverse DCF

| ticker | market_equity_value_usd | less_financial_products_equity_value_usd | add_mpe_debt_usd | less_mpe_cash_usd | market_target_mpe_enterprise_value_usd | reverse_dcf_status | market_implied_near_term_growth_pct | solver_residual_usd | search_lower_pct | search_upper_pct | boundary_reported_as_solution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | 385211393522.354 | 8970834187.35831 | 10990000000.0 | 9333000000.0 | 377897559334.99567 | UNBRACKETED_NO_SOLUTION_IN_DOMAIN |  | 234022556133.65402 | -10.0 | 15.0 | False |

## V1 comparison

| ticker | v1_consolidated_dcf_value_per_share | v1_reported_expectations_gap_pct | v1_gap_interpretation | v1_1_sotp_value_per_share | v1_1_minus_v1_value_per_share | v1_1_research_gap_pct | change_driver_1 | change_driver_2 | change_driver_3 | investment_conclusion_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT | 185.61854994263183 | -77.57959361409593 | RETIRED_NOT_INTERPRETABLE_AS_MISPRICING | 248.62051963982546 | 63.00196969719363 | -69.96974123587157 | RPO_RETIRED_DIRECT_FIRM_BACKLOG_DIAGNOSTIC | MPE_DEBT_ONLY_EV_TO_EQUITY_BRIDGE | FINANCIAL_PRODUCTS_RESIDUAL_INCOME_SOTP | False |

This is a research-only semantic/accounting audit. The displayed gap is not a
mispricing conclusion. Terminal replacement, model freeze, and production
promotion remain prohibited; production stays locked at 0/20.
