# V2.7.0 laws derived from the disclosed twelfth holdout.  Rules are
# issuer-neutral and bind values to explicit semantic roles only.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "GROSS_MARGIN" { expression = {"concept": "GROSS_MARGIN"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "SHARES" { expression = {"concept": "SHARES"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "COUNT" { expression = {"quantity": "COUNT"} }
var "BE" { expression = {"lemma": "be"} }
var "HIGHER" { expression = {"lower": "higher"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "ORGANIC" { expression = {"lower": "organic"} }
var "CONSTANT" { expression = {"lower": "constant"} }
var "CURRENCY" { expression = {"lower": "currency"} }
var "REPRESENT" { expression = {"lemma": "represent"} }
var "BENEFIT" { expression = {"lemma": "benefit"} }
var "PROJECT" { expression = {"lemma": "project"} }
var "AS" { expression = {"lower": "as"} }
var "A" { expression = {"lower": "a"} }
var "PERCENT_WORD" { expression = {"lower": "percent"} }
var "OF" { expression = {"lower": "of"} }
var "ON" { expression = {"lower": "on"} }
var "IN" { expression = {"lower": "in"} }
var "AND" { expression = {"lower": "and"} }
var "TO" { expression = {"lower": "to"} }

text_rule "v270.revenue_level_percent_higher" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["higher"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":3},{"label":"value","var":"MONEY","max_gap":0},{"label":"change","var":"PERCENT","max_gap":2},{"label":"trigger","var":"HIGHER","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v270.activity_volume_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["volume growth"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v270.gross_margin_percent_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["gross margin"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"GROSS_MARGIN"},{"label":"as","var":"AS","max_gap":0},{"label":"article","var":"A","optional":true,"max_gap":0},{"label":"percent_word","var":"PERCENT_WORD","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"revenue","var":"REVENUE","max_gap":0},{"label":"second_of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v270.operating_margin_percent_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"as","var":"AS","max_gap":0},{"label":"article","var":"A","optional":true,"max_gap":0},{"label":"percent_word","var":"PERCENT_WORD","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"revenue","var":"REVENUE","max_gap":0},{"label":"second_of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v270.organic_secondary_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["organic"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"and","var":"AND","max_gap":20},{"label":"value","var":"PERCENT","max_gap":0},{"label":"organic","var":"ORGANIC","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v270.constant_currency_secondary_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["constant currency"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"value","var":"PERCENT","max_gap":30},{"label":"in","var":"IN","max_gap":0},{"label":"constant","var":"CONSTANT","max_gap":0},{"label":"currency","var":"CURRENCY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v270.revenue_representing_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["representing"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"REPRESENT","max_gap":5},{"label":"change","var":"PERCENT","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":8}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v270.guidance_representing_growth" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["representing year-over-year growth", "representing year over year growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"REPRESENT","max_gap":24},{"label":"growth","var":"GROWTH","max_gap":5},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v270.fx_benefit_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["foreign exchange benefit"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"BENEFIT"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"on","var":"ON","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":6}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v270.shares_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["shares outstanding"]
  concepts = ["SHARES"]
  quantity_kinds = ["COUNT"]
  relation_words = ["to"]
  pattern = [{"label":"low","var":"COUNT"},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"COUNT","max_gap":0},{"label":"metric","var":"SHARES","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_count", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v270.projected_operating_margin" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["project"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"PROJECT"},{"label":"metric","var":"OPERATING_MARGIN","max_gap":2},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}
