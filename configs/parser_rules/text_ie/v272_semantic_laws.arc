# V2.7.2 issuer-neutral ownership laws derived from the disclosed fourteenth
# holdout.  Token roles and economic concepts are resolved by spaCy; no regex.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "DEBT" { expression = {"concept": "DEBT"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "BPS" { expression = {"quantity": "BASIS_POINTS"} }
var "BE" { expression = {"lemma": "be"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "decrease"}, {"lower": "up"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "REDUCE" { expression = {"lemma": "reduce"} }
var "DELIVER" { expression = {"lemma": "deliver"} }
var "EXPAND" { expression = {"lemma": "expand"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "HIGHER" { expression = {"lemma": "high"} }
var "COMPARED" { expression = {"lemma": "compare"} }
var "APPROXIMATELY" { expression = {"lemma": "approximately"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "MIDPOINT" { expression = {"lower": "midpoint"} }
var "RESPECTIVELY" { expression = {"lower": "respectively"} }
var "OF" { expression = {"lower": "of"} }
var "IN" { expression = {"lower": "in"} }
var "BY" { expression = {"lower": "by"} }
var "OR" { expression = {"lower": "or"} }
var "AND" { expression = {"lower": "and"} }
var "TO" { expression = {"lower": "to"} }
var "FROM" { expression = {"lower": "from"} }
var "UP" { expression = {"lower": "up"} }
var "DASH" { expression = {"lower": "-"} }

text_rule "v272.operating_margin_abbreviated_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"dash","var":"DASH","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 5
}

text_rule "v272.revenue_money_percent_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increased", "decreased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"amount_change","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v272.revenue_level_first_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":2},{"label":"second_of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v272.revenue_level_secondary_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increase"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"level","var":"MONEY","max_gap":0},{"label":"first_trigger","var":"INCREASE","max_gap":2},{"label":"first_of","var":"OF","max_gap":0},{"label":"first_change","var":"PERCENT","max_gap":0},{"label":"and","var":"AND","max_gap":12},{"label":"trigger","var":"INCREASE","max_gap":1},{"label":"second_of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v272.revenue_was_current_prior" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"change_trigger","var":"CHANGE","max_gap":2},{"label":"growth","var":"PERCENT","max_gap":1},{"label":"comparator","var":"COMPARED","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v272.revenue_of_current_prior" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":4},{"label":"current","var":"MONEY","max_gap":0},{"label":"change_trigger","var":"CHANGE","max_gap":0},{"label":"growth","var":"PERCENT","max_gap":0},{"label":"comparator","var":"COMPARED","max_gap":1},{"label":"to","var":"TO","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v272.debt_reduced_approximately" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["reduced", "reducing"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"REDUCE"},{"label":"metric","var":"DEBT","max_gap":1},{"label":"by","var":"BY","max_gap":0},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v272.revenue_delivered_level_up" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["delivered"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"trigger","var":"DELIVER"},{"label":"value","var":"MONEY","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0},{"label":"up","var":"UP","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v272.operating_margin_expanded_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["expanded"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["BASIS_POINTS", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"EXPAND","max_gap":1},{"label":"by","var":"BY","max_gap":0},{"label":"change","var":"BPS","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v272.operating_margin_level_up_bps" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT", "BASIS_POINTS"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0},{"label":"trigger","var":"UP","max_gap":1},{"label":"change","var":"BPS","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v272.operating_margin_increased_to_from" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["increased"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"current","var":"PERCENT","max_gap":0},{"label":"from","var":"FROM","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v272.operating_margin_compared_to" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"copula","var":"BE","max_gap":0},{"label":"current","var":"PERCENT","max_gap":0},{"label":"comparator","var":"COMPARED","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v272.revenue_guidance_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["expects"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"REVENUE","max_gap":5},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v272.revenue_guidance_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["expects", "guidance"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"REVENUE","max_gap":12},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0},{"label":"midpoint","var":"MIDPOINT","max_gap":4},{"label":"guidance","var":"GUIDANCE","max_gap":1}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v272.revenue_level_percent_higher" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["higher"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"change","var":"PERCENT","max_gap":1},{"label":"trigger","var":"HIGHER","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v272.operating_income_respectively" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["respectively"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"first_trigger","var":"INCREASE","max_gap":0},{"label":"first_delta","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"second_metric","var":"OPERATING_INCOME","max_gap":1},{"label":"second_of","var":"OF","max_gap":0},{"label":"second_value","var":"MONEY","max_gap":0},{"label":"second_trigger","var":"INCREASE","max_gap":0},{"label":"second_delta","var":"MONEY","max_gap":0},{"label":"up","var":"UP","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0},{"label":"second_and","var":"AND","max_gap":0},{"label":"second_percent","var":"PERCENT","max_gap":0},{"label":"respectively","var":"RESPECTIVELY","max_gap":1}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}
