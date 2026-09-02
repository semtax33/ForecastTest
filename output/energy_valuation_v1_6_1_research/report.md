# E&P V1.6.1 accounting proof and M&A-normalized capital bridge

V1.6.1 is an accounting-proven research layer built on the reproducible V1.6
coverage output. Its consumed V1.6 outputs are hash-pinned when this layer is
frozen. Frozen V1.0 through V1.5 manifests are verified before and after
execution. No WACC, terminal, scenario, or production assumption changes.

## Core accounting proof

| ticker   | scope_identity_proven   | hedge_presentation_proven   | numeric_or_like_for_like_gate   | historical_outlier_disclosure                 | special_case_classified   | accounting_perimeter_pass   | accounting_perimeter_status                                          |
|:---------|:------------------------|:----------------------------|:--------------------------------|:----------------------------------------------|:--------------------------|:----------------------------|:---------------------------------------------------------------------|
| AR       | True                    | False                       | True                            | 2021_AND_2022_RED_GAPS_RETAINED               | True                      | True                        | PASS_AUTHORITATIVE_COMPOSITE_LIFTING_SCOPE_OLDER_RED_YEARS_DISCLOSED |
| CNX      | True                    | True                        | True                            | 2022_RED_GAP_RETAINED                         | True                      | True                        | PASS_AUTHORITATIVE_HEDGE_PRESENTATION_RECONCILIATION                 |
| FANG     | True                    | True                        | True                            | 2025_REPORTED_GAAP_GAP_ATTRIBUTED_NOT_DROPPED | True                      | True                        | PASS_LIKE_FOR_LIKE_SCOPE_WITH_2025_IMPAIRMENT_ATTRIBUTION            |

AR's reported lease operating, GP&T, and production/ad valorem tax expenses
reconcile to the already-selected composite lifting cost. Adding separate
transport and tax would double count them. Historical 2021/2022 red margin-gap
rows remain disclosed.

CNX's annual supplemental statements separately reconcile production revenue,
realized derivative settlement, unrealized derivative change, and cash-settled
production sales. No best-fit hedge hypothesis is used.

## FANG 2025 attribution

| ticker   |   year |   product_revenue_usd_millions |   purchased_oil_revenue_usd_millions |   purchased_oil_expense_usd_millions |   other_operating_revenue_usd_millions |   consolidated_revenue_usd_millions |   lease_operating_usd_millions |   production_tax_usd_millions |   transport_usd_millions |   dda_usd_millions |   g_and_a_usd_millions |   other_operating_expense_usd_millions |   impairment_usd_millions |   reported_operating_income_usd_millions |   reported_composite_lifting_cost_per_boe |   frozen_lifting_cost_per_boe |   composite_to_frozen_lifting_ratio | tax_and_transport_already_in_composite_lifting_cost   |   corrected_unit_operating_margin_pct |   reported_like_for_like_operating_margin_pct |   like_for_like_margin_gap_pct_points |   reported_consolidated_operating_margin_pct |   impairment_adjusted_consolidated_margin_pct |   v16_margin_gap_pct_points |   duplicate_cost_effect_pct_points |   impairment_effect_pct_points |   residual_after_primary_attribution_pct_points | margin_gap_classification                                | derivative_in_operating_income   | source_file                                                                                                                                     | source_sha256                                                    | availability_date   | research_only   |
|:---------|-------:|-------------------------------:|-------------------------------------:|-------------------------------------:|---------------------------------------:|------------------------------------:|-------------------------------:|------------------------------:|-------------------------:|-------------------:|-----------------------:|---------------------------------------:|--------------------------:|-----------------------------------------:|------------------------------------------:|------------------------------:|------------------------------------:|:------------------------------------------------------|--------------------------------------:|----------------------------------------------:|--------------------------------------:|---------------------------------------------:|----------------------------------------------:|----------------------------:|-----------------------------------:|-------------------------------:|------------------------------------------------:|:---------------------------------------------------------|:---------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------|:--------------------|:----------------|
| FANG     |   2025 |                          13453 |                                 1476 |                                 1474 |                                     97 |                               15026 |                           1865 |                           851 |                      515 |               5038 |                    288 |                                     77 |                      3652 |                                     1266 |                                   9.61098 |                       9.61098 |                                   1 | True                                                  |                               37.0995 |                                       36.3934 |                               0.70618 |                                       8.4254 |                                       32.7299 |                     18.5251 |                            10.1491 |                        24.3045 |                                         4.36961 | EXPLAINED_IMPAIRMENT_PLUS_DUPLICATE_COMPOSITE_COST_SCOPE | False                            | D:\Programming\python_example\Arcana\data-lake\bronze\sec\fillings\ir\FANG\2026-02-23_0001539838-26-000006_EX-99.1_diamondbackex991-2x23x26.htm | cb1fd91057213904e3d37143ff371645f812c2b998e93d034d36a24918540fd0 | 2026-02-23          | True            |

The reported consolidated operating margin contains a $3.652 billion oil and
gas property impairment. The V1.6 comparison also added tax and transport to a
lifting-cost measure that already contained LOE, tax, and GP&T. V1.6.1 removes
the duplicate additions only in this child research layer and preserves all
reported GAAP values.

## M&A-normalized company incremental ROIC

| ticker   |   diagnostic_years |   mna_normalized_incremental_roic_q50_pct |   acquisition_fact_years |   divestiture_fact_years | diagnostic_implemented   | mna_normalization_validated   | status                                      |
|:---------|-------------------:|------------------------------------------:|-------------------------:|-------------------------:|:-------------------------|:------------------------------|:--------------------------------------------|
| AR       |                  2 |                                nan        |                        0 |                        7 | True                     | False                         | DIAGNOSTIC_IMPLEMENTED_NOT_FULLY_NORMALIZED |
| CNX      |                  3 |                                 31.2087   |                        4 |                        8 | True                     | False                         | DIAGNOSTIC_IMPLEMENTED_NOT_FULLY_NORMALIZED |
| EOG      |                  5 |                                 -9.87909  |                        2 |                        8 | True                     | False                         | DIAGNOSTIC_IMPLEMENTED_NOT_FULLY_NORMALIZED |
| FANG     |                  7 |                                  0.119783 |                        0 |                        7 | True                     | False                         | DIAGNOSTIC_IMPLEMENTED_NOT_FULLY_NORMALIZED |

The bridge subtracts observed cash acquisition facts and adds observed
divestiture proceeds to the total invested-capital change. It is denominator-
only diagnostic normalization: acquired NOPAT, non-cash consideration, and
book-value differences remain in the disclosed residual. It is not a validated
terminal ROIC input.

## Freeze gate

| reserve_coverage_8_of_14   | all_group_coverage   | core_accounting_min_2_of_3   | fang_2025_classified   | cnx_hedge_presentation_proven   | ar_transport_tax_scope_proven   | three_level_roic_separated   | mna_normalization_diagnostic_implemented   | terminal_replacement_remains_locked   |   core_accounting_pass_tickers |   core_accounting_target_tickers |   terminal_candidate_ready_tickers | v1_6_1_research_freeze_eligible   | terminal_anchor_replacement_allowed   | wacc_recalibrated   | production_promoted   | live_matched_observations   |
|:---------------------------|:---------------------|:-----------------------------|:-----------------------|:--------------------------------|:--------------------------------|:-----------------------------|:-------------------------------------------|:--------------------------------------|-------------------------------:|---------------------------------:|-----------------------------------:|:----------------------------------|:--------------------------------------|:--------------------|:----------------------|:----------------------------|
| True                       | True                 | True                         | True                   | True                            | True                            | True                         | True                                       | True                                  |                              3 |                                2 |                                  0 | True                              | False                                 | False               | False                 | 0/20                        |

Terminal replacement remains locked at 0/14 and production remains locked at
0/20 live matched observations.
