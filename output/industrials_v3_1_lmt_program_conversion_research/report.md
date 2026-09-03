# Industrials Platform V3.1 — LMT program conversion closure

## Gate

| version | parent_v3_status | program_evidence_gate_pass | historical_pit_cutoff_pass | fixed_oos_window_pass | parent_preservation_pass | revenue_challengers_tested | revenue_challengers_accepted | margin_challengers_tested | margin_challengers_accepted | selected_revenue_champions | selected_margin_champions | selected_joint_champions | minimum_joint_champions | uncertainty_champions | financial_bridge_claim_periods | research_freeze_eligible | terminal_gate_pass | production_gate_pass | live_matched_observations | new_dcf_run | new_reverse_dcf_run | status | failed_conditions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INDUSTRIALS_PLATFORM_V3_1_LMT_PROGRAM_CONVERSION_RESEARCH | HOLD_RESEARCH_UNFROZEN | True | True | True | True | 2 | 0 | 1 | 0 | 2 | 3 | 1 | 2 | 0 | 0 | False | False | False | 0/20 | False | False | HOLD_RESEARCH_UNFROZEN | PORTABILITY_POINT_PERFORMANCE |

The 2025Q1–2026Q2 OOS window is unchanged. A challenger must beat both the
parent route and the seasonal-naive baseline before it can replace a target.

## Inherited 10-K, 10-Q, notes, IR and industry authority

| sec_10k_filings | sec_10q_filings | note_families_audited | ir_earnings_releases | ir_segment_rows | sec_ir_segment_identity_cells | sec_rpo_ir_backlog_identity_periods | bls_vintage_rows | census_context_rows | bea_context_only | inherited_source_gate_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 17 | 16 | 27 | 108 | 184 | 23 | 1080 | 486 | True | True |

## New program evidence coverage

| ir_releases_audited | expected_segment_metric_narratives | parsed_segment_metric_narratives | segment_metric_narrative_coverage_pct | rms_sikorsky_attribution_periods | aero_f35_attribution_periods | space_profit_booking_attribution_periods | space_equity_earnings_attribution_periods | annual_backlog_horizon_filings | annual_backlog_horizon_coverage_pct | program_level_backlog_amount_coverage_pct | program_level_backlog_fail_closed | sec_10q_program_amount_cells | sec_10q_program_amount_identity_pass_cells | sec_10q_program_amount_identity_pct | evidence_gate_pass | pdf_parsing_used |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | 216 | 216 | 100.0 | 25 | 26 | 23 | 19 | 6 | 100.0 | 0.0 | True | 70 | 70 | 100.0 | True | False |

| fiscal_year | filing_date | backlog_expected_within_12m_pct | backlog_expected_within_24m_pct | program_level_backlog_amount_disclosed | authority | source_url | source_sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2020 | 2021-01-28 | 39.0 | 61.0 | False | COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG | https://www.sec.gov/Archives/edgar/data/936468/000093646821000013/lmt-20201231.htm | b1b46a2a932d22bdf6e01f52cced31faf58f21047014237bc29537d7787f0afa |
| 2021 | 2022-01-25 | 38.0 | 60.0 | False | COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG | https://www.sec.gov/Archives/edgar/data/936468/000093646822000008/lmt-20211231.htm | 184e2797ab173eb7b716e2c3288eaf49b76614a89237686530cf55f8f149401f |
| 2022 | 2023-01-26 | 37.0 | 61.0 | False | COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG | https://www.sec.gov/Archives/edgar/data/936468/000093646823000009/lmt-20221231.htm | aeedb2881c45450cb492f9c353426a3815b1df3465313640fa6eb5313d76250a |
| 2023 | 2024-01-23 | 36.0 | 62.0 | False | COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG | https://www.sec.gov/Archives/edgar/data/936468/000093646824000010/lmt-20231231.htm | 62c65e8fb58d193511d0eca187c5bbbe575751279307ffd336b1abf02a616143 |
| 2024 | 2025-01-28 | 35.0 | 60.0 | False | COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG | https://www.sec.gov/Archives/edgar/data/936468/000093646825000009/lmt-20241231.htm | 2f0cfc64cf462d85a072f100e716b375eff60ee13d7f9eb35759b311fa22cb20 |
| 2025 | 2026-01-29 | 37.0 | 60.0 | False | COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG | https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm | 252829a67a8ce7821a595295a9a20353f8a05c18a2ff989a9b21983a1ea51b32 |

The 12/24-month conversion percentages are company-wide disclosures. LMT does
not disclose program-level backlog amounts, so no program-level backlog claim is allowed.

## Pre-specified challenger results

| segment | validation_observations | revenue_claim_observations | margin_claim_observations | revenue_route | revenue_mase | parent_revenue_mase | revenue_mase_change | revenue_level_ape_pct | revenue_champion_eligible | margin_route | margin_mase | parent_margin_mase | margin_mase_change | margin_champion_eligible | joint_champion | margin_boundary_hits | historical_pit_input_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics | 6 | 6 | 5 | STRUCTURAL_BACKLOG_HORIZON_MAJOR_PROGRAM_MIX | 1.298278538929297 | 1.0678595591180708 | 0.23041897981122617 | 7.095015359966644 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.2745055806096747 | 0.2745055806096747 | 0.0 | True | False | 0 | 100.0 |
| missiles_fire_control | 6 | 6 | 6 | STRUCTURAL_BACKLOG_PRICE | 0.3132342756063001 | 0.3132342756063001 | 0.0 | 3.7064673601003797 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.042353365190104374 | 0.042353365190104374 | 0.0 | True | True | 0 | 100.0 |
| rotary_mission_systems | 6 | 6 | 5 | STRUCTURAL_REVENUE_WEIGHTED_SIKORSKY_PROGRAM_MIX | 1.6901061286428432 | 1.4517688961424497 | 0.2383372325003934 | 12.226625781299866 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.10390683384528196 | 0.10390683384528196 | 0.0 | True | False | 1 | 100.0 |
| space | 6 | 6 | 6 | STRUCTURAL_BACKLOG_PRICE | 0.6611087424008795 | 0.6611087424008795 | 0.0 | 3.6613312302533214 | True | CONDITIONAL_SPACE_PROFIT_RECOGNITION_BRIDGE | 1.095821375661692 | 1.0293042449306273 | 0.06651713073106458 | False | False | 0 | 100.0 |

| segment | revenue_challenger_tested | revenue_challenger_accepted | revenue_challenger_mase | parent_revenue_mase | margin_challenger_tested | margin_challenger_accepted | margin_challenger_mase | parent_margin_mase | selection_policy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics | True | False | 1.298278538929297 | 1.0678595591180708 | False | False | 0.2745055806096747 | 0.2745055806096747 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS |
| missiles_fire_control | False | False | 0.3132342756063001 | 0.3132342756063001 | False | False | 0.042353365190104374 | 0.042353365190104374 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS |
| rotary_mission_systems | True | False | 1.6901061286428432 | 1.4517688961424497 | False | False | 0.10390683384528196 | 0.10390683384528196 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS |
| space | False | False | 0.6611087424008795 | 0.6611087424008795 | True | False | 1.095821375661692 | 1.0293042449306273 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS |

All three challengers deteriorated on the fixed OOS window and were rejected.
No post-result feature substitution was performed.

## Selected champion results

| segment | validation_observations | revenue_claim_observations | margin_claim_observations | revenue_route | revenue_mase | parent_revenue_mase | revenue_mase_change | revenue_level_ape_pct | revenue_champion_eligible | margin_route | margin_mase | parent_margin_mase | margin_mase_change | margin_champion_eligible | joint_champion | margin_boundary_hits | historical_pit_input_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics | 6 | 6 | 5 | STRUCTURAL_BACKLOG_DELIVERIES_PRICE | 1.0678595591180708 | 1.0678595591180708 | 0.0 | 5.829424087323801 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.2745055806096747 | 0.2745055806096747 | 0.0 | True | False | 0 | 100.0 |
| missiles_fire_control | 6 | 6 | 6 | STRUCTURAL_BACKLOG_PRICE | 0.3132342756063001 | 0.3132342756063001 | 0.0 | 3.7064673601003797 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.042353365190104374 | 0.042353365190104374 | 0.0 | True | True | 0 | 100.0 |
| rotary_mission_systems | 6 | 6 | 5 | STRUCTURAL_BACKLOG_HELICOPTER_DELIVERIES | 1.4517688961424497 | 1.4517688961424497 | 0.0 | 10.61107312380908 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.10390683384528196 | 0.10390683384528196 | 0.0 | True | False | 1 | 100.0 |
| space | 6 | 6 | 6 | STRUCTURAL_BACKLOG_PRICE | 0.6611087424008795 | 0.6611087424008795 | 0.0 | 3.6613312302533214 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 1.0293042449306273 | 1.0293042449306273 | 0.0 | False | False | 0 | 100.0 |

## Uncertainty and financial bridge

| segments_targets_evaluated | point_champions | uncertainty_champions | insufficient_calibration_targets | point_champion_equals_uncertainty_champion_policy | uncertainty_terminal_input_allowed | status |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | 5 | 0 | 8 | False | False | HOLD_UNCERTAINTY_CALIBRATION |

| forecast_periods | forecast_first_period | forecast_last_period | revenue_margin_joint_champion_segments | financial_bridge_claim_periods | mean_revenue_ape_pct | mean_operating_margin_error_pct_points | reinvestment_forecast_is_conditional_bridge | roic_forecast_claim_allowed | terminal_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 2025Q1 | 2026Q2 | 1 | 0 | 4.00069712170067 | 1.8757166839869759 | True | False | False |

## Target and valuation authority

| segment | validation_observations | revenue_claim_observations | margin_claim_observations | revenue_route | revenue_mase | parent_revenue_mase_x | revenue_mase_change | revenue_level_ape_pct | revenue_champion_eligible | margin_route | margin_mase | parent_margin_mase_x | margin_mase_change | margin_champion_eligible | joint_champion | margin_boundary_hits | historical_pit_input_pct | challenger_revenue_route | challenger_revenue_mase | challenger_margin_route | challenger_margin_mase | revenue_challenger_tested | revenue_challenger_accepted | revenue_challenger_mase | parent_revenue_mase_y | margin_challenger_tested | margin_challenger_accepted | margin_challenger_mase | parent_margin_mase_y | selection_policy | program_narrative_research_evidence_allowed | program_level_backlog_claim_allowed | challenger_component_forecast_claim_allowed | reinvestment_forecast_claim_allowed | roic_forecast_claim_allowed | terminal_input_allowed | production_input_allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aeronautics | 6 | 6 | 5 | STRUCTURAL_BACKLOG_DELIVERIES_PRICE | 1.0678595591180708 | 1.0678595591180708 | 0.0 | 5.829424087323801 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.2745055806096747 | 0.2745055806096747 | 0.0 | True | False | 0 | 100.0 | STRUCTURAL_BACKLOG_HORIZON_MAJOR_PROGRAM_MIX | 1.298278538929297 | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.2745055806096747 | True | False | 1.298278538929297 | 1.0678595591180708 | False | False | 0.2745055806096747 | 0.2745055806096747 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS | True | False | False | False | False | False | False |
| missiles_fire_control | 6 | 6 | 6 | STRUCTURAL_BACKLOG_PRICE | 0.3132342756063001 | 0.3132342756063001 | 0.0 | 3.7064673601003797 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.042353365190104374 | 0.042353365190104374 | 0.0 | True | True | 0 | 100.0 | STRUCTURAL_BACKLOG_PRICE | 0.3132342756063001 | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.042353365190104374 | False | False | 0.3132342756063001 | 0.3132342756063001 | False | False | 0.042353365190104374 | 0.042353365190104374 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS | True | False | False | False | False | False | False |
| rotary_mission_systems | 6 | 6 | 5 | STRUCTURAL_BACKLOG_HELICOPTER_DELIVERIES | 1.4517688961424497 | 1.4517688961424497 | 0.0 | 10.61107312380908 | False | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.10390683384528196 | 0.10390683384528196 | 0.0 | True | False | 1 | 100.0 | STRUCTURAL_REVENUE_WEIGHTED_SIKORSKY_PROGRAM_MIX | 1.6901061286428432 | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 0.10390683384528196 | True | False | 1.6901061286428432 | 1.4517688961424497 | False | False | 0.10390683384528196 | 0.10390683384528196 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS | True | False | False | False | False | False | False |
| space | 6 | 6 | 6 | STRUCTURAL_BACKLOG_PRICE | 0.6611087424008795 | 0.6611087424008795 | 0.0 | 3.6613312302533214 | True | CONDITIONAL_PROGRAM_MIX_PRICE_COST | 1.0293042449306273 | 1.0293042449306273 | 0.0 | False | False | 0 | 100.0 | STRUCTURAL_BACKLOG_PRICE | 0.6611087424008795 | CONDITIONAL_SPACE_PROFIT_RECOGNITION_BRIDGE | 1.095821375661692 | False | False | 0.6611087424008795 | 0.6611087424008795 | True | False | 1.095821375661692 | 1.0293042449306273 | CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS | True | False | False | False | False | False | False |

| lmt_v31_dcf_value_per_share_usd | lmt_v31_reverse_dcf_result | reason | terminal_input_allowed | production_promotable |
| --- | --- | --- | --- | --- |
|  | NOT_RUN_BY_DESIGN | PROGRAM_CONVERSION_CHALLENGERS_DID_NOT_CLOSE_POINT_PERFORMANCE_GATE | False | False |
