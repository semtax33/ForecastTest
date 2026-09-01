# V3.4 live-forward operations

The frozen champion passed code, config, input, schema, and model-artifact hash verification.
The consensus vintage store contains 1612 rows (0 new this run) and matched 0 released actuals.
Model changes are **LOCKED**; 20 more matched observations are required.

`EDGE` in this report means model-consensus disagreement only. It is not investment alpha or a buy/sell recommendation.

## Current decisions

- COP 2026Q3: WEAK_NEGATIVE_DISAGREEMENT (model-consensus -6.3%)
- DVN 2026Q3: STRONG_POSITIVE_DISAGREEMENT (model-consensus +26.9%)
- EOG 2026Q3: WEAK_POSITIVE_DISAGREEMENT (model-consensus +8.1%)
- FANG 2026Q3: WEAK_POSITIVE_DISAGREEMENT (model-consensus +11.3%)

## Dashboard

| metric | value | status |
| --- | --- | --- |
| MASE | 0.5315818422629403 | V3.4_FROZEN_BACKTEST |
| Revenue-level MAPE | 8.733009256400173 | V3.4_FROZEN_BACKTEST |
| 80% PI coverage | 0.7142857142857143 | V3.4_FROZEN_BACKTEST |
| Model vs consensus MAE |  | LOCKED |
| Model-consensus directional hit |  | LOCKED |

## Seven-condition candidate gate

| condition | passed | detail | model_change_lock | promotion_eligible |
| --- | --- | --- | --- | --- |
| overall_mase_not_worse | False | nan <= 0.5315818422629403 | LOCKED | False |
| revenue_mape_within_tolerance | False | tolerance=0.25 | LOCKED | False |
| untouched_or_live_forward_not_worse | False | NO_CANDIDATE_REGISTERED | LOCKED | False |
| prediction_interval_coverage_normal | False | 80% coverage=nan | LOCKED | False |
| minimum_candidate_observations | False | 0/20 | LOCKED | False |
| no_severe_existing_ticker_regression | False | floor=-2.0 | LOCKED | False |
| beats_consensus_when_eligible | True | matched=0; deferred below 20 | LOCKED | False |
