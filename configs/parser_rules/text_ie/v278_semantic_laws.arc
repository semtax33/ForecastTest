# V2.7.8 issuer-neutral laws disclosed by the twentieth independent holdout.
# Patterns are spaCy token/concept/typed-quantity programs; no issuer callbacks
# and no regular-expression matching are used by this layer.

var "REVENUE" { expression = {"concept":"REVENUE"} }
var "GROSS_MARGIN" { expression = {"concept":"GROSS_MARGIN"} }
var "OPERATING_INCOME" { expression = {"concept":"OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept":"OPERATING_MARGIN"} }
var "DEBT" { expression = {"concept":"DEBT"} }
var "CASH" { expression = {"concept":"CASH"} }
var "SHARES" { expression = {"concept":"SHARES"} }
var "ACTIVITY_VOLUME" { expression = {"concept":"ACTIVITY_VOLUME"} }
var "BACKLOG" { expression = {"concept":"BACKLOG"} }
var "MONEY" { expression = {"quantity":"MONEY"} }
var "PERCENT" { expression = {"quantity":"PERCENT"} }
var "BASIS_POINTS" { expression = {"quantity":"BASIS_POINTS"} }
var "COUNT" { expression = {"quantity":"COUNT"} }
var "BE" { expression = {"lemma":"be"} }
var "BE_OR_OF" { expression = {"any":[{"lemma":"be"},{"lower":"of"}]} }
var "OF" { expression = {"lower":"of"} }
var "OR" { expression = {"lower":"or"} }
var "TO" { expression = {"lower":"to"} }
var "FROM" { expression = {"lower":"from"} }
var "BY" { expression = {"lower":"by"} }
var "IN" { expression = {"lower":"in"} }
var "AND" { expression = {"lower":"and"} }
var "UP" { expression = {"lower":"up"} }
var "VERSUS" { expression = {"any":[{"lower":"versus"},{"lower":"vs."},{"lower":"vs"}]} }
var "COMPARE" { expression = {"lemma":"compare"} }
var "INCREASE" { expression = {"lemma":"increase"} }
var "DECREASE" { expression = {"lemma":"decrease"} }
var "GROW" { expression = {"lemma":"grow"} }
var "DRIVE" { expression = {"lemma":"drive"} }
var "REPRESENT" { expression = {"lemma":"represent"} }
var "REFLECT" { expression = {"lemma":"reflect"} }
var "GUIDANCE" { expression = {"lower":"guidance"} }
var "RANGE" { expression = {"lower":"range"} }
var "BENEFIT" { expression = {"lower":"benefit"} }
var "GROWTH" { expression = {"lemma":"growth"} }
var "YIELD" { expression = {"lower":"yield"} }
var "ORGANIC" { expression = {"lower":"organic"} }
var "UNDERLYING" { expression = {"lower":"underlying"} }
var "DECLINE" { expression = {"lemma":"decline"} }
var "AROUND" { expression = {"any":[{"lower":"around"},{"lower":"approximately"}]} }
var "INCLUDE" { expression = {"lemma":"include"} }
var "FAVORABLE" { expression = {"lower":"favorable"} }
var "CURRENCY" { expression = {"lower":"currency"} }
var "IMPACT" { expression = {"lemma":"impact"} }

text_rule "v278.gross_profit_sales_margin" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["gross profit", "of sales"]
  concepts = ["GROSS_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"GROSS_MARGIN"},{"label":"first_or","var":"OR","max_gap":30},{"label":"current","var":"PERCENT","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"denominator","var":"REVENUE","max_gap":0},{"label":"from","var":"FROM","max_gap":6},{"label":"second_or","var":"OR","max_gap":6},{"label":"prior","var":"PERCENT","max_gap":0},{"label":"prior_of","var":"OF","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v278.diluted_eps_share_comparison" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["diluted earnings per common share", "shares versus"]
  concepts = ["SHARES"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"current","var":"COUNT"},{"label":"metric","var":"SHARES","max_gap":0},{"label":"versus","var":"VERSUS","max_gap":0},{"label":"prior","var":"COUNT","max_gap":5}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_count","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v278.operating_income_footnoted_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["income from operations", "operating profit"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":12},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v278.revenue_level_then_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["revenue increased", "sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"value","var":"MONEY","max_gap":2},{"label":"trigger","var":"UP","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v278.revenue_growth_then_level" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["revenue increased", "sales increased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v278.net_interest_income_dual_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["net interest income", "up"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":0},{"label":"trigger","var":"UP","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_each_value","emit_base_metric","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v278.revenue_and_organic_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["net revenues increased", "organic net revenue growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"current","var":"PERCENT","max_gap":0},{"label":"drive","var":"DRIVE","max_gap":1},{"label":"underlying","var":"UNDERLYING","optional":true,"max_gap":3},{"label":"organic","var":"ORGANIC","max_gap":0},{"label":"organic_metric","var":"REVENUE","max_gap":1},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_each_value","emit_base_metric","resolve_polarity","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v278.revenue_currency_component" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["currency impact", "including"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"include","var":"INCLUDE","max_gap":12},{"label":"value","var":"PERCENT","max_gap":0},{"label":"favorable","var":"FAVORABLE","optional":true,"max_gap":0},{"label":"currency","var":"CURRENCY","max_gap":0},{"label":"impact","var":"IMPACT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_base_metric","resolve_polarity","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 75
}

text_rule "v278.yield_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["revenue growth", "average yield"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"growth","var":"GROWTH","max_gap":0},{"label":"from","var":"FROM","max_gap":0},{"label":"yield","var":"YIELD","max_gap":2},{"label":"copula","var":"BE","max_gap":5},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_base_metric","resolve_polarity","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v278.volume_revenue_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["volume decreased", "revenue by"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"cause","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"DECREASE","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":4},{"label":"by","var":"BY","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_base_metric","resolve_polarity","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v278.revenue_guidance_revision_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["guidance range", "to a range"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"GUIDANCE","max_gap":0},{"label":"range_word","var":"RANGE","max_gap":0},{"label":"by","var":"BY","max_gap":0},{"label":"delta","var":"MONEY","max_gap":0},{"label":"first_to","var":"TO","max_gap":0},{"label":"range","var":"RANGE","max_gap":2},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v278.revenue_guidance_revision_delta" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["guidance range", "increasing"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"GUIDANCE","max_gap":0},{"label":"range_word","var":"RANGE","max_gap":0},{"label":"by","var":"BY","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"to","var":"TO","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_base_metric","resolve_polarity","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v278.revenue_growth_guidance_component" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["revenue guidance", "benefit"]
  concepts = ["REVENUE"]
  quantity_kinds = ["BASIS_POINTS"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"GUIDANCE","max_gap":0},{"label":"reflect","var":"REFLECT","max_gap":3},{"label":"benefit","var":"BENEFIT","max_gap":8},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"BASIS_POINTS","max_gap":1},{"label":"in","var":"IN","max_gap":0},{"label":"growth","var":"GROWTH","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_base_metric","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v278.current_revenue_guidance_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["revenue guidance", "raised"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"guidance","var":"GUIDANCE","max_gap":0},{"label":"first_to","var":"TO","max_gap":0},{"label":"low","var":"MONEY","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"MONEY","max_gap":0},{"label":"from","var":"FROM","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v278.debt_decrease_dual" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["borrowings decreased", "decreased"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY","PERCENT"]
  pattern = [{"label":"metric","var":"DEBT"},{"label":"trigger","var":"DECREASE","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_each_value","emit_base_metric","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v278.debt_increase_dual" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["debt increased", "increased"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY","PERCENT"]
  pattern = [{"label":"metric","var":"DEBT"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"current","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_each_value","emit_base_metric","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v278.activity_volume_growth" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["volumes grew", "volume grew"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"GROW","max_gap":0},{"label":"by","var":"BY","optional":true,"max_gap":0},{"label":"around","var":"AROUND","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","emit_base_metric","resolve_polarity","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v278.activity_volume_decline_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["shipment volume", "decline"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"DECLINE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"low","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"high","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}

text_rule "v278.revenue_parallel_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["representing", "growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE_OR_OF","max_gap":2},{"label":"value","var":"MONEY","max_gap":0},{"label":"represent","var":"REPRESENT","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0},{"label":"first_growth","var":"GROWTH","max_gap":10},{"label":"and","var":"AND","max_gap":0},{"label":"secondary_change","var":"PERCENT","max_gap":0},{"label":"second_growth","var":"GROWTH","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 180
}

text_rule "v278.cash_extended_comparison" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["cash equivalents", "marketable securities", "compared"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CASH"},{"label":"copula","var":"BE","max_gap":24},{"label":"current","var":"MONEY","max_gap":0},{"label":"compare","var":"COMPARE","max_gap":1},{"label":"to","var":"TO","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 190
}

text_rule "v278.reverse_operating_margin_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating margin", "profit margin"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"metric","var":"OPERATING_MARGIN","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_percent","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 195
}

text_rule "v278.backlog_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["backlog", "record"]
  concepts = ["BACKLOG"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"BACKLOG"},{"label":"value","var":"MONEY","max_gap":4}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles","require_same_clause","normalize_money","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 200
}

text_rule "v278.semantic_bullet_highlights" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["highlights"]
  concepts = ["REVENUE","OPERATING_INCOME","OPERATING_MARGIN","BACKLOG"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 210
}
