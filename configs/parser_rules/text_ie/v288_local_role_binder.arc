# V2.8.8 local role binder. Rules describe grammatical ownership rather than
# issuer vocabulary. Each fact requires an explicit metric, operator and local
# quantity; heading context may provide only the forward-looking state.

text_rule "v288.level_change_role" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["was", "increased", "up", "from", "reached"]
  concepts = ["REVENUE","GROSS_MARGIN","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v288.forward_role" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expected", "outlook", "range", "at least", "under"]
  concepts = ["REVENUE","GROSS_MARGIN","ADJUSTED_EBITDA","CAPEX","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v288.financial_role" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["net interest income", "promissory note", "operating income", "adjusted ebitda", "cash and cash equivalents"]
  concepts = ["REVENUE","DEBT","OPERATING_INCOME","ADJUSTED_EBITDA","CASH"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v288.strict_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["net loss", "tax expense", "liquidity", "per share", "milestone payment"]
  concepts = ["REVENUE","CASH","SHARES","ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 100
}
