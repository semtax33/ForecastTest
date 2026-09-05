# V2.8.7 expands strict adjudication with reusable financial roles learned
# from the disclosed twenty-ninth failure. Parent context may classify a block
# as forward-looking, but every emitted number remains locally owned.

text_rule "v287.comparative_ownership" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared to", "respectively", "year-ago quarter"]
  concepts = ["DEBT","ADJUSTED_EBITDA","GROSS_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v287.performance_ownership" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["sales increased", "yielding", "for the quarter were", "grew"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","ADJUSTED_EBITDA_MARGIN","OPERATING_INCOME","OPERATING_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v287.guidance_ownership" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["now expect", "full year", "in the range of", "guidance"]
  concepts = ["REVENUE","GROSS_MARGIN","ADJUSTED_EBITDA","ACTIVITY_VOLUME","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v287.activity_ownership" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["membership", "originations", "application volume", "demand response events"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v287.strict_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["expenses", "net income", "financial definitions", "reconciliation"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","ACTIVITY_VOLUME"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 100
}
