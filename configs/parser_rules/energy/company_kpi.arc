# Energy SEC 8-K / IR operating KPI rules.
# Declarative and non-Turing-complete: no callbacks, I/O, network, or issuer code.

rule "XOM.upstream_total_boe" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["XOM"]
  row_patterns = ["oil-equivalent production"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "upstream_total_boe"
  scope = "TOTAL_OIL_EQUIVALENT_PRODUCTION_VOLUME"
  unit = "koebd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "XOM.downstream_product_sales" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["XOM"]
  row_patterns = ["energy products sales"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "downstream_product_sales"
  scope = "ENERGY_PRODUCTS_SALES_VOLUME"
  unit = "kbd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "XOM.chemicals_product_sales" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["XOM"]
  row_patterns = ["chemical products sales"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "chemicals_product_sales"
  scope = "CHEMICAL_PRODUCTS_SALES_VOLUME"
  unit = "kt"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "CVX.upstream_total_boe" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["CVX"]
  row_patterns = ["^net oil-equivalent production$"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "upstream_total_boe"
  scope = "TOTAL_OIL_EQUIVALENT_PRODUCTION_VOLUME"
  unit = "mboed"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "CVX.downstream_throughput" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["CVX"]
  row_patterns = ["^refinery crude unit inputs$"]
  value_mode = "FIRST"
  combine = "SUM"
  metric = "downstream_throughput"
  scope = "REFINERY_CRUDE_INPUT_VOLUME"
  unit = "mbd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "CVX.downstream_product_sales" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["CVX"]
  row_patterns = ["^refined product sales$"]
  value_mode = "FIRST"
  combine = "SUM"
  metric = "downstream_product_sales"
  scope = "REFINED_PRODUCTS_SALES_VOLUME"
  unit = "mbd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "VLO.company_throughput" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["VLO"]
  row_patterns = ["^total throughput volumes$"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "company_throughput"
  scope = "TOTAL_REFINERY_THROUGHPUT_VOLUME"
  unit = "mbpd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "MPC.company_throughput" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["MPC"]
  row_patterns = ["^crude oil refined$", "^other charge and blendstocks$"]
  value_mode = "FIRST"
  combine = "ADJACENT_PAIR_SUM_MAX"
  metric = "company_throughput"
  scope = "TOTAL_REFINERY_THROUGHPUT_VOLUME"
  unit = "mbpd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "MPC.company_utilization" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["MPC"]
  row_patterns = ["^crude oil capacity utilization"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "company_utilization"
  scope = "CRUDE_CAPACITY_UTILIZATION"
  unit = "pct"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "PSX.company_throughput" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["PSX"]
  row_patterns = ["^crude oil charge input"]
  value_mode = "REPORTED_QUARTER_INDEX"
  combine = "MAX"
  metric = "company_throughput"
  scope = "CRUDE_CHARGE_INPUT_VOLUME"
  unit = "mbd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "PSX.company_utilization" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["PSX"]
  row_patterns = ["^crude oil capacity utilization"]
  value_mode = "REPORTED_QUARTER_INDEX"
  combine = "MAX"
  metric = "company_utilization"
  scope = "CRUDE_CAPACITY_UTILIZATION"
  unit = "pct"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "KMI.gas_transport_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["KMI"]
  row_patterns = ["^transport volumes"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "gas_transport_volume"
  scope = "NATURAL_GAS_TRANSPORT_VOLUME"
  unit = "bbtu_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "KMI.gas_gathering_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["KMI"]
  row_patterns = ["^gathering volumes"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "gas_gathering_volume"
  scope = "NATURAL_GAS_GATHERING_VOLUME"
  unit = "bbtu_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "WMB.gas_transport_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["WMB"]
  row_patterns = ["^avg\\. daily transportation volumes"]
  value_mode = "CURRENT_YEAR_AFTER_PRIOR_YEAR"
  combine = "SUM"
  metric = "gas_transport_volume"
  scope = "NATURAL_GAS_TRANSPORT_VOLUME"
  unit = "mmdth"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "WMB.gas_gathering_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["WMB"]
  row_patterns = ["^gathering volumes \\(bcf/d\\)"]
  value_mode = "CURRENT_YEAR_AFTER_PRIOR_YEAR"
  combine = "SUM"
  metric = "gas_gathering_volume"
  scope = "NATURAL_GAS_GATHERING_VOLUME"
  unit = "bcf_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
  scale_when_pattern = "mmcf/d"
  scale_when_factor = 0.001
}

rule "ET.gas_transport_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["ET"]
  row_patterns = ["^natural gas transported"]
  value_mode = "FIRST"
  combine = "SUM"
  metric = "gas_transport_volume"
  scope = "NATURAL_GAS_TRANSPORT_VOLUME"
  unit = "bbtu_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "ET.gas_gathering_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["ET"]
  row_patterns = ["^gathered volumes"]
  value_mode = "FIRST"
  combine = "SUM"
  metric = "gas_gathering_volume"
  scope = "NATURAL_GAS_GATHERING_VOLUME"
  unit = "bbtu_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "ET.liquids_transport_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["ET"]
  row_patterns = ["^(ngl|crude(?: oil)?) transportation volumes"]
  value_mode = "FIRST"
  combine = "SUM"
  metric = "liquids_transport_volume"
  scope = "COMBINED_NGL_AND_CRUDE_TRANSPORT_VOLUME"
  unit = "mbbls_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "EPD.equivalent_pipeline_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["EPD"]
  row_patterns = ["^equivalent pipeline transportation volumes"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "equivalent_pipeline_volume"
  scope = "EQUIVALENT_PIPELINE_TRANSPORT_VOLUME"
  unit = "mbpd"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "EPD.fee_gas_processing_volume" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["EPD"]
  row_patterns = ["^fee-based natural gas processing volumes"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "fee_gas_processing_volume"
  scope = "FEE_BASED_GAS_PROCESSING_VOLUME"
  unit = "bcf_d"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  scale_when_pattern = "mmcf/d"
  scale_when_factor = 0.001
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "SLB.international_activity" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["SLB"]
  row_patterns = ["^international(?: revenue)?$"]
  context_patterns = ["three months ended"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "international_activity"
  scope = "GEOGRAPHIC_REVENUE"
  unit = "usd_million"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "SLB.north_america_activity" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["SLB"]
  row_patterns = ["^north america(?: revenue)?\\*?$"]
  context_patterns = ["three months ended"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "north_america_activity"
  scope = "GEOGRAPHIC_REVENUE"
  unit = "usd_million"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "HAL.completion_production_activity" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["HAL"]
  row_patterns = ["^completion and production$"]
  context_patterns = ["three months ended"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "completion_production_activity"
  scope = "SEGMENT_REVENUE"
  unit = "usd_million"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "HAL.north_america_activity" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["HAL"]
  row_patterns = ["^north america$"]
  context_patterns = ["three months ended"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "north_america_activity"
  scope = "GEOGRAPHIC_REVENUE"
  unit = "usd_million"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "BKR.orders_activity" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["BKR"]
  row_patterns = ["^(total )?orders$"]
  context_patterns = ["three months ended"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "orders_activity"
  scope = "COMPANY_ORDERS"
  unit = "usd_million"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}

rule "BKR.international_activity" {
  version = 1
  source = "SEC_EDGAR"
  document = "SEC_8K_EARNINGS_EXHIBIT"
  selector = "TABLE_ROW"
  period_mode = "REPORT_PERIOD"
  entities = ["BKR"]
  row_patterns = ["^international$"]
  context_patterns = ["three months ended"]
  value_mode = "FIRST"
  combine = "MAX"
  metric = "international_activity"
  scope = "GEOGRAPHIC_REVENUE"
  unit = "usd_million"
  origin = "OBSERVED"
  relation = "STRUCTURAL"
  evidence = "PIT"
  authority = "RESEARCH_EVIDENCE"
  min_value = 0
  finite = true
  ambiguity = "FAIL"
  missing = "SKIP"
}
