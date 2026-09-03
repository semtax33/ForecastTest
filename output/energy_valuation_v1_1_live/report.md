# Energy Valuation V1.1 live-forward monitoring

The V1.1 benchmark was verified before and after this append-only run.
Benchmark manifest SHA-256: `25d4a4d28d89f7e8565ea6b681d9492eb9ffec4c095ee998a0043157e7081fee`. No frozen assumption, bridge,
parser, WACC, scenario bound, terminal growth, or weight was changed.

## Live gate

|   matched_observations |   fcff_mape_pct |   fair_value_to_settlement_price_mape_pct |   median_initial_value_gap_pct |   ep_matched_observations | model_change_lock   |   observations_needed | production_status                     |
|-----------------------:|----------------:|------------------------------------------:|-------------------------------:|--------------------------:|:--------------------|----------------------:|:--------------------------------------|
|                      0 |             nan |                                       nan |                            nan |                         0 | LOCKED              |                    20 | NOT_PROMOTED_REQUIRES_SEPARATE_REVIEW |

Snapshots: {'inserted': 26, 'unchanged': 0}. FCFF attributions: {'inserted': 26, 'unchanged': 0}.
Consensus vintages: {'inserted': 0, 'unchanged': 3158, 'coverage_inserted': 0}. Production remains separately locked.

## Frozen research hypotheses

| hypothesis                             | scope      | status                                     | metric                                        |    value | secondary_metric         | secondary_value   |
|:---------------------------------------|:-----------|:-------------------------------------------|:----------------------------------------------|---------:|:-------------------------|:------------------|
| E&P_SYSTEMATIC_SKEW                    | ep         | MONITOR_DO_NOT_RETUNE                      | median_probability_weighted_value_gap_pct     | 90.6671  | outliers_over_total      | 8/14              |
| HIGH_TERMINAL_DEPENDENCE               | ep         | MONITOR_LONG_RUN_ECONOMICS                 | median_base_terminal_value_share_pct          | 84.0712  | high_or_unstable_tickers | 9                 |
| HIGH_TERMINAL_DEPENDENCE               | integrated | MONITOR_LONG_RUN_ECONOMICS                 | median_base_terminal_value_share_pct          | 81.211   | high_or_unstable_tickers | 2                 |
| HIGH_TERMINAL_DEPENDENCE               | midstream  | MONITOR_LONG_RUN_ECONOMICS                 | median_base_terminal_value_share_pct          | 87.3762  | high_or_unstable_tickers | 4                 |
| HIGH_TERMINAL_DEPENDENCE               | refining   | MONITOR_LONG_RUN_ECONOMICS                 | median_base_terminal_value_share_pct          | 79.7821  | high_or_unstable_tickers | 0                 |
| HIGH_TERMINAL_DEPENDENCE               | services   | MONITOR_LONG_RUN_ECONOMICS                 | median_base_terminal_value_share_pct          | 80.7744  | high_or_unstable_tickers | 3                 |
| E&P_FCFF_MARGIN_ABOVE_OPERATING_MARGIN | ep         | MONITOR_CASH_CONVERSION_AND_CAPEX_FALLBACK | median_fcff_minus_operating_margin_pct_points |  9.51391 | tickers_above_over_total | 8/14              |

E&P skew remains `MONITOR_DO_NOT_RETUNE` at 90.67% with
8/14 outliers. This is evidence to collect, not a reason to
change V1.1.

## FCFF attribution

`NOPAT + D&A - Cash CapEx - Delta operating NWC + Other cash conversion = FCFF`.
`Other cash conversion` is reported explicitly so missing/non-working-capital
cash-flow items are never mislabeled as Delta NWC. 5 ticker rows use
the fail-closed combined CFO bridge because standardized D&A or NWC components
are unavailable. All rows remain diagnostics and cannot feed back into V1.1.

This monitoring output is not an investment recommendation.
