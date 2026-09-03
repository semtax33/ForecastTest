# HII V5 third-company A&D research

HII was selected before forecast evaluation. This is research evidence, not production authority.

## Company revenue routes

| route | validation_observations | mae | mase | mean_ape_pct | beats_prior_year_naive |
| --- | --- | --- | --- | --- | --- |
| PIT_INDUSTRY_BRIDGE | 6 | 202541395.08012152 | 0.678151992455764 | 6.338076388648414 | True |
| HISTORICAL_GROWTH | 6 | 223736093.7224358 | 0.7491163852313698 | 7.026940985356384 | True |
| PREDECLARED_EQUAL_BLEND | 6 | 238969349.50726327 | 0.8001205898680689 | 7.379075131055676 | True |
| TOTAL_BACKLOG_BRIDGE | 6 | 267460758.7223606 | 0.8955159332221895 | 8.133377678517688 | True |
| SUM_SEGMENT_BRIDGE | 6 | 269280353.7311818 | 0.901608327224939 | 8.33383807787164 | True |
| PRIOR_YEAR_NAIVE | 6 | 298666666.6666667 | 1.0 | 9.178230267503908 | False |

## Segment revenue champions

| segment | route | validation_observations | mae | mase | mean_ape_pct | beats_prior_year_naive |
| --- | --- | --- | --- | --- | --- | --- |
| ingalls_shipbuilding | PIT_INDUSTRY_BRIDGE | 6 | 71815554.21305078 | 0.7749879951048645 | 8.877068015277873 | True |
| mission_technologies | PREDECLARED_BLEND | 6 | 27645097.677970808 | 0.9164120777227892 | 3.6350667682026194 | True |
| newport_news_shipbuilding | PIT_INDUSTRY_BRIDGE | 6 | 169034928.29517707 | 0.8983255710992581 | 9.825855180356191 | True |

## Segment margin diagnostics

| segment | route | validation_observations | mae | mase | mean_ape_pct | beats_prior_year_naive |
| --- | --- | --- | --- | --- | --- | --- |
| ingalls_shipbuilding | PREDECLARED_BLEND | 6 | 0.7694532938242852 | 0.8755867856161723 | 10.536221025968517 | True |
| mission_technologies | NORMALIZED_MARGIN | 6 | 1.0649198074859827 | 0.7208396801987026 | 17.79991858090758 | True |
| newport_news_shipbuilding | NORMALIZED_MARGIN | 6 | 0.7192069861987349 | 0.4267425284557132 | 14.082811069008574 | True |

## Three-company hypothesis

| companies | aggregate_revenue_pass_companies | all_three_aggregate_revenue_pass | segments_compared | segments_beating_naive | segment_timing_mixed_across_three_companies | segment_timing_uniformly_identified | platform_hypothesis | industry_conclusion_allowed | production_authority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 3 | True | 10 | 6 | True | False | THREE_COMPANY_AGGREGATE_REPEATED_SEGMENT_TIMING_MIXED_RESEARCH_HYPOTHESIS | False | False |

## Authority

| company | aggregate_revenue_point_authority | aggregate_revenue_champion_route | aggregate_revenue_mase | aggregate_revenue_mean_ape_pct | segment_revenue_attribution_authority | segment_revenue_routes_beating_naive | margin_authority | margin_routes_beating_naive | backlog_point_authority | segment_backlog_available | funded_backlog_incremental_value | uncertainty_authority | roic_reinvestment_authority | terminal_authority | production_authority | dcf_authority | reverse_dcf_authority | forecast_freeze_eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HII | True | PIT_INDUSTRY_BRIDGE | 0.678151992455764 | 6.338076388648414 | False | 3 | False | 3 | False | False | NOT_TESTABLE_NO_FUNDED_DISCLOSURE | False | HISTORICAL_DIAGNOSTIC_ONLY | False | False | False | False | False |

DCF and reverse DCF were not run because terminal and production gates remain locked.
