# V2.7.6 issuer-neutral laws disclosed by the eighteenth independent holdout.
# spaCy semantic roles and typed quantities only; no regex or ticker callbacks.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "CAPEX" { expression = {"concept": "CAPEX"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "COUNT" { expression = {"quantity": "COUNT"} }
var "BE_OR_OF" { expression = {"any": [{"lemma":"be"}, {"lower":"of"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "REVPAR_TREND" { expression = {"any": [{"lemma":"increase"}, {"lemma":"rise"}, {"lemma":"decline"}]} }
var "OVER" { expression = {"lower": "over"} }
var "OF" { expression = {"lower": "of"} }
var "OR" { expression = {"lower": "or"} }
var "AND" { expression = {"lower": "and"} }
var "INCLUDE" { expression = {"lemma": "include"} }
var "PARTICIPATE" { expression = {"lemma": "participate"} }
var "IN" { expression = {"lower": "in"} }
var "MORE" { expression = {"lower": "more"} }
var "THAN" { expression = {"lower": "than"} }

text_rule "v276.revpar_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["revpar"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"REVPAR_TREND","max_gap":0},{"label":"over","var":"OVER","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v276.underwriting_income_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["underwriting income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"connector","var":"BE_OR_OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v276.revenue_money_or_percent_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["fee income", "increased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "emit_base_metric", "resolve_polarity", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v276.revenue_including_components" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["including", "year-over-year increases"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"level","var":"MONEY","max_gap":0},{"label":"include","var":"INCLUDE","max_gap":1},{"label":"current","var":"PERCENT","max_gap":7},{"label":"and","var":"AND","max_gap":12},{"label":"prior","var":"PERCENT","max_gap":3}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "emit_base_metric", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v276.revenue_simple_percent_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["income increased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_polarity", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v276.capex_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["capital expenditures"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CAPEX"},{"label":"copula","var":"BE_OR_OF","max_gap":20},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v276.activity_transaction_count" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["participated", "transactions"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"trigger","var":"PARTICIPATE"},{"label":"in","var":"IN","max_gap":0},{"label":"more","var":"MORE","optional":true,"max_gap":0},{"label":"than","var":"THAN","optional":true,"max_gap":0},{"label":"value","var":"COUNT","max_gap":0},{"label":"metric","var":"ACTIVITY_VOLUME","max_gap":3}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_count", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}
