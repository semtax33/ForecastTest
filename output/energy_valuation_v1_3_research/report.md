# E&P V1.3 normalized unit-economics research

This branch was created after freezing the V1.2 expectations surface. V1.0,
V1.1, and V1.2 manifests are verified before and after execution. No frozen
valuation assumption is recalibrated and production remains locked at 0/20.

## Coverage gate

|   ep_tickers |   price_volume_proxy_ready |   core_reserve_replacement_cross_check |   partial_price_volume_only |   fully_locked |   strict_realized_gas_tickers |   common_cross_commodity_realized_basis_ready |   terminal_anchor_ready |   directionally_consistent_margin_cross_checks |   roic_proxy_above_100pct_flags | production_eligible   |
|-------------:|---------------------------:|---------------------------------------:|----------------------------:|---------------:|------------------------------:|----------------------------------------------:|------------------------:|-----------------------------------------------:|--------------------------------:|:----------------------|
|           14 |                         13 |                                      3 |                          10 |              1 |                             4 |                                             0 |                       0 |                                              2 |                               2 | False                 |

Standardized reserve roll-forwards are used only where SEC quantity facts can
be reconciled to the separately audited production KPI within 25%. Filing unit
power-of-ten adjustments are detected from that reconciliation and retained in
the annual audit panel. Missing reserve event facts may be zero only inside the
stock-flow identity and are separately disclosed; they are never silently
presented as reported observations.

## Core reserve-replacement cross-checks

| ticker   |   reserve_life_median_years |   stock_flow_organic_replacement_rate_median_pct |   normalized_lifting_cost_per_boe |   normalized_dda_per_boe |   normalized_development_cost_per_added_boe |   normalized_gross_price_q50_per_boe |   commodity_normalized_accounting_margin_q50_pct |   reserve_replacement_cash_margin_q50_pct |   reserve_replacement_roic_proxy_q50_pct |   v12_historical_margin_q50_pct |   accounting_margin_q50_gap_vs_v12_pct_points | margin_cross_check_status                            | roic_cross_check_status                   |
|:---------|----------------------------:|-------------------------------------------------:|----------------------------------:|-------------------------:|--------------------------------------------:|-------------------------------------:|-------------------------------------------------:|------------------------------------------:|-----------------------------------------:|--------------------------------:|----------------------------------------------:|:-----------------------------------------------------|:------------------------------------------|
| AR       |                     14.8484 |                                         129.241  |                         14.5174   |                  3.61342 |                                     3.02884 |                              21.7108 |                                          16.4893 |                                   19.1819 |                                  93.4041 |                         17.5925 |                                      -1.10316 | DIRECTIONALLY_CONSISTENT_WITH_V12_WITHIN_10PPT       | RESEARCH_RANGE_BELOW_100PCT_NOT_VALIDATED |
| CNX      |                     15.5983 |                                          99.2384 |                          0.689365 |                  5.23629 |                                     2.76978 |                              19.0294 |                                          68.8606 |                                   81.8222 |                                 384.468  |                         15.5352 |                                      53.3255  | REJECT_AS_TERMINAL_ANCHOR_CORE_COST_SCOPE_INCOMPLETE | PLAUSIBILITY_REVIEW_REQUIRED_ABOVE_100PCT |
| FANG     |                     13.3267 |                                          75.0672 |                         10.3052   |                 12.7003  |                                     6.24094 |                              42.7357 |                                          46.1681 |                                   61.2827 |                                 258.662  |                         41.8646 |                                       4.30358 | DIRECTIONALLY_CONSISTENT_WITH_V12_WITHIN_10PPT       | PLAUSIBILITY_REVIEW_REQUIRED_ABOVE_100PCT |

The commodity price reference is the empirical 2015Q1-2024Q4 WTI, Henry Hub,
and propane distribution. It deliberately excludes 2025-2026 from the long-run
anchor. The accounting-margin proxy subtracts normalized lifting cost and
DD&A. The replacement-cash-margin proxy substitutes development cost per added
BOE for DD&A. Both omit unstandardized transport, production tax, hedging,
corporate cost, and realized-basis effects, so they are cross-checks rather than
terminal assumptions.

## Independent return-based WACC range

|   tickers |   range_available_tickers |   v1_1_base_wacc_median_pct |   symmetric_return_wacc_median_pct |   downside_return_wacc_median_pct |   return_based_low_median_pct |   return_based_high_median_pct | single_appropriate_wacc_claim_allowed   |
|----------:|--------------------------:|----------------------------:|-----------------------------------:|----------------------------------:|------------------------------:|-------------------------------:|:----------------------------------------|
|        14 |                        13 |                     6.56559 |                            8.45722 |                           10.4014 |                       8.45722 |                        10.4014 | False                                   |

The range uses local adjusted-total-return beta against the S&P 500, current
risk-free/debt/capital-structure inputs, and the frozen 4.5% ERP. Symmetric and
downside 10-year beta endpoints are reported separately. Market prices and the
V1.2 expectations surface are not used to fit this range; therefore no row is
labelled an appropriate WACC point estimate.

|   v1_1_base_wacc_median_pct |   v1_2_q50_conditional_market_equivalent_wacc_median_pct |   v1_3_independent_symmetric_return_wacc_median_pct |   v1_3_independent_downside_return_wacc_median_pct |   v1_3_symmetric_minus_v1_2_conditional_pct_points | interpretation                                                         |
|----------------------------:|---------------------------------------------------------:|----------------------------------------------------:|---------------------------------------------------:|---------------------------------------------------:|:-----------------------------------------------------------------------|
|                     6.56559 |                                                  7.91722 |                                             8.45722 |                                            10.4014 |                                           0.539999 | V1_2_IS_CONDITIONAL_PRICE_EXPLANATION_V1_3_IS_INDEPENDENT_RETURN_RANGE |

## Risk-channel separation

| risk                                   | allocated_channel           | dual_channel_allowed   | policy                                                               |
|:---------------------------------------|:----------------------------|:-----------------------|:---------------------------------------------------------------------|
| NORMALIZED_COMMODITY_PRICE             | CASH_FLOW_SCENARIO          | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| PRODUCTION_DECLINE                     | CASH_FLOW_SCENARIO          | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| RESERVE_REPLACEMENT_COST               | CASH_FLOW_SCENARIO          | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| OPERATING_TRANSPORT_PRODUCTION_TAX     | CASH_FLOW_SCENARIO          | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| GEOPOLITICAL_OPERATING_DISRUPTION      | CASH_FLOW_SCENARIO          | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| BROAD_MARKET_SYSTEMATIC_RETURN_RISK    | WACC                        | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| CAPITAL_STRUCTURE_AND_DEFAULT_RISK     | WACC                        | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| EXTREME_UNMODELED_RESIDUAL_UNCERTAINTY | RESIDUAL_SEPARATE_UNAPPLIED | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |
| HORMUZ_PRICE_OR_VOLUME_REGIME          | CASH_FLOW_SCENARIO          | False                  | ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION |

The proposed V1.3 policy has `0`
duplicated risk allocations and its double-count gate is
`True`. Frozen V1.1 has
`28` non-base rows where cash-flow
and WACC both move. That coupling is not proof of double counting, but the risk
source is not separately attributed, so it remains an explicit monitoring item
rather than being retroactively changed.

## Research decision

- Commodity-normalized price/volume economics: research-ready for 13/14.
- Core reserve-replacement cross-check: research-ready for 3/14.
- Terminal anchor replacement: locked for 14/14 until transport, production
  tax, and cross-commodity realized basis are standardized.
- Common realized-price/basis anchor: locked; strict coverage is gas-only for
  four tickers and is not cross-commodity complete.
- Hormuz overlay: deferred to cash-flow regime scenarios, with no WACC premium.
- Production: locked at 0/20. These outputs are not investment recommendations.
