# V2.8.4 issuer-neutral economic-role laws disclosed by holdout 26.
# spaCy phrase/token/dependency context is primary; parent context may supply a
# role such as GUIDANCE but never a numeric value.

text_rule "v284.segment_economics" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["generated revenues", "adjusted ebitda", "a margin of"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","ADJUSTED_EBITDA_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v284.economic_driver_roles" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["patient days", "revenue per patient day", "revenue per advisor", "solutions sales", "follow-on contract"]
  concepts = ["ACTIVITY_VOLUME","PRICE_REALIZATION","ORDERS"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v284.multi_role_comparison" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared with", "prior year", "from", "reported production", "adjusted production"]
  concepts = ["REVENUE","OPERATING_MARGIN","SHARES","PRODUCTION"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v284.plus_minus_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["guidance", "+/-", "revenue"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = true
  require_unique_value = false
  operations = ["bind_labeled_roles","derive_relative_range","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v284.results_highlights" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["results", "total revenue was", "adjusted ebitda", "capital expenditures", "financial news release"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","ADJUSTED_EBITDA_MARGIN","CAPEX","GROSS_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v284.balance_and_unit_ownership" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["borrowings outstanding", "reduced total debt", "cash from operations", "million cubic feet", "segment earnings margin"]
  concepts = ["DEBT","CASH","PRODUCTION","OPERATING_MARGIN"]
  quantity_kinds = ["MONEY","COUNT","PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","assert_unique","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}
