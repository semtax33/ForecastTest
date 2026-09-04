# V2.6.7 recovery laws derived from the disclosed ninth holdout.  Rules model
# issuer-neutral role topology and may only call registered pure operations.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "CAPEX" { expression = {"concept": "CAPEX"} }
var "CASH" { expression = {"concept": "CASH"} }
var "ADJUSTED_EBITDA" { expression = {"concept": "ADJUSTED_EBITDA"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "GROSS_MARGIN" { expression = {"concept": "GROSS_MARGIN"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "NUMBER" { expression = {"like_num": true} }
var "DASH" { expression = {"lower": "-"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "decrease"}, {"lemma": "grow"}, {"lower": "up"}]} }
var "TOTAL" { expression = {"lemma": "total"} }
var "ACCELERATE" { expression = {"lemma": "accelerate"} }
var "ASSUME" { expression = {"lemma": "assume"} }
var "HEADWIND" { expression = {"lower": "headwind"} }
var "ANTICIPATE" { expression = {"lemma": "anticipate"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "BE" { expression = {"lemma": "be"} }
var "GENERATE" { expression = {"lemma": "generate"} }
var "ACHIEVE" { expression = {"lemma": "achieve"} }
var "RESULT" { expression = {"lemma": "result"} }
var "OF" { expression = {"lower": "of"} }
var "TO" { expression = {"lower": "to"} }
var "IN" { expression = {"lower": "in"} }
var "AND" { expression = {"lower": "and"} }
var "OR" { expression = {"lower": "or"} }
var "BETWEEN" { expression = {"lower": "between"} }
var "RANGE" { expression = {"lemma": "range"} }
var "OVER" { expression = {"lower": "over"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "FOREIGN_CURRENCY" { expression = {"lower": "foreign currency"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "RESPECTIVELY" { expression = {"lower": "respectively"} }

text_rule "v267.sales_dash_level_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"dash","var":"DASH","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v267.revenue_total_level_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["totaled"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"total","var":"TOTAL","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":5},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v267.metric_money_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increased", "decreased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v267.capex_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["capital expenditures"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CAPEX"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v267.coordinated_revenue_growth_primary" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["growing"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0},{"label":"and","var":"AND","max_gap":8},{"label":"second_metric","var":"REVENUE","max_gap":2},{"label":"second_trigger","var":"ACCELERATE","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v267.coordinated_revenue_growth_secondary" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["accelerating"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"first_metric","var":"REVENUE"},{"label":"and","var":"AND","max_gap":8},{"label":"metric","var":"REVENUE","max_gap":2},{"label":"trigger","var":"ACCELERATE","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v267.revenue_fx_headwind_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["headwind"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"guidance","var":"GUIDANCE"},{"label":"assume","var":"ASSUME","max_gap":1},{"label":"driver","var":"FOREIGN_CURRENCY","max_gap":0},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":2},{"label":"trigger","var":"HEADWIND","max_gap":0},{"label":"to","var":"TO","max_gap":4},{"label":"metric","var":"REVENUE","max_gap":8},{"label":"growth","var":"GROWTH","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v267.cash_balance_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["were"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CASH"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v267.capex_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["anticipate"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  relation_words = ["-"]
  pattern = [{"label":"trigger","var":"ANTICIPATE"},{"label":"metric","var":"CAPEX","max_gap":2},{"label":"range","var":"RANGE","max_gap":12},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"dash","var":"DASH","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v267.sales_current_prior_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["prior-year"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"copula","var":"BE","max_gap":8},{"label":"current","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v267.multi_period_revenue_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["respectively"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":6},{"label":"current","var":"MONEY","min":2,"max":2,"max_gap":1},{"label":"first_respectively","var":"RESPECTIVELY","max_gap":10},{"label":"and","var":"AND","max_gap":1},{"label":"prior","var":"MONEY","min":2,"max":2,"max_gap":1},{"label":"second_respectively","var":"RESPECTIVELY","max_gap":10}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v267.organic_sales_word_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expects"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  relation_words = ["to"]
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"REVENUE","max_gap":2},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"range","var":"RANGE","max_gap":3},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"NUMBER","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"NUMBER","max_gap":0},{"label":"percent","var":"PERCENT","optional":true,"max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v267.adjusted_ebitda_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expects"]
  concepts = ["ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY"]
  relation_words = ["between"]
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"ADJUSTED_EBITDA","max_gap":14},{"label":"to","var":"TO","max_gap":0},{"label":"range","var":"RANGE","max_gap":0},{"label":"between","var":"BETWEEN","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v267.resulting_operating_margin" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["resulting"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"trigger","var":"RESULT"},{"label":"in","var":"IN","max_gap":0},{"label":"value","var":"PERCENT","max_gap":1},{"label":"metric","var":"OPERATING_MARGIN","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v267.generated_revenue_lower_bound" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["generated"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"GENERATE"},{"label":"over","var":"OVER","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v267.achieved_gross_margin" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["achieving"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"trigger","var":"ACHIEVE"},{"label":"value","var":"PERCENT","max_gap":1},{"label":"metric","var":"GROSS_MARGIN","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}
