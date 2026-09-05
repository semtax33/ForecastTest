# V2.7.3 issuer-neutral laws derived from the disclosed fifteenth holdout.
# Patterns are executed by spaCy over typed concepts and quantities; no regex.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "GROSS_MARGIN" { expression = {"concept": "GROSS_MARGIN"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "BPS" { expression = {"quantity": "BASIS_POINTS"} }
var "BE" { expression = {"lemma": "be"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "decrease"}, {"lemma": "contract"}, {"lemma": "rise"}, {"lower": "up"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "REPRESENT" { expression = {"lemma": "represent"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "GROW" { expression = {"lemma": "grow"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "RANGE" { expression = {"lower": "range"} }
var "APPROXIMATELY" { expression = {"lemma": "approximately"} }
var "CONTRACT" { expression = {"lemma": "contract"} }
var "REPRESENTING" { expression = {"lemma": "represent"} }
var "TOTAL" { expression = {"lower": "total"} }
var "CONSTANT_CURRENCY" { expression = {"lower": "constant currency"} }
var "USD" { expression = {"lower": "usd"} }
var "OF" { expression = {"lower": "of"} }
var "WHICH" { expression = {"lower": "which"} }
var "IN" { expression = {"lower": "in"} }
var "A" { expression = {"lower": "a"} }
var "ARTICLE" { expression = {"any": [{"lower": "a"}, {"lower": "the"}]} }
var "FROM" { expression = {"lower": "from"} }
var "TO" { expression = {"lower": "to"} }
var "UP" { expression = {"lower": "up"} }
var "OR" { expression = {"lower": "or"} }
var "AND" { expression = {"lower": "and"} }
var "COLON" { expression = {"lower": ":"} }

text_rule "v273.operating_income_parallel_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":8},{"label":"current","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"second_metric","var":"OPERATING_INCOME","max_gap":3},{"label":"second_copula","var":"BE","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v273.revenue_represents_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["represents"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"which","var":"WHICH","max_gap":1},{"label":"trigger","var":"REPRESENT","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":7}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v273.operating_income_money_increase" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increased"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v273.gross_margin_change_to_from" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["increased", "decreased"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"GROSS_MARGIN"},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"to","var":"TO","optional":true,"max_gap":0},{"label":"current","var":"PERCENT","max_gap":0},{"label":"from","var":"FROM","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v273.gross_margin_level_change_from" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["increased", "decreased"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"GROSS_MARGIN"},{"label":"of","var":"OF","max_gap":0},{"label":"current","var":"PERCENT","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"from","var":"FROM","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v273.revenue_growth_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expect", "expects"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"REVENUE","max_gap":8},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"article","var":"A","max_gap":0},{"label":"range","var":"RANGE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v273.gross_margin_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["gross margin"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"GROSS_MARGIN"},{"label":"in","var":"IN","max_gap":0},{"label":"article","var":"ARTICLE","max_gap":0},{"label":"range","var":"RANGE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v273.operating_margin_approximate_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"of","var":"OF","max_gap":0},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v273.revenue_reported_and_cc_pairs" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["constant currency"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"value","var":"MONEY","max_gap":2},{"label":"trigger","var":"UP","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0},{"label":"usd","var":"USD","max_gap":0},{"label":"and","var":"AND","max_gap":1},{"label":"second_up","var":"UP","max_gap":0},{"label":"cc_change","var":"PERCENT","max_gap":0},{"label":"cc","var":"CONSTANT_CURRENCY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v273.operating_income_reported_pairs" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["operating income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"UP","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v273.revenue_expected_growth_from_to" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expected"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":0},{"label":"trigger","var":"EXPECT","max_gap":0},{"label":"grow","var":"GROW","max_gap":1},{"label":"from","var":"FROM","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v273.operating_margin_contracted_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["contracted"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["BASIS_POINTS", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"CONTRACT","max_gap":0},{"label":"change","var":"BPS","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v273.operating_income_of_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating income", "earnings from operations"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v273.operating_income_was_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating income", "earnings from operations"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v273.revenue_colon_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["sales:", "revenue:"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"colon","var":"COLON","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v273.operating_income_colon_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["adjusted"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"colon","var":"COLON","max_gap":1},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v273.revenue_composition" {
  version = 1
  frame = "COMPOSITION"
  triggers = ["representing"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"trigger","var":"REPRESENTING"},{"label":"value","var":"PERCENT","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"total","var":"TOTAL","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":1}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}

text_rule "v273.operating_income_was_increased" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increased"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 180
}

text_rule "v273.revenue_was_increased_cc" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["constant currency"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":3},{"label":"value","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"up","var":"UP","max_gap":1},{"label":"cc_change","var":"PERCENT","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"cc","var":"CONSTANT_CURRENCY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 190
}
