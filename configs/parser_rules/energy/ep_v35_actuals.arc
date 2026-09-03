# E&P issuer-specific actual-production layouts.
# Generic row classification and unit normalization remain typed sector semantics;
# issuer layout exceptions are declarative and non-Turing-complete.

rule "AR.actual_gas_mmcfd" {
  version = 1
  source = "COMPANY_IR_SEC"
  document = "EARNINGS_RELEASE"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["AR"]
  row_patterns = ["^average net production$"]
  value_indices = [0]
  scale_factor = 1
  combine = "MAX"
  metric = "ep_actual_gas_mmcfd"
  scope = "E_AND_P_PRODUCTION_ACTUAL"
  unit = "MMCF/D"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "AR.actual_oil_mbpd" {
  version = 1
  source = "COMPANY_IR_SEC"
  document = "EARNINGS_RELEASE"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["AR"]
  row_patterns = ["^average net production$"]
  value_indices = [1]
  scale_factor = 0.001
  combine = "MAX"
  metric = "ep_actual_oil_mbpd"
  scope = "E_AND_P_PRODUCTION_ACTUAL"
  unit = "MBBL/D"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "AR.actual_ngl_mbpd" {
  version = 1
  source = "COMPANY_IR_SEC"
  document = "EARNINGS_RELEASE"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["AR"]
  row_patterns = ["^average net production$"]
  value_indices = [2, 3]
  scale_factor = 0.001
  combine = "MAX"
  metric = "ep_actual_ngl_mbpd"
  scope = "E_AND_P_PRODUCTION_ACTUAL"
  unit = "MBBL/D"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "AR.actual_total_mboed" {
  version = 1
  source = "COMPANY_IR_SEC"
  document = "EARNINGS_RELEASE"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["AR"]
  row_patterns = ["^average net production$"]
  value_indices = [4]
  scale_factor = 0.16666666666666666
  combine = "MAX"
  metric = "ep_actual_total_mboed"
  scope = "E_AND_P_PRODUCTION_ACTUAL"
  unit = "MBOE/D"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}
