# V3.5.2 clean-component report

V3.5.2 preserves the corrected V3.5.1 labels, quarterly-guidance policy, unit traces,
and directional metric fix. Its only model change is disabling company basis adjustment.
No new feature or macro overlay is added.

## Corrected evaluation roles

- TIME holdout: primary research gate
- LOCO: cold-start diagnostic
- Live-forward: production promotion gate after 20 matched actuals

## Results

| validation | evaluable_company_count | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mean_candidate_mae_log_points | mase_below_1_count | mase_below_1_share | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | legacy_no_regression_count | legacy_no_regression_share | beats_legacy_pct | median_improvement_log_points | overall_revenue_wape_pct | overall_revenue_median_ape_pct | overall_revenue_mape_pct_diagnostic | small_denominator_observations | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TIME_HOLDOUT_8Q_PRIMARY | 13 | 13 | 99 | 0.7187 | 0.7157 | 33.3071 | 12 | 0.9231 | 7 | 4 | 92.3077 | 9 | 0.6923 | 69.2308 | 4.769 | 10.184 | 8.814 | 144.1784 | 1 | 0.8397 | 0.7083 |
| LOCO_TIME_SAFE_8Q_COLD_START | 13 | 13 | 99 | 0.7187 | 0.7157 | 33.3071 | 12 | 0.9231 | 7 | 4 | 92.3077 | 7 | 0.5385 | 53.8462 | 0.0159 | 10.184 | 8.814 | 144.1784 | 1 | 0.8494 | 0.7083 |

- TIME median / mean MASE: 0.719 / 0.716
- TIME MASE<1: 12/13 evaluable (92.3%)
- TIME legacy no-regression: 9/13 evaluable (69.2%)
- LOCO median / mean MASE: 0.719 / 0.716
- LOCO MASE<1: 12/13 evaluable (92.3%)

## Basis-removal effect on primary TIME holdout

| ticker | mase_v351_basis_on | candidate_mae_log_points_v351_basis_on | improvement_log_points_v351_basis_on | mase_v352_basis_off | candidate_mae_log_points_v352_basis_off | improvement_log_points_v352_basis_off | candidate_mae_change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AR | 2.0101 | 28.9666 | -20.8166 | 1.1236 | 16.1922 | -8.0422 | -12.7744 |
| CNX | 0.9221 | 113.2003 | -3.4362 | 0.975 | 119.6865 | -9.9225 | 6.4863 |
| COP | 0.5438 | 4.9369 | 8.2681 | 0.5436 | 4.9354 | 8.2695 | -0.0014 |
| DVN | 0.7289 | 29.2344 | -4.3651 | 0.4496 | 18.0325 | 6.8368 | -11.2019 |
| EOG | 2.4188 | 19.6291 | -7.7113 | 0.8809 | 7.1488 | 4.769 | -12.4803 |
| EQT | 0.7253 | 27.5905 | -6.6112 | 0.8223 | 31.2792 | -10.2999 | 3.6888 |
| FANG | 0.7793 | 23.538 | -3.1555 | 0.247 | 7.459 | 12.9235 | -16.079 |
| MGY | 2.3665 | 13.9601 | -0.7968 | 0.4675 | 2.758 | 10.4052 | -11.2021 |
| MTDR | 1.3109 | 19.4864 | -4.4904 | 0.6554 | 9.7415 | 5.2545 | -9.7449 |
| NOG | 0.9613 | 168.4866 | 15.6733 | 0.9968 | 174.6975 | 9.4624 | 6.2109 |
| OVV |  |  |  |  |  |  |  |
| PR | 1.109 | 22.797 | -2.23 | 0.8054 | 16.5568 | 4.0102 | -6.2402 |
| RRC | 1.9199 | 29.4665 | -22.2209 | 0.7187 | 11.0306 | -3.7849 | -18.4359 |
| SM | 0.6638 | 14.4747 | -0.226 | 0.618 | 13.4744 | 0.7743 | -1.0002 |

## Revenue-level diagnostics

MAPE remains available only as a diagnostic. WAPE and median APE are the reported
revenue-level metrics. Small denominators are flagged, not removed.

| ticker | quarter | revenue | rolling_median_revenue_8q | candidate_revenue | candidate_revenue_ape_pct |
| --- | --- | --- | --- | --- | --- |
| NOG | 2026Q1 | 5029000.0 | 581432000.0 | 607899557.4109882 | 11987.881435891593 |

## Promotion gate

| scope | condition | passed | detail | time_primary_gate | loco_cold_start_gate | research_component_gate | macro_overlay_enabled | champion_promotion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared | standardized_kpi_coverage | True | 12/14 registered | False | True | False | False | False |
| shared | minimum_8_time_forecasts | True | 12/14 registered | False | True | False | False | False |
| shared | minimum_8_loco_forecasts | True | 12/14 registered | False | True | False | False | False |
| time_primary | time_median_mase_below_0_80 | True | 0.7187039274588769 | False | True | False | False | False |
| time_primary | time_mean_mase_below_0_90 | True | 0.7156749875974432 | False | True | False | False | False |
| time_primary | time_mase_below_1_share_at_least_70pct | True | 12/13 evaluable = 92.3% | False | True | False | False | False |
| time_primary | time_median_improvement_positive | True | 4.768954522783285 | False | True | False | False | False |
| time_primary | time_legacy_no_regression_at_least_70pct | False | 9/13 evaluable = 69.2% | False | True | False | False | False |
| time_primary | time_no_severe_ticker_regression | False | 4/13 below -2.0 | False | True | False | False | False |
| time_primary | time_pi_80_coverage_between_75_85pct | True | 84.0% | False | True | False | False | False |
| loco_cold_start | loco_median_mase_at_most_0_80 | True | 0.7187039274588769 | False | True | False | False | False |
| loco_cold_start | loco_mean_mase_at_most_0_90 | True | 0.7156749875974432 | False | True | False | False | False |
| loco_cold_start | loco_mase_below_1_share_at_least_70pct | True | 12/13 evaluable = 92.3% | False | True | False | False | False |
| unlock | company_basis_overlay | False | Disabled by default; requires a separate ticker-level nested walk-forward promotion | False | True | False | False | False |
| unlock | macro_overlay_unlock | False | Requires both primary time and cold-start gates | False | True | False | False | False |
| production | live_20_match_model_change_lock | False | 0/20 matched | False | True | False | False | False |

## Decision

- Company basis overlay: **OFF**
- Macro residual overlay: **BLOCKED_CLEAN_COMPONENT_GATE**
- Research component gate: **FAIL**
- Champion promotion: **LOCKED**
- Champion: **V3.4 unchanged**