# Industrials V1.6 — Segment cost perimeter and timing closure

## Three independent gates

| gate | eligible | failed_conditions | independent_of_terminal_and_production | status |
| --- | --- | --- | --- | --- |
| RESEARCH_FREEZE_ELIGIBLE | False | VALIDATED_MARGIN_ROUTE_COUNT\|WORST_MARGIN_MASE | True | HOLD_RESEARCH_UNFROZEN |
| TERMINAL_EVIDENCE_ELIGIBLE | False | RESEARCH_FREEZE\|REINVESTMENT_N_GE_3\|BACKLOG_OOS_N_GE_3 | False | TERMINAL_LOCKED |
| PRODUCTION_PROMOTABLE | False | RESEARCH_FREEZE\|LIVE_FORWARD_20_OF_20 | False | PRODUCTION_LOCKED |

Research freeze, terminal evidence, and production promotion are intentionally
separate. Production 0/20 and backlog 2/3 do not directly fail the research
freeze gate. The forecast branch nevertheless remains `HOLD_RESEARCH_UNFROZEN`
on its own margin evidence.

## V1.5 PIT data benchmark

The V1.5 PIT data infrastructure is immutable and independently verified across
81 files. The V1.5 forecast model is not frozen.

## Cost perimeter identity

| segment | validation_observations | identity_mismatches | maximum_identity_error_usd | material_recast_rows | mean_absolute_recast_scope_pct | mean_comparable_economic_cost_growth_pct | mean_reported_cost_growth_pct | reported_minus_comparable_growth_pct | comparable_cost_identity_proven | homogeneous_reported_scope | forecast_target |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | 0 | 0.0 | 0 | 0.0 | 14.474794712815187 | 14.474794712815187 | 0.0 | True | True | COMPARABLE_ECONOMIC_COST_GROWTH |
| power_energy | 6 | 0 | 0.0 | 2 | 4.455361751940778 | 13.648718258539027 | 8.339776756826057 | -5.30894150171297 | True | False | COMPARABLE_ECONOMIC_COST_GROWTH |
| resource | 6 | 0 | 0.0 | 2 | 10.769804495312563 | 8.934742679828352 | 21.38135524138764 | 12.446612561559292 | True | False | COMPARABLE_ECONOMIC_COST_GROWTH |

Reported segment cost is separated exactly into prior-scope recast and
comparable economic cost movement. Unexpected recasts are flagged and are never
forecast as though they were ordinary operating inflation.

## Recognition-lag validation

| segment | validation_observations | champion_cost_route | champion_route_selection_share_pct | comparable_economic_cost_mae_pct | naive_lagged_comparable_cost_mae_pct | comparable_cost_mase | reported_cost_mae_pct | v1_5_reported_cost_mae_pct | reported_cost_mae_change_vs_v1_5_pct | material_recast_rows | historical_pit_input_pct | unexpected_recast_forecasted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | LAGGED_ACTUAL_COMPARABLE_COST | 50.0 | 11.318098220266192 | 9.908795047894698 | 1.1422275024924373 | 11.318098220266187 | 14.665125831366419 | -22.823040522035352 | 0 | 100.0 | False |
| power_energy | 6 | LAGGED_ACTUAL_COMPARABLE_COST | 100.0 | 6.4395373915945795 | 6.4395373915945795 | 1.0 | 11.185904986148275 | 10.548138158351483 | 6.046250231296413 | 2 | 100.0 | False |
| resource | 6 | LAGGED_ACTUAL_COMPARABLE_COST | 66.66666666666666 | 8.115240159080486 | 6.907596201715177 | 1.1748283950161196 | 18.312049882264553 | 19.402620316404963 | -5.620737902180817 | 2 | 100.0 | False |

Only lags 0-3 and one Construction load/mix route were compared. Each route was
selected using training-only inner validation on the unchanged six-quarter OOS
window.

## Revenue champion evidence

| segment | validation_observations | revenue_level_mae_usd | naive_prior_year_revenue_mae_usd | revenue_level_mase | maximum_revenue_mase | revenue_wape_pct | naive_revenue_wape_pct | revenue_direction_accuracy_pct | minimum_direction_accuracy_pct | no_material_regression | target_level_scaled_metric_pass | revenue_champion_eligible | historical_pit_input |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | 737381481.6794591 | 1200666666.6666667 | 0.6141433773010486 | 1.0 | 10.906127862737582 | 17.75827643158232 | 66.66666666666666 | 50.0 | True | True | True | True |
| power_energy | 6 | 696168062.1530129 | 739666666.6666666 | 0.9411916117435957 | 1.0 | 8.799259264626242 | 9.349062565831051 | 100.0 | 50.0 | True | True | True | True |
| resource | 6 | 501732219.9220064 | 562500000.0 | 0.8919683909724558 | 1.0 | 14.4182830572922 | 16.164567268547344 | 66.66666666666666 | 50.0 | True | True | True | True |

Revenue is evaluated independently with level MASE, WAPE, direction accuracy,
and no-regression checks.

## Margin route evidence

| segment | validation_observations | margin_mae_pct_points | prior_margin_mae_pct_points | margin_mase_vs_prior | v1_5_margin_mae_pct_points | margin_mae_change_vs_v1_5_pct | mean_reported_component_gross_error_pct | mean_component_cancellation_ratio | component_cancellation_lock | material_recast_rows | cost_perimeter_uncertainty_lock | margin_statistical_pass | validated_margin_route | historical_pit_input |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| construction | 6 | 3.654927717379763 | 4.385057433358045 | 0.8334959742091327 | 2.7849257217154446 | 31.23968402031272 | 24.90461852913613 | 0.7450452829739326 | True | 0 | False | True | False | True |
| power_energy | 6 | 1.7235219973587192 | 1.0676666333518974 | 1.6142885274477388 | 1.4220873292383633 | 21.19663553164468 | 17.93825234032399 | 0.8492313910895343 | False | 2 | True | False | False | True |
| resource | 6 | 4.156437466379323 | 4.964438901213724 | 0.8372421433896874 | 4.7052650967203675 | -11.664117091374603 | 30.36889237933809 | 0.8503472901061303 | True | 2 | True | True | False | True |

A statistically passing margin remains blocked when component cancellation or
unforecasted segment-scope recasts are present.

## Valuation authority

| valuation_update_allowed | terminal_evidence_eligible | reason | v1_3_lite_reference_preserved | reference_value_per_share_usd | new_dcf_value_per_share | new_reverse_dcf_result | roic_reestimate_allowed | terminal_replacement_allowed | production_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| False | False | TERMINAL_EVIDENCE_GATE_FAILED | True | 399.1175 |  | NOT_RUN_BY_DESIGN | False | False | False |

Reinvestment remains a frozen pending evidence gate at one PIT OOS year and
backlog remains 2/3. No DCF, Reverse DCF, ROIC, or terminal update was run.
