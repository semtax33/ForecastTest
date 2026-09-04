# V2.6.5 issuer-neutral semantic laws derived from the disclosed seventh
# holdout.  Every numeric role is labeled and bounded; no issuer callback or
# sentence-specific regular expression is allowed.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "BACKLOG" { expression = {"concept": "BACKLOG"} }
var "PRODUCTION" { expression = {"concept": "PRODUCTION"} }
var "CASH" { expression = {"concept": "CASH"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "BPS" { expression = {"quantity": "BASIS_POINTS"} }
var "COUNT" { expression = {"quantity": "COUNT"} }
var "NUMBER" { expression = {"like_num": true} }
var "OF" { expression = {"lower": "of"} }
var "TO" { expression = {"lower": "to"} }
var "FOR" { expression = {"lower": "for"} }
var "AND" { expression = {"lower": "and"} }
var "THAN" { expression = {"lower": "than"} }
var "MORE" { expression = {"lower": "more"} }
var "ABOUT" { expression = {"any": [{"lower": "about"}, {"lower": "approximately"}]} }
var "GREATER" { expression = {"lower": ">"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "decrease"}, {"lemma": "contract"}, {"lemma": "grow"}, {"lower": "up"}, {"lower": "down"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "HAVE" { expression = {"lemma": "have"} }
var "INCLUDE" { expression = {"lemma": "include"} }
var "RAISE" { expression = {"lemma": "raise"} }
var "REPORT" { expression = {"any": [{"lemma": "report"}, {"lemma": "announce"}]} }
var "AVERAGE" { expression = {"lemma": "average"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "OUTLOOK" { expression = {"lower": "outlook"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "ORGANIC" { expression = {"any": [{"lower": "organic"}, {"lower": "organically"}]} }
var "EXPANSION" { expression = {"lower": "expansion"} }
var "COMPARED" { expression = {"any": [{"lower": "compared"}, {"lower": "versus"}]} }
var "PLANNED" { expression = {"any": [{"lemma": "plan"}, {"lower": "planned"}]} }
var "CAGR" { expression = {"lower": "cagr"} }
var "MOEBD" { expression = {"any": [{"lower": "moebd"}, {"lower": "mboed"}]} }

text_rule "v265.operating_income_margin_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase", "increased"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT", "BASIS_POINTS"]
  relation_words = ["of"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"relation","var":"OF","max_gap":2},{"label":"value","var":"PERCENT","max_gap":1},{"label":"trigger","var":"INCREASE","max_gap":5},{"label":"link","var":"OF","max_gap":2},{"label":"change","var":"BPS","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v265.operating_margin_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["contracted", "decreased", "increased"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT", "BASIS_POINTS"]
  relation_words = ["to"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"CHANGE","max_gap":3},{"label":"change","var":"BPS","max_gap":2},{"label":"relation","var":"TO","max_gap":1},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v265.operating_margin_expansion_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expansion"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["BASIS_POINTS"]
  relation_words = ["to"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"EXPANSION","max_gap":2},{"label":"footnote","var":"NUMBER","optional":true,"max_gap":0},{"label":"link","var":"OF","max_gap":1},{"label":"low","var":"BPS","max_gap":1},{"label":"relation","var":"TO","max_gap":1},{"label":"high","var":"BPS","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v265.operating_margin_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["margin", "margins"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"relation","var":"OF","max_gap":3},{"label":"qualifier","var":"ABOUT","optional":true,"max_gap":1},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v265.total_sales_growth_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"qualifier","var":"GROWTH","max_gap":1},{"label":"relation","var":"OF","max_gap":3},{"label":"bound","var":"GREATER","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v265.organic_sales_growth_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["organic"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"organic","var":"ORGANIC"},{"label":"metric","var":"REVENUE","max_gap":1},{"label":"qualifier","var":"GROWTH","max_gap":1},{"label":"relation","var":"OF","max_gap":3},{"label":"bound","var":"GREATER","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v265.cash_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["had"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"HAVE"},{"label":"value","var":"MONEY","max_gap":3},{"label":"relation","var":"OF","max_gap":1},{"label":"metric","var":"CASH","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v265.included_cash_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["including"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"INCLUDE"},{"label":"value","var":"MONEY","max_gap":1},{"label":"relation","var":"OF","max_gap":1},{"label":"metric","var":"CASH","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v265.revenue_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["raising", "raises", "raised"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"RAISE"},{"label":"guidance","var":"GUIDANCE","max_gap":3},{"label":"for","var":"FOR","optional":true,"max_gap":1},{"label":"metric","var":"REVENUE","max_gap":3},{"label":"relation","var":"TO","max_gap":2},{"label":"approximation","var":"ABOUT","optional":true,"max_gap":1},{"label":"value","var":"MONEY","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v265.operating_income_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["raising", "raises", "raised"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"trigger","var":"RAISE"},{"label":"guidance","var":"GUIDANCE","max_gap":3},{"label":"metric","var":"OPERATING_INCOME","max_gap":15},{"label":"relation","var":"TO","max_gap":2},{"label":"approximation","var":"ABOUT","optional":true,"max_gap":1},{"label":"value","var":"MONEY","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v265.revenue_outlook" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["outlook"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"OUTLOOK","max_gap":1},{"label":"relation","var":"TO","max_gap":2},{"label":"approximation","var":"ABOUT","optional":true,"max_gap":1},{"label":"value","var":"MONEY","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v265.operating_income_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["reported"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"REPORT"},{"label":"current","var":"MONEY","max_gap":3},{"label":"relation","var":"OF","max_gap":2},{"label":"metric","var":"OPERATING_INCOME","max_gap":2},{"label":"comparator","var":"COMPARED","max_gap":12},{"label":"to","var":"TO","max_gap":1},{"label":"prior","var":"MONEY","max_gap":8}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v265.production_lower_bound" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["production"]
  concepts = ["PRODUCTION"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"metric","var":"PRODUCTION"},{"label":"relation","var":"OF","max_gap":2},{"label":"lower","var":"MORE","max_gap":1},{"label":"than","var":"THAN","max_gap":0},{"label":"value","var":"NUMBER","max_gap":0},{"label":"unit","var":"MOEBD","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_count", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v265.production_reported_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["averaged"]
  concepts = ["PRODUCTION"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"metric","var":"PRODUCTION"},{"label":"trigger","var":"AVERAGE","max_gap":2},{"label":"value","var":"COUNT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_count", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v265.production_cagr_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["planned"]
  concepts = ["PRODUCTION"]
  quantity_kinds = ["PERCENT"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"metric","var":"PRODUCTION"},{"label":"guidance","var":"PLANNED","max_gap":5},{"label":"value","var":"PERCENT","max_gap":1},{"label":"qualifier","var":"CAGR","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v265.backlog_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase", "increases", "increased"]
  concepts = ["BACKLOG"]
  quantity_kinds = ["MONEY"]
  relation_words = ["to"]
  pattern = [{"label":"trigger","var":"INCREASE"},{"label":"metric","var":"BACKLOG","max_gap":1},{"label":"relation","var":"TO","max_gap":2},{"label":"value","var":"MONEY","max_gap":2}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v265.organic_secondary_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["organically"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"current","var":"MONEY","max_gap":3},{"label":"primary_trigger","var":"CHANGE","max_gap":2},{"label":"primary_change","var":"PERCENT","max_gap":1},{"label":"and","var":"AND","max_gap":4},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"value","var":"PERCENT","max_gap":1},{"label":"qualifier","var":"ORGANIC","max_gap":1}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}
