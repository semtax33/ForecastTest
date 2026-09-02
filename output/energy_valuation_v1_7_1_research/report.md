# E&P V1.7.1 M&A numerator and purchase-accounting proof

V1.7.1 is a child research layer. Frozen V1.6.1 and the V1.7 parent snapshot
are hash-verified before and after the run. WACC, terminal economics, scenario
weights, parser semantics, and production status are unchanged.

## Acquisition numerator, ownership period, and purchase accounting

| ticker   |   fiscal_year | event_name                  |   ownership_fraction |   acquiree_net_income_since_close_usd |   full_year_normalized_acquiree_net_income_usd |   acquired_invested_capital_usd |   predeal_book_invested_capital_usd |   purchase_accounting_step_up_usd |   normalized_acquiree_return_proxy_pct | purchase_accounting_step_up_status                                   |
|:---------|--------------:|:----------------------------|---------------------:|--------------------------------------:|-----------------------------------------------:|--------------------------------:|------------------------------------:|----------------------------------:|---------------------------------------:|:---------------------------------------------------------------------|
| COP      |          2021 | Concho Resources            |             0.961644 |                             2.33e+09  |                                    2.42293e+09 |                     1.7439e+10  |                          1.1241e+10 |                         6.198e+09 |                                13.8938 | PROVEN_PPA_ECONOMIC_CAPITAL_MINUS_PUBLIC_TARGET_PREDEAL_BOOK_CAPITAL |
| DVN      |          2021 | WPX Energy                  |             0.983562 |                             1.382e+09 |                                    1.4051e+09  |                     8.65e+09    |                          7.598e+09  |                         1.052e+09 |                                16.2439 | PROVEN_PPA_ECONOMIC_CAPITAL_MINUS_PUBLIC_TARGET_PREDEAL_BOOK_CAPITAL |
| FANG     |          2024 | Endeavor Energy Resources   |             0.308743 |                             4.59e+08  |                                    1.48667e+09 |                     2.742e+10   |                        nan          |                       nan         |                               nan      | LOCKED_PRIVATE_TARGET_PREDEAL_BOOK_BASIS_UNAVAILABLE                 |
| CNX      |          2025 | Apex Energy II              |             0.928767 |                           nan         |                                  nan           |                     5.23256e+08 |                        nan          |                       nan         |                               nan      | LOCKED_PRIVATE_TARGET_PREDEAL_BOOK_BASIS_UNAVAILABLE                 |
| EOG      |          2025 | Encino Acquisition Partners |             0.419178 |                             2.46e+08  |                                    5.86863e+08 |                     5.717e+09   |                        nan          |                       nan         |                                10.2652 | LOCKED_PRIVATE_TARGET_PREDEAL_BOOK_BASIS_UNAVAILABLE                 |

Reported post-close net income is subtracted only from the buyer's same-period
change in NOPAT. Its full-year normalized value is kept separately for an
acquiree run-rate return proxy. This prevents a full-year numerator from being
mixed into a partial-year consolidated bridge. The proxy remains net income,
not NOPAT, and therefore is not validated company ROIC.

WPX and Concho use the last public pre-deal 10-Q book basis filed before close.
Purchase-accounting step-up is PPA economic invested capital minus that book
basis. Private targets Endeavor and Encino remain locked rather than receiving
an inferred pre-deal book value.

## Company-year M&A bridges

| ticker   |   year | event_name                  |   organic_delta_nopat_same_period_proxy_usd |   organic_delta_invested_capital_v171_proxy_usd |   organic_incremental_roic_v171_after_tax_proxy_pct | company_year_mna_scope_fully_bridged   | company_year_bridge_status                                     |
|:---------|-------:|:----------------------------|--------------------------------------------:|------------------------------------------------:|----------------------------------------------------:|:---------------------------------------|:---------------------------------------------------------------|
| COP      |   2021 | Concho Resources            |                                 8.90667e+09 |                                      6.46e+08   |                                            nan      | False                                  | LOCKED_OTHER_MATERIAL_SHELL_ACQUISITION_AND_DISPOSITIONS       |
| DVN      |   2021 | WPX Energy                  |                                 4.11425e+09 |                                     -1.38e+08   |                                            nan      | True                                   | FULL_MNA_SCOPE_BRIDGE_NONPOSITIVE_OR_SMALL_ORGANIC_DENOMINATOR |
| FANG     |   2024 | Endeavor Energy Resources   |                                -1.4528e+08  |                                      1.767e+09  |                                            nan      | False                                  | LOCKED_OTHER_MATERIAL_TRP_EXCHANGE_AND_UNBRIDGED_DISPOSITIONS  |
| CNX      |   2025 | Apex Energy II              |                               nan           |                                     -1.2492e+07 |                                            nan      | False                                  | LOCKED_ASSET_ACQUISITION_NO_SEPARATE_OPERATING_CONTRIBUTION    |
| EOG      |   2025 | Encino Acquisition Partners |                                -1.50499e+09 |                                      1.645e+09  |                                            -91.4887 | True                                   | DIAGNOSTIC_FULL_MNA_SCOPE_AFTER_TAX_PROXY_NOT_NOPAT            |

Divestiture materiality is measured against opening capital plus acquired
capital in the event year. Immaterial dispositions are left unadjusted and
explicitly labelled. Known additional material transactions still fail closed.

## Divestiture capital and earnings evidence

| ticker   |   fiscal_year | event_name             | event_close_period   |   net_proceeds_usd |   divested_book_invested_capital_usd |   pre_tax_operating_contribution_usd |   divested_after_tax_operating_contribution_proxy_usd | divestiture_proof_status                                   |
|:---------|--------------:|:-----------------------|:---------------------|-------------------:|-------------------------------------:|-------------------------------------:|------------------------------------------------------:|:-----------------------------------------------------------|
| COP      |          2022 | Indonesia subsidiaries | 2022-03              |          731000000 |                            200000000 |                            138000000 |                                              8.97e+07 | BOOK_CAPITAL_AND_AFTER_TAX_EARNINGS_PROXY_PROVEN_NOT_NOPAT |

The Indonesia disclosure proves divested book capital and pre-close earnings,
but the after-tax amount is still a tax-adjusted earnings proxy rather than
directly disclosed NOPAT.

## Deal-year through t+2 cohorts

| ticker   |   deal_year | year_label   |   observation_year |   annual_organic_incremental_roic_proxy_pct |   cumulative_organic_incremental_roic_proxy_pct | cohort_window_complete   | cohort_status                                                        |
|:---------|------------:|:-------------|-------------------:|--------------------------------------------:|------------------------------------------------:|:-------------------------|:---------------------------------------------------------------------|
| COP      |        2021 | t            |               2021 |                                    nan      |                                        nan      | False                    | LOCKED_INCOMPLETE_COMPANY_YEAR_MNA_SCOPE                             |
| COP      |        2021 | t+1          |               2022 |                                    nan      |                                        nan      | False                    | LOCKED_INCOMPLETE_COMPANY_YEAR_MNA_SCOPE                             |
| COP      |        2021 | t+2          |               2023 |                                    nan      |                                        nan      | False                    | LOCKED_INCOMPLETE_COMPANY_YEAR_MNA_SCOPE                             |
| DVN      |        2021 | t            |               2021 |                                    nan      |                                        nan      | False                    | PARTIAL_OBSERVATION_WINDOW                                           |
| DVN      |        2021 | t+1          |               2022 |                                    126.945  |                                        295.754  | False                    | PARTIAL_OBSERVATION_WINDOW                                           |
| DVN      |        2021 | t+2          |               2023 |                                   -199.593  |                                        143.932  | True                     | COMPLETE_3Y_DIAGNOSTIC_AFTER_TAX_PROXY_NOT_NOPAT_OR_CYCLE_NORMALIZED |
| FANG     |        2024 | t            |               2024 |                                    nan      |                                        nan      | False                    | LOCKED_INCOMPLETE_COMPANY_YEAR_MNA_SCOPE                             |
| FANG     |        2024 | t+1          |               2025 |                                    -56.3155 |                                        nan      | False                    | LOCKED_INCOMPLETE_COMPANY_YEAR_MNA_SCOPE                             |
| EOG      |        2025 | t            |               2025 |                                    -91.4887 |                                        -91.4887 | False                    | PARTIAL_OBSERVATION_WINDOW                                           |

Only DVN/WPX currently has a complete t, t+1, t+2 diagnostic window. Its
cumulative return is a cycle-sensitive after-tax proxy, not a terminal input.
Other cohorts remain partial or fail closed when company-year M&A scope is
contaminated.

## Gate

| v1_6_1_frozen_parent_gate_preserved   | v1_7_parent_research_gate_preserved   | acquiree_numerator_normalized_min_2   | purchase_accounting_step_up_min_2   | divestiture_capital_and_earnings_proof_min_1   | material_mna_fully_bridged_min_2   | ownership_period_math_proven   | terminal_replacement_remains_locked   | validated_organic_roic_tickers_min_2   | complete_multi_year_roic_cohort_tickers_min_2   |   acquiree_numerator_normalized_events |   purchase_accounting_step_up_proven_events |   divestiture_capital_and_earnings_proxy_proven_events |   material_mna_fully_bridged_company_years |   direct_acquiree_nopat_disclosed_events |   validated_organic_roic_tickers |   complete_multi_year_roic_cohort_tickers | v1_7_1_research_gate   | v1_7_1_research_freeze_eligible   | development_status                   | terminal_anchor_replacement_allowed   | wacc_recalibrated   | production_promoted   | live_matched_observations   |
|:--------------------------------------|:--------------------------------------|:--------------------------------------|:------------------------------------|:-----------------------------------------------|:-----------------------------------|:-------------------------------|:--------------------------------------|:---------------------------------------|:------------------------------------------------|---------------------------------------:|--------------------------------------------:|-------------------------------------------------------:|-------------------------------------------:|-----------------------------------------:|---------------------------------:|------------------------------------------:|:-----------------------|:----------------------------------|:-------------------------------------|:--------------------------------------|:--------------------|:----------------------|:----------------------------|
| True                                  | True                                  | True                                  | True                                | True                                           | True                               | True                           | True                                  | False                                  | False                                           |                                      4 |                                           2 |                                                      1 |                                          2 |                                        0 |                                0 |                                         1 | True                   | False                             | RESEARCH_GATE_PASSED_FREEZE_DEFERRED | False                                 | False               | False                 | 0/20                        |

The V1.7.1 research gate passes, but freeze remains deferred: directly matched
organic NOPAT is still unavailable, validated organic ROIC remains zero, and
only one ticker has a complete three-year cohort. Terminal replacement stays
locked at 0/14 and production stays locked at 0/20.
