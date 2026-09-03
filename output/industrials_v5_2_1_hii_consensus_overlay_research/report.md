# HII V5.2.1 consensus expectations overlay

Finnworlds ratings and targets are added without changing frozen V5.2 DCF inputs.
A provider reference price that disagrees with the official close is rejected as a valuation target.

## Provider coverage

| provider | metric_family | rows | snapshot_dates | used_to_fit_dcf |
| --- | --- | --- | --- | --- |
| ALPHA_VANTAGE | REVENUE_AND_EPS_ESTIMATES | 2 | 2026-07-26 | False |
| FINNWORLDS | RATING_AND_PRICE_TARGET | 1 | 2026-07-31 | False |
| FMP | REVENUE_AND_EPS_ESTIMATES | 2 | 2026-07-31 | False |
| YAHOO | REVENUE_AND_EPS_ESTIMATES | 2 | 2026-07-31 | False |

## Price-target vintages

| provider | snapshot_date | metric_family | reference_stock_price | target_average | target_high | target_low | analyst_count | buy_count | hold_count | sell_count | source_path | source_sha256 | reference_price_gap_vs_official_close_pct | reference_price_quality_pass | reference_price_used_for_valuation | target_used_to_fit_dcf | use |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FINNWORLDS | 2026-07-31 | RATING_AND_PRICE_TARGET | 232.95 | 363.5 | 435.0 | 325.0 | 6 | 3 | 3 | 0 | D:\Programming\python_example\Arcana\data-lake\bronze\consensus\finnworlds\company-ratings\snapshot_date=2026-07-31\ticker=HII.json | 7dfc927d3f796773f375a28e19968f0ae0d86eae9d2bb6315556bffbb1cb8db2 | -28.1051835660285 | False | False | False | MODEL_VS_ANALYST_EXPECTATIONS_DIAGNOSTIC_ONLY |
| YAHOO | 2026-07-31 | PRICE_TARGET | 315.335 | 360.0909 | 431.0 | 280.0 | 11 |  |  |  | D:\Programming\python_example\Arcana\data-lake\bronze\consensus\yahoo\snapshot_date=2026-07-31\ticker=HII.json | 6fb51267c4495b11b38a1635a1bb0cd7d664edb5c3ac390ce3f9f66221b608b3 | -2.6788927228744375 | True | False | False | MODEL_VS_ANALYST_EXPECTATIONS_DIAGNOSTIC_ONLY |

## Model versus analyst expectations

| valuation_date | official_market_close | analyst_average_target_median | analyst_target_upside_vs_close_pct | scenario_weighted_conditional_dcf_per_share | conditional_dcf_gap_vs_analyst_target_pct | finnworlds_reference_price_quality_pass | official_close_remains_reverse_dcf_target | analyst_target_used_to_fit_dcf | terminal_authority | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-31 | 324.0150146484375 | 361.79544999999996 | 11.660087848877907 | 134.6643631885627 | -62.77886767548826 | False | True | False | False | False | CONSENSUS_EXPECTATIONS_OVERLAY_DIAGNOSTIC_ONLY |
