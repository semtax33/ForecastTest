# E&P universe scorecard

This is a 14-company cross-company diagnostic, not a replacement for the frozen V3.4 champion.
The common candidate uses SEC quarterly revenue plus a lagged implied volume/basis proxy derived
from revenue and the fixed WTI/Henry/propane basket. It does not claim to parse each company's
production actuals or guidance. All forecasts use the same features, alpha, and gate rules.

## Universe summary

### TIME_HOLDOUT

- Companies: 14
- Quarter forecasts: 56
- Median / mean ticker MASE: 1.354 / 1.363
- MASE < 1.0 / 0.8 / 0.6: 2 / 2 / 1
- Beats naive / common legacy: 14.3% / 85.7%
- Mean 80% PI coverage: 82.1%

### LOCO_TIME_SAFE

- Companies: 14
- Quarter forecasts: 56
- Median / mean ticker MASE: 1.367 / 1.246
- MASE < 1.0 / 0.8 / 0.6: 3 / 2 / 2
- Beats naive / common legacy: 21.4% / 14.3%
- Mean 80% PI coverage: 83.9%

## LOCO ticker scorecard

| ticker | observations | mase | revenue_mape_pct | legacy_mae_log_points | candidate_mae_log_points | improvement_log_points | pi_80_coverage | directional_hit_rate | company_gate_pass | promoted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AR | 4 | 1.517 | 112.291 | 65.09 | 65.901 | -0.811 | 0.75 | 0.25 | False | False |
| CNX | 4 | 0.902 | 59.056 | 50.433 | 53.562 | -3.129 | 1.0 | 0.75 | False | False |
| COP | 4 | 1.504 | 56.96 | 41.787 | 42.879 | -1.092 | 0.75 | 0.25 | False | False |
| DVN | 4 | 1.461 | 57.905 | 42.305 | 43.25 | -0.944 | 0.75 | 0.25 | False | False |
| EOG | 4 | 1.835 | 24.338 | 22.301 | 20.877 | 1.424 | 1.0 | 0.5 | True | False |
| EQT | 4 | 1.112 | 38.018 | 26.807 | 29.787 | -2.98 | 1.0 | 0.75 | False | False |
| FANG | 4 | 1.12 | 90.76 | 59.789 | 60.557 | -0.768 | 0.5 | 0.5 | False | False |
| MGY | 4 | 1.319 | 87.283 | 49.649 | 50.484 | -0.835 | 0.75 | 0.5 | False | False |
| MTDR | 4 | 1.193 | 105.956 | 58.034 | 58.807 | -0.773 | 0.75 | 0.5 | False | False |
| NOG | 4 | 0.544 | 24.47 | 29.187 | 31.147 | -1.961 | 1.0 | 1.0 | False | False |
| OVV | 4 | 1.646 | 43.908 | 34.185 | 35.446 | -1.261 | 1.0 | 0.25 | False | False |
| PR | 4 | 0.355 | 14.353 | 16.382 | 15.656 | 0.726 | 1.0 | 1.0 | True | False |
| RRC | 4 | 1.524 | 113.677 | 65.257 | 66.263 | -1.006 | 0.75 | 0.0 | False | False |
| SM | 4 | 1.415 | 84.775 | 57.768 | 58.677 | -0.909 | 0.75 | 0.5 | False | False |

## Promotion gate

| condition | passed | detail | universe_promotion |
| --- | --- | --- | --- |
| company_no_regression | False | all LOCO companies | False |
| median_universe_improvement | False | time=2.786; loco=-0.927 | False |
| at_least_70pct_no_regression | False | time=85.7%; loco=14.3% | False |
| untouched_company_holdout | False | LOCO median improvement=-0.927 | False |
| live_forward_not_worse | False | PENDING | False |
