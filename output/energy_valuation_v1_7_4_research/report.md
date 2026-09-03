# E&P V1.7.4 cohort closure and organic ROIC validation

V1.7.4 is a child research layer of V1.7.3. Frozen V1.6.1 and the full V1.7.3
parent snapshot are hash-verified before and after execution. The predeclared
two-route tolerance remains 10%. No WACC, terminal, scenario, parser, or
production state is changed.

## FANG-Energen transaction-perimeter closure

|   asset_total_production_low_mboe_per_day |   asset_total_production_high_mboe_per_day |   asset_loe_per_boe_low |   asset_loe_per_boe_high |   after_tax_unit_margin_low |   after_tax_unit_margin_high |   missing_after_tax_operating_contribution_low_usd |   missing_after_tax_operating_contribution_high_usd |   energen_incremental_production_low_mboe |   energen_incremental_production_high_mboe | material_transaction_perimeter_resolved   |
|------------------------------------------:|-------------------------------------------:|------------------------:|-------------------------:|----------------------------:|-----------------------------:|---------------------------------------------------:|----------------------------------------------------:|------------------------------------------:|-------------------------------------------:|:------------------------------------------|
|                                      6.45 |                                       6.55 |                 20.9924 |                  22.4806 |                     3.56519 |                      8.16729 |                                        4.23117e+06 |                                         9.84322e+06 |                                   32231.2 |                                    32249.6 | True                                      |

The 2018 Energen 9M production observation is annualized from 26,709 MBOE over
273 days. The 2019 divestiture is bounded from the company's approximately
6.5 MBOE/d total and 5.8 MBbl/d oil disclosures. Approximate production figures
are widened by 0.05 MBOE/d before calculating the range. The sold assets'
company-wide LOE contribution, actual product prices, production tax, gathering,
and depletion guidance produce a disclosure-bounded missing after-tax operating
contribution. It is not represented as directly disclosed NOPAT.
This is a retrospective transaction-perimeter validation and is not represented
as information available at the 2018 deal date.

## DVN-WPX NOPAT discrepancy reconciliation

|   headline_route_a_usd |   headline_route_b_usd |   headline_route_gap_pct |   noncontrolling_scope_adjustment_annualized_usd |   discontinued_operations_scope_adjustment_annualized_usd |   scope_adjusted_route_a_usd |   scope_adjusted_route_b_usd |   scope_adjusted_route_gap_pct |   nonoperating_residual_after_tax_annualized_usd |   unexplained_difference_usd | scope_adjusted_two_route_triangulated   |
|-----------------------:|-----------------------:|-------------------------:|-------------------------------------------------:|----------------------------------------------------------:|-----------------------------:|-----------------------------:|-------------------------------:|-------------------------------------------------:|-----------------------------:|:----------------------------------------|
|           -1.11706e+09 |           -8.64616e+08 |                  25.4781 |                                       4.0073e+06 |                                               2.43109e+08 |                 -8.69947e+08 |                 -8.64616e+08 |                       0.614628 |                                     -5.33056e+06 |                  2.08616e-07 | True                                    |

The original Route A used parent-attributable net income containing discontinued
operations, while Route B used consolidated continuing operating income. Moving
Route A to consolidated continuing scope explains the material difference. The
remaining gap equals the independently reconstructed after-tax non-operating
residual. The $967m YTD oil-and-gas impairment is present in both continuing
operations routes and is therefore not a route-gap adjustment.

## Closed three-year cohorts

| ticker   | event_name          |   v174_reported_organic_nopat_cumulative_roic_low_pct |   v174_reported_organic_nopat_cumulative_roic_high_pct |   v174_reported_economic_organic_nopat_cumulative_roic_low_pct |   v174_reported_economic_organic_nopat_cumulative_roic_high_pct |   v174_full_cycle_normalized_organic_nopat_cumulative_roic_low_pct |   v174_full_cycle_normalized_organic_nopat_cumulative_roic_high_pct | v174_reported_3y_cohort_complete   | v174_independent_full_cycle_3y_cohort_complete   | material_transaction_perimeter_resolved   |
|:---------|:--------------------|------------------------------------------------------:|-------------------------------------------------------:|---------------------------------------------------------------:|----------------------------------------------------------------:|-------------------------------------------------------------------:|--------------------------------------------------------------------:|:-----------------------------------|:-------------------------------------------------|:------------------------------------------|
| FANG     | Energen Corporation |                                              -775.202 |                                               -774.353 |                                                       -61.7058 |                                                        -61.6737 |                                                           64.9751  |                                                            65.0008  | True                               | True                                             | True                                      |
| DVN      | WPX Energy          |                                               139.394 |                                                139.394 |                                                        39.3015 |                                                         39.3015 |                                                           -2.17579 |                                                            -2.17579 | True                               | True                                             | True                                      |

## Validated company organic ROIC research ranges

| ticker   | event_name          |   deal_year |   reported_gaap_3y_roic_low_pct |   reported_gaap_3y_roic_high_pct |   reported_economic_3y_roic_low_pct |   reported_economic_3y_roic_high_pct |   full_cycle_3y_roic_low_pct |   full_cycle_3y_roic_high_pct |   economically_comparable_roic_low_pct |   economically_comparable_roic_high_pct |   economically_comparable_range_width_pct | accounting_stress_endpoint_separated   | reported_cohort_complete   | independent_full_cycle_cohort_complete   | two_route_nopat_triangulated   | material_transaction_perimeter_resolved   | organic_company_roic_validated   | validation_status                                                         | normal_roic_claimed   | terminal_input_allowed   | research_only   |
|:---------|:--------------------|------------:|--------------------------------:|---------------------------------:|------------------------------------:|-------------------------------------:|-----------------------------:|------------------------------:|---------------------------------------:|----------------------------------------:|------------------------------------------:|:---------------------------------------|:---------------------------|:-----------------------------------------|:-------------------------------|:------------------------------------------|:---------------------------------|:--------------------------------------------------------------------------|:----------------------|:-------------------------|:----------------|
| FANG     | Energen Corporation |        2018 |                        -775.202 |                         -774.353 |                            -61.7058 |                             -61.6737 |                     64.9751  |                      65.0008  |                              -61.7058  |                                 65.0008 |                                  126.707  | True                                   | True                       | True                                     | True                           | True                                      | True                             | VALIDATED_COMPANY_ORGANIC_ROIC_RESEARCH_RANGE_NOT_NORMAL_OR_TERMINAL_ROIC | False                 | False                    | True            |
| DVN      | WPX Energy          |        2021 |                         139.394 |                          139.394 |                             39.3015 |                              39.3015 |                     -2.17579 |                      -2.17579 |                               -2.17579 |                                 39.3015 |                                   41.4773 | True                                   | True                       | True                                     | True                           | True                                      | True                             | VALIDATED_COMPANY_ORGANIC_ROIC_RESEARCH_RANGE_NOT_NORMAL_OR_TERMINAL_ROIC | False                 | False                    | True            |

Reported GAAP is retained as an accounting-stress endpoint. The economically
comparable range spans reported upstream economics and independent full-cycle
economics. Neither endpoint, midpoint, nor the range is called normal ROIC, and
none is eligible for terminal input.

## Freeze gate

| v1_7_3_parent_research_gate_preserved   | complete_reported_3y_cohorts_min_2   | complete_independent_full_cycle_cohorts_min_2   | triangulated_nopat_validated_cohort_tickers_min_2   | validated_organic_roic_tickers_min_2   | no_unresolved_material_transaction_perimeter   | terminal_replacement_remains_locked   |   complete_reported_3y_cohort_tickers |   complete_independent_full_cycle_cohort_tickers |   triangulated_nopat_validated_cohort_tickers |   validated_organic_roic_tickers |   unresolved_material_transaction_perimeters | v1_7_4_research_freeze_eligible   | development_status                   | terminal_anchor_replacement_allowed   | wacc_recalibrated   | production_promoted   | live_matched_observations   |
|:----------------------------------------|:-------------------------------------|:------------------------------------------------|:----------------------------------------------------|:---------------------------------------|:-----------------------------------------------|:--------------------------------------|--------------------------------------:|-------------------------------------------------:|----------------------------------------------:|---------------------------------:|---------------------------------------------:|:----------------------------------|:-------------------------------------|:--------------------------------------|:--------------------|:----------------------|:----------------------------|
| True                                    | True                                 | True                                            | True                                                | True                                   | True                                           | True                                  |                                     2 |                                                2 |                                             2 |                                2 |                                            0 | True                              | RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE | False                                 | False               | False                 | 0/20                        |

The research freeze gate requires two complete reported cohorts, two complete
independent full-cycle cohorts, two cohort tickers with NOPAT triangulation, two
validated company organic ROIC ranges, zero unresolved material transaction
perimeters, and a locked terminal replacement state.
