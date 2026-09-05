# V2.8.0 issuer-neutral semantic context laws disclosed by the twenty-second
# holdout. The implementation uses spaCy phrase/token/sentence spans and typed
# quantities. These declarations are executable provenance for every emitted
# frame; no issuer-specific callback or regular expression is permitted.

var "REVENUE" { expression = {"concept":"REVENUE"} }
var "OPERATING_INCOME" { expression = {"concept":"OPERATING_INCOME"} }
var "OPERATING_MARGIN" { expression = {"concept":"OPERATING_MARGIN"} }
var "GROSS_MARGIN" { expression = {"concept":"GROSS_MARGIN"} }
var "ADJUSTED_EBITDA" { expression = {"concept":"ADJUSTED_EBITDA"} }
var "ORDERS" { expression = {"concept":"ORDERS"} }
var "BOOK_TO_BILL" { expression = {"concept":"BOOK_TO_BILL"} }
var "PRICE_REALIZATION" { expression = {"concept":"PRICE_REALIZATION"} }
var "ACTIVITY_VOLUME" { expression = {"concept":"ACTIVITY_VOLUME"} }
var "CASH" { expression = {"concept":"CASH"} }
var "DEBT" { expression = {"concept":"DEBT"} }
var "MONEY" { expression = {"quantity":"MONEY"} }
var "PERCENT" { expression = {"quantity":"PERCENT"} }
var "BASIS_POINTS" { expression = {"quantity":"BASIS_POINTS"} }
var "RATE" { expression = {"quantity":"RATE"} }

text_rule "v280.parallel_metric_ownership" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["operating income", "operating margin", "adjusted ebitda", "book-to-bill"]
  concepts = ["OPERATING_INCOME","OPERATING_MARGIN","GROSS_MARGIN","ADJUSTED_EBITDA","ORDERS","BOOK_TO_BILL"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS","RATE"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 10
}

text_rule "v280.driver_preposed_value" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["average ticket", "traffic", "volume growth", "portfolio mix"]
  concepts = ["REVENUE","PRICE_REALIZATION","ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v280.guidance_context" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expected", "anticipated", "plan", "guidance"]
  concepts = ["REVENUE","OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}

text_rule "v280.comparative_context" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["compared to", "versus last year", "up from", "prior year", "last year"]
  concepts = ["REVENUE","OPERATING_INCOME","GROSS_MARGIN","DEBT"]
  quantity_kinds = ["MONEY","PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 40
}

text_rule "v280.margin_component_context" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["including", "included", "inclusive of", "benefit", "headwind", "charges"]
  concepts = ["GROSS_MARGIN","OPERATING_MARGIN"]
  quantity_kinds = ["PERCENT","BASIS_POINTS"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 50
}

text_rule "v280.balance_sheet_level" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["cash balances", "borrowings", "total debt"]
  concepts = ["CASH","DEBT"]
  quantity_kinds = ["MONEY"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 60
}

text_rule "v280.respectively_alignment" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["respectively"]
  concepts = ["REVENUE"]
  quantity_kinds = ["PERCENT"]
  require_unique_metric = false
  require_unique_value = false
  operations = ["bind_labeled_roles","require_same_clause","resolve_polarity","resolve_period","resolve_scope","emit_frame"]
  ambiguity = "REVIEW"
  priority = 70
}
