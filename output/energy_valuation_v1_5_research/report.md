# E&P V1.5 accounting-perimeter and reserve-coverage research

V1.5 is a research-only child of frozen V1.4. It verifies V1.0 through V1.4
before and after execution. It does not change frozen cash-flow assumptions,
the independent WACC range, terminal economics, scenario weights, or parser
semantics.

## Accounting-perimeter reconciliation gate

| ticker   | v14_cost_scope_status                            | v14_hedge_inclusion_diagnostic                              |   comparable_years_2021_2025 |   green_years |   yellow_years |   red_years |   red_year_share |   median_absolute_raw_margin_gap_pct_points |   median_upstream_to_consolidated_revenue_ratio | numeric_reconciliation_pass   | accounting_perimeter_reconciliation_gate          | gate_thresholds                                        | terminal_anchor_ready   | research_only   |
|:---------|:-------------------------------------------------|:------------------------------------------------------------|-----------------------------:|--------------:|---------------:|------------:|-----------------:|--------------------------------------------:|------------------------------------------------:|:------------------------------|:--------------------------------------------------|:-------------------------------------------------------|:------------------------|:----------------|
| AR       | UPPER_BOUND_MISSING_TRANSPORT_AND_PRODUCTION_TAX | NO_MECHANICAL_NETTING_REVENUE_INCLUSION_NOT_PROVEN          |                            5 |             3 |              0 |           2 |         0.4      |                                     2.48479 |                                        0.953882 | False                         | LOCKED_INCOMPLETE_STANDARDIZED_COST_SCOPE         | PROVISIONAL_GREEN_LE_5PPT_YELLOW_LE_10PPT_RED_GT_10PPT | False                   | True            |
| CNX      | COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK     | STRONG_EXACT_HEDGE_ASSOCIATION_REVENUE_INCLUSION_NOT_PROVEN |                            4 |             3 |              0 |           1 |         0.25     |                                     2.83183 |                                        0.924429 | True                          | LOCKED_NUMERIC_PASS_HEDGE_PRESENTATION_NOT_PROVEN | PROVISIONAL_GREEN_LE_5PPT_YELLOW_LE_10PPT_RED_GT_10PPT | False                   | True            |
| FANG     | UPPER_BOUND_MISSING_TRANSPORT                    | NO_MECHANICAL_NETTING_REVENUE_INCLUSION_NOT_PROVEN          |                            3 |             2 |              0 |           1 |         0.333333 |                                     3.54127 |                                        0.912706 | False                         | LOCKED_INCOMPLETE_STANDARDIZED_COST_SCOPE         | PROVISIONAL_GREEN_LE_5PPT_YELLOW_LE_10PPT_RED_GT_10PPT | False                   | True            |

Annual reconstructed upstream margin is compared with the same-year
consolidated EBIT margin. Provisional row grades are green at an absolute gap
of at most 5 percentage points, yellow above 5 through 10, and red above 10.
A company pass additionally requires complete standardized cost scope, at
least three comparable years, red-year share no greater than 25%, and median
upstream/consolidated revenue coverage between 90% and 110%.
Even a numeric pass remains locked when the frozen V1.4 diagnostic shows a
strong exact-hedge association whose revenue presentation is not proven.

Reported hedge gain/loss is shown under alternative accounting-presentation
hypotheses, but no hedge adjustment is applied. The lower-gap presentation is
diagnostic only and cannot prove where the hedge sits in reported revenue.

## Route-aware reserve coverage

| ticker   |   v13_reserve_quantity_years |   v15_route_aware_reserve_quantity_years |   v15_usable_replacement_years |   coverage_year_improvement | route_aware_reserve_chain_ready   | coverage_status                        |
|:---------|-----------------------------:|-----------------------------------------:|-------------------------------:|----------------------------:|:----------------------------------|:---------------------------------------|
| AR       |                            8 |                                       10 |                              9 |                           2 | True                              | ROUTE_AWARE_RESERVE_CHAIN_READY        |
| CNX      |                            7 |                                        9 |                              7 |                           2 | True                              | ROUTE_AWARE_RESERVE_CHAIN_READY        |
| COP      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| DVN      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| EOG      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| EQT      |                            2 |                                       10 |                              9 |                           8 | True                              | ROUTE_AWARE_RESERVE_CHAIN_READY        |
| FANG     |                            3 |                                        3 |                              2 |                           0 | True                              | ROUTE_AWARE_RESERVE_CHAIN_READY        |
| MGY      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| MTDR     |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| NOG      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| OVV      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| PR       |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| RRC      |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |
| SM       |                            0 |                                        0 |                              0 |                           0 | False                             | LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS |

The route-aware extractor selects the earliest original 10-K fact by year and
can fall back from the Energy reserve tags to the equivalent generic reserve
tags. Every production quantity is independently calibrated to the audited
annual production KPI. The result expands research-ready chains from 3/14 to
4/14, still below the explicit 8/14 sector-coverage target.

## Project versus broader company-scope reserve ROIC

| ticker   |   observed_all_in_reserve_cost_years |   project_development_cost_per_added_boe |   observed_all_in_cost_per_gross_added_boe |   project_development_roic_proxy_q50_pct |   company_scope_all_in_reserve_roic_proxy_q50_pct |   roic_reduction_from_project_to_company_scope_pct_points | roic_scope_status                                                            | project_roic_equals_company_incremental_roic   | company_incremental_roic_validated   | terminal_anchor_ready   | research_only   |
|:---------|-------------------------------------:|-----------------------------------------:|-------------------------------------------:|-----------------------------------------:|--------------------------------------------------:|----------------------------------------------------------:|:-----------------------------------------------------------------------------|:-----------------------------------------------|:-------------------------------------|:------------------------|:----------------|
| AR       |                                    5 |                                  3.02884 |                                    3.47709 |                                  30.2136 |                                           26.3186 |                                                   3.89501 | OBSERVED_DEV_EXPLORATION_ACQUISITION_SCOPE_NOT_FULL_COMPANY_INCREMENTAL_ROIC | False                                          | False                                | False                   | True            |
| CNX      |                                    5 |                                  2.76978 |                                    3.15962 |                                  85.3772 |                                           74.8431 |                                                  10.534   | OBSERVED_DEV_EXPLORATION_ACQUISITION_SCOPE_NOT_FULL_COMPANY_INCREMENTAL_ROIC | False                                          | False                                | False                   | True            |
| FANG     |                                    3 |                                  6.24094 |                                   17.7961  |                                 119.405  |                                           41.8745 |                                                  77.5309  | OBSERVED_DEV_EXPLORATION_ACQUISITION_SCOPE_NOT_FULL_COMPANY_INCREMENTAL_ROIC | False                                          | False                                | False                   | True            |

Project ROIC uses development cost per added BOE. The broader proxy uses
observed development, exploration, and proved/unproved acquisition costs per
gross organic plus purchased reserve additions. It still does not prove full
leasehold, infrastructure, corporate capital, dry-hole overlap, or acquisition
premium scope, so it is not labelled company incremental ROIC.

## Production-mix coverage

| ticker   |   basis_years |   audited_all_component_mix_years |   single_residual_component_years |   group_prior_allocated_mix_years | actual_mix_ready   |
|:---------|--------------:|----------------------------------:|----------------------------------:|----------------------------------:|:-------------------|
| AR       |             5 |                                 5 |                                 0 |                                 0 | True               |
| CNX      |             5 |                                 0 |                                 5 |                                 0 | False              |
| FANG     |             4 |                                 0 |                                 0 |                                 4 | False              |

FANG remains group-prior allocated for NGL and gas. CNX uses one residual
component. Only AR has fully audited oil/NGL/gas mix across the recent window.

## Research gate

|   ep_tickers |   accounting_perimeter_reconciliation_pass_tickers |   route_aware_reserve_chain_ready_tickers |   reserve_coverage_target_tickers | reserve_coverage_target_met   |   all_in_reserve_cost_roic_cross_check_tickers |   company_scope_roic_below_100pct_tickers |   actual_three_component_production_mix_ready_tickers |   company_incremental_roic_validated_tickers |   terminal_anchor_ready_tickers | terminal_anchor_replacement_allowed   | wacc_range_recalibrated   | v1_1_mutation_allowed   |   risk_channel_duplicate_count | production_eligible   | live_matched_observations   |
|-------------:|---------------------------------------------------:|------------------------------------------:|----------------------------------:|:------------------------------|-----------------------------------------------:|------------------------------------------:|------------------------------------------------------:|---------------------------------------------:|--------------------------------:|:--------------------------------------|:--------------------------|:------------------------|-------------------------------:|:----------------------|:----------------------------|
|           14 |                                                  0 |                                         4 |                                 8 | False                         |                                              3 |                                         3 |                                                     4 |                                            0 |                               0 | False                                 | False                     | False                   |                              0 | False                 | 0/20                        |

- Frozen independent WACC range remains approximately
  8.46% to
  10.40%.
- WACC recalibration: prohibited.
- Terminal economics replacement: locked at 0/14.
- Hormuz: cash-flow regime overlay only, no WACC premium.
- Production: locked at 0/20 matched live observations.

These outputs are research diagnostics and not investment recommendations.
