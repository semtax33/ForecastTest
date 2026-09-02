# E&P V1.1 expectations-gap attribution

This is a read-only counterfactual analysis outside V1.1. Both immutable
manifests were verified before and after the run. Frozen V1.1 fair values were
reproduced with a maximum absolute per-share error of
`2.842e-14`.

## Identification boundary

| candidate_driver                     | direct_v1_1_input   | coverage   | analysis_treatment                 |
|:-------------------------------------|:--------------------|:-----------|:-----------------------------------|
| COMMODITY_SPOT_OR_QTD_PRICE          | False               | 0/14       | NOT_IDENTIFIABLE_FROM_V1_1         |
| HORMUZ_GEOPOLITICAL_PREMIUM          | False               | 0/14       | MARGIN_PERSISTENCE_PROXY_ONLY      |
| AIS_VISIBLE_OR_DARK_TRANSIT          | False               | 0/14       | NOT_IDENTIFIABLE_FROM_V1_1         |
| FROZEN_REVENUE_NOWCAST_GROWTH_ANCHOR | True                | 4/14       | REMOVE_25PCT_ANCHOR_CONTRIBUTION   |
| WACC_RISK_PREMIUM                    | True                | 14/14      | +100_TO_300BP_SENSITIVITY          |
| TERMINAL_MARGIN_ROIC_GROWTH          | True                | 14/14      | LONG_RUN_NORMALIZATION_SENSITIVITY |

V1.1 has no direct spot-oil, Hormuz-premium, AIS-visible-flow, dark-shipping, or
geopolitical-premium-duration input. Only 4/14 E&P tickers use a frozen revenue
nowcast anchor, and that anchor enters the growth center at 25%. Therefore the
Hormuz contribution cannot be estimated directly. The 1/2/4-year experiments
below are recent-window margin-persistence proxies, not measured Hormuz effects.

## Counterfactual results

| experiment                            |   median_value_gap_pct |   median_gap_reduction_vs_original_pct_points |   median_fair_value_change_vs_original_pct |   outlier_tickers_abs_gap_over_75pct |   median_terminal_value_share_pct |
|:--------------------------------------|-----------------------:|----------------------------------------------:|-------------------------------------------:|-------------------------------------:|----------------------------------:|
| COMBINED_LONG_RUN_NORMALIZATION       |              -32.7751  |                                      123.442  |                                   -54.5143 |                                    3 |                           79.253  |
| GROWTH_IMMEDIATELY_AT_TERMINAL_RATE   |               61.2079  |                                       29.4592 |                                   -15.5722 |                                    6 |                           82.7774 |
| MARGIN_PREMIUM_PROXY_1Y_FADE          |                7.72174 |                                       82.9453 |                                   -21.8765 |                                    8 |                           87.0378 |
| MARGIN_PREMIUM_PROXY_2Y_FADE          |                7.80934 |                                       82.8577 |                                   -21.8291 |                                    7 |                           86.1317 |
| MARGIN_PREMIUM_PROXY_4Y_FADE          |                8.27596 |                                       82.3911 |                                   -21.5828 |                                    7 |                           85.478  |
| NO_NEAR_TERM_REVENUE_ANCHOR           |               90.6671  |                                        0      |                                     0      |                                    8 |                           86.7788 |
| ORIGINAL_V1_1                         |               90.6671  |                                        0      |                                     0      |                                    8 |                           87.6409 |
| TERMINAL_G_MINUS_100BP                |               56.1587  |                                       34.5083 |                                   -17.4399 |                                    6 |                           84.6689 |
| TERMINAL_PRE_RECENT_WINDOW_MARGIN     |               11.4899  |                                       79.1772 |                                   -19.8917 |                                    7 |                           84.3791 |
| TERMINAL_ROIC_FADE_TO_WACC_PLUS_200BP |               58.5434  |                                       32.1237 |                                   -17.2302 |                                    6 |                           84.8669 |
| WACC_PLUS_100BP                       |               42.8137  |                                       47.8534 |                                   -24.4168 |                                    6 |                           84.5104 |
| WACC_PLUS_200BP                       |               15.708   |                                       74.9591 |                                   -39.9273 |                                    3 |                           81.5402 |
| WACC_PLUS_300BP                       |               -1.57704 |                                       92.2441 |                                   -50.7053 |                                    1 |                           78.6546 |

The original median gap is `90.67%`.
Removing the embedded near-term revenue anchor changes it to
`90.67%`. The combined long-run
normalization changes it to `-32.78%`.
Counterfactual effects are nonlinear and overlapping, so rows must not be added
as if they were an accounting waterfall.

## Cross-sectional diagnostics

| driver                                            |   spearman_rank_correlation_with_original_gap |   observations | interpretation                                     |
|:--------------------------------------------------|----------------------------------------------:|---------------:|:---------------------------------------------------|
| terminal_roic_gap_reduction_pct_points            |                                     0.995604  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| base_growth_pct                                   |                                     0.573626  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| historical_fcff_minus_operating_margin_pct_points |                                     0.538462  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| base_operating_margin_pct                         |                                     0.468132  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| base_roic_pct                                     |                                     0.437363  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| net_claims_to_market_ev_pct                       |                                     0.406593  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| no_anchor_gap_reduction_pct_points                |                                    -0.0581051 |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| terminal_margin_gap_reduction_pct_points          |                                    -0.112088  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |
| base_wacc_pct                                     |                                    -0.665934  |             14 | CROSS_SECTIONAL_ASSOCIATION_NOT_CAUSAL_ATTRIBUTION |

| metric                                                      |     value | detail                                            |
|:------------------------------------------------------------|----------:|:--------------------------------------------------|
| equity_value_gap_median_pct                                 | 90.6671   | 12/14 positive; 8/14 absolute gap above 75%       |
| enterprise_value_gap_median_pct                             | 79.1163   | Before EV-to-common-equity claims                 |
| ev_to_equity_individual_gap_amplification_median_pct_points | 12.5292   | Amplifier, not originating operating-value driver |
| base_wacc_median_pct                                        |  6.56559  | Frozen V1.1 E&P base                              |
| base_operating_margin_median_pct                            | 32.5051   | Held constant into terminal in V1.1               |
| base_roic_median_pct                                        | 15.2132   | Used for explicit and terminal reinvestment       |
| near_term_anchor_coverage_tickers                           |  4        | Revenue nowcast anchor, 25% growth-center weight  |
| near_term_anchor_gap_reduction_median_anchored_pct_points   |  9.40128  | Four anchored tickers only                        |
| near_term_anchor_gap_reduction_median_all_ep_pct_points     |  0        | Sector median unchanged                           |
| terminal_margin_prior_window_high_confidence_tickers        |  4        | Remaining names use full-history fallback         |
| historical_fcff_margin_gap_rank_correlation                 |  0.538462 | Descriptive, not mechanical or causal             |

These rank correlations use only 14 companies and are descriptive, not causal.
Historical CFO-derived FCFF does not directly feed the forward DCF: V1.1
projects FCFF as NOPAT minus growth/normalized-ROIC reinvestment. Therefore the
historical E&P FCFF-margin anomaly is a monitoring clue, not a mechanical source
of the +90.7% valuation gap.

## Interpretation

The analysis distinguishes three claims: (1) a Hormuz explanation is not
identified by V1.1 inputs; (2) near-term anchor removal measures the maximum
embedded revenue-nowcast channel available in the frozen model; and (3) WACC
and terminal-normalization sensitivities measure how much of the gap depends on
long-run economics rather than a short-lived commodity shock. No V1.1 input or
frozen output was changed. This is not an investment recommendation.
