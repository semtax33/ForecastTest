# PAC issuer vocabulary and structural signatures.  No network, file access,
# arbitrary functions, terminal assumptions, or silent ambiguity is expressible.

rule "airport.monthly_terminal_passengers" {
  version = 1
  source = "SEC_6K"
  document = "OPERATING_RELEASE"
  selector = "TABLE"
  period_mode = "DOCUMENT_TEXT_MONTH"
  period_patterns = [
    "(?is)Reports.{0,220}?Passenger\\s+Traffic.{0,120}?\\bin\\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\\s+(?P<year>20\\d{2})",
    "(?is)Reports.{0,160}?\\bin\\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\\s+(?P<year>20\\d{2}).{0,180}?Passenger\\s+Traffic"
  ]
  table_headers_all = ["Airport"]
  row_labels = ["Total"]
  capture_column = "REPORT_MONTH"
  fact_names = []
  full_year_only = false
  dimensions = "ANY"
  combine = "MAX"
  metric = "TERMINAL_PASSENGERS"
  scope = "CONSOLIDATED"
  unit = "THOUSAND_PASSENGERS"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  max_value = 10000
  finite = true
  assertions = ["MAX_EQUALS_SUM_OF_TWO_OR_SINGLE"]
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "airport.ifric12_concession_capex" {
  version = 1
  source = "SEC_20F"
  document = "ANNUAL_REPORT"
  selector = "INLINE_FACT"
  period_mode = "REPORT_PERIOD"
  period_patterns = []
  table_headers_all = []
  row_labels = []
  capture_column = null
  fact_names = ["pac:CostOfImprovementsToConcessionAssets"]
  full_year_only = true
  dimensions = "NONE"
  combine = "UNIQUE_VALUE"
  metric = "CONCESSION_CAPEX"
  scope = "CONSOLIDATED"
  unit = "MXN"
  origin = "OBSERVED"
  relation = "ACCOUNTING"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  max_value = null
  finite = true
  assertions = []
  ambiguity = "FAIL"
  missing = "SKIP"
}
