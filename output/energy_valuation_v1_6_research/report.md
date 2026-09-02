# E&P V1.6 coverage completion and accounting proof

V1.6 is a research-only child of frozen V1.5. It verifies V1.0 through V1.5
before and after execution and does not modify valuation assumptions, WACC,
terminal economics, or any frozen parser semantics.

## Reserve coverage completion

|   ep_tickers |   reserve_chain_ready_tickers |   sector_target_tickers | sector_target_met   | group_targets_met   | coverage_completion_gate   |   oil_heavy_ready |   gas_heavy_ready |   mixed_ready | production_eligible   | terminal_anchor_replacement_allowed   |
|-------------:|------------------------------:|------------------------:|:--------------------|:--------------------|:---------------------------|------------------:|------------------:|--------------:|:----------------------|:--------------------------------------|
|           14 |                             9 |                       8 | True                | True                | True                       |                 3 |                 4 |             2 | False                 | False                                 |

| group     |   ready_tickers |   target_tickers | target_met   | ticker_list    |
|:----------|----------------:|-----------------:|:-------------|:---------------|
| oil_heavy |               3 |                3 | True         | EOG;FANG;MTDR  |
| gas_heavy |               4 |                3 | True         | AR;CNX;EQT;RRC |
| mixed     |               2 |                2 | True         | DVN;SM         |

Supplemental reserve routes preserve their economic meaning. EOG, RRC, DVN,
and SM use total-proved event rollforwards with an independent operational
production check. MTDR uses consecutive total-proved stock snapshots and is
explicitly labelled total replacement including acquisitions, not organic
replacement.

## Accounting proof

| ticker   | complete_standardized_cost_scope   | accounting_perimeter_pass   | accounting_perimeter_gate                         |   median_absolute_margin_gap_pct_points | actual_three_component_mix_ready   | hedge_presentation_proven   | primary_accounting_blocker                                  | terminal_anchor_ready   | research_only   |
|:---------|:-----------------------------------|:----------------------------|:--------------------------------------------------|----------------------------------------:|:-----------------------------------|:----------------------------|:------------------------------------------------------------|:------------------------|:----------------|
| AR       | False                              | False                       | LOCKED_INCOMPLETE_STANDARDIZED_COST_SCOPE         |                                 2.48479 | True                               | True                        | TRANSPORT_AND_PRODUCTION_TAX_SCOPE_NOT_PROVEN               | False                   | True            |
| CNX      | True                               | False                       | LOCKED_NUMERIC_PASS_HEDGE_PRESENTATION_NOT_PROVEN |                                 2.83183 | False                              | False                       | HEDGE_PRESENTATION_NOT_PROVEN                               | False                   | True            |
| FANG     | True                               | False                       | REVIEW_V16_IR_COST_SUPPLEMENT_ANNUAL_GAPS         |                                 7.04331 | True                               | False                       | DERIVATIVE_PRESENTATION_AND_2025_MARGIN_GAP_REMAIN_UNPROVEN | False                   | True            |

FANG actual oil, NGL, and gas volumes and exact reported gathering, processing,
and transportation cost are extracted from annual Selected Operating Data.
No hedge adjustment is inferred. AR transport/tax and CNX hedge presentation
remain fail-closed blockers.

## Three-level ROIC

| ticker   |   level_1_development_roic_pct | level_1_semantics                        |   level_2_reserve_replacement_roic_pct | level_2_semantics                             |   level_3_company_incremental_roic_q50_pct |   level_3_eligible_years | level_3_semantics                             | three_level_roic_separated   | company_incremental_roic_validated   | level_3_status                                            | unexplained_roic_over_100pct   | terminal_anchor_ready   | research_only   |
|:---------|-------------------------------:|:-----------------------------------------|---------------------------------------:|:----------------------------------------------|-------------------------------------------:|-------------------------:|:----------------------------------------------|:-----------------------------|:-------------------------------------|:----------------------------------------------------------|:-------------------------------|:------------------------|:----------------|
| AR       |                        30.2136 | PROJECT_DEVELOPMENT_UNIT_ECONOMICS_PROXY |                                26.3186 | DEV_EXPLORATION_AND_ACQUISITION_RESERVE_PROXY |                                   nan      |                        2 | DELTA_NOPAT_OVER_DELTA_TOTAL_INVESTED_CAPITAL | True                         | False                                | LOCKED_FEWER_THAN_3_POSITIVE_MATERIAL_DELTA_CAPITAL_YEARS | False                          | False                   | True            |
| CNX      |                        85.3772 | PROJECT_DEVELOPMENT_UNIT_ECONOMICS_PROXY |                                74.8431 | DEV_EXPLORATION_AND_ACQUISITION_RESERVE_PROXY |                                    34.7776 |                        3 | DELTA_NOPAT_OVER_DELTA_TOTAL_INVESTED_CAPITAL | True                         | False                                | DIAGNOSTIC_3PLUS_YEARS_NOT_MNA_NORMALIZED                 | False                          | False                   | True            |
| EOG      |                       nan      | PROJECT_DEVELOPMENT_UNIT_ECONOMICS_PROXY |                               nan      | DEV_EXPLORATION_AND_ACQUISITION_RESERVE_PROXY |                                   -10.3865 |                        5 | DELTA_NOPAT_OVER_DELTA_TOTAL_INVESTED_CAPITAL | True                         | False                                | DIAGNOSTIC_3PLUS_YEARS_NOT_MNA_NORMALIZED                 | False                          | False                   | True            |
| FANG     |                       119.405  | PROJECT_DEVELOPMENT_UNIT_ECONOMICS_PROXY |                                41.8745 | DEV_EXPLORATION_AND_ACQUISITION_RESERVE_PROXY |                                     0.1217 |                        5 | DELTA_NOPAT_OVER_DELTA_TOTAL_INVESTED_CAPITAL | True                         | False                                | DIAGNOSTIC_3PLUS_YEARS_NOT_MNA_NORMALIZED                 | True                           | False                   | True            |

Company incremental ROIC is Delta NOPAT divided by Delta total invested capital,
using only positive material denominators. It remains diagnostic because M&A
normalization and full accounting-perimeter proof are incomplete.

## Terminal candidate gate

Ready research candidates: 0/14. Terminal replacement remains
prohibited for every ticker, even if an intermediate research-candidate row
passes. Production remains locked at 0/20 live matched observations.
