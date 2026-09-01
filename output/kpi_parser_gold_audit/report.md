# KPI parser manual-gold audit

A stratified 75-row sample was transcribed from official SEC earnings
exhibits across early, middle, and recent periods. Numeric, unit,
quarter/period, and semantic matches are evaluated independently.

`HIGH` source quality means a directly transcribed, period-unambiguous
disclosure row; `LOW` means period-context selection, component
aggregation, or unit normalization was required.

## Gold sampling strata

| subindustry   | sample_era   | source_quality_stratum   |   gold_rows |
|:--------------|:-------------|:-------------------------|------------:|
| integrated    | EARLY        | HIGH                     |           1 |
| integrated    | MID          | HIGH                     |           2 |
| integrated    | MID          | LOW                      |           3 |
| integrated    | RECENT       | HIGH                     |           5 |
| integrated    | RECENT       | LOW                      |           7 |
| midstream     | EARLY        | HIGH                     |           5 |
| midstream     | EARLY        | LOW                      |           4 |
| midstream     | MID          | HIGH                     |           4 |
| midstream     | MID          | LOW                      |           5 |
| midstream     | RECENT       | HIGH                     |           4 |
| midstream     | RECENT       | LOW                      |           5 |
| refining      | EARLY        | HIGH                     |           2 |
| refining      | EARLY        | LOW                      |           3 |
| refining      | MID          | HIGH                     |           2 |
| refining      | MID          | LOW                      |           3 |
| refining      | RECENT       | HIGH                     |           2 |
| refining      | RECENT       | LOW                      |           3 |
| services      | EARLY        | LOW                      |           3 |
| services      | MID          | LOW                      |           5 |
| services      | RECENT       | LOW                      |           7 |

## Overall parser accuracy

|   gold_rows |   pre_numeric_accuracy |   post_numeric_accuracy |   pre_unit_accuracy |   post_unit_accuracy |   pre_period_accuracy |   post_period_accuracy |   pre_semantic_accuracy |   post_semantic_accuracy |   pre_all_dimension_accuracy |   post_all_dimension_accuracy | parser_quality_gate   |
|------------:|-----------------------:|------------------------:|--------------------:|---------------------:|----------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------:|------------------------------:|:----------------------|
|          75 |                 0.8667 |                       1 |              0.9467 |                    1 |                0.9333 |                      1 |                    0.92 |                        1 |                       0.8267 |                             1 | True                  |

## Accuracy by subindustry

| subindustry   |   gold_rows |   pre_numeric_accuracy |   post_numeric_accuracy |   pre_unit_accuracy |   post_unit_accuracy |   pre_period_accuracy |   post_period_accuracy |   pre_semantic_accuracy |   post_semantic_accuracy |   pre_all_dimension_accuracy |   post_all_dimension_accuracy | parser_quality_gate   |
|:--------------|------------:|-----------------------:|------------------------:|--------------------:|---------------------:|----------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------:|------------------------------:|:----------------------|
| integrated    |          18 |                 1      |                       1 |              1      |                    1 |                1      |                      1 |                  1      |                        1 |                       1      |                             1 | True                  |
| midstream     |          27 |                 0.9259 |                       1 |              0.8889 |                    1 |                1      |                      1 |                  0.9259 |                        1 |                       0.8148 |                             1 | True                  |
| refining      |          15 |                 0.8    |                       1 |              1      |                    1 |                1      |                      1 |                  0.8    |                        1 |                       0.8    |                             1 | True                  |
| services      |          15 |                 0.6667 |                       1 |              0.9333 |                    1 |                0.6667 |                      1 |                  0.9333 |                        1 |                       0.6667 |                             1 | True                  |

## Parser corrections

| subindustry   | change_reason                              |   changed_rows |
|:--------------|:-------------------------------------------|---------------:|
| midstream     | HISTORICAL_LABEL_VARIANT_MISSING_COMPONENT |             21 |
| midstream     | UNIT_LABEL_CORRECTION                      |             34 |
| refining      | DUPLICATE_AND_REGION_AGGREGATION           |             34 |
| services      | PERIOD_OR_TABLE_CONTEXT_SELECTION          |             51 |

## Parser value versus manual-gold replacement backtest

| subindustry   |   pre_parser_median_mase |   gold_sample_replacement_median_mase |   post_parser_median_mase |   pre_parser_mean_mase |   gold_sample_replacement_mean_mase |   post_parser_mean_mase |   pre_parser_wape_pct |   gold_sample_replacement_wape_pct |   post_parser_wape_pct |   post_vs_pre_median_mase_change |
|:--------------|-------------------------:|--------------------------------------:|--------------------------:|-----------------------:|------------------------------------:|------------------------:|----------------------:|-----------------------------------:|-----------------------:|---------------------------------:|
| integrated    |                   1.2229 |                                1.2229 |                    1.2229 |                 1.2229 |                              1.2229 |                  1.2229 |                6.513  |                             6.513  |                 6.513  |                           0      |
| refining      |                   0.532  |                                0.5271 |                    0.531  |                 0.5877 |                              0.5813 |                  0.5863 |                4.3101 |                             4.2777 |                 4.3011 |                          -0.001  |
| midstream     |                   0.8038 |                                0.8038 |                    0.8038 |                 0.6992 |                              0.6992 |                  0.6992 |                8.5827 |                             8.5827 |                 8.5827 |                           0      |
| services      |                   0.7358 |                                0.7214 |                    0.7015 |                 0.7917 |                              0.7785 |                  0.7665 |                3.1835 |                             3.1428 |                 3.1032 |                          -0.0343 |

The gold-sample replacement column changes only the 75 manually
reviewed rows in the frozen pre-audit snapshot. The post-parser column
applies the corrected rule to every matching historical filing.

## Rule confidence versus forecast error

| subindustry   | quality_bucket   |   observations |   kpi_used_share |   mean_rule_confidence |   mean_kpi_age_days |   mean_absolute_forecast_error_log_points |   median_absolute_forecast_error_log_points |   mean_revenue_ape_pct |     revenue |   candidate_revenue |   aggregate_revenue_error_pct |
|:--------------|:-----------------|---------------:|-----------------:|-----------------------:|--------------------:|------------------------------------------:|--------------------------------------------:|-----------------------:|------------:|--------------------:|------------------------------:|
| integrated    | 0_85_TO_0_90     |              8 |                1 |                 0.8708 |             31.125  |                                    7.3227 |                                      4.7084 |                 7.4993 | 3.91714e+11 |         4.05066e+11 |                        3.4087 |
| integrated    | 0_90_TO_0_95     |              8 |                1 |                 0.9    |             31.125  |                                    5.8782 |                                      4.9582 |                 5.9544 | 6.83878e+11 |         6.98453e+11 |                        2.1312 |
| midstream     | 0_85_TO_0_90     |             16 |                1 |                 0.8583 |             23.9375 |                                    7.6592 |                                      6.1815 |                 7.5378 | 1.97061e+11 |         1.9355e+11  |                        1.7819 |
| midstream     | 0_90_TO_0_95     |             16 |                1 |                 0.9    |             37.625  |                                    5.9426 |                                      2.3332 |                 6.2074 | 1.41464e+11 |         1.4765e+11  |                        4.3726 |
| refining      | 0_85_TO_0_90     |              8 |                1 |                 0.875  |             27.125  |                                    5.1747 |                                      4.982  |                 5.0138 | 2.73057e+11 |         2.6218e+11  |                        3.9835 |
| refining      | 0_90_TO_0_95     |             15 |                1 |                 0.9    |             35.1333 |                                    4.0746 |                                      3.2151 |                 3.9588 | 4.95018e+11 |         4.77392e+11 |                        3.5606 |
| refining      | FALLBACK         |              1 |                0 |               nan      |            nan      |                                    4.2373 |                                      4.2373 |                 4.3283 | 3.043e+10   |         3.17471e+10 |                        4.3283 |
| services      | 0_95_PLUS        |             24 |                1 |                 0.95   |             39.625  |                                    2.9998 |                                      3.0268 |                 2.9925 | 1.72468e+11 |         1.71818e+11 |                        0.3767 |

Parser quality is a mandatory gate for company-KPI research selection.
It does not replace the point-model, uncertainty, or live-forward gates.