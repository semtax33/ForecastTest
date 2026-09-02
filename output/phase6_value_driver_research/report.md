# Phase 6 — Subindustry Driver Forecast → Financial Bridge → Valuation

## Decision

- Revenue routes are frozen by `D:\Programming\python_example\ForecastTest\benchmarks\phase5_revenue_research\manifest.json` and verified before and after this run.
- Production remains V3.4; live changes remain 0/20.
- Integrated consolidated-revenue improvement is stopped. Segment earnings are the primary anchor.
- No bridge uses a fixed margin or fixed ratio. Every available bridge uses PIT trailing distributions and reports scenarios plus anchor/bridge error attribution.

## Target hierarchy

| subindustry   | primary_anchor                              | secondary_targets                        | validation_targets    | bridge                                                  | architecture                 | fixed_ratio_reverse_calculation_allowed   | scenario_bridge_required   | production_eligible   |
|:--------------|:--------------------------------------------|:-----------------------------------------|:----------------------|:--------------------------------------------------------|:-----------------------------|:------------------------------------------|:---------------------------|:----------------------|
| E&P           | PRODUCTION_PLUS_REALIZED_PRICE              | GAAP_REVENUE;OPERATING_MARGIN;CASH_CAPEX | FCFF;ROIC             | VOLUME_X_REALIZED_PRICE_THEN_COST_AND_REINVESTMENT      | ANCHOR_TO_CONDITIONAL_BRIDGE | False                                     | True                       | False                 |
| Refining      | THROUGHPUT_PLUS_REFINING_MARGIN             | GAAP_REVENUE;EBITDA                      | OPERATING_INCOME;FCFF | THROUGHPUT_X_PRODUCT_PRICE_AND_CAPTURE_MARGIN           | ANCHOR_TO_CONDITIONAL_BRIDGE | False                                     | True                       | False                 |
| Midstream     | VOLUME_PLUS_FEE_PLUS_ADJUSTED_EBITDA        | GAAP_REVENUE                             | FCF                   | ADJUSTED_EBITDA_WITH_PIT_MARGIN_REGIME_SCENARIOS        | ANCHOR_TO_CONDITIONAL_BRIDGE | False                                     | True                       | False                 |
| Services      | ACTIVITY_PLUS_PRICING_PLUS_OPERATING_MARGIN | GAAP_REVENUE;EBIT                        | FCFF                  | ACTIVITY_X_PRICING_THEN_UTILIZATION_AND_MARGIN          | ANCHOR_TO_CONDITIONAL_BRIDGE | False                                     | True                       | False                 |
| Integrated    | SEGMENT_EARNINGS                            | CONSOLIDATED_EARNINGS;EBIT               | FCF                   | SUM_SEGMENT_EARNINGS_PLUS_CORPORATE_UNMODELED_SCENARIOS | ANCHOR_TO_CONDITIONAL_BRIDGE | False                                     | True                       | False                 |

## Forecast performance

Margin targets use percentage-point MAE as the interpretable level metric. WAPE on signed margins is retained in detailed diagnostics only.

| subindustry   | forecast_target                          | scope                                    | selected_research_route         |   entities |   forecasts |   median_time_mase |   mean_time_mase | level_error_metric   |   level_error_value | gate_status         | production_eligible   |
|:--------------|:-----------------------------------------|:-----------------------------------------|:--------------------------------|-----------:|------------:|-------------------:|-----------------:|:---------------------|--------------------:|:--------------------|:----------------------|
| midstream     | ADJUSTED_EBITDA_NON_GAAP                 | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | LAG_ADJUSTED_EBITDA_BASELINE    |          4 |          32 |           0.585682 |         0.563311 | WAPE_PCT             |         4.75417     | FROZEN_NOT_RETESTED | False                 |
| ep_gas_heavy  | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | V3.5.3_GROUPED_LEGACY           |          4 |          32 |           0.558538 |         0.620831 | WAPE_PCT             |        22.1354      | FROZEN_NOT_RETESTED | True                  |
| ep_mixed      | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | V3.5.3_GROUPED_CLEAN_COMPONENT  |          3 |          24 |           0.54363  |         0.53707  | WAPE_PCT             |         6.20146     | FROZEN_NOT_RETESTED | True                  |
| ep_oil_heavy  | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | V3.5.3_GROUPED_CLEAN_COMPONENT  |          6 |          43 |           0.730385 |         0.675493 | WAPE_PCT             |         8.83672     | FROZEN_NOT_RETESTED | True                  |
| integrated    | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | STRUCTURAL_PROXY_RECALIBRATED   |          2 |          16 |           1.05062  |         1.05062  | WAPE_PCT             |         5.38245     | FROZEN_NOT_RETESTED | True                  |
| midstream     | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | STRUCTURAL_PROXY_RECALIBRATED   |          4 |          32 |           0.747271 |         0.689638 | WAPE_PCT             |         8.32243     | FROZEN_NOT_RETESTED | True                  |
| refining      | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | P2.1_REFINING_COMPANY_KPI       |          3 |          24 |           0.531001 |         0.586341 | WAPE_PCT             |         4.30112     | FROZEN_NOT_RETESTED | True                  |
| services      | GAAP_REVENUE                             | FROZEN_REVENUE_OR_EBITDA_BENCHMARK       | STRUCTURAL_PROXY_RECALIBRATED   |          3 |          24 |           0.694937 |         0.746228 | WAPE_PCT             |         3.03742     | FROZEN_NOT_RETESTED | True                  |
| Integrated    | SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT | UPSTREAM                                 | PRIOR_YEAR_ZERO_CHANGE_BASELINE |          2 |          16 |           3.62207  |         3.62207  | MAE_TARGET_UNITS     |         6.65146     | FAIL                | False                 |
| Integrated    | SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT | DOWNSTREAM                               | RIDGE_ECONOMIC_DRIVER_CANDIDATE |          2 |          16 |           0.779838 |         0.779838 | MAE_TARGET_UNITS     |         1.37838     | PASS                | False                 |
| Integrated    | SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT | CHEMICALS                                | PRIOR_YEAR_ZERO_CHANGE_BASELINE |          1 |           8 |           1        |         1        | MAE_TARGET_UNITS     |         0.390776    | FAIL                | False                 |
| E&P           | CONSOLIDATED_OPERATING_MARGIN_PCT        | 10_OF_14_STANDARDIZED_GAAP_TAG_COVERAGE  | PRIOR_YEAR_ZERO_CHANGE_BASELINE |         10 |          80 |           1.34144  |         1.66481  | MAE_TARGET_UNITS     |       183.242       | FAIL                | False                 |
| Refining      | CONSOLIDATED_OPERATING_MARGIN_PCT        | 2_OF_3_STANDARDIZED_GAAP_TAG_COVERAGE    | PRIOR_YEAR_ZERO_CHANGE_BASELINE |          2 |          16 |           0.726888 |         0.726888 | MAE_TARGET_UNITS     |         3.05798     | FAIL                | False                 |
| Services      | CONSOLIDATED_OPERATING_MARGIN_PCT        | 3_OF_3_STANDARDIZED_GAAP_TAG_COVERAGE    | PRIOR_YEAR_ZERO_CHANGE_BASELINE |          3 |          24 |           3.22732  |         3.60152  | MAE_TARGET_UNITS     |        11.2164      | FAIL                | False                 |
| E&P           | CASH_CAPEX                               | 13_OF_14_TICKERS_HETEROGENEOUS_GAAP_TAGS | PRIOR_YEAR_ZERO_CHANGE_BASELINE |         13 |          99 |           1.3245   |         2.19912  | MAE_TARGET_UNITS     |         1.85559e+08 | FAIL                | False                 |

## Integrated segment decisions

| subindustry   | forecast_target                          | scope      | candidate_route                 | selected_research_route         |   median_time_mase |   mean_time_mase |   mean_target_level_mae |   entities |   forecasts | research_gate   | production_eligible   |
|:--------------|:-----------------------------------------|:-----------|:--------------------------------|:--------------------------------|-------------------:|-----------------:|------------------------:|-----------:|------------:|:----------------|:----------------------|
| Integrated    | SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT | UPSTREAM   | RIDGE_ECONOMIC_DRIVER_CANDIDATE | PRIOR_YEAR_ZERO_CHANGE_BASELINE |           3.62207  |         3.62207  |                6.65146  |          2 |          16 | False           | False                 |
| Integrated    | SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT | DOWNSTREAM | RIDGE_ECONOMIC_DRIVER_CANDIDATE | RIDGE_ECONOMIC_DRIVER_CANDIDATE |           0.779838 |         0.779838 |                1.37838  |          2 |          16 | True            | False                 |
| Integrated    | SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT | CHEMICALS  | RIDGE_ECONOMIC_DRIVER_CANDIDATE | PRIOR_YEAR_ZERO_CHANGE_BASELINE |           1        |         1        |                0.390776 |          1 |           8 | False           | False                 |

The parser gold audit covers 20 rows with 100.0% all-dimension accuracy. Only `downstream` passes the strict TIME gate. Failed segments use the prior-year zero-change baseline and are not promoted to production.

## Conditional bridge performance

| bridge                                                |   forecasts |   available_forecasts |   mean_absolute_anchor_error_pct_points |   mean_absolute_bridge_error_pct_points |   mean_absolute_total_error_pct_points |   scenario_coverage |   fixed_ratio_used | production_eligible   |   evaluable_forecasts |   aggregate_revenue_wape_pct |   median_revenue_ape_pct |   fixed_margin_used |
|:------------------------------------------------------|------------:|----------------------:|----------------------------------------:|----------------------------------------:|---------------------------------------:|--------------------:|-------------------:|:----------------------|----------------------:|-----------------------------:|-------------------------:|--------------------:|
| INTEGRATED_SEGMENTS_TO_CONSOLIDATED_NET_INCOME_MARGIN |          16 |                    16 |                                 1.65473 |                                0.480334 |                                2.02709 |            0        |                  0 | False                 |                   nan |                     nan      |                nan       |                 nan |
| MIDSTREAM_ADJUSTED_EBITDA_TO_REVENUE_RANGE            |          32 |                    32 |                               nan       |                              nan        |                              nan       |            0.535714 |                nan | False                 |                    28 |                      12.0176 |                  6.33863 |                   0 |

Integrated segment disclosures are GAAP segment earnings, not EBIT. The current bridge therefore targets consolidated net-income margin. EBIT/FCFF remains locked until corporate/unmodeled, tax, D&A, working-capital, and CapEx semantics are standardized.

## Analyst consensus

Arcana Alpha Vantage and FMP revenue estimates are normalized with release-date cutoffs. Finnworlds is inventoried but excluded from revenue consensus because the available local dataset contains ratings only.

| status                  |   observations |   model_mape_pct |   consensus_mape_pct |   model_win_rate |   surprise_direction_accuracy | statistical_test_status   |
|:------------------------|---------------:|-----------------:|---------------------:|-----------------:|------------------------------:|:--------------------------|
| NO_MATCHED_OBSERVATIONS |              0 |              nan |                  nan |              nan |                           nan | NEEDS_20_OBSERVATIONS     |

Current forward model-versus-consensus spreads remain in `current_model_vs_consensus.csv`; a historical performance claim stays locked until at least 20 matched PIT observations exist.
