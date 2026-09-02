# Energy Valuation Platform V1.1 RC sanity audit

## Status

| status_dimension   | status                    | passed   |
|:-------------------|:--------------------------|:---------|
| V1_1_CODE          | COMPLETE                  | True     |
| V1_1_RESEARCH      | COMPLETE                  | True     |
| V1_1_PRODUCTION    | NOT_PROMOTED_LIVE_0_OF_20 | False    |

The immutable V1.0 manifest was verified before this run and remains unchanged.
V1.1 can be frozen only when every hard sanity invariant passes. Production
remains not promoted at 0/20 matched live-forward observations.

## Requirement audit

| requirement                                                    | passed   |
|:---------------------------------------------------------------|:---------|
| scenario_boundary_saturation_gate                              | True     |
| no_ticker_has_all_scenarios_on_same_boundary                   | True     |
| reverse_dcf_roundtrip_test_a_solved                            | True     |
| reverse_dcf_roundtrip_test_a_value                             | True     |
| reverse_dcf_roundtrip_test_a_assumption                        | True     |
| reverse_dcf_roundtrip_test_b_solved_values_reprice_market      | True     |
| unbracketed_reverse_dcf_is_explicit_not_fake_boundary_solution | True     |
| ev_to_common_equity_reconciliation                             | True     |
| market_price_times_shares_reconciliation                       | True     |
| forward_fcff_identity                                          | True     |
| growth_reinvestment_roic_consistency                           | True     |
| scenario_weights_are_labeled_defaults                          | True     |
| scenario_weights_sum_to_one                                    | True     |
| historical_and_forecast_roic_are_distinctly_labeled            | True     |
| terminal_dependence_is_computed_and_flagged                    | True     |
| expectations_gap_outliers_are_flagged                          | True     |
| fixed_ratio_reverse_calculation_absent                         | True     |
| production_live_gate_not_met                                   | True     |

## Boundary saturation: V1.0 parent

| subindustry   | variable          |   assumptions |   boundary_hits |   lower_hits |   upper_hits |   all_scenarios_same_boundary_tickers |   boundary_hit_pct | boundary_status       | freeze_eligible   |
|:--------------|:------------------|--------------:|----------------:|-------------:|-------------:|--------------------------------------:|-------------------:|:----------------------|:------------------|
| ep            | growth            |            42 |              29 |            8 |           21 |                                     1 |            69.0476 | RED_FREEZE_PROHIBITED | False             |
| ep            | operating_margin  |            42 |               9 |            4 |            5 |                                     0 |            21.4286 | YELLOW_INVESTIGATE    | True              |
| ep            | reinvestment_rate |            42 |              19 |           15 |            4 |                                     0 |            45.2381 | RED_FREEZE_PROHIBITED | False             |
| ep            | roic              |            42 |              11 |            8 |            3 |                                     0 |            26.1905 | RED_FREEZE_PROHIBITED | False             |
| ep            | terminal_growth   |            42 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| ep            | wacc              |            42 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| integrated    | growth            |             6 |               6 |            0 |            6 |                                     2 |           100      | RED_FREEZE_PROHIBITED | False             |
| integrated    | operating_margin  |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| integrated    | reinvestment_rate |             6 |               1 |            0 |            1 |                                     0 |            16.6667 | YELLOW_INVESTIGATE    | True              |
| integrated    | roic              |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| integrated    | terminal_growth   |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| integrated    | wacc              |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| midstream     | growth            |            12 |               8 |            1 |            7 |                                     1 |            66.6667 | RED_FREEZE_PROHIBITED | False             |
| midstream     | operating_margin  |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| midstream     | reinvestment_rate |            12 |               6 |            2 |            4 |                                     0 |            50      | RED_FREEZE_PROHIBITED | False             |
| midstream     | roic              |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| midstream     | terminal_growth   |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| midstream     | wacc              |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| refining      | growth            |             9 |               9 |            0 |            9 |                                     3 |           100      | RED_FREEZE_PROHIBITED | False             |
| refining      | operating_margin  |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| refining      | reinvestment_rate |             9 |               5 |            0 |            5 |                                     0 |            55.5556 | RED_FREEZE_PROHIBITED | False             |
| refining      | roic              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| refining      | terminal_growth   |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| refining      | wacc              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| services      | growth            |             9 |               1 |            0 |            1 |                                     0 |            11.1111 | YELLOW_INVESTIGATE    | True              |
| services      | operating_margin  |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| services      | reinvestment_rate |             9 |               2 |            2 |            0 |                                     0 |            22.2222 | YELLOW_INVESTIGATE    | True              |
| services      | roic              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| services      | terminal_growth   |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |
| services      | wacc              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN                 | True              |

## Boundary saturation: V1.1 candidate

| subindustry   | variable          |   assumptions |   boundary_hits |   lower_hits |   upper_hits |   all_scenarios_same_boundary_tickers |   boundary_hit_pct | boundary_status    | freeze_eligible   |
|:--------------|:------------------|--------------:|----------------:|-------------:|-------------:|--------------------------------------:|-------------------:|:-------------------|:------------------|
| ep            | growth            |            42 |               9 |            2 |            7 |                                     0 |            21.4286 | YELLOW_INVESTIGATE | True              |
| ep            | operating_margin  |            42 |               8 |            4 |            4 |                                     0 |            19.0476 | YELLOW_INVESTIGATE | True              |
| ep            | reinvestment_rate |            42 |               9 |            6 |            3 |                                     0 |            21.4286 | YELLOW_INVESTIGATE | True              |
| ep            | roic              |            42 |              10 |            7 |            3 |                                     0 |            23.8095 | YELLOW_INVESTIGATE | True              |
| ep            | terminal_growth   |            42 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| ep            | wacc              |            42 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| integrated    | growth            |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| integrated    | operating_margin  |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| integrated    | reinvestment_rate |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| integrated    | roic              |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| integrated    | terminal_growth   |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| integrated    | wacc              |             6 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| midstream     | growth            |            12 |               2 |            0 |            2 |                                     0 |            16.6667 | YELLOW_INVESTIGATE | True              |
| midstream     | operating_margin  |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| midstream     | reinvestment_rate |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| midstream     | roic              |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| midstream     | terminal_growth   |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| midstream     | wacc              |            12 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| refining      | growth            |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| refining      | operating_margin  |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| refining      | reinvestment_rate |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| refining      | roic              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| refining      | terminal_growth   |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| refining      | wacc              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| services      | growth            |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| services      | operating_margin  |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| services      | reinvestment_rate |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| services      | roic              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| services      | terminal_growth   |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |
| services      | wacc              |             9 |               0 |            0 |            0 |                                     0 |             0      | GREEN              | True              |

## Value-gap change

| subindustry   |   v1_0_median_value_gap_pct |   v1_1_median_value_gap_pct |   median_value_gap_change_pct_points |   absolute_skew_reduction_pct_points |
|:--------------|----------------------------:|----------------------------:|-------------------------------------:|-------------------------------------:|
| ep            |                    96.7375  |                   90.6671   |                             -6.07046 |                              6.07046 |
| integrated    |                     3.37535 |                   -7.10589  |                            -10.4812  |                             -3.73054 |
| midstream     |                   -25.5231  |                   -9.85567  |                             15.6674  |                             15.6674  |
| refining      |                    24.6606  |                   10.6945   |                            -13.9661  |                             13.9661  |
| services      |                    -2.12133 |                   -0.850066 |                              1.27126 |                              1.27126 |

## Financial bridge change

| subindustry   |   v1_0_median_operating_margin_pct |   v1_0_median_fcff_margin_pct |   v1_0_median_roic_pct |   v1_1_median_operating_margin_pct |   v1_1_median_fcff_margin_pct |   v1_1_median_roic_pct |   fcff_margin_change_pct_points |
|:--------------|-----------------------------------:|------------------------------:|-----------------------:|-----------------------------------:|------------------------------:|-----------------------:|--------------------------------:|
| ep            |                           24.5032  |                      31.8617  |               10.1544  |                           24.5032  |                      31.8617  |               10.1544  |                               0 |
| integrated    |                           10.7032  |                       6.86003 |                8.31339 |                           10.7032  |                       6.86003 |                8.31339 |                               0 |
| midstream     |                           21.5072  |                      12.9529  |                7.87722 |                           21.5072  |                      12.9529  |                7.87722 |                               0 |
| refining      |                            4.65668 |                       4.01293 |               13.3159  |                            4.65668 |                       4.01293 |               13.3159  |                               0 |
| services      |                           13.1083  |                       8.91011 |               12.7502  |                           13.1083  |                       8.91011 |               12.7502  |                               0 |

## Reverse DCF round-trip

| test                        | subindustry   | variable         |   tickers |   solved_tickers |   unbracketed_tickers |   solved_median_abs_assumption_error |   solved_maximum_abs_assumption_error |   solved_median_abs_forward_roundtrip_error_pct |   solved_maximum_abs_forward_roundtrip_error_pct |
|:----------------------------|:--------------|:-----------------|----------:|-----------------:|----------------------:|-------------------------------------:|--------------------------------------:|------------------------------------------------:|-------------------------------------------------:|
| A_FORWARD_BASE_TO_REVERSE   | ep            | growth           |        14 |               14 |                     0 |                          4.18674e-11 |                           4.45691e-10 |                                     5.25471e-11 |                                      8.37303e-11 |
| A_FORWARD_BASE_TO_REVERSE   | ep            | operating_margin |        14 |               14 |                     0 |                          1.112e-11   |                           3.07523e-11 |                                     3.34524e-11 |                                      9.53807e-11 |
| A_FORWARD_BASE_TO_REVERSE   | ep            | roic             |        14 |               14 |                     0 |                          1.50626e-11 |                           1.7258e-10  |                                     3.23736e-11 |                                      9.56764e-11 |
| A_FORWARD_BASE_TO_REVERSE   | integrated    | growth           |         2 |                2 |                     0 |                          6.15643e-11 |                           6.83169e-11 |                                     8.19281e-11 |                                      8.48481e-11 |
| A_FORWARD_BASE_TO_REVERSE   | integrated    | operating_margin |         2 |                2 |                     0 |                          3.90266e-12 |                           7.18714e-12 |                                     2.73693e-11 |                                      5.02928e-11 |
| A_FORWARD_BASE_TO_REVERSE   | integrated    | roic             |         2 |                2 |                     0 |                          3.77787e-11 |                           4.04228e-11 |                                     5.97852e-11 |                                      6.50403e-11 |
| A_FORWARD_BASE_TO_REVERSE   | midstream     | growth           |         4 |                4 |                     0 |                          9.37495e-11 |                           1.32221e-10 |                                     2.43101e-11 |                                      7.78993e-11 |
| A_FORWARD_BASE_TO_REVERSE   | midstream     | operating_margin |         4 |                4 |                     0 |                          9.22995e-12 |                           1.34328e-11 |                                     4.43597e-11 |                                      5.09957e-11 |
| A_FORWARD_BASE_TO_REVERSE   | midstream     | roic             |         4 |                4 |                     0 |                          3.5536e-12  |                           9.72022e-12 |                                     2.81725e-11 |                                      6.35657e-11 |
| A_FORWARD_BASE_TO_REVERSE   | refining      | growth           |         3 |                3 |                     0 |                          2.29203e-11 |                           5.56538e-11 |                                     2.64319e-11 |                                      8.3766e-11  |
| A_FORWARD_BASE_TO_REVERSE   | refining      | operating_margin |         3 |                3 |                     0 |                          1.41132e-12 |                           5.50937e-12 |                                     2.92674e-11 |                                      9.09306e-11 |
| A_FORWARD_BASE_TO_REVERSE   | refining      | roic             |         3 |                3 |                     0 |                          5.24576e-11 |                           6.74323e-11 |                                     7.82692e-11 |                                      7.95e-11    |
| A_FORWARD_BASE_TO_REVERSE   | services      | growth           |         3 |                3 |                     0 |                          2.36664e-11 |                           8.06359e-11 |                                     3.155e-11   |                                      8.11595e-11 |
| A_FORWARD_BASE_TO_REVERSE   | services      | operating_margin |         3 |                3 |                     0 |                          9.16778e-12 |                           1.00435e-11 |                                     6.89582e-11 |                                      9.65497e-11 |
| A_FORWARD_BASE_TO_REVERSE   | services      | roic             |         3 |                3 |                     0 |                          2.86455e-11 |                           5.37046e-11 |                                     7.72967e-11 |                                      8.78748e-11 |
| B_MARKET_REVERSE_TO_FORWARD | ep            | growth           |        14 |               10 |                     4 |                        nan           |                         nan           |                                     3.10795e-11 |                                      6.85984e-11 |
| B_MARKET_REVERSE_TO_FORWARD | ep            | operating_margin |        14 |               14 |                     0 |                        nan           |                         nan           |                                     5.38671e-11 |                                      8.8215e-11  |
| B_MARKET_REVERSE_TO_FORWARD | ep            | roic             |        14 |               12 |                     2 |                        nan           |                         nan           |                                     7.40108e-12 |                                      9.24251e-11 |
| B_MARKET_REVERSE_TO_FORWARD | integrated    | growth           |         2 |                2 |                     0 |                        nan           |                         nan           |                                     3.87028e-11 |                                      4.24195e-11 |
| B_MARKET_REVERSE_TO_FORWARD | integrated    | operating_margin |         2 |                2 |                     0 |                        nan           |                         nan           |                                     5.56559e-11 |                                      7.59867e-11 |
| B_MARKET_REVERSE_TO_FORWARD | integrated    | roic             |         2 |                0 |                     2 |                        nan           |                         nan           |                                   nan           |                                    nan           |
| B_MARKET_REVERSE_TO_FORWARD | midstream     | growth           |         4 |                2 |                     2 |                        nan           |                         nan           |                                     7.31935e-11 |                                      7.3315e-11  |
| B_MARKET_REVERSE_TO_FORWARD | midstream     | operating_margin |         4 |                3 |                     1 |                        nan           |                         nan           |                                     7.04496e-12 |                                      5.90329e-11 |
| B_MARKET_REVERSE_TO_FORWARD | midstream     | roic             |         4 |                2 |                     2 |                        nan           |                         nan           |                                     3.88501e-11 |                                      3.94422e-11 |
| B_MARKET_REVERSE_TO_FORWARD | refining      | growth           |         3 |                3 |                     0 |                        nan           |                         nan           |                                     2.73028e-11 |                                      2.88507e-11 |
| B_MARKET_REVERSE_TO_FORWARD | refining      | operating_margin |         3 |                3 |                     0 |                        nan           |                         nan           |                                     1.36445e-11 |                                      5.36796e-11 |
| B_MARKET_REVERSE_TO_FORWARD | refining      | roic             |         3 |                1 |                     2 |                        nan           |                         nan           |                                     9.98676e-11 |                                      9.98676e-11 |
| B_MARKET_REVERSE_TO_FORWARD | services      | growth           |         3 |                2 |                     1 |                        nan           |                         nan           |                                     2.45277e-11 |                                      4.07288e-11 |
| B_MARKET_REVERSE_TO_FORWARD | services      | operating_margin |         3 |                3 |                     0 |                        nan           |                         nan           |                                     2.86702e-11 |                                      5.37043e-11 |
| B_MARKET_REVERSE_TO_FORWARD | services      | roic             |         3 |                2 |                     1 |                        nan           |                         nan           |                                     6.63141e-11 |                                      7.06218e-11 |

## Terminal-value dependence

| subindustry   | scenario   |   tickers |   median_terminal_value_share_pct |   high_terminal_dependence_tickers |   unstable_terminal_value_tickers |
|:--------------|:-----------|----------:|----------------------------------:|-----------------------------------:|----------------------------------:|
| ep            | BASE       |        14 |                           84.0712 |                                  8 |                                 1 |
| ep            | BEAR       |        14 |                           71.1049 |                                  2 |                                 7 |
| ep            | BULL       |        14 |                           90.0343 |                                 14 |                                 0 |
| integrated    | BASE       |         2 |                           81.211  |                                  2 |                                 0 |
| integrated    | BEAR       |         2 |                           72.7812 |                                  0 |                                 0 |
| integrated    | BULL       |         2 |                           90.0286 |                                  2 |                                 0 |
| midstream     | BASE       |         4 |                           87.3762 |                                  4 |                                 0 |
| midstream     | BEAR       |         4 |                           76.886  |                                  0 |                                 0 |
| midstream     | BULL       |         4 |                           95.0468 |                                  4 |                                 0 |
| refining      | BASE       |         3 |                           79.7821 |                                  0 |                                 0 |
| refining      | BEAR       |         3 |                           69.6886 |                                  0 |                                 0 |
| refining      | BULL       |         3 |                           89.4622 |                                  3 |                                 0 |
| services      | BASE       |         3 |                           80.7744 |                                  3 |                                 0 |
| services      | BEAR       |         3 |                           73.2603 |                                  0 |                                 0 |
| services      | BULL       |         3 |                           87.5404 |                                  3 |                                 0 |

## Historical FCFF sanity by subindustry

| subindustry   |   tickers |   median_operating_margin_pct |   median_fcff_margin_pct |   median_fcff_less_operating_margin_pct_points |   median_cash_conversion_adjustment_usd |   median_cash_capex_usd |   fcff_margin_above_operating_margin_tickers |
|:--------------|----------:|------------------------------:|-------------------------:|-----------------------------------------------:|----------------------------------------:|------------------------:|---------------------------------------------:|
| ep            |        14 |                      24.5032  |                 31.8617  |                                        9.51391 |                             2.34867e+09 |             8.99016e+08 |                                            8 |
| integrated    |         2 |                      10.7032  |                  6.86003 |                                       -3.84313 |                             2.04091e+10 |             2.2984e+10  |                                            0 |
| midstream     |         4 |                      21.5072  |                 12.9529  |                                       -3.77255 |                             3.76316e+09 |             4.6655e+09  |                                            0 |
| refining      |         3 |                       4.65668 |                  4.01293 |                                       -1.61663 |                             2.35013e+09 |             1.67051e+09 |                                            0 |
| services      |         3 |                      13.1083  |                  8.91011 |                                       -2.49847 |                             1.05759e+09 |             1.309e+09   |                                            1 |

## Expectations-gap skew

| subindustry   |   tickers |   median_probability_weighted_value_gap_pct |   outlier_tickers | systematic_sector_skew_flag   | systematic_skew_status          |
|:--------------|----------:|--------------------------------------------:|------------------:|:------------------------------|:--------------------------------|
| ep            |        14 |                                   90.6671   |                 8 | True                          | SYSTEMATIC_SKEW_REQUIRES_REVIEW |
| integrated    |         2 |                                   -7.10589  |                 0 | False                         | WITHIN_REVIEW_RANGE             |
| midstream     |         4 |                                   -9.85567  |                 2 | False                         | WITHIN_REVIEW_RANGE             |
| refining      |         3 |                                   10.6945   |                 0 | False                         | WITHIN_REVIEW_RANGE             |
| services      |         3 |                                   -0.850066 |                 0 | False                         | WITHIN_REVIEW_RANGE             |

## Accounting and solver corrections

- Net `PaymentsForProceedsFromOtherInvestingActivities` is rejected as gross
  cash CapEx and replaced only by a prior-only subindustry distribution.
- Debt concepts that already represent total long-term debt are not added to
  current debt a second time. If a current taxonomy gap reports zero debt while
  an older point-in-time debt fact exists, the last disclosed balance is carried
  forward and its fallback method is exposed in the reconciliation artifact.
- NCI and preferred claims are included in the EV-to-common-equity bridge when
  standardized facts exist. Lease liabilities are disclosed but not added a
  second time without a matching lease-expense adjustment.
- Reverse DCF returns an explicit unbracketed status instead of presenting the
  nearest search boundary as a market-implied assumption.
- Reinvestment is not clipped inside DCF projections, preserving the forward
  growth/reinvestment/normalized-ROIC identity.
- 60/20/20 values are labelled default scenario weights, not empirical
  probabilities. Possible/Plausible/Probable remains a story-validation class.

## Interpretation boundary

Historical incremental ROIC is a backward-looking change ratio. Forecast
normalized ROIC is a separate forward bridge assumption; they are not the same
metric. Terminal dependence and expectations-gap outliers are flags, not
investment recommendations.
