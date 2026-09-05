# V2.7.4 issuer-neutral laws derived from the disclosed sixteenth holdout.
# Typed concepts, token roles, and quantities are executed by spaCy; no regex.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "ADJUSTED_EBITDA" { expression = {"concept": "ADJUSTED_EBITDA"} }
var "ORDERS" { expression = {"concept": "ORDERS"} }
var "CASH" { expression = {"concept": "CASH"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "EBIT" { expression = {"concept": "EBIT"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "BE" { expression = {"lemma": "be"} }
var "INCLUDE" { expression = {"lemma": "include"} }
var "ESTIMATE" { expression = {"lemma": "estimate"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "REPRESENT" { expression = {"lemma": "represent"} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "DECREASE" { expression = {"lemma": "decrease"} }
var "SURPASS" { expression = {"lemma": "surpass"} }
var "DELIVER" { expression = {"lemma": "deliver"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "APPROXIMATELY" { expression = {"lemma": "approximately"} }
var "COMPARED" { expression = {"lemma": "compare"} }
var "OF" { expression = {"lower": "of"} }
var "TO" { expression = {"lower": "to"} }
var "UP" { expression = {"lower": "up"} }
var "AND" { expression = {"lower": "and"} }
var "A" { expression = {"any": [{"lower": "a"}, {"lower": "an"}]} }
var "ARTICLE" { expression = {"any": [{"lower": "a"}, {"lower": "the"}]} }
var "WITH" { expression = {"lower": "with"} }
var "AT" { expression = {"lower": "at"} }
var "IN" { expression = {"lower": "in"} }
var "RANGE" { expression = {"lower": "range"} }
var "COLON" { expression = {"lower": ":"} }

text_rule "v274.adjusted_ebitda_was_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["adjusted ebitda"]
  concepts = ["ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"ADJUSTED_EBITDA"},{"label":"copula","var":"BE","max_gap":14},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v274.orders_including_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["including"]
  concepts = ["ORDERS"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"ORDERS"},{"label":"of","var":"OF","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"including","var":"INCLUDE","max_gap":1},{"label":"prior","var":"MONEY","max_gap":0},{"label":"second_of","var":"OF","max_gap":0},{"label":"second_metric","var":"ORDERS","max_gap":2}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v274.revenue_estimated_growth_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["estimates"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"trigger","var":"ESTIMATE"},{"label":"metric","var":"REVENUE","max_gap":1},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"to","var":"TO","max_gap":20},{"label":"copula","var":"BE","max_gap":0},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"range_to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v274.revenue_representing_increase" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["representing"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"REPRESENT","max_gap":1},{"label":"article","var":"A","optional":true,"max_gap":0},{"label":"increase","var":"INCREASE","max_gap":0},{"label":"second_of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v274.operating_income_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"compared","var":"COMPARED","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v274.cash_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CASH"},{"label":"copula","var":"BE","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"compared","var":"COMPARED","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v274.revenue_surpassing_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["surpassing"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"SURPASS"},{"label":"value","var":"MONEY","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":3}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v274.revenue_growth_to_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"increase","var":"INCREASE","max_gap":0},{"label":"growth","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"compared","var":"COMPARED","max_gap":0},{"label":"second_to","var":"TO","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v274.activity_volume_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["decreased", "increased"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"DECREASE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v274.ebit_decrease_money" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["decrease"]
  concepts = ["EBIT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"EBIT"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"article","var":"A","max_gap":1},{"label":"trigger","var":"DECREASE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v274.ebit_up_money" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up"]
  concepts = ["EBIT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"EBIT"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"UP","max_gap":1},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v274.revenue_delivered_of_reported_fx" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["delivered"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"trigger","var":"DELIVER"},{"label":"value","var":"MONEY","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0},{"label":"up","var":"UP","max_gap":8},{"label":"change","var":"PERCENT","max_gap":0},{"label":"and","var":"AND","max_gap":8},{"label":"second_up","var":"UP","max_gap":0},{"label":"secondary","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v274.revenue_contextual_colon_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["sales", "revenue"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"colon","var":"COLON","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v274.operating_income_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["operating income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"UP","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v274.operating_margin_at_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"at","var":"AT","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v274.revenue_expected_money_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expected", "range"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":2},{"label":"expected","var":"EXPECT","max_gap":1},{"label":"second_copula","var":"BE","max_gap":1},{"label":"in","var":"IN","max_gap":0},{"label":"article","var":"ARTICLE","max_gap":0},{"label":"range","var":"RANGE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}
