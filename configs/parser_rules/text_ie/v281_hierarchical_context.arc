# V2.8.1 issuer-neutral hierarchical context laws disclosed by holdout 23B.
# spaCy phrase/token/sentence spans and typed quantities implement the laws.

var "REVENUE" { expression = {"concept":"REVENUE"} }
var "PRICE_REALIZATION" { expression = {"concept":"PRICE_REALIZATION"} }
var "ACTIVITY_VOLUME" { expression = {"concept":"ACTIVITY_VOLUME"} }
var "PRODUCTION" { expression = {"concept":"PRODUCTION"} }
var "ORDERS" { expression = {"concept":"ORDERS"} }
var "ADJUSTED_EBITDA" { expression = {"concept":"ADJUSTED_EBITDA"} }
var "OPERATING_MARGIN" { expression = {"concept":"OPERATING_MARGIN"} }
var "CAPEX" { expression = {"concept":"CAPEX"} }
var "MONEY" { expression = {"quantity":"MONEY"} }
var "PERCENT" { expression = {"quantity":"PERCENT"} }
var "BASIS_POINTS" { expression = {"quantity":"BASIS_POINTS"} }
var "COUNT" { expression = {"quantity":"COUNT"} }

text_rule "v281.local_revenue_context" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["revenue", "revenues", "sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v281.economic_driver_context" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["shipments", "passenger unit revenue", "booked", "supply"]
  concepts = ["PRICE_REALIZATION","ACTIVITY_VOLUME","ORDERS"]
  quantity_kinds = ["PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v281.physical_range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["production and shipments", "million metric tons", "respectively"]
  concepts = ["PRODUCTION","ACTIVITY_VOLUME"]
  quantity_kinds = ["COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v281.metric_comparison_context" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["adjusted ebitda", "compared to", "prior year"]
  concepts = ["ADJUSTED_EBITDA","REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v281.actual_level_change_context" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["new bookings", "were", "decrease", "increase"]
  concepts = ["ORDERS"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 45
}

text_rule "v281.parallel_margin_context" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["operating margin", "segment margin", "basis points"]
  concepts = ["OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v281.range_guidance_context" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["growth of", "expects", "expectation", "plan"]
  concepts = ["REVENUE","ORDERS","ADJUSTED_EBITDA","CAPEX"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v281.negative_context_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["cash used", "cash dividend", "cash returns", "repositioning sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 70
}
