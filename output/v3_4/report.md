# Energy revenue nowcast V3.4

The frozen V3.3 champion artifact hashes passed verification.

## Validation

- Overall MAE: 9.04 log-points
- Revenue YoY MAE: 10.65%p
- MASE vs zero-growth naive: 0.532
- Revenue-level MAPE: 8.73%
- Infrastructure gate: PASS (+1.48% vs V3.3; tolerance 2.00%)
- Untouched test MAE: 8.58 log-points
- Untouched test MASE: 0.327

## Current nowcast

- COP 2026Q3: $16.15B, 80% PI $14.89B–$18.07B, 95% PI $13.89B–$20.38B
- DVN 2026Q3: $8.53B, 80% PI $7.67B–$10.17B, 95% PI $7.33B–$11.51B
- EOG 2026Q3: $7.66B, 80% PI $6.46B–$8.36B, 95% PI $6.33B–$9.67B
- FANG 2026Q3: $4.92B, 80% PI $4.40B–$5.94B, 95% PI $4.13B–$7.73B

## Promotion gates

- V3.4_REALIZED_BASIS / EOG: PROMOTED (PROMOTED_NO_MAE_REGRESSION)
- COMPONENT_EXPANSION / COP: NOT PROMOTED (REJECTED_MAE_REGRESSION)
- COMPONENT_EXPANSION / DVN: NOT PROMOTED (INSUFFICIENT_HISTORY_0_OF_4)
- COMPONENT_EXPANSION / FANG: NOT PROMOTED (REJECTED_MAE_REGRESSION)

## Model vs consensus

- Status: NO_MATCHED_OBSERVATIONS
- Matched observations: 0
- Statistical comparison: NEEDS_20_OBSERVATIONS


### Current gaps

- COP: model $16.15B vs consensus $17.24B (-6.3%, FMP)
- DVN: model $8.53B vs consensus $6.72B (+26.9%, ALPHA_VANTAGE,FMP)
- EOG: model $7.66B vs consensus $7.09B (+8.1%, FMP)
- FANG: model $4.92B vs consensus $4.42B (+11.3%, ALPHA_VANTAGE,FMP)