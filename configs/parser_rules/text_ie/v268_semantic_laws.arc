# V2.6.8 laws derived from the disclosed tenth holdout.  The program keeps
# issuer names out of extraction logic and expresses only bounded semantic roles.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "ORDERS" { expression = {"concept": "ORDERS"} }
var "BOOK_TO_BILL" { expression = {"concept": "BOOK_TO_BILL"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "DEBT" { expression = {"concept": "DEBT"} }
var "CASH" { expression = {"concept": "CASH"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "RATE" { expression = {"quantity": "RATE"} }
var "NUMBER" { expression = {"like_num": true} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "decrease"}, {"lower": "up"}, {"lower": "down"}]} }
var "RECEIVE" { expression = {"lemma": "receive"} }
var "BE" { expression = {"lemma": "be"} }
var "GENERATE" { expression = {"lemma": "generate"} }
var "REDUCE" { expression = {"lemma": "reduce"} }
var "INCLUDE" { expression = {"lemma": "include"} }
var "LOWER" { expression = {"lower": "lower"} }
var "HIGHER" { expression = {"lower": "higher"} }
var "ADJUST" { expression = {"lemma": "adjust"} }
var "DECLINE" { expression = {"lemma": "decline"} }
var "HEADWIND" { expression = {"lower": "headwind"} }
var "ANTICIPATE" { expression = {"lemma": "anticipate"} }
var "ACCELERATE" { expression = {"lemma": "accelerate"} }
var "DRIVE" { expression = {"lemma": "drive"} }
var "ORGANIC" { expression = {"lower": "organic"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "RANGE" { expression = {"lemma": "range"} }
var "RAISE" { expression = {"lemma": "raise"} }
var "INCREMENTAL" { expression = {"lower": "incremental"} }
var "TOTAL" { expression = {"lemma": "total"} }
var "MIDPOINT" { expression = {"lower": "midpoint"} }
var "APPROXIMATELY" { expression = {"lower": "approximately"} }
var "OF" { expression = {"lower": "of"} }
var "IN" { expression = {"lower": "in"} }
var "BY" { expression = {"lower": "by"} }
var "TO" { expression = {"lower": "to"} }
var "AT" { expression = {"lower": "at"} }
var "AND" { expression = {"lower": "and"} }
var "OR" { expression = {"lower": "or"} }

text_rule "v268.orders_received_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["received"]
  concepts = ["ORDERS"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"ORDERS"},{"label":"trigger","var":"RECEIVE","max_gap":5},{"label":"value","var":"MONEY","min":3,"max":3,"max_gap":12}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v268.book_to_bill_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was"]
  concepts = ["BOOK_TO_BILL"]
  quantity_kinds = ["RATE"]
  pattern = [{"label":"metric","var":"BOOK_TO_BILL"},{"label":"copula","var":"BE","max_gap":12},{"label":"value","var":"RATE","min":3,"max":3,"max_gap":14}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v268.generated_revenue_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["generated"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"GENERATE"},{"label":"value","var":"MONEY","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v268.debt_reduced_by" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["reduced"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"REDUCE"},{"label":"metric","var":"DEBT","max_gap":1},{"label":"relation","var":"BY","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v268.incremental_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["included"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"INCLUDE"},{"label":"value","var":"MONEY","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"incremental","var":"INCREMENTAL","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v268.cash_component_of_liquidity" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["includes"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"INCLUDE"},{"label":"value","var":"MONEY","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"metric","var":"CASH","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v268.cash_current_prior_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["compared to"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"current","var":"MONEY"},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"CASH","max_gap":0},{"label":"prior","var":"MONEY","max_gap":18}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v268.operating_income_delta_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increased", "decreased"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"value","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"percent","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v268.operating_income_delta_percent" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increased", "decreased"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"amount","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v268.lower_operating_income_pair" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["lower"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"current","var":"MONEY"},{"label":"trigger","var":"LOWER","max_gap":1},{"label":"metric","var":"OPERATING_INCOME","max_gap":0},{"label":"and","var":"AND","max_gap":4},{"label":"prior","var":"MONEY","max_gap":0},{"label":"second_trigger","var":"LOWER","max_gap":1},{"label":"second_metric","var":"OPERATING_INCOME","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_each_value", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v268.higher_operating_income_pair" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["higher"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"current","var":"MONEY"},{"label":"trigger","var":"HIGHER","max_gap":1},{"label":"metric","var":"OPERATING_INCOME","max_gap":0},{"label":"and","var":"AND","max_gap":4},{"label":"prior","var":"MONEY","max_gap":0},{"label":"second_trigger","var":"HIGHER","max_gap":1},{"label":"second_metric","var":"OPERATING_INCOME","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_each_value", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v268.higher_operating_income_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["higher"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"HIGHER"},{"label":"metric","var":"OPERATING_INCOME","max_gap":1},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v268.revenue_was_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v268.operating_income_was_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v268.operating_income_level_percent" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase", "decrease", "up", "down"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"amount","var":"MONEY","max_gap":2},{"label":"or","var":"OR","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v268.operating_income_level_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increase", "decrease", "up", "down"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"level","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"value","var":"MONEY","max_gap":2},{"label":"or","var":"OR","max_gap":1},{"label":"percent","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v268.adjusted_operating_income_level_percent" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["adjusting"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"context","var":"ADJUST"},{"label":"metric","var":"OPERATING_INCOME","max_gap":45},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"amount","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}

text_rule "v268.adjusted_operating_income_level_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["adjusting"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"context","var":"ADJUST"},{"label":"metric","var":"OPERATING_INCOME","max_gap":45},{"label":"copula","var":"BE","max_gap":0},{"label":"level","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"value","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"percent","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 180
}

text_rule "v268.revenue_level_amount_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up", "down"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 190
}

text_rule "v268.revenue_decline_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["declined"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"DECLINE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 200
}

text_rule "v268.revenue_headwind_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["headwind"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"trigger","var":"HEADWIND","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 210
}

text_rule "v268.revenue_level_percent_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up", "down"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"amount","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 220
}

text_rule "v268.revenue_delta_amount" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["up", "down"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"level","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"percent","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 230
}

text_rule "v268.volume_decline" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["decline"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"DECLINE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 240
}

text_rule "v268.anticipated_revenue_growth" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["anticipate"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"trigger","var":"ANTICIPATE"},{"label":"accelerated","var":"ACCELERATE","optional":true,"max_gap":1},{"label":"metric","var":"REVENUE","max_gap":4},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 250
}

text_rule "v268.driven_operating_income_growth" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["driving"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"trigger","var":"DRIVE"},{"label":"value","var":"PERCENT","max_gap":0},{"label":"higher","var":"HIGHER","max_gap":0},{"label":"metric","var":"OPERATING_INCOME","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 260
}

text_rule "v268.organic_revenue_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["was"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"organic","var":"ORGANIC"},{"label":"metric","var":"REVENUE","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 270
}

text_rule "v268.revenue_growth_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["to be"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  relation_words = ["to"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"copula","var":"BE","max_gap":4},{"label":"low","var":"NUMBER","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 280
}

text_rule "v268.revenue_guidance_midpoint_raise" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["raising"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"GUIDANCE","max_gap":0},{"label":"range","var":"RANGE","max_gap":0},{"label":"trigger","var":"RAISE","max_gap":9},{"label":"value","var":"MONEY","max_gap":1},{"label":"at","var":"AT","max_gap":0},{"label":"midpoint","var":"MIDPOINT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 290
}

text_rule "v268.revenue_guidance_growth" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["up"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"GUIDANCE","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":22},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 300
}

text_rule "v268.operating_margin_at" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["at"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"at","var":"AT","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 310
}

text_rule "v268.operating_margin_higher_values" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["higher"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"HIGHER","max_gap":1},{"label":"at","var":"AT","max_gap":4},{"label":"current","var":"PERCENT","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"second_metric","var":"OPERATING_MARGIN","max_gap":2},{"label":"second_trigger","var":"HIGHER","max_gap":1},{"label":"second_at","var":"AT","max_gap":4},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 320
}

text_rule "v268.higher_sales_amounts" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["higher sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"HIGHER"},{"label":"metric","var":"REVENUE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":14},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 330
}
