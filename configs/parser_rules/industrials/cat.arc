# CAT issuer vocabulary for direct order-backlog narrative disclosures.
# Each rule extracts one typed fact; cross-fact accounting and period identities
# remain in the economic bridge, not in regex callbacks.

rule "machinery.cat.firm_backlog_current" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)The dollar amount of backlog believed to be firm was approximately\\s+\\$(?P<current_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<current_year>\\d{4}) and\\s+\\$(?P<prior_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<prior_year>\\d{4})"]
  capture_group = "current_value"
  combine = "UNIQUE"
  metric = "FIRM_ORDER_BACKLOG"
  scope = "CONSOLIDATED"
  unit = "USD_BILLION"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}

rule "machinery.cat.firm_backlog_current_year" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)The dollar amount of backlog believed to be firm was approximately\\s+\\$(?P<current_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<current_year>\\d{4}) and\\s+\\$(?P<prior_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<prior_year>\\d{4})"]
  capture_group = "current_year"
  combine = "UNIQUE"
  metric = "FIRM_ORDER_BACKLOG_CURRENT_YEAR"
  scope = "CONSOLIDATED"
  unit = "YEAR"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 1900
  max_value = 2200
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}

rule "machinery.cat.firm_backlog_prior" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)The dollar amount of backlog believed to be firm was approximately\\s+\\$(?P<current_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<current_year>\\d{4}) and\\s+\\$(?P<prior_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<prior_year>\\d{4})"]
  capture_group = "prior_value"
  combine = "UNIQUE"
  metric = "PRIOR_YEAR_FIRM_ORDER_BACKLOG"
  scope = "CONSOLIDATED"
  unit = "USD_BILLION"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}

rule "machinery.cat.firm_backlog_prior_year" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)The dollar amount of backlog believed to be firm was approximately\\s+\\$(?P<current_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<current_year>\\d{4}) and\\s+\\$(?P<prior_value>[\\d,.]+)\\s+billion at December 31,\\s+(?P<prior_year>\\d{4})"]
  capture_group = "prior_year"
  combine = "UNIQUE"
  metric = "FIRM_ORDER_BACKLOG_PRIOR_YEAR"
  scope = "CONSOLIDATED"
  unit = "YEAR"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 1900
  max_value = 2200
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}

rule "machinery.cat.not_expected_next_year" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)Of the total backlog at December 31,\\s+(?P<backlog_year>\\d{4}), approximately\\s+\\$(?P<not_expected_value>[\\d,.]+)\\s+billion was not expected to be filled in\\s+(?P<fill_year>\\d{4})"]
  capture_group = "not_expected_value"
  combine = "UNIQUE"
  metric = "BACKLOG_NOT_EXPECTED_NEXT_YEAR"
  scope = "CONSOLIDATED"
  unit = "USD_BILLION"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}

rule "machinery.cat.not_expected_backlog_year" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)Of the total backlog at December 31,\\s+(?P<backlog_year>\\d{4}), approximately\\s+\\$(?P<not_expected_value>[\\d,.]+)\\s+billion was not expected to be filled in\\s+(?P<fill_year>\\d{4})"]
  capture_group = "backlog_year"
  combine = "UNIQUE"
  metric = "BACKLOG_NOT_EXPECTED_REFERENCE_YEAR"
  scope = "CONSOLIDATED"
  unit = "YEAR"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 1900
  max_value = 2200
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}

rule "machinery.cat.expected_fill_year" {
  version = 1
  source = "SEC_10K"
  document = "ANNUAL_REPORT"
  selector = "TEXT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  text_patterns = ["(?i)Of the total backlog at December 31,\\s+(?P<backlog_year>\\d{4}), approximately\\s+\\$(?P<not_expected_value>[\\d,.]+)\\s+billion was not expected to be filled in\\s+(?P<fill_year>\\d{4})"]
  capture_group = "fill_year"
  combine = "UNIQUE"
  metric = "EXPECTED_FILL_YEAR"
  scope = "CONSOLIDATED"
  unit = "YEAR"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 1900
  max_value = 2200
  finite = true
  ambiguity = "FAIL"
  missing = "FAIL"
}
