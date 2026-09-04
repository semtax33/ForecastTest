# V2.6.9 laws derived from the disclosed eleventh holdout.  They describe
# issuer-neutral semantic roles; no issuer names or document hashes are used.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "PRICE_REALIZATION" { expression = {"concept": "PRICE_REALIZATION"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "CASH" { expression = {"concept": "CASH"} }
var "DEBT" { expression = {"concept": "DEBT"} }
var "CAPEX" { expression = {"concept": "CAPEX"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "COUNT" { expression = {"quantity": "COUNT"} }
var "NUMBER" { expression = {"like_num": true} }
var "BE" { expression = {"lemma": "be"} }
var "TOTAL" { expression = {"lemma": "total"} }
var "HAVE" { expression = {"lemma": "have"} }
var "SPEND" { expression = {"lemma": "spend"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "GROW" { expression = {"lemma": "grow"} }
var "REACH" { expression = {"lemma": "reach"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "decrease"}, {"lemma": "grow"}, {"lemma": "decline"}, {"lower": "up"}, {"lower": "down"}]} }
var "HIGHER" { expression = {"lower": "higher"} }
var "LOWER" { expression = {"lower": "lower"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "CALL" { expression = {"lemma": "call"} }
var "RANGE" { expression = {"lemma": "range"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "ORGANIC" { expression = {"lower": "organic"} }
var "CONSTANT" { expression = {"lower": "constant"} }
var "CURRENCY" { expression = {"lower": "currency"} }
var "FIRST" { expression = {"lower": "first"} }
var "HALF" { expression = {"lower": "half"} }
var "CC" { expression = {"lower": "cc"} }
var "PROJECTED" { expression = {"lemma": "project"} }
var "APPROXIMATELY" { expression = {"lower": "approximately"} }
var "OF" { expression = {"lower": "of"} }
var "IN" { expression = {"lower": "in"} }
var "ON" { expression = {"lower": "on"} }
var "FOR" { expression = {"lower": "for"} }
var "TO" { expression = {"lower": "to"} }
var "AND" { expression = {"lower": "and"} }

text_rule "v269.revenue_money_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["range"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  relation_words = ["to"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"range","var":"RANGE","max_gap":4},{"label":"low","var":"MONEY","max_gap":2},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v269.price_change_component" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["higher", "lower"]
  concepts = ["PRICE_REALIZATION"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"trigger","var":"HIGHER","optional":true,"max_gap":1},{"label":"negative_trigger","var":"LOWER","optional":true,"max_gap":1},{"label":"metric","var":"PRICE_REALIZATION","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v269.volume_change_component" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["higher", "lower", "growth"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"higher","var":"HIGHER","optional":true,"max_gap":1},{"label":"lower","var":"LOWER","optional":true,"max_gap":1},{"label":"metric","var":"ACTIVITY_VOLUME","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v269.cash_totaled_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["totaled"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CASH"},{"label":"trigger","var":"TOTAL","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v269.debt_totaled_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["totaled"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"DEBT"},{"label":"trigger","var":"TOTAL","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v269.cash_had_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["had"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"HAVE"},{"label":"value","var":"MONEY","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"metric","var":"CASH","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v269.debt_of_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["debt"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"value","var":"MONEY"},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"DEBT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v269.margin_guidance_percent_of_revenue" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["guidance"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":3},{"label":"value","var":"PERCENT","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"projected","var":"PROJECTED","max_gap":0},{"label":"revenue","var":"REVENUE","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v269.multi_margin_guidance_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["guidance"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"guidance","var":"GUIDANCE","max_gap":1},{"label":"value","var":"PERCENT","min":2,"max":2,"max_gap":12}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v269.multi_margin_levels" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"value","var":"PERCENT","min":2,"max":2,"max_gap":10}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_each_value", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v269.expected_revenue_level_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["expect"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"EXPECT"},{"label":"metric","var":"REVENUE","max_gap":5},{"label":"grow","var":"GROW","max_gap":3},{"label":"change","var":"PERCENT","max_gap":2},{"label":"to","var":"TO","max_gap":6},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v269.capex_spent_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["spent"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"SPEND"},{"label":"value","var":"MONEY","max_gap":0},{"label":"on","var":"ON","max_gap":0},{"label":"metric","var":"CAPEX","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v269.capex_was_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["were", "was"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CAPEX"},{"label":"copula","var":"BE","max_gap":0},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v269.revenue_word_percent_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increased", "decreased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v269.first_half_revenue_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["first half growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"first","var":"FIRST","max_gap":24},{"label":"half","var":"HALF","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v269.constant_currency_secondary_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["in cc"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"and","var":"AND","max_gap":14},{"label":"value","var":"PERCENT","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"cc","var":"CC","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v269.signed_revenue_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["y/y", "year over year", "year-over-year"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"change","var":"PERCENT","max_gap":2}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}

text_rule "v269.adjusted_operating_income_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["adjusted operating profit increased", "adjusted operating income increased"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 180
}

text_rule "v269.revenue_growth_guidance_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["guidance calls for"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  relation_words = ["to"]
  pattern = [{"label":"guidance","var":"GUIDANCE"},{"label":"call","var":"CALL","max_gap":0},{"label":"for","var":"FOR","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 190
}

text_rule "v269.organic_cc_growth_guidance_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["organic constant currency growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  relation_words = ["to"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"organic","var":"ORGANIC","max_gap":12},{"label":"constant","var":"CONSTANT","max_gap":0},{"label":"currency","var":"CURRENCY","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 200
}

text_rule "v269.activity_volume_reaching_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["reaching", "reached"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"REACH","max_gap":14},{"label":"value","var":"COUNT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_count", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 210
}

text_rule "v269.revenue_change_then_level" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increased", "decreased", "grew", "declined"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":6},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 220
}
