# V3.5.1 audit-only report

The V3.5 model equation was not changed. This run rebuilds SEC revenue labels from
Companyfacts durations, excludes non-quarterly guidance, preserves unit conversion traces,
and re-runs the same time/LOCO validation. Promotion and macro overlay are disabled.

## Confirmed bugs and controls

| check | status | affected_rows | checked_rows | detail |
| --- | --- | --- | --- | --- |
| silver_revenue_comparative_fact_alignment | BUG_CONFIRMED | 386 | 472 | 57.4% of all silver audit rows map to a different fact-end quarter |
| old_quarter_label_matches_prior_year | BUG_CONFIRMED | 223 | 673 | Old derived revenue equals corrected target-4 revenue |
| quarter_alignment_after_fix | PASS | 0 | 112 | target/revenue/guidance/price/prior-year alignment |
| nonquarterly_guidance_previously_eligible | BUG_FIXED | 95 | 177 | Annual, mixed, and unresolved guidance is now excluded |
| production_unit_traceability | PASS | 0 | 379 | Unresolved raw units remain visible and are not silently relabeled |
| directional_metric_numpy_bool_aggregation | BUG_FIXED | 26 | 26 | Object numpy.bool_ mean reported about 1/n; explicit boolean counting now used |
| company_basis_adjustment_stability | MODEL_WEAKNESS_CONFIRMED | 74 | 99 | Company basis increases absolute error by 7.003 log-points on average |

## Corrected validation

| validation | company_count | quarter_forecasts | median_ticker_mase | mean_ticker_mase | mase_below_1_count | mase_below_0_8_count | mase_below_0_6_count | beats_naive_pct | beats_legacy_pct | median_improvement_log_points | mean_pi_80_coverage | mean_directional_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TIME_HOLDOUT_8Q | 13 | 99 | 0.9613 | 1.2661 | 7 | 5 | 1 | 53.8462 | 15.3846 | -3.4362 | 0.8013 | 0.609 |
| LOCO_TIME_SAFE_8Q | 13 | 99 | 0.7187 | 0.7157 | 12 | 7 | 4 | 92.3077 | 53.8462 | 0.0159 | 0.8301 | 0.7083 |

## Before / after

- Old V3.5 LOCO median MASE: 1.243
- Corrected V3.5.1 time median MASE: 0.961
- Corrected V3.5.1 LOCO median MASE: 0.719
- Corrected LOCO directional hit rate across forecasts: 72.7%

## Ticker-level before / after

| ticker | mase_old_v35 | revenue_mape_pct_old_v35 | directional_hit_rate_old_v35 | mase_corrected_v351 | revenue_mape_pct_corrected_v351 | directional_hit_rate_corrected_v351 | mase_change | directional_hit_change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AR | 1.4567 | 111.5261 | 0.25 | 1.1236 | 16.7121 | 0.625 | -0.3331 | 0.375 |
| CNX | 1.1488 | 280.9264 | 0.375 | 0.975 | 153.1563 | 0.375 | -0.1738 | 0.0 |
| COP | 1.2434 | 57.8588 | 0.25 | 0.5436 | 5.0761 | 1.0 | -0.6997 | 0.75 |
| DVN | 1.1061 | 63.9015 | 0.5714 | 0.4496 | 12.0219 | 0.875 | -0.6565 | 0.3036 |
| EOG | 1.4826 | 31.4566 | 0.25 | 0.8809 | 7.066 | 0.625 | -0.6017 | 0.375 |
| EQT | 1.1964 | 95.2249 | 0.375 | 0.8223 | 27.8272 | 0.75 | -0.3741 | 0.375 |
| FANG | 0.992 | 54.6304 | 0.5 | 0.247 | 7.0885 | 0.875 | -0.745 | 0.375 |
| MGY | 1.2467 | 70.3888 | 0.125 | 0.4675 | 2.7828 | 0.875 | -0.7791 | 0.75 |
| MTDR | 1.6356 | 80.0001 | 0.25 | 0.6554 | 10.2316 | 0.625 | -0.9802 | 0.375 |
| NOG | 0.9548 | 48.2205 | 1.0 | 0.9968 | 4012.6978 | 0.3333 | 0.0419 | -0.6667 |
| OVV |  |  |  |  |  |  |  |  |
| PR | 0.9423 | 44.119 | 0.625 | 0.8054 | 14.5004 | 0.875 | -0.1368 | 0.25 |
| RRC | 1.3224 | 110.8269 | 0.125 | 0.7187 | 10.2751 | 0.625 | -0.6037 | 0.5 |
| SM | 1.8574 | 52.8879 | 0.0 | 0.618 | 12.7084 | 0.75 | -1.2394 | 0.75 |

LOCO is reported as a cold-start diagnostic. Time-safe holdout is the primary research
evaluation, while production promotion remains dependent on live-forward evidence.

## Promotion safety

| condition | passed | detail | research_component_gate | macro_overlay_enabled | champion_promotion | audit_only_promotion_disabled |
| --- | --- | --- | --- | --- | --- | --- |
| standardized_kpi_coverage | True | 12/14 ready | False | False | False | True |
| minimum_8_forecasts_per_ticker | True | 12/14 tickers | False | False | False | True |
| median_loco_mase_below_0_80 | True | 0.7187039274588769 | False | False | False | True |
| mean_loco_mase_below_0_90 | True | 0.7156749875974432 | False | False | False | True |
| mase_below_1_share_at_least_70pct | True | 78.6% | False | False | False | True |
| legacy_no_regression_at_least_70pct | False | 42.9% | False | False | False | True |
| median_candidate_improvement_positive | False | -0.011118632173189091 | False | False | False | True |
| pi_80_coverage_between_75_85pct | True | 83.0% | False | False | False | True |
| no_severe_ticker_regression | False | floor=-2.0 log-points | False | False | False | True |
| macro_overlay_unlock | False | Requires every KPI component research gate | False | False | False | True |
| live_20_match_model_change_lock | False | 0/20 matched | False | False | False | True |

- V3.5.1 status: **AUDIT_ONLY; NOT PROMOTABLE**
- Macro residual overlay: **BLOCKED**
- Champion: **V3.4 unchanged**

## Required audit artifacts

- `audit_revenue_quarters.csv`
- `audit_quarter_alignment.csv`
- `audit_production_units.csv`
- `audit_guidance_semantics.csv`
- `audit_direction_errors.csv`
- `audit_basis_adjustment.csv` (additional model-weakness diagnostic)