# V2.7.1 issuer-neutral laws derived from the disclosed thirteenth holdout.
# Symbols, token roles, and economic concepts are matched by spaCy; no regex.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "GROSS_MARGIN" { expression = {"concept": "GROSS_MARGIN"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "CAPEX" { expression = {"concept": "CAPEX"} }
var "CASH" { expression = {"concept": "CASH"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "BE" { expression = {"lemma": "be"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "grow"}, {"lower": "up"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "GROW" { expression = {"lemma": "grow"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "REACH" { expression = {"lemma": "reach"} }
var "TOTAL" { expression = {"lemma": "total"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "BETWEEN" { expression = {"lower": "between"} }
var "OF" { expression = {"lower": "of"} }
var "TO" { expression = {"lower": "to"} }
var "OR" { expression = {"lower": "or"} }
var "AND" { expression = {"lower": "and"} }
var "A" { expression = {"lower": "a"} }
var "PLUS_SIGN" { expression = {"lower": "+"} }
var "SLASH_MINUS" { expression = {"lower": "/-"} }
var "DASH" { expression = {"lower": "-"} }

text_rule "v271.revenue_absolute_tolerance_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["+/-"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"value","var":"MONEY","max_gap":3},{"label":"plus","var":"PLUS_SIGN","max_gap":1},{"label":"minus","var":"SLASH_MINUS","max_gap":0},{"label":"tolerance","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v271.gross_margin_relative_tolerance_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["+/-"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"metric","var":"GROSS_MARGIN"},{"label":"value","var":"PERCENT","max_gap":8},{"label":"plus","var":"PLUS_SIGN","max_gap":1},{"label":"minus","var":"SLASH_MINUS","max_gap":0},{"label":"tolerance","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v271.operating_margin_compact_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v271.operating_margin_reverse_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"metric","var":"OPERATING_MARGIN","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v271.operating_margin_dash_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  relation_words = ["-"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"low","var":"PERCENT","max_gap":1},{"label":"dash","var":"DASH","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v271.operating_income_money_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v271.operating_income_ratio_margin" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["percent of revenue"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"of","var":"OF","max_gap":0},{"label":"income","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0},{"label":"second_of","var":"OF","max_gap":0},{"label":"revenue","var":"REVENUE","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v271.revenue_was_percent_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":16},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":6}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v271.revenue_was_money_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":16},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v271.operating_income_level_percent_increase" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"value","var":"MONEY","max_gap":2},{"label":"article","var":"A","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v271.capex_between_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expected"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  relation_words = ["between"]
  pattern = [{"label":"metric","var":"CAPEX"},{"label":"copula","var":"BE","max_gap":2},{"label":"trigger","var":"EXPECT","max_gap":0},{"label":"between","var":"BETWEEN","max_gap":3},{"label":"low","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v271.revenue_growth_to_level" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"MONEY","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v271.revenue_reached_up" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["reached"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"REACH","max_gap":2},{"label":"value","var":"MONEY","max_gap":3},{"label":"change_cue","var":"CHANGE","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v271.activity_assets_growth_to_level" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["grew"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"GROW","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":8},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v271.cash_and_investments_total" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["totaled"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CASH"},{"label":"and","var":"AND","max_gap":0},{"label":"total","var":"TOTAL","max_gap":8},{"label":"value","var":"MONEY","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}
