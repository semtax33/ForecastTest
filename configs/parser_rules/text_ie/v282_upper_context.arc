# V2.8.2 issuer-neutral upper-context role laws disclosed by holdout 24.
# spaCy token, phrase, sentence, and section cues remain the execution substrate.

text_rule "v282.margin_role_context" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["adjusted ebit margin", "operating margin", "gross margin", "percentage points", "pp"]
  concepts = ["OPERATING_MARGIN","GROSS_MARGIN"]
  quantity_kinds = ["PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v282.revenue_role_context" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["revenue", "revenues", "sales", "comprised of", "respectively", "net sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v282.driver_role_context" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["realized rent", "net client cash flows", "net inflows", "volumes", "production"]
  concepts = ["PRICE_REALIZATION","ACTIVITY_VOLUME","PRODUCTION"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v282.metric_pair_context" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["adjusted ebit", "adjusted ebitda", "common shares", "respectively"]
  concepts = ["EBIT","ADJUSTED_EBITDA","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v282.semantic_ownership_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["cash and agency mbs", "net service revenue", "operating expenses", "net of"]
  concepts = ["CASH","REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 50
}
