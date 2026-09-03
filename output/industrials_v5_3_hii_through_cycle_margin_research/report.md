# HII V5.3 through-cycle margin research benchmark

This layer tests whether 8-12% long-run consolidated operating margins are supported by
10-K, 10-Q, Arcana IR HTML, and PIT BLS industry evidence. It does not replace frozen V5.2
DCF assumptions and grants no fair-value, terminal-input, or production authority.

## Research summary

| as_of_date | ir_quarters | reported_ttm_windows | catchup_neutral_segment_ttm_windows_per_segment | latest_reported_ttm_operating_margin_pct | latest_catchup_neutral_ttm_operating_margin_pct | catchup_neutral_median_operating_margin_pct | catchup_neutral_q90_operating_margin_pct | catchup_neutral_max_operating_margin_pct | latest_fixed_price_risk_share_pct | latest_total_backlog_usd | eight_pct_assessment | ten_pct_assessment | twelve_pct_assessment | terminal_authority | production_promoted | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-31 | 27 | 24 | 11 | 5.293894577171028 | 5.346985210466439 | 5.685131195335277 | 6.791324455273164 | 8.845208845208845 | 49.06377998829725 | 57322000000.0 | ACCOUNTING_OBSERVED_BUT_NOT_NORMALIZED_BASE_RATE | NONCONTEMPORANEOUS_COMPONENT_EXTREMES_ONLY | OUTSIDE_OBSERVED_COMPONENT_DOMAIN | False | False | THROUGH_CYCLE_MARGIN_RESEARCH_BENCHMARK_NOT_TERMINAL_AUTHORITY |

## Catch-up-neutral margin distributions

| entity | basis | observations | minimum_pct | q25_pct | median_pct | q75_pct | q90_pct | maximum_pct | latest_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| consolidated | AS_REPORTED_TTM | 24 | 4.460195349641283 | 5.115138895643885 | 5.340143424662792 | 6.896106228586456 | 7.720195382649275 | 8.53541288323897 | 5.293894577171028 |
| consolidated | CATCHUP_NEUTRAL_TTM | 23 | 4.0114029729179395 | 4.590772476235339 | 5.685131195335277 | 5.878021917471546 | 6.791324455273164 | 8.845208845208845 | 5.346985210466439 |
| consolidated | SEGMENT_SUM_TTM | 24 | 4.693577664448094 | 5.704509492595693 | 6.357765993977411 | 7.0888500668492425 | 7.507529961779774 | 7.974947807933194 | 5.8399696624952595 |
| consolidated | NONSEGMENT_CONTRIBUTION_TTM | 24 | -1.7849643007139857 | -0.9965103417709832 | -0.535103321063642 | -0.27178857430078646 | 1.1716856256279073 | 2.606559128298259 | -0.5460750853242321 |
| ingalls_shipbuilding | AS_REPORTED_TTM | 24 | 7.062658457080769 | 7.611653097057519 | 10.744460544677153 | 11.843729281703993 | 12.364345685903794 | 13.154069767441861 | 7.301490721022209 |
| mission_technologies | AS_REPORTED_TTM | 24 | 0.301659125188537 | 2.9189287974824603 | 3.9571051069509853 | 4.5890569532335235 | 5.013849860737919 | 5.518836748182419 | 5.518836748182419 |
| newport_news_shipbuilding | AS_REPORTED_TTM | 24 | 3.6672778796466075 | 4.58717322417576 | 5.869777174918629 | 6.216863937571763 | 6.403263229668549 | 6.5543071161048685 | 5.169467388208488 |
| ingalls_shipbuilding | CATCHUP_NEUTRAL_TTM | 11 | 7.043588123815541 | 7.082726825957735 | 7.119624141669679 | 9.739380270405412 | 9.787985865724382 | 9.847383720930232 | 7.088530574992394 |
| mission_technologies | CATCHUP_NEUTRAL_TTM | 11 | 3.075213041867358 | 3.6016266301433455 | 3.8670284938941655 | 4.159140776135517 | 4.369250985545335 | 4.593522802379379 | 4.593522802379379 |
| newport_news_shipbuilding | CATCHUP_NEUTRAL_TTM | 11 | 5.767587581885502 | 6.0516611555376745 | 6.185908038372478 | 6.475645414360377 | 6.693643567695161 | 6.701289998324677 | 5.767587581885502 |

## Terminal-margin feasibility

| terminal_margin_hypothesis_pct | latest_reported_ttm_margin_pct | latest_catchup_neutral_ttm_margin_pct | catchup_neutral_median_pct | catchup_neutral_q90_pct | reported_historical_max_pct | segment_sum_historical_max_pct | nonsegment_historical_max_contribution_pct | noncontemporaneous_component_ceiling_pct | gap_vs_latest_reported_pp | gap_vs_catchup_neutral_q90_pp | economic_support_status | terminal_input_allowed | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8.0 | 5.293894577171028 | 5.346985210466439 | 5.685131195335277 | 6.791324455273164 | 8.53541288323897 | 7.974947807933194 | 2.606559128298259 | 10.581506936231452 | 2.706105422828972 | 1.2086755447268356 | ACCOUNTING_OBSERVED_BUT_NOT_NORMALIZED_BASE_RATE | False | Historical feasibility test; catch-up and pension/FAS-CAS effects are not assumed to persist into perpetuity. |
| 10.0 | 5.293894577171028 | 5.346985210466439 | 5.685131195335277 | 6.791324455273164 | 8.53541288323897 | 7.974947807933194 | 2.606559128298259 | 10.581506936231452 | 4.706105422828972 | 3.2086755447268356 | NONCONTEMPORANEOUS_COMPONENT_EXTREMES_ONLY | False | Historical feasibility test; catch-up and pension/FAS-CAS effects are not assumed to persist into perpetuity. |
| 12.0 | 5.293894577171028 | 5.346985210466439 | 5.685131195335277 | 6.791324455273164 | 8.53541288323897 | 7.974947807933194 | 2.606559128298259 | 10.581506936231452 | 6.706105422828972 | 5.208675544726836 | OUTSIDE_OBSERVED_COMPONENT_DOMAIN | False | Historical feasibility test; catch-up and pension/FAS-CAS effects are not assumed to persist into perpetuity. |

## DCF and reverse-DCF cross-check

| terminal_margin_pct | margin_basis | economic_support_status | market_implied_wacc_pct | market_implied_wacc_status | independent_wacc_low_pct | independent_wacc_midpoint_pct | independent_wacc_high_pct | market_price | conditional_value_at_independent_low_wacc_per_share | conditional_value_at_independent_midpoint_wacc_per_share | terminal_value_share_at_independent_midpoint_wacc_pct | conditional_value_at_independent_high_wacc_per_share | conditional_only | fair_value_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5.685131195335277 | CATCHUP_NEUTRAL_HISTORICAL_MEDIAN | HISTORICAL_DISTRIBUTION_DIAGNOSTIC | 5.368920878332574 | SOLVED | 8.0957342204704 | 8.333234636506527 | 8.570735052542654 | 324.0150146484375 | 139.9183722889293 | 131.42757028844966 | 79.552946308467 | 123.55622082500935 | True | False | False |
| 6.791324455273164 | CATCHUP_NEUTRAL_HISTORICAL_Q90 | HISTORICAL_DISTRIBUTION_DIAGNOSTIC | 5.951305797760142 | SOLVED | 8.0957342204704 | 8.333234636506527 | 8.570735052542654 | 324.0150146484375 | 176.87996366710567 | 166.7567199980167 | 80.74669610327226 | 157.37329025306485 | True | False | False |
| 8.0 | HYPOTHESIS_FEASIBILITY_TEST | ACCOUNTING_OBSERVED_BUT_NOT_NORMALIZED_BASE_RATE | 6.566037715470884 | SOLVED | 8.0957342204704 | 8.333234636506527 | 8.570735052542654 | 324.0150146484375 | 217.26582860674242 | 205.3589071713002 | 81.69861725908369 | 194.32331182010583 | True | False | False |
| 10.0 | HYPOTHESIS_FEASIBILITY_TEST | NONCONTEMPORANEOUS_COMPONENT_EXTREMES_ONLY | 7.538645601598546 | SOLVED | 8.0957342204704 | 8.333234636506527 | 8.570735052542654 | 324.0150146484375 | 284.09247222641466 | 269.23409243784346 | 82.7954935690731 | 255.46465240277098 | True | False | False |
| 12.0 | HYPOTHESIS_FEASIBILITY_TEST | OUTSIDE_OBSERVED_COMPONENT_DOMAIN | 8.461909633857431 | SOLVED | 8.0957342204704 | 8.333234636506527 | 8.570735052542654 | 324.0150146484375 | 350.9191158460869 | 333.10927770438684 | 83.54325503992804 | 316.6059929854362 | True | False | False |

## Latest contract mix

| period | source_type | segment | contract_type | contract_revenue_usd | external_contract_revenue_usd | contract_mix_pct | fixed_price_risk_channel | source_path | source_sha256 | table_index |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026Q2 | SEC_10Q | consolidated | cost_type | 1709000000.0 | 3418000000.0 | 50.0 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | consolidated | firm_fixed_price | 123000000.0 | 3418000000.0 | 3.598595669982446 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | consolidated | fixed_price_incentive | 1554000000.0 | 3418000000.0 | 45.465184318314805 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | consolidated | time_and_materials | 32000000.0 | 3418000000.0 | 0.9362200117027502 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | ingalls_shipbuilding | cost_type | 121000000.0 | 843000000.0 | 14.353499406880191 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | ingalls_shipbuilding | firm_fixed_price | 13000000.0 | 843000000.0 | 1.542111506524318 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | ingalls_shipbuilding | fixed_price_incentive | 709000000.0 | 843000000.0 | 84.10438908659549 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | ingalls_shipbuilding | time_and_materials | 0.0 | 843000000.0 | 0.0 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | mission_technologies | cost_type | 585000000.0 | 726000000.0 | 80.57851239669421 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | mission_technologies | firm_fixed_price | 108000000.0 | 726000000.0 | 14.87603305785124 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | mission_technologies | fixed_price_incentive | 1000000.0 | 726000000.0 | 0.13774104683195593 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | mission_technologies | time_and_materials | 32000000.0 | 726000000.0 | 4.40771349862259 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | newport_news_shipbuilding | cost_type | 1003000000.0 | 1849000000.0 | 54.24553812871823 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | newport_news_shipbuilding | firm_fixed_price | 2000000.0 | 1849000000.0 | 0.1081665765278529 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | newport_news_shipbuilding | fixed_price_incentive | 844000000.0 | 1849000000.0 | 45.64629529475392 | True | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |
| 2026Q2 | SEC_10Q | newport_news_shipbuilding | time_and_materials | 0.0 | 1849000000.0 | 0.0 | False | D:\Programming\python_example\ForecastTest\data-lake\bronze\industrials\v5\sec\hii\10-Q\2026-07-30_0001501585-26-000047_hii-20260630.htm | cc018dfd509fe4bc6db1fdd5fc2bd89cfb56c4f601faf2bd09e4fdfaa7400191 | 13 |

## PIT industry cost-recovery context

| period | segment | forecast_as_of | feature_reference_quarter | output_price_yoy_pct | dedicated_cost_yoy_pct | price_less_cost_proxy_yoy_pp | ppi_series_coverage_pct | signal | dedicated_shipbuilding_output_series_available | terminal_margin_point_input_allowed | authority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026Q2 | mission_technologies | 2026-05-05 | 2026Q1 | 10.184287099903004 | 15.568375448062884 | -5.38408834815988 | 100.0 | INDUSTRY_COST_PROXY_OUTRUNNING_OUTPUT_PRICE_PROXY | False | False | PIT_INDUSTRY_CONTEXT_DIAGNOSTIC_ONLY |
| 2026Q2 | ingalls_shipbuilding | 2026-05-05 | 2026Q1 | 8.395759157163567 | 24.002213558850592 | -15.606454401687024 | 100.0 | INDUSTRY_COST_PROXY_OUTRUNNING_OUTPUT_PRICE_PROXY | False | False | PIT_INDUSTRY_CONTEXT_DIAGNOSTIC_ONLY |
| 2026Q2 | newport_news_shipbuilding | 2026-05-05 | 2026Q1 | 8.395759157163567 | 24.002213558850592 | -15.606454401687024 | 100.0 | INDUSTRY_COST_PROXY_OUTRUNNING_OUTPUT_PRICE_PROXY | False | False | PIT_INDUSTRY_CONTEXT_DIAGNOSTIC_ONLY |

## Consensus and governance corrections

| correction_id | superseded_artifact | superseded_field | replacement_field | preserved_value | correction | independent_analyst_count_claim_allowed | parent_artifact_mutated |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HII_V5_ROUTE_AUTHORITY_001 | INDUSTRIALS_V5_HII_EVIDENCE | PIT_INDUSTRY_BRIDGE_CHAMPION_CLAIM | BEST_TESTED_DIAGNOSTIC | 0.678151992455764 | V5 finding superseded by V5.2 governance correction; six routes shared the same OOS window. |  | False |
| HII_V521_TARGET_SEMANTICS_001 | INDUSTRIALS_V5_2_1_HII_CONSENSUS_EXPECTATIONS_OVERLAY | analyst_average_target_median | provider_average_target_median | 361.79545 | Median of Finnworlds and Yahoo provider-average targets; underlying analysts may overlap. | False | False |

| provider_average_target_median | provider_count | provider_names | reported_provider_analyst_counts | independent_analyst_count | analyst_counts_may_overlap | analyst_counts_can_be_summed | target_used_to_fit_dcf | authority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 361.79544999999996 | 2 | FINNWORLDS\|YAHOO | FINNWORLDS:6\|YAHOO:11 |  | True | False | False | PROVIDER_LEVEL_EXPECTATIONS_DIAGNOSTIC_ONLY |

## Gate

| all_10k_parsed | all_10q_parsed | ir_history_coverage_complete | ir_source_hashes_verified | contract_mix_identities_pass | catchup_identities_pass | fas_cas_identities_pass | backlog_identities_pass | consensus_semantics_corrected_without_parent_mutation | dcf_crosscheck_run | fair_value_claim_allowed | terminal_input_allowed | production_promoted | live_forward_matched_observations | research_freeze_eligible | status | frozen_parents_unchanged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | True | True | True | True | True | True | True | True | True | False | False | False | 0/20 | True | RESEARCH_FREEZE_READY_TERMINAL_AND_PRODUCTION_LOCKED | True |
