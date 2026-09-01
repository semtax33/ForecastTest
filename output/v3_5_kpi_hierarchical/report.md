# V3.5 KPI hierarchical research report

V3.4 remains the frozen production champion. V3.5 is a locked research candidate built
from company operational KPIs; the rejected revenue-implied-volume shortcut is not used.

## Fixed design

- Common structural engine: production volume × oil/NGL/gas price
- Explicit 14-company adapter registry with fixed source policies
- Fixed oil-heavy / gas-heavy / mixed taxonomy with company-to-group partial pooling
- Point-in-time cutoff: day 61 of each target quarter
- LOCO excludes the held company's revenue-derived basis labels
- No revenue-implied production fallback
- Eight-quarter time holdout and time-safe LOCO

## KPI source coverage

Ready companies (at least 12 actual quarters): **12/14**.

| ticker | group | actual_quarters | guidance_quarters | realized_price_quarters | first_actual_quarter | last_actual_quarter | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EOG | oil_heavy | 18 | 15 | 0 | 2022Q1 | 2026Q2 | READY |
| FANG | oil_heavy | 26 | 35 | 0 | 2019Q4 | 2026Q2 | READY |
| PR | oil_heavy | 40 | 27 | 21 | 2016Q3 | 2026Q2 | READY |
| MTDR | oil_heavy | 43 | 22 | 1 | 2015Q4 | 2026Q2 | READY |
| MGY | oil_heavy | 32 | 0 | 2 | 2018Q1 | 2026Q2 | READY |
| NOG | oil_heavy | 8 | 10 | 23 | 2024Q3 | 2026Q2 | INSUFFICIENT_KPI_HISTORY |
| EQT | gas_heavy | 43 | 1 | 43 | 2015Q4 | 2026Q2 | READY |
| AR | gas_heavy | 43 | 14 | 4 | 2015Q4 | 2026Q2 | READY |
| RRC | gas_heavy | 43 | 0 | 0 | 2015Q4 | 2026Q2 | READY |
| CNX | gas_heavy | 42 | 22 | 24 | 2015Q4 | 2026Q2 | READY |
| COP | mixed | 12 | 20 | 0 | 2022Q4 | 2026Q2 | READY |
| DVN | mixed | 17 | 10 | 0 | 2017Q4 | 2026Q2 | READY |
| OVV | mixed | 0 | 0 | 0 |  |  | INSUFFICIENT_KPI_HISTORY |
| SM | mixed | 12 | 1 | 0 | 2019Q3 | 2026Q2 | READY |

## Validation summary

| validation | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mase_below_1_count | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | beats_legacy_pct | median_improvement_log_points | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TIME_HOLDOUT_8Q | 13 | 92 | 1.18 | 1.0893 | 5 | 4 | 0 | 38.4615 | 76.9231 | 10.9685 | 0.875 | 0.1552 |
| LOCO_TIME_SAFE_8Q | 13 | 92 | 1.2434 | 1.2758 | 3 | 0 | 0 | 23.0769 | 30.7692 | -8.1145 | 0.8846 | 0.1424 |

## LOCO ticker scorecard

| ticker | observations | mase | revenue_mape_pct | legacy_mae_log_points | candidate_mae_log_points | improvement_log_points | pi_80_coverage | directional_hit_rate | company_gate_pass | promoted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AR | 8 | 1.4567 | 111.5261 | 74.727 | 82.8415 | -8.1145 | 0.75 | 0.125 | False | False |
| CNX | 8 | 1.1488 | 280.9264 | 102.9659 | 114.1217 | -11.1558 | 0.625 | 0.125 | False | False |
| COP | 4 | 1.2434 | 57.8588 | 49.4903 | 44.1141 | 5.3763 | 1.0 | 0.25 | False | False |
| DVN | 7 | 1.1061 | 63.9015 | 35.7652 | 49.8679 | -14.1026 | 1.0 | 0.1429 | False | False |
| EOG | 8 | 1.4826 | 31.4566 | 43.2463 | 36.8476 | 6.3987 | 1.0 | 0.125 | True | False |
| EQT | 8 | 1.1964 | 95.2249 | 65.697 | 72.3821 | -6.6851 | 0.75 | 0.125 | False | False |
| FANG | 8 | 0.992 | 54.6304 | 54.3224 | 50.4303 | 3.8921 | 1.0 | 0.125 | True | False |
| MGY | 8 | 1.2467 | 70.3888 | 60.887 | 57.4198 | 3.4672 | 0.875 | 0.125 | True | False |
| MTDR | 8 | 1.6356 | 80.0001 | 60.3086 | 76.9101 | -16.6015 | 0.625 | 0.125 | False | False |
| NOG | 3 | 0.9548 | 48.2205 | 37.9159 | 67.7277 | -29.8118 | 1.0 | 0.3333 | False | False |
| OVV | 0 |  |  |  |  |  |  |  | False | False |
| PR | 8 | 0.9423 | 44.119 | 43.6982 | 55.6007 | -11.9026 | 1.0 | 0.125 | False | False |
| RRC | 8 | 1.3224 | 110.8269 | 81.4739 | 83.5664 | -2.0925 | 0.875 | 0.125 | False | False |
| SM | 6 | 1.8574 | 52.8879 | 36.133 | 56.1404 | -20.0074 | 1.0 | 0.0 | False | False |

## Fixed promotion gate

| condition | passed | detail | research_component_gate | macro_overlay_enabled | champion_promotion |
| --- | --- | --- | --- | --- | --- |
| standardized_kpi_coverage | True | 12/14 ready | False | False | False |
| minimum_8_forecasts_per_ticker | False | 9/14 tickers | False | False | False |
| median_loco_mase_below_0_80 | False | 1.2433734445430225 | False | False | False |
| mean_loco_mase_below_0_90 | False | 1.2757821608220274 | False | False | False |
| mase_below_1_share_at_least_70pct | False | 14.3% | False | False | False |
| legacy_no_regression_at_least_70pct | False | 21.4% | False | False | False |
| median_candidate_improvement_positive | False | -6.685142196513723 | False | False | False |
| pi_80_coverage_between_75_85pct | False | 88.5% | False | False | False |
| no_severe_ticker_regression | False | floor=-2.0 log-points | False | False | False |
| macro_overlay_unlock | False | Requires every KPI component research gate | False | False | False |
| live_20_match_model_change_lock | False | 0/20 matched | False | False | False |

## Decision

- LOCO median / mean MASE: 1.243 / 1.276
- Beats naive / legacy: 23.1% / 30.8%
- 80% PI coverage: 88.5%
- Macro residual overlay: **BLOCKED_KPI_COMPONENT_GATE**
- Live model-change lock: **0/20 matched actuals**
- Champion: **V3.4 (unchanged)**

OVV has no local operational KPI source and NOG has only eight parsed actual quarters.
Neither is filled with a revenue-derived proxy; the limitation remains visible in the gate.