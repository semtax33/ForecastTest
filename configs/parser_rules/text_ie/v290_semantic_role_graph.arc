# V2.9.0 issuer-neutral semantic role graph.  spaCy phrase/token/sentence
# boundaries create metric, value, change, comparator and non-target nodes;
# edges are confined to the same clause and reduced by role precedence.

text_rule "v290.role_graph" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase", "decrease", "grow", "up", "from", "to", "compared"]
  concepts = ["REVENUE","CASH","DEBT","CAPEX","ADJUSTED_EBITDA","GROSS_MARGIN","OPERATING_MARGIN","ACTIVITY_VOLUME","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v290.range_graph" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["guidance", "outlook", "expect", "range"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","GROSS_MARGIN","CAPEX","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","derive_relative_range","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v290.non_target_graph" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["non-cash", "cash flow", "sales and marketing expense", "sales price", "liquidity", "availability"]
  concepts = ["REVENUE","CASH","DEBT","CAPEX","ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 100
}
