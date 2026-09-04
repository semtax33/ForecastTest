# V2.6.6 semantic recovery laws.  These laws encode reusable role topology;
# issuer names and holdout-specific callbacks are forbidden.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept": "OPERATING_MARGIN"} }
var "CASH" { expression = {"concept": "CASH"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "BPS" { expression = {"quantity": "BASIS_POINTS"} }
var "BE" { expression = {"lemma": "be"} }
var "END" { expression = {"lemma": "end"} }
var "REPORT" { expression = {"lemma": "report"} }
var "CHANGE" { expression = {"any": [{"lemma": "increase"}, {"lemma": "grow"}, {"lower": "up"}]} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "EXPECT" { expression = {"lemma": "expect"} }
var "IMPACT" { expression = {"lemma": "impact"} }
var "COMPARED" { expression = {"lemma": "compare"} }
var "NEGATIVE" { expression = {"any": [{"lower": "negatively"}, {"lower": "negative"}]} }
var "OF" { expression = {"lower": "of"} }
var "FOR" { expression = {"lower": "for"} }
var "TO" { expression = {"lower": "to"} }
var "WITH" { expression = {"lower": "with"} }
var "FROM" { expression = {"lower": "from"} }
var "BY" { expression = {"lower": "by"} }
var "AND" { expression = {"lower": "and"} }
var "OR" { expression = {"lower": "or"} }
var "AT" { expression = {"lower": "at"} }
var "THAN" { expression = {"lower": "than"} }
var "PLUS" { expression = {"lower": "plus"} }
var "MINUS" { expression = {"lower": "minus"} }
var "GROWTH" { expression = {"lower": "growth"} }
var "GUIDANCE" { expression = {"lower": "guidance"} }
var "MIDPOINT" { expression = {"lower": "midpoint"} }
var "OPERATIONAL" { expression = {"lower": "operational"} }
var "ORGANIC" { expression = {"any": [{"lower": "organic"}, {"lower": "organically"}]} }
var "ADJUSTED" { expression = {"lemma": "adjust"} }
var "RECORD" { expression = {"lower": "record"} }
var "RANGE" { expression = {"lower": "range"} }
var "AROUND" { expression = {"any": [{"lower": "around"}, {"lower": "approximately"}]} }
var "HIGHER" { expression = {"lemma": "high"} }

text_rule "v266.operating_margin_was_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"copula","var":"BE","max_gap":1},{"label":"current","var":"PERCENT","max_gap":0},{"label":"comparator","var":"COMPARED","max_gap":8},{"label":"with","var":"WITH","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v266.operating_margin_increased_from_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["increased"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"of","var":"OF","max_gap":1},{"label":"current","var":"PERCENT","max_gap":0},{"label":"trigger","var":"INCREASE","max_gap":15},{"label":"from","var":"FROM","max_gap":0},{"label":"prior_metric","var":"OPERATING_MARGIN","max_gap":9},{"label":"prior_of","var":"OF","max_gap":1},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v266.ending_cash_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["ended"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"trigger","var":"END"},{"label":"with","var":"WITH","max_gap":4},{"label":"value","var":"MONEY","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"CASH","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v266.operating_income_level_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":1},{"label":"record","var":"RECORD","optional":true,"max_gap":2},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v266.operating_margin_level_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["up"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT", "BASIS_POINTS"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"copula","var":"BE","max_gap":5},{"label":"value","var":"PERCENT","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"change","var":"BPS","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v266.reported_sales_growth_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["reported"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"reported","var":"REPORT"},{"label":"metric","var":"REVENUE","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"relation","var":"TO","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v266.operational_sales_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["operational growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"primary_growth","var":"GROWTH","max_gap":0},{"label":"primary_of","var":"OF","max_gap":0},{"label":"primary","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"with","var":"WITH","max_gap":0},{"label":"qualifier","var":"OPERATIONAL","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v266.adjusted_operational_sales_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["adjusted operational growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"primary_growth","var":"GROWTH","max_gap":0},{"label":"primary_of","var":"OF","max_gap":0},{"label":"primary","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":7},{"label":"adjusted","var":"ADJUSTED","max_gap":0},{"label":"qualifier","var":"OPERATIONAL","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v266.reported_sales_midpoint_guidance" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["guidance"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  output_metric_suffix = "_GUIDANCE"
  pattern = [{"label":"guidance","var":"GUIDANCE"},{"label":"metric","var":"REVENUE","max_gap":4},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"at","var":"AT","max_gap":0},{"label":"midpoint","var":"MIDPOINT","max_gap":1}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v266.negative_sales_growth_impact" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["negatively"]
  concepts = ["REVENUE"]
  quantity_kinds = ["BASIS_POINTS"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"NEGATIVE","max_gap":12},{"label":"impact","var":"IMPACT","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"by","var":"BY","max_gap":0},{"label":"value","var":"BPS","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v266.relative_revenue_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expected"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  relation_words = ["plus", "minus"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"EXPECT","max_gap":2},{"label":"copula","var":"BE","max_gap":1},{"label":"midpoint","var":"MONEY","max_gap":0},{"label":"plus","var":"PLUS","max_gap":1},{"label":"minus","var":"MINUS","max_gap":1},{"label":"tolerance","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "derive_relative_range", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v266.net_sales_level_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["higher"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"relation","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"copula","var":"BE","max_gap":5},{"label":"change","var":"PERCENT","max_gap":0},{"label":"higher","var":"HIGHER","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v266.margin_change_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["expected"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["BASIS_POINTS"]
  output_metric_suffix = "_CHANGE_GUIDANCE"
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"EXPECT","max_gap":3},{"label":"range","var":"RANGE","max_gap":4},{"label":"around","var":"AROUND","max_gap":0},{"label":"value","var":"BPS","max_gap":0},{"label":"higher","var":"HIGHER","max_gap":0},{"label":"than","var":"THAN","max_gap":0},{"label":"prior_metric","var":"OPERATING_MARGIN","max_gap":8},{"label":"of","var":"OF","max_gap":1},{"label":"baseline","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v266.prior_margin_reference_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["expected"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"OPERATING_MARGIN"},{"label":"trigger","var":"EXPECT","max_gap":3},{"label":"range","var":"RANGE","max_gap":4},{"label":"around","var":"AROUND","max_gap":0},{"label":"delta","var":"BPS","max_gap":0},{"label":"higher","var":"HIGHER","max_gap":0},{"label":"than","var":"THAN","max_gap":0},{"label":"prior_metric","var":"OPERATING_MARGIN","max_gap":8},{"label":"of","var":"OF","max_gap":1},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v266.secondary_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["up"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"current","var":"MONEY","max_gap":15},{"label":"primary_trigger","var":"CHANGE","max_gap":1},{"label":"primary","var":"PERCENT","max_gap":0},{"label":"and","var":"AND","max_gap":5},{"label":"trigger","var":"CHANGE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_percent", "resolve_period", "resolve_scope", "emit_base_metric", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v266.segment_sales_record_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["record"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"for","var":"FOR","max_gap":0},{"label":"copula","var":"BE","max_gap":5},{"label":"record","var":"RECORD","max_gap":2},{"label":"value","var":"MONEY","max_gap":0},{"label":"trigger","var":"CHANGE","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0},{"label":"organic","var":"ORGANIC","optional":true,"max_gap":0}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}
