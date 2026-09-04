# V2.6.4 research laws. These are issuer-neutral semantic patterns compiled
# to spaCy PhraseMatcher/Matcher/DependencyMatcher primitives. Arbitrary
# Python callbacks are intentionally not part of the language.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "ORDERS" { expression = {"concept": "ORDERS"} }
var "CAPEX" { expression = {"concept": "CAPEX"} }
var "DEBT" { expression = {"concept": "DEBT"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "NUMBER" { expression = {"like_num": true} }
var "CHANGE" { expression = {"any": [{"lemma": "grow"}, {"lemma": "increase"}, {"lemma": "rise"}, {"lemma": "decrease"}, {"lemma": "decline"}, {"lemma": "fall"}, {"lower": "up"}, {"lower": "down"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "DECREASE" { expression = {"lemma": "decrease"} }
var "REDUCE" { expression = {"lemma": "reduce"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "BE" { expression = {"lemma": "be"} }
var "OF" { expression = {"lower": "of"} }
var "BY" { expression = {"lower": "by"} }
var "AND" { expression = {"lower": "and"} }
var "VERSUS" { expression = {"lower": "versus"} }
var "COMPARABLE" { expression = {"lower": "comparable"} }
var "ORGANIC" { expression = {"lower": "organic"} }
var "BOOKED" { expression = {"lemma": "book"} }
var "NET" { expression = {"lower": "net"} }
var "REPRESENT" { expression = {"lemma": "represent"} }
var "ATTRIBUTABLE" { expression = {"lower": "attributable to"} }
var "OFFSET" { expression = {"lower": "partially offset by"} }
var "FROM_INCREASE" { expression = {"lower": "from an increase"} }
var "POINTS_OF_GROWTH" { expression = {"lower": "points of that growth"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "RESPECTIVELY" { expression = {"lower": "respectively"} }
var "OPEN_PAREN" { expression = {"lower": "("} }
var "CLOSE_PAREN" { expression = {"lower": ")"} }
var "PERCENT_WORD" { expression = {"any": [{"lower": "percent"}, {"lower": "%"}]} }

text_rule "v264.operating_income_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["expect", "expects", "expected"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"OPERATING_INCOME","max_gap":10},{"label":"relation","var":"OF","optional":true,"max_gap":3},{"label":"value","var":"MONEY","max_gap":3}]
  backends = ["PHRASE", "SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v264.debt_reduction" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["reduced"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  relation_words = ["by"]
  pattern = [{"label":"metric","var":"DEBT"},{"label":"trigger","var":"REDUCE","max_gap":4},{"label":"relation","var":"BY","max_gap":2},{"label":"value","var":"MONEY","max_gap":5}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v264.booked_orders" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["booked"]
  concepts = ["ORDERS"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"trigger","var":"BOOKED"},{"label":"value","var":"NUMBER","max_gap":2},{"label":"qualifier","var":"NET","optional":true,"max_gap":1},{"label":"metric","var":"ORDERS","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_count", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v264.parenthesized_margin" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was", "were"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"BE","max_gap":3},{"label":"open","var":"OPEN_PAREN","max_gap":1},{"label":"value","var":"NUMBER","max_gap":0},{"label":"close","var":"CLOSE_PAREN","max_gap":0},{"label":"unit","var":"PERCENT_WORD","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_parenthesized_sign", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v264.order_composition" {
  version = 1
  frame = "COMPOSITION"
  triggers = ["representing", "represented"]
  concepts = ["ORDERS"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"trigger","var":"REPRESENT","max_gap":3},{"label":"metric","var":"ORDERS","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v264.capex_respectively" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["guidance"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"GUIDANCE"},{"label":"metric","var":"CAPEX","max_gap":12},{"label":"other","var":"MONEY","max_gap":5},{"label":"relation","var":"AND","max_gap":2},{"label":"value","var":"MONEY","max_gap":3},{"label":"qualifier","var":"RESPECTIVELY","max_gap":2}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v264.value_of_capex" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["capital expenditures", "capital expenditure"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"value","var":"MONEY"},{"label":"relation","var":"OF","max_gap":2},{"label":"metric","var":"CAPEX","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v264.compact_orders" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["orders"]
  concepts = ["ORDERS"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"ORDERS"},{"label":"value","var":"MONEY","max_gap":2},{"label":"change","var":"PERCENT","max_gap":3}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v264.compact_operating_income" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["operating profit", "operating income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"value","var":"MONEY","max_gap":2},{"label":"change","var":"PERCENT","max_gap":3}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v264.revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["grew", "increased", "decreased", "up", "down"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"CHANGE","max_gap":6},{"label":"value","var":"PERCENT","max_gap":5}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v264.organic_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["grew", "increased", "decreased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"qualifier","var":"ORGANIC"},{"label":"metric","var":"REVENUE","max_gap":2},{"label":"trigger","var":"CHANGE","max_gap":8},{"label":"value","var":"PERCENT","max_gap":3}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v264.operating_income_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["grew", "increased", "decreased", "up", "down"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"trigger","var":"CHANGE","max_gap":6},{"label":"value","var":"PERCENT","max_gap":4}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v264.comparable_operating_income_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["grew", "increased", "decreased"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"qualifier","var":"COMPARABLE"},{"label":"metric","var":"OPERATING_INCOME","max_gap":6},{"label":"trigger","var":"CHANGE","max_gap":5},{"label":"value","var":"PERCENT","max_gap":3}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v264.operating_income_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["growth"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"relation","var":"GROWTH","max_gap":2},{"label":"trigger","var":"BE","max_gap":2},{"label":"value","var":"PERCENT","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v264.points_of_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["points of that growth"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"baseline","var":"PERCENT","max_gap":8},{"label":"value","var":"NUMBER","max_gap":12},{"label":"relation","var":"POINTS_OF_GROWTH","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v264.operating_margin_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["versus"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"BE","max_gap":5},{"label":"value","var":"PERCENT","max_gap":2},{"label":"relation","var":"VERSUS","max_gap":2},{"label":"prior","var":"PERCENT","max_gap":2}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v264.comparable_operating_margin" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["versus"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"qualifier","var":"COMPARABLE"},{"label":"metric","var":"OPERATING_MARGIN","max_gap":2},{"label":"trigger","var":"BE","max_gap":5},{"label":"value","var":"PERCENT","max_gap":2},{"label":"relation","var":"VERSUS","max_gap":2},{"label":"prior","var":"PERCENT","max_gap":2}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}

text_rule "v264.revenue_attributable_increase" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["attributable to"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"relation","var":"ATTRIBUTABLE","max_gap":14},{"label":"trigger","var":"INCREASE","max_gap":2},{"label":"link","var":"OF","max_gap":1},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 180
}

text_rule "v264.revenue_attributable_decrease" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["attributable to"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"relation","var":"ATTRIBUTABLE","max_gap":14},{"label":"trigger","var":"DECREASE","max_gap":2},{"label":"link","var":"OF","max_gap":1},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 190
}

text_rule "v264.revenue_offset_increase" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["partially offset by"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"relation","var":"OFFSET","max_gap":30},{"label":"trigger","var":"INCREASE","max_gap":2},{"label":"link","var":"OF","max_gap":1},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 200
}

text_rule "v264.revenue_offset_decrease" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["partially offset by"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"relation","var":"OFFSET","max_gap":30},{"label":"trigger","var":"DECREASE","max_gap":2},{"label":"link","var":"OF","max_gap":1},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 210
}

text_rule "v264.revenue_followup_increase" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["from an increase"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"FROM_INCREASE","max_gap":35},{"label":"value","var":"PERCENT","max_gap":10}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 220
}
