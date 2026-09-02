# Energy Valuation Platform V1 — Research Freeze Candidate

## Completion status

| status_dimension   | status                    | passed   |
|:-------------------|:--------------------------|:---------|
| V1_CODE            | COMPLETE                  | True     |
| V1_RESEARCH        | COMPLETE                  | True     |
| V1_PRODUCTION      | NOT_PROMOTED_LIVE_0_OF_20 | False    |

Development and research V1 are complete. Production remains explicitly not promoted because live-forward coverage is 0/20.

## End-to-end architecture

Every Energy subindustry now runs through:

`Economic Anchor → Revenue/EBIT → NOPAT → Reinvestment → FCFF → Invested Capital/ROIC → Forward DCF → Reverse DCF → Expectations Gap`

No fixed-margin reverse calculation is used. Missing source taxonomy is bridged only with prior-only trailing distributions and is separately labelled.

## Requirement audit

| requirement                                                 | passed   |
|:------------------------------------------------------------|:---------|
| all_26_tickers_have_latest_ttm_financials                   | True     |
| all_5_subindustries_covered                                 | True     |
| all_tickers_have_standardized_or_conditional_source_history | True     |
| historical_fcff_identity_holds                              | True     |
| all_market_inputs_complete                                  | True     |
| all_market_prices_within_freshness_limit                    | True     |
| three_scenarios_per_ticker                                  | True     |
| scenario_probabilities_sum_to_one                           | True     |
| scenario_guardrails_pass                                    | True     |
| minimum_distribution_history_pass                           | True     |
| five_year_projection_complete                               | True     |
| forward_dcf_complete                                        | True     |
| reverse_dcf_complete                                        | True     |
| fixed_ratio_reverse_calculation_absent                      | True     |
| production_live_gate_not_met                                | True     |

## Subindustry valuation results

| subindustry   |   tickers |   median_operating_margin_pct |   median_fcff_margin_pct |   median_roic_pct |   median_incremental_roic_pct |   median_probability_weighted_value_gap_pct |   median_growth_expectations_gap_pct_points |   median_margin_expectations_gap_pct_points |   median_roic_expectations_gap_pct_points |
|:--------------|----------:|------------------------------:|-------------------------:|------------------:|------------------------------:|--------------------------------------------:|--------------------------------------------:|--------------------------------------------:|------------------------------------------:|
| ep            |        14 |                      24.5032  |                 31.8617  |          10.1544  |                      -5.69273 |                                    96.7375  |                                    25.5241  |                                    11.1402  |                                 11.1984   |
| integrated    |         2 |                      10.7032  |                  6.86003 |           8.31339 |                     -48.2169  |                                     3.37535 |                                    -5.95    |                                    -1.31984 |                                 -5.84911  |
| midstream     |         4 |                      21.5072  |                 12.9529  |           7.87722 |                      -9.66313 |                                   -25.5231  |                                   -11.2444  |                                   -10.5376  |                                 -9.73461  |
| refining      |         3 |                       4.65668 |                  4.01293 |          13.3159  |                      64.711   |                                    24.6606  |                                    -1.7     |                                    -0.07908 |                                 -0.779923 |
| services      |         3 |                      13.1083  |                  8.91011 |          12.7502  |                      64.4761  |                                    -2.12133 |                                    -5.96545 |                                    -1.49321 |                                -25.1096   |

## Scenario engine

Bear/Base/Bull assumptions separately carry growth, operating margin, reinvestment, ROIC, WACC, terminal growth, probability, and Possible/Plausible/Probable validation. Probabilities sum to one for every ticker.

| subindustry   | scenario   |   tickers |   median_growth_pct |   median_operating_margin_pct |   median_reinvestment_rate_pct |   median_roic_pct |   median_wacc_pct |   median_terminal_growth_pct |   probability |
|:--------------|:-----------|----------:|--------------------:|------------------------------:|-------------------------------:|------------------:|------------------:|-----------------------------:|--------------:|
| ep            | BASE       |        14 |            15.97    |                      32.7602  |                       81.5715  |          15.6984  |           6.56559 |                          2   |           0.6 |
| ep            | BEAR       |        14 |           -12.477   |                       3.52853 |                      -50       |           3.33672 |           8.06559 |                          1   |           0.2 |
| ep            | BULL       |        14 |            20       |                      42.7104  |                       85.0355  |          23.5542  |           5.56559 |                          2.5 |           0.2 |
| integrated    | BASE       |         2 |            15       |                      14.0802  |                      116.652   |          12.9509  |           6.72663 |                          2   |           0.6 |
| integrated    | BEAR       |         2 |            15       |                      11.494   |                      145.363   |           9.50758 |           8.22663 |                          1   |           0.2 |
| integrated    | BULL       |         2 |            15       |                      18.1625  |                       71.6529  |          20.9375  |           5.72663 |                          2.5 |           0.2 |
| midstream     | BASE       |         4 |            11.7556  |                      20.45    |                      124.88    |           7.39309 |           6.13514 |                          2   |           0.6 |
| midstream     | BEAR       |         4 |            -1.30136 |                      16.9571  |                      -20.564   |           6.34406 |           7.63514 |                          1   |           0.2 |
| midstream     | BULL       |         4 |            12       |                      22.2962  |                      144.473   |           8.23829 |           5.13514 |                          2.5 |           0.2 |
| refining      | BASE       |         3 |            20       |                       4.72092 |                      150       |          12.4469  |           6.71736 |                          2   |           0.6 |
| refining      | BEAR       |         3 |            20       |                       2.30862 |                      150       |           5.51172 |           8.21736 |                          1   |           0.2 |
| refining      | BULL       |         3 |            20       |                       8.332   |                       81.6714  |          24.4884  |           5.71736 |                          2.5 |           0.2 |
| services      | BASE       |         3 |             1.43455 |                      13.3272  |                        9.38209 |          15.055   |           6.9586  |                          2   |           0.6 |
| services      | BEAR       |         3 |            -7.88226 |                      10.9898  |                      -50       |          11.3995  |           8.4586  |                          1   |           0.2 |
| services      | BULL       |         3 |            13.0549  |                      17.189   |                       93.3896  |          17.9602  |           5.9586  |                          2.5 |           0.2 |

## Interpretation boundary

This is a research-complete valuation engine, not a production investment-decision engine. Fair values and reverse-DCF gaps are scenario outputs, not recommendations. Production promotion remains gated on 20 matched live-forward observations.
