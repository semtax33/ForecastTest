# V2.7.5 issuer-neutral laws derived from the disclosed seventeenth holdout.
# spaCy token roles and typed quantities only; no sentence regex or issuer callback.

var "REVENUE" { expression = {"concept": "REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept": "OPERATING_INCOME"} }
var "PRICE_REALIZATION" { expression = {"concept": "PRICE_REALIZATION"} }
var "ACTIVITY_VOLUME" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "CAPEX" { expression = {"concept": "CAPEX"} }
var "SHARES" { expression = {"concept": "SHARES"} }
var "EBIT" { expression = {"concept": "EBIT"} }
var "MONEY" { expression = {"quantity": "MONEY"} }
var "PERCENT" { expression = {"quantity": "PERCENT"} }
var "COUNT" { expression = {"quantity": "COUNT"} }
var "BE" { expression = {"lemma": "be"} }
var "INCREASE" { expression = {"lemma": "increase"} }
var "DECREASE" { expression = {"lemma": "decrease"} }
var "REPORT" { expression = {"lemma": "report"} }
var "REFLECT" { expression = {"lemma": "reflect"} }
var "REPRESENT" { expression = {"lemma": "represent"} }
var "ASSUME" { expression = {"lemma": "assume"} }
var "GOAL" { expression = {"lower": "goal"} }
var "IMPACT" { expression = {"lower": "impact"} }
var "LOSS" { expression = {"lower": "loss"} }
var "DECLINE" { expression = {"lower": "decline"} }
var "HIGHER" { expression = {"lower": "higher"} }
var "YOY" { expression = {"any": [{"lower": "yoy"}, {"lower": "yoy%"}]} }
var "FX_TAILWINDS" { expression = {"lower": "foreign currency tailwinds"} }
var "APPROXIMATELY" { expression = {"lemma": "approximately"} }
var "A" { expression = {"any": [{"lower": "a"}, {"lower": "an"}]} }
var "OF" { expression = {"lower": "of"} }
var "FROM" { expression = {"lower": "from"} }
var "TO" { expression = {"lower": "to"} }
var "IN" { expression = {"lower": "in"} }
var "ON" { expression = {"lower": "on"} }
var "FOR" { expression = {"lower": "for"} }
var "AND" { expression = {"lower": "and"} }
var "OR" { expression = {"lower": "or"} }
var "UP" { expression = {"lower": "up"} }
var "BETWEEN" { expression = {"lower": "between"} }

text_rule "v275.reported_revenue_change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["reported", "revenue"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"article","var":"A","max_gap":2},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"second_of","var":"OF","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v275.compact_product_sales" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["yoy", "sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"value","var":"MONEY","max_gap":0},{"label":"yoy","var":"YOY","max_gap":3},{"label":"change","var":"PERCENT","max_gap":2}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v275.revenue_reflecting_components" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["reflecting"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"reflect","var":"REFLECT","max_gap":30},{"label":"value","var":"PERCENT","max_gap":3}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v275.price_mix_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["price/mix"]
  concepts = ["PRICE_REALIZATION"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"PRICE_REALIZATION"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"of","var":"OF","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v275.volume_change_with_of" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["volume", "decrease"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"trigger","var":"DECREASE","max_gap":0},{"label":"of","var":"OF","optional":true,"max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v275.operating_loss_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["operating loss"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"OPERATING_INCOME"},{"label":"copula","var":"BE","max_gap":5},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v275.volume_impact_pair" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["volume impact"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"impact","var":"IMPACT","max_gap":0},{"label":"copula","var":"BE","max_gap":4},{"label":"current","var":"PERCENT","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"prior","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v275.residential_sales_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["residential sales", "higher"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"ACTIVITY_VOLUME"},{"label":"copula","var":"BE","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0},{"label":"higher","var":"HIGHER","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v275.industrial_volume_reverse_change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["industrial volume"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"value","var":"PERCENT"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"in","var":"IN","max_gap":0},{"label":"metric","var":"ACTIVITY_VOLUME","max_gap":1}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v275.ebit_loss_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["ebit loss"]
  concepts = ["EBIT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"EBIT"},{"label":"loss","var":"LOSS","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v275.revenue_reverse_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["revenue"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"value","var":"MONEY"},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"REVENUE","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}

text_rule "v275.ebit_was_money_increase" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["ebit", "increase"]
  concepts = ["EBIT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"EBIT"},{"label":"copula","var":"BE","max_gap":2},{"label":"value","var":"MONEY","max_gap":0},{"label":"article","var":"A","max_gap":2},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 120
}

text_rule "v275.ebit_of_money_up" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["ebit", "up"]
  concepts = ["EBIT"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"EBIT"},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"up","var":"UP","max_gap":1},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 130
}

text_rule "v275.revenue_percent_level_cc" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["constant dollar"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"change","var":"PERCENT","max_gap":0},{"label":"to","var":"TO","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"second_trigger","var":"INCREASE","max_gap":0},{"label":"secondary","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_polarity", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 140
}

text_rule "v275.revenue_decline_range" {
  version = 1
  frame = "COMPOSITION"
  triggers = ["representing", "decline"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"represent","var":"REPRESENT","max_gap":18},{"label":"decline","var":"DECLINE","max_gap":1},{"label":"of","var":"OF","max_gap":0},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 150
}

text_rule "v275.revenue_acquisition_fx" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["acquisitions", "foreign currency tailwinds"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":2},{"label":"value","var":"MONEY","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"fx","var":"FX_TAILWINDS","max_gap":0},{"label":"second_copula","var":"BE","max_gap":0},{"label":"change","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 160
}

text_rule "v275.diluted_share_outlook" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["outlook", "assumes"]
  concepts = ["SHARES"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"trigger","var":"ASSUME"},{"label":"approximately","var":"APPROXIMATELY","optional":true,"max_gap":0},{"label":"value","var":"COUNT","max_gap":0},{"label":"of","var":"OF","max_gap":0},{"label":"metric","var":"SHARES","max_gap":3}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 170
}

text_rule "v275.capex_comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["property and equipment", "decrease from"]
  concepts = ["CAPEX"]
  quantity_kinds = ["MONEY"]
  pattern = [{"label":"metric","var":"CAPEX"},{"label":"copula","var":"BE","max_gap":12},{"label":"current","var":"MONEY","max_gap":0},{"label":"decrease","var":"DECREASE","max_gap":14},{"label":"from","var":"FROM","max_gap":0},{"label":"prior","var":"MONEY","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 180
}

text_rule "v275.revenue_money_percent_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["sales increased"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY", "PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"trigger","var":"INCREASE","max_gap":0},{"label":"value","var":"MONEY","max_gap":0},{"label":"or","var":"OR","max_gap":1},{"label":"change","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "normalize_money", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 190
}

text_rule "v275.activity_goal_range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["goal", "between"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["COUNT"]
  pattern = [{"label":"goal","var":"GOAL"},{"label":"for","var":"FOR","max_gap":0},{"label":"metric","var":"ACTIVITY_VOLUME","max_gap":5},{"label":"copula","var":"BE","max_gap":5},{"label":"between","var":"BETWEEN","max_gap":0},{"label":"low","var":"COUNT","max_gap":0},{"label":"and","var":"AND","max_gap":0},{"label":"high","var":"COUNT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 200
}

text_rule "v275.revenue_mix_impact" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["acquisition and divestiture mix"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  pattern = [{"label":"metric","var":"REVENUE"},{"label":"copula","var":"BE","max_gap":1},{"label":"value","var":"PERCENT","max_gap":0}]
  backends = ["SEQUENCE"]
  operations = ["bind_labeled_roles", "require_same_clause", "emit_base_metric", "normalize_percent", "resolve_period", "resolve_scope", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 210
}
