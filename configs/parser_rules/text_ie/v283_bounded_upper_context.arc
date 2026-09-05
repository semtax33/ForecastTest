# V2.8.3 issuer-neutral semantic role laws disclosed by holdout 25C.
# Upper context contributes only a bounded FUTURE/GUIDANCE role. Numeric values
# remain owned by their local clause; no parent numeric inheritance is allowed.

text_rule "v283.metric_range_roles" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["guidance", "outlook", "expected to be", "in the range of", "capital expenditures"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","GROSS_MARGIN","OPERATING_MARGIN","CAPEX"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","assert_unique","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v283.ebitda_margin_pair" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["adjusted ebitda", "of net sales", "of revenue", "compared to"]
  concepts = ["ADJUSTED_EBITDA","ADJUSTED_EBITDA_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v283.operating_sales_pair" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["comparable operating earnings", "on sales", "compared to"]
  concepts = ["OPERATING_INCOME","REVENUE"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v283.multi_period_comparison" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["operating income", "previous quarter", "prior year"]
  concepts = ["OPERATING_INCOME"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = true
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v283.semantic_ownership_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["non-cash", "expenses as a percentage of", "per diluted share", "projected ffo per share"]
  concepts = ["CASH","REVENUE"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 50
}
