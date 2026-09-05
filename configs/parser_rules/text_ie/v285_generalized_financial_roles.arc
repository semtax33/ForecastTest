# V2.8.5 issuer-neutral financial-role laws disclosed by holdout 27B.
# Numeric ownership remains local to the current block; upper context can only
# contribute a semantic role such as guidance.

text_rule "v285.growth_components" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["revenue growth", "organic growth", "acquisition growth", "product sales"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v285.financing_action" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["prepay", "term loan balance", "incremental borrowings"]
  concepts = ["DEBT"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = true
  require_unique_value = true
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "SKIP"
  priority = 20
}

text_rule "v285.segment_performance" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["adjusted segment ebitda", "margin expanded"]
  concepts = ["ADJUSTED_EBITDA","ADJUSTED_EBITDA_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v285.comparison_basis" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared to", "as compared to", "prior year"]
  concepts = ["REVENUE"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v285.forward_economics" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["long-term ambition", "on track to achieve", "we expect", "targeting"]
  concepts = ["REVENUE","GROSS_MARGIN","ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v285.highlight_list" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["highlights", "revenue of", "gross margin of", "operating margin of"]
  concepts = ["REVENUE","GROSS_MARGIN","OPERATING_MARGIN"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v285.absolute_operating_metric" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["otif performance", "ebitda margin"]
  concepts = ["ACTIVITY_VOLUME","ADJUSTED_EBITDA_MARGIN"]
  quantity_kinds = ["PERCENT"]
  require_unique_metric = true
  require_unique_value = true
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "SKIP"
  priority = 70
}

text_rule "v285.damaged_layout_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["ebitda ttm increase", "ttm revenue ttm increase"]
  concepts = ["REVENUE","ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 100
}
