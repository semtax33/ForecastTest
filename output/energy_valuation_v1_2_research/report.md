# E&P V1.2 expectations-surface research

This research layer does not alter frozen V1.1. The immutable V1.0 and V1.1
manifests were verified before and after execution. Maximum V1.1 fair-value
reproduction error was `2.842e-14` per share.

## Research boundary

- No single market-implied margin, growth, ROIC, or WACC is reported.
- Every solved row is one point on a non-unique iso-value curve.
- Unbracketed combinations remain explicit; no domain edge is presented as a solution.
- Through-cycle distributions use company history with an eight-observation peer prior.
- Hormuz/AIS is deferred to a later regime overlay and is not a long-run anchor.
- All outputs are `V1.2_RESEARCH_ONLY`; production remains V1.1 live 0/20 locked.

## Through-cycle evidence quality

| normalization_confidence         |   tickers |
|:---------------------------------|----------:|
| HIGH_PRE_RECENT_WINDOW           |         2 |
| LOW_LIMITED_COMPANY_HISTORY      |         3 |
| MEDIUM_HIERARCHICAL_FULL_HISTORY |         9 |

## Terminal margin × WACC sector median gap matrix

|   terminal_margin_pct |   wacc_6.5_pct |   wacc_7.5_pct |   wacc_8.5_pct |   wacc_9.5_pct |   wacc_10.5_pct |
|----------------------:|---------------:|---------------:|---------------:|---------------:|----------------:|
|                    12 |      -17.0833  |      -32.6509  |      -43.6455  |      -54.7984  |        -64.0267 |
|                    17 |        4.73473 |      -16.9452  |      -30.1781  |      -39.5061  |        -50.143  |
|                    22 |       28.5136  |       -1.23945 |      -17.68    |      -29.2583  |        -37.8955 |
|                    27 |       52.2925  |       16.7844  |       -5.18196 |      -19.0105  |        -29.3108 |
|                    32 |       76.0714  |       34.8527  |        8.2937  |       -8.76279 |        -20.7262 |
|                    37 |       99.8503  |       52.9209  |       22.6637  |        1.48496 |        -12.1415 |

## Iso-value curve coverage

| surface                   |   curve_points |   solved_points |   unbracketed_points |   tickers |   solved_value_q25_pct |   solved_value_median_pct |   solved_value_q75_pct |
|:--------------------------|---------------:|----------------:|---------------------:|----------:|-----------------------:|--------------------------:|-----------------------:|
| GROWTH_X_NORMALIZED_ROIC  |             98 |              54 |                   44 |        14 |                3.41143 |                   4.39335 |                6.89789 |
| GROWTH_X_OPERATING_MARGIN |             98 |              98 |                    0 |        14 |               14.3815  |                  18.9963  |               23.8548  |
| TERMINAL_MARGIN_X_WACC    |            210 |             210 |                    0 |        14 |                6.79786 |                   8.10702 |                9.71728 |

## Conditional market-equivalent WACC

| through_cycle_margin_reference   |   tickers |   solved_tickers |   unbracketed_tickers |   terminal_margin_median_pct |   conditional_wacc_q25_pct |   conditional_wacc_median_pct |   conditional_wacc_q75_pct |
|:---------------------------------|----------:|-----------------:|----------------------:|-----------------------------:|---------------------------:|------------------------------:|---------------------------:|
| Q25                              |        14 |               10 |                     4 |                      11.6491 |                    5.12313 |                       6.26139 |                    8.35481 |
| Q50                              |        14 |               13 |                     1 |                      28.3725 |                    7.13783 |                       7.91722 |                   10.2499  |
| Q75                              |        14 |               14 |                     0 |                      36.272  |                    8.43177 |                       9.40874 |                   11.5884  |

At the hierarchical Q50 through-cycle terminal-margin reference, the median
conditional market-equivalent WACC among solved tickers is
`7.92%`. This is a conditional
combination, not an independently estimated appropriate discount rate.

## Interpretation

The surface makes non-identification visible: lower terminal margins can pair
with lower WACC, while higher margins require higher WACC to explain the same
price. Growth/margin and growth/ROIC curves preserve the same many-solutions
property. These results are evidence for designing independent through-cycle
margin, ROIC, and risk-premium research; they are not instructions to calibrate
V1.1 to current market prices and are not investment recommendations.
