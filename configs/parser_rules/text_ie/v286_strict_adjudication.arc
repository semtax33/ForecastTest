# V2.8.6 strict block adjudication. A V286 decision replaces inherited frames
# for that block. Parent/heading context may mark a role as forward-looking but
# never supplies a numeric value.

text_rule "v286.revenue_ownership" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["revenue was", "revenue increased", "record revenue", "revenue constituted"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v286.forward_ownership" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["outlook", "guidance", "projected", "long-term annual revenue"]
  concepts = ["REVENUE","GROSS_MARGIN","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v286.balance_activity_ownership" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["cash balance", "effective backlog", "test volume", "sales volumes"]
  concepts = ["CASH","BACKLOG","ACTIVITY_VOLUME"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v286.profitability_ownership" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["adjusted ebitda", "ebitda margin", "gross margin", "operating margin", "operating income"]
  concepts = ["ADJUSTED_EBITDA","ADJUSTED_EBITDA_MARGIN","GROSS_MARGIN","OPERATING_MARGIN","OPERATING_INCOME"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v286.financing_ownership" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["prepay", "incremental borrowings"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = true
  require_unique_value = true
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "SKIP"
  priority = 50
}

text_rule "v286.strict_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["net loss", "consulting expenses", "cash flow", "per share"]
  concepts = ["REVENUE","CASH"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 100
}
