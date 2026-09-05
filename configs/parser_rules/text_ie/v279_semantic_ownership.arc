# V2.7.9 issuer-neutral semantic ownership laws disclosed by the twenty-first-B
# independent holdout.  Runtime binders use spaCy token/dependency spans and
# typed quantities; no issuer callback, regular expression, or LLM is allowed.

var "REVENUE" { expression = {"concept":"REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept":"OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept":"OPERATING_MARGIN"} }
var "GROSS_MARGIN" { expression = {"concept":"GROSS_MARGIN"} }
var "CASH" { expression = {"concept":"CASH"} }
var "ORDERS" { expression = {"concept":"ORDERS"} }
var "PRICE_REALIZATION" { expression = {"concept":"PRICE_REALIZATION"} }
var "ACTIVITY_VOLUME" { expression = {"concept":"ACTIVITY_VOLUME"} }
var "MONEY" { expression = {"quantity":"MONEY"} }
var "PERCENT" { expression = {"quantity":"PERCENT"} }
var "BASIS_POINTS" { expression = {"quantity":"BASIS_POINTS"} }

text_rule "v279.clause_revenue_level_and_growth" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["net revenue", "net sales", "revenue"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v279.amount_before_metric_ownership" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["booked", "recognized"]
  concepts = ["ORDERS","REVENUE"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v279.revenue_expected_between_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["revenue expected between", "midpoint"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v279.revenue_unchanged_guidance_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["revenue guidance", "unchanged at"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v279.revenue_growth_reduction_guidance" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["expected to reduce", "net sales growth"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 45
}

text_rule "v279.revenue_bridge_components" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["benefit", "headwind", "price realization", "volume/mix"]
  concepts = ["REVENUE","PRICE_REALIZATION","ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v279.operating_income_level_and_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["operating profit", "operating income"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v279.margin_level_and_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["gross margin", "operating margin", "operating profit margin"]
  concepts = ["GROSS_MARGIN","OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}

text_rule "v279.margin_comparison" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["expanded from", "compared to"]
  concepts = ["GROSS_MARGIN","OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 80
}

text_rule "v279.margin_driver_component" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["basis point benefit", "basis points benefit"]
  concepts = ["GROSS_MARGIN","OPERATING_MARGIN"]
  quantity_kinds = ["BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 90
}

text_rule "v279.cash_comparison" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["cash and investments", "compared to"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 100
}

text_rule "v279.cash_level_and_change" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["cash and equivalents", "short-term investments"]
  concepts = ["CASH"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 110
}
