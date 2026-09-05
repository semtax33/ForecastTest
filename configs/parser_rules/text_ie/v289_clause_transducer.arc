# V2.8.9 issuer-neutral clause transducer.  spaCy supplies sentence, phrase and
# token boundaries; each quantity is owned by the nearest financial metric
# anchor inside the same clause.  Parent context may provide state, never a
# numeric value.

text_rule "v289.change_to_role" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increase", "decrease", "grow", "climb", "fall", "to", "from"]
  concepts = ["REVENUE","CASH","ADJUSTED_EBITDA","OPERATING_INCOME"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v289.comparative_role" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared with", "compared to", "from", "prior year"]
  concepts = ["REVENUE","GROSS_MARGIN","OPERATING_INCOME","CASH"]
  quantity_kinds = ["MONEY","PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v289.absolute_role" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was", "of", "above", "over", "totaled"]
  concepts = ["REVENUE","CASH","DEBT","CAPEX","ADJUSTED_EBITDA","BACKLOG","BOOK_TO_BILL","ORDERS"]
  quantity_kinds = ["MONEY","PERCENT","RATE"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","emit_each_value","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v289.forward_range_role" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["range", "guidance", "outlook", "expected"]
  concepts = ["REVENUE","ADJUSTED_EBITDA","GROSS_MARGIN","CAPEX","SHARES"]
  quantity_kinds = ["MONEY","PERCENT","COUNT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","derive_relative_range","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v289.non_target_guard" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["cogs", "cost of goods sold", "free cash flow", "net income", "per share", "working capital"]
  concepts = ["REVENUE","CASH","DEBT","ADJUSTED_EBITDA"]
  quantity_kinds = ["MONEY","PERCENT","RATE"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","assert_unique"]
  ambiguity = "SKIP"
  priority = 100
}
