# E&P V1.4 standardized cost-scope research

V1.4 is a research-only child of the frozen V1.3 benchmark. It verifies V1.0,
V1.1, V1.2, and V1.3 before and after execution and does not recalibrate any
frozen WACC, terminal assumption, scenario, parser, or valuation result.

## Standardized tag coverage

| concept              |   tickers_with_any_standardized_year |   tickers_with_at_least_3_years |   total_standardized_years |
|:---------------------|-------------------------------------:|--------------------------------:|---------------------------:|
| g_and_a_usd          |                                   14 |                              14 |                         70 |
| hedge_gain_loss_usd  |                                   12 |                              12 |                         57 |
| production_tax_usd   |                                    6 |                               4 |                         23 |
| transport_cost_usd   |                                    3 |                               3 |                         13 |
| upstream_revenue_usd |                                    6 |                               5 |                         26 |

The annual panel uses original 10-K annual facts with filing-lag and duration
checks. Transport and production tax require their exact standardized tags.
G&A may use a disclosed consolidated allocation route, and every selected tag
and scope remains in the annual audit panel. Missing cost components stay null;
they are never silently set to zero.

## Expanded core cross-check

| ticker   | v14_cost_scope_status                            |   median_realized_revenue_basis_per_boe |   median_transport_cost_per_boe |   median_production_tax_per_boe |   median_g_and_a_per_boe |   median_reported_hedge_gain_loss_per_boe |   median_abs_reported_hedge_gain_loss_per_boe |   basis_hedge_correlation | hedge_inclusion_diagnostic                                  |   basis_iqr_pct_of_adjusted_price | basis_dispersion_status                     |   v13_historical_margin_q50_pct |   v13_core_accounting_margin_q50_pct |   v14_known_cost_accounting_margin_q50_pct |   v14_margin_gap_vs_v13_historical_q50_pct_points |   absolute_margin_gap_improvement_vs_v13_core_pct_points |   v13_core_roic_proxy_q50_pct |   v14_known_cost_roic_proxy_q50_pct |   roic_proxy_reduction_vs_v13_pct_points | roic_cross_check_status                              |
|:---------|:-------------------------------------------------|----------------------------------------:|--------------------------------:|--------------------------------:|-------------------------:|------------------------------------------:|----------------------------------------------:|--------------------------:|:------------------------------------------------------------|----------------------------------:|:--------------------------------------------|--------------------------------:|-------------------------------------:|-------------------------------------------:|--------------------------------------------------:|---------------------------------------------------------:|------------------------------:|------------------------------------:|-----------------------------------------:|:-----------------------------------------------------|
| AR       | UPPER_BOUND_MISSING_TRANSPORT_AND_PRODUCTION_TAX |                                -1.33409 |                       nan       |                      nan        |                 1.08785  |                                0.00350322 |                                      0.805893 |                 -0.420591 | NO_MECHANICAL_NETTING_REVENUE_INCLUSION_NOT_PROVEN          |                           2.76989 | LOWER_DISPERSION_LE_25PCT_OF_ADJUSTED_PRICE |                         17.5925 |                              16.4893 |                                    5.68306 |                                         -11.9094  |                                                 -10.8063 |                       93.4041 |                             30.2136 |                                  63.1905 | UPPER_BOUND_BELOW_100PCT_STILL_INCOMPLETE            |
| CNX      | COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK     |                                -4.73234 |                         3.82297 |                        0.300149 |                 1.33843  |                               -1.87803    |                                     16.597    |                  0.99928  | STRONG_EXACT_HEDGE_ASSOCIATION_REVENUE_INCLUSION_NOT_PROVEN |                         115.033   | HIGH_DISPERSION_GT_25PCT_OF_ADJUSTED_PRICE  |                         15.5352 |                              68.8606 |                                   20.3531  |                                           4.81794 |                                                  48.5075 |                      384.468  |                             85.3772 |                                 299.091  | BELOW_100PCT_AFTER_COMPLETE_COST_SCOPE_NOT_VALIDATED |
| FANG     | UPPER_BOUND_MISSING_TRANSPORT                    |                                -6.63833 |                       nan       |                        3.04465  |                 0.939286 |                               -0.481485   |                                      1.29815  |                 -0.983435 | NO_MECHANICAL_NETTING_REVENUE_INCLUSION_NOT_PROVEN          |                           9.21292 | LOWER_DISPERSION_LE_25PCT_OF_ADJUSTED_PRICE |                         41.8646 |                              46.1681 |                                   25.2318  |                                         -16.6327  |                                                 -12.3292 |                      258.662  |                            119.405  |                                 139.257  | ABOVE_100PCT_OR_UNAVAILABLE_REQUIRES_MORE_COST_SCOPE |

`Realized revenue basis` means exact upstream revenue per BOE minus the
production-mix benchmark basket. It is not claimed to be a pure price
differential because upstream revenue can contain mix, timing, and other
presentation effects. Reported hedge gains/losses are quantified separately.
The long-run hedge normalization is zero, but it is not mechanically netted
against revenue without evidence that the selected revenue fact includes it.
The basis/hedge correlation is an association diagnostic only. A 25%-of-price
IQR flag makes unstable basis histories visible but does not fit or alter any
valuation assumption.

Only CNX currently has at least three usable years for transport, production
tax, G&A, and exact-upstream-revenue basis. AR and FANG are explicitly labelled
known-cost upper bounds. A lower ROIC proxy is therefore a diagnostic, not a
validated terminal input.

## Gate

|   ep_tickers |   standardized_complete_cost_scope_tickers |   v13_core_cross_check_tickers |   v14_complete_core_cross_check_tickers |   v14_roic_below_100pct_core_tickers |   v14_complete_core_roic_below_100pct_tickers |   high_basis_dispersion_core_tickers |   terminal_anchor_ready_tickers | terminal_anchor_replacement_allowed   | v1_1_mutation_allowed   | wacc_range_recalibrated   |   risk_channel_duplicate_count | production_eligible   | live_matched_observations   |
|-------------:|-------------------------------------------:|-------------------------------:|----------------------------------------:|-------------------------------------:|----------------------------------------------:|-------------------------------------:|--------------------------------:|:--------------------------------------|:------------------------|:--------------------------|-------------------------------:|:----------------------|:----------------------------|
|           14 |                                          1 |                              3 |                                       1 |                                    2 |                                             1 |                                    1 |                               0 | False                                 | False                   | False                     |                              0 | False                 | 0/20                        |

- Complete standardized cost scope: 1/14.
- Complete V1.3-core cross-check: 1/3.
- High basis dispersion among core cross-checks: 1/3.
- Terminal anchor replacement: locked at 0/14.
- Independent V1.3 WACC range: retained unchanged; no point estimate selected.
- Risk channels: no new duplicate allocation; Hormuz remains a cash-flow overlay.
- Production: locked at 0/20 matched live observations.

These outputs are research diagnostics and not investment recommendations.
