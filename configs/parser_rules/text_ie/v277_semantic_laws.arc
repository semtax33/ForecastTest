# V2.7.7 issuer-neutral laws disclosed by the nineteenth independent holdout.
# spaCy-backed typed roles only; no ticker callbacks and no raw regex.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "GROWTH" { expression = {"lemma": "growth"} }
var "OF" { expression = {"lower": "of"} }
var "INCLUDE" { expression = {"lemma": "include"} }
var "ORGANIC" { expression = {"lower": "organic"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "BE" { expression = {"lemma": "be"} }
var "REPRESENT" { expression = {"lemma": "represent"} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "LOWER" { expression = {"lower": "lower"} }
var "OR" { expression = {"lower": "or"} }
var "REFLECT" { expression = {"lemma": "reflect"} }
var "IMPACT" { expression = {"lemma": "impact"} }
var "AND" { expression = {"lower": "and"} }
var "TAILWIND" { expression = {"lemma": "tailwind"} }
var "TO" { expression = {"lower": "to"} }

text_rule "v277.revenue_and_organic_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["revenue growth", "organic growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"current","var":"PERCENT","max_gap":0},{"label":"include","var":"INCLUDE","max_gap":1},{"label":"organic","var":"ORGANIC","max_gap":0},{"label":"organic_growth","var":"GROWTH","max_gap":0},{"label":"organic_of","var":"OF","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "emit_base_metric", "resolve_polarity", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v277.operating_income_represents_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["representing", "increase"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"represent","var":"REPRESENT","max_gap":7},{"label":"change","var":"PERCENT","max_gap":1},{"label":"trigger","var":"INCREASE","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v277.operating_income_level_percent_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":2},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v277.operating_income_percent_lower" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["lower"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"PERCENT","max_gap":0},{"label":"trigger","var":"LOWER","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v277.operating_income_level_absolute_delta" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":2},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":0},{"label":"percent","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v277.operating_income_percent_delta_after_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increase"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"level","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":2},{"label":"of","var":"OF","max_gap":0},{"label":"amount","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v277.revenue_attribution_components" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["reflects", "impact", "tailwind"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"reflect","var":"REFLECT","max_gap":0},{"label":"current","var":"PERCENT","max_gap":1},{"label":"impact","var":"IMPACT","max_gap":2},{"label":"and","var":"AND","max_gap":2},{"label":"prior","var":"PERCENT","max_gap":6},{"label":"tailwind","var":"TAILWIND","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "emit_base_metric", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v277.segment_property_revenue_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["property revenue"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}
