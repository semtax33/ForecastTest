# E&P V1.7.3 normalization attribution and NOPAT triangulation

V1.7.3 is a child research layer of V1.7.2. Frozen V1.6.1 and the full
V1.7.2 parent snapshot are hash-verified before and after execution. No WACC,
terminal, scenario, parser, or production state is changed.

## Predeclared evidence rules

- Two-route NOPAT triangulation tolerance: symmetric absolute gap <= 10.0%.
- Grade A: independently sourced complete production and component cost scope.
- Grade B: accounting-proven partial cost scope; half weight.
- Grade C: hierarchical-implied cost; diagnostic only and zero sector weight.
- Organic validation requires a complete reported cohort, a complete independent
  full-cycle cohort, a triangulated NOPAT route, and an acquisition return.

## NOPAT route triangulation

| ticker   |   fiscal_year | event_name                  |   route_a_net_income_plus_after_tax_interest_usd |   route_b_operating_income_after_tax_usd |   route_a_b_symmetric_gap_pct | two_route_nopat_triangulated   |   evidence_backed_nopat_bridge_usd |   evidence_backed_acquisition_return_proxy_pct | evidence_backed_nopat_bridge_semantics                                    |
|:---------|--------------:|:----------------------------|-------------------------------------------------:|-----------------------------------------:|------------------------------:|:-------------------------------|-----------------------------------:|-----------------------------------------------:|:--------------------------------------------------------------------------|
| FANG     |          2018 | Energen Corporation         |                                      2.47875e+08 |                              2.47171e+08 |                      0.284522 | True                           |                        2.47523e+08 |                                        3.01628 | PREDEAL_TARGET_SAME_PERIOD_TWO_ROUTE_RUN_RATE_NOT_POST_CLOSE_CONTRIBUTION |
| COP      |          2021 | Concho Resources            |                                     -1.29096e+10 |                             -1.2645e+10  |                      2.07087  | True                           |                        2.59933e+09 |                                       14.9053  | POST_CLOSE_NET_INCOME_PLUS_PREDEAL_YIELD_AFTER_TAX_INTEREST_PROXY         |
| DVN      |          2021 | WPX Energy                  |                                     -1.11706e+09 |                             -8.64616e+08 |                     25.4781   | False                          |                        1.57416e+09 |                                       18.1984  | POST_CLOSE_NET_INCOME_PLUS_PREDEAL_YIELD_AFTER_TAX_INTEREST_PROXY         |
| FANG     |          2024 | Endeavor Energy Resources   |                                    nan           |                            nan           |                    nan        | False                          |                      nan           |                                      nan       | LOCKED_PRIVATE_TARGET_FINANCING_AND_NONOPERATING_SCOPE_UNAVAILABLE        |
| CNX      |          2025 | Apex Energy II              |                                    nan           |                            nan           |                    nan        | False                          |                      nan           |                                      nan       | LOCKED_PRIVATE_TARGET_FINANCING_AND_NONOPERATING_SCOPE_UNAVAILABLE        |
| EOG      |          2025 | Encino Acquisition Partners |                                    nan           |                            nan           |                    nan        | False                          |                      nan           |                                      nan       | LOCKED_PRIVATE_TARGET_FINANCING_AND_NONOPERATING_SCOPE_UNAVAILABLE        |

Energen adds a public-target same-period Route A/Route B observation. Its bridge
is a pre-deal target run-rate and is not substituted for post-close contribution.
Negative target NOPAT can still validate an accounting identity, but it is
separately barred from being interpreted as a positive economic run-rate.

## Annual normalization attribution

| ticker   |   year |   actual_price_per_boe |   actual_unit_cost_per_boe |   normalized_price_per_boe |   normalized_unit_cost_per_boe |   accounting_scope_residual_usd |   price_normalization_effect_usd |   cost_normalization_effect_usd |   tax_normalization_effect_usd |   normalization_attribution_identity_error_usd | normalization_confidence_grade   |
|:---------|-------:|-----------------------:|---------------------------:|---------------------------:|-------------------------------:|--------------------------------:|---------------------------------:|--------------------------------:|-------------------------------:|-----------------------------------------------:|:---------------------------------|
| DVN      |   2020 |                22.0902 |                    23.2377 |                    37.2446 |                        24.0981 |                    -2.22701e+09 |                      1.46058e+09 |                    -8.29243e+07 |                   -1.01029e+07 |                                    0           | A                                |
| DVN      |   2021 |                45.6029 |                    21.9426 |                    37.2446 |                        24.0981 |                    -1.57477e+09 |                     -1.58922e+09 |                    -4.09843e+08 |                   -3.46327e+08 |                                    4.76837e-07 | A                                |
| DVN      |   2022 |                63.148  |                    23.9462 |                    37.2446 |                        24.0981 |                    -4.52655e+08 |                     -4.47834e+09 |                    -2.62624e+07 |                    2.4706e+07  |                                   -1.43051e-06 | A                                |
| DVN      |   2023 |                44.9625 |                    24.25   |                    37.2446 |                        24.0981 |                     4.74626e+07 |                     -1.50386e+09 |                     2.95993e+07 |                   -8.89348e+07 |                                    0           | A                                |
| FANG     |   2017 |                41.0234 |                    20.3441 |                    36.0974 |                        24.4004 |                     8.34136e+07 |                     -1.12533e+08 |                    -9.26629e+07 |                38147.7         |                                   -2.98023e-08 | A                                |
| FANG     |   2018 |                44.7339 |                    22.0824 |                    36.0974 |                        24.4004 |                    -4.55473e+07 |                     -3.21329e+08 |                    -8.62436e+07 |                    4.81037e+06 |                                    0           | A                                |
| FANG     |   2019 |                37.6337 |                    23.014  |                    36.0974 |                        24.4004 |                    -6.48432e+08 |                     -1.25358e+08 |                    -1.13123e+08 |               136255           |                                    0           | A                                |
| FANG     |   2020 |                25.0726 |                    19.5777 |                    36.0974 |                        24.4004 |                    -4.8032e+09  |                      9.57371e+08 |                    -4.1879e+08  |               145009           |                                    0           | A                                |

The bridge is `reported GAAP NOPAT -> reported upstream economic NOPAT -> price
only -> cost only -> price+cost -> full cycle tax`. The accounting-scope residual
is explicit, so impairments, hedges, and non-upstream scope are not silently
mislabelled as commodity-price effects. The maximum bridge identity error is
0.000001 USD. Source-cell verification is 48/48.

## Three-year attribution cohorts

| ticker   | event_name          |   reported_cumulative_organic_roic_pct |   reported_economic_cumulative_organic_roic_pct |   price_only_normalized_cumulative_organic_roic_pct |   cost_only_normalized_cumulative_organic_roic_pct |   price_and_cost_normalized_cumulative_organic_roic_pct |   full_cycle_normalized_cumulative_organic_roic_pct | methodology_attribution_complete   | independent_cost_normalized_cohort_complete   | reported_cohort_complete   | full_cycle_normalized_cohort_complete   |
|:---------|:--------------------|---------------------------------------:|------------------------------------------------:|----------------------------------------------------:|---------------------------------------------------:|--------------------------------------------------------:|----------------------------------------------------:|:-----------------------------------|:----------------------------------------------|:---------------------------|:----------------------------------------|
| FANG     | Energen Corporation |                                nan     |                                        nan      |                                            nan      |                                            nan     |                                               nan       |                                           nan       | True                               | True                                          | False                      | False                                   |
| DVN      | WPX Energy          |                                139.394 |                                         39.3015 |                                            -15.5113 |                                             49.102 |                                                -5.71082 |                                            -2.17579 | True                               | True                                          | True                       | True                                    |

DVN has a complete organic perimeter. FANG has complete independent price/cost
methodology evidence, but its 2019 asset sale lacks the disposed assets' operating
contribution. The disclosed $300m proceeds and $1m gain prove a $299m book-capital
bridge; they do not prove NOPAT. FANG therefore remains fail-closed for organic
cohort validation.

## Organic ROIC validation

| ticker   |   fiscal_year | event_name                  |   reported_3y_roic_pct |   cycle_normalized_3y_roic_pct |   acquisition_return_proxy_pct | organic_company_roic_validated   | validation_status                                                                                                                                                                                  |
|:---------|--------------:|:----------------------------|-----------------------:|-------------------------------:|-------------------------------:|:---------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| FANG     |          2018 | Energen Corporation         |                nan     |                      nan       |                        3.01628 | False                            | LOCKED__REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE__CYCLE_NORMALIZED_ORGANIC_3Y_COHORT_INCOMPLETE                                                                                                       |
| COP      |          2021 | Concho Resources            |                nan     |                      nan       |                       14.9053  | False                            | LOCKED__REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE__CYCLE_NORMALIZED_ORGANIC_3Y_COHORT_INCOMPLETE__INDEPENDENT_COST_COHORT_INCOMPLETE                                                                   |
| DVN      |          2021 | WPX Energy                  |                139.394 |                       -2.17579 |                       18.1984  | False                            | LOCKED__NOPAT_TWO_ROUTE_NOT_TRIANGULATED                                                                                                                                                           |
| FANG     |          2024 | Endeavor Energy Resources   |                nan     |                      nan       |                      nan       | False                            | LOCKED__NOPAT_TWO_ROUTE_NOT_TRIANGULATED__REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE__CYCLE_NORMALIZED_ORGANIC_3Y_COHORT_INCOMPLETE__INDEPENDENT_COST_COHORT_INCOMPLETE__ACQUISITION_RETURN_UNAVAILABLE |
| CNX      |          2025 | Apex Energy II              |                nan     |                      nan       |                      nan       | False                            | LOCKED__NOPAT_TWO_ROUTE_NOT_TRIANGULATED__REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE__CYCLE_NORMALIZED_ORGANIC_3Y_COHORT_INCOMPLETE__INDEPENDENT_COST_COHORT_INCOMPLETE__ACQUISITION_RETURN_UNAVAILABLE |
| EOG      |          2025 | Encino Acquisition Partners |                nan     |                      nan       |                      nan       | False                            | LOCKED__NOPAT_TWO_ROUTE_NOT_TRIANGULATED__REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE__CYCLE_NORMALIZED_ORGANIC_3Y_COHORT_INCOMPLETE__INDEPENDENT_COST_COHORT_INCOMPLETE__ACQUISITION_RETURN_UNAVAILABLE |

## Gate

| v1_7_2_parent_research_gate_preserved   | evidence_backed_nopat_bridge_min_3   | nopat_two_route_triangulation_min_2   | normalization_attribution_min_2_tickers   | independent_cost_normalized_cohort_min_2   | complete_3y_reported_cohort_min_2   | complete_3y_cycle_normalized_cohort_min_2   | validated_organic_roic_min_2   | terminal_replacement_remains_locked   |   evidence_backed_nopat_bridge_deals |   two_route_nopat_triangulated_deals |   positive_two_route_nopat_deals |   normalization_attribution_tickers |   independent_cost_normalized_cohort_tickers |   complete_3y_reported_cohort_tickers |   complete_3y_cycle_normalized_cohort_tickers |   validated_organic_roic_tickers | v1_7_3_research_gate   | v1_7_3_research_freeze_eligible   | development_status                   | terminal_anchor_replacement_allowed   | wacc_recalibrated   | production_promoted   | live_matched_observations   |
|:----------------------------------------|:-------------------------------------|:--------------------------------------|:------------------------------------------|:-------------------------------------------|:------------------------------------|:--------------------------------------------|:-------------------------------|:--------------------------------------|-------------------------------------:|-------------------------------------:|---------------------------------:|------------------------------------:|---------------------------------------------:|--------------------------------------:|----------------------------------------------:|---------------------------------:|:-----------------------|:----------------------------------|:-------------------------------------|:--------------------------------------|:--------------------|:----------------------|:----------------------------|
| True                                    | True                                 | True                                  | True                                      | True                                       | False                               | False                                       | False                          | True                                  |                                    3 |                                    2 |                                1 |                                   2 |                                            2 |                                     1 |                                             1 |                                0 | True                   | False                             | RESEARCH_GATE_PASSED_FREEZE_DEFERRED | False                                 | False               | False                 | 0/20                        |

The infrastructure gate passes, but freeze remains deferred. Evidence-backed
NOPAT bridges, two-route triangulation, and independent-cost attribution coverage
reach their predeclared research targets. Complete organic three-year cohorts and
validated organic ROIC do not. Terminal replacement remains 0/14 and production
remains 0/20.
