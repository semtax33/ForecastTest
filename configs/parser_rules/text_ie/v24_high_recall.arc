# Platform V2.4 candidate-generation semantics.  These rules generate noisy
# candidates; only the deterministic V2.4 verifier may promote a frame.

frame "ABSOLUTE_VALUE" { roles = ["metric:Concept", "value:Quantity", "scope:Scope?", "period:Period?"] }
frame "CHANGE_BY" { roles = ["metric:Concept", "change:Quantity", "scope:Scope?", "period:Period?"] }
frame "RANGE_GUIDANCE" { roles = ["metric:Concept", "low:Quantity", "high:Quantity", "period:Period"] }
frame "CAUSE_EFFECT" { roles = ["cause:Concept", "effect:Concept", "direction:Direction?"] }

# HMRB-inspired alias declarations are backend-neutral data.  The V2.4 loader
# compiles these into MetricAnchor IR rather than embedding issuer callbacks.
alias "REVENUE" { terms = ["net sales", "organic revenue", "organic revenues"] }
alias "OPERATING_INCOME" { terms = ["income from operations"] }
alias "OPERATING_MARGIN" { terms = ["segment profit margin", "adjusted operating margin"] }
alias "BACKLOG" { terms = ["order book"] }
alias "PRODUCTION" { terms = ["output volumes", "production output"] }
alias "CAPEX" { terms = ["cash capital expenditures", "capital investments", "capital spending"] }
alias "DEBT" { terms = ["total borrowings", "debt and finance lease obligations"] }
alias "CASH" { terms = ["cash on hand", "quarter-end cash"] }
alias "SHARES" { terms = ["weighted average diluted shares", "weighted average basic shares", "diluted shares"] }
alias "ADJUSTED_EBITDA" { terms = ["adjusted ebitdax", "operating ebitda", "modified ebitda"] }

text_rule "v24.proximity" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was", "were", "is", "are", "of", "at", "reached", "totaled", "invested", "reported", "ended", "had", "has"]
  quantity_kinds = ["MONEY", "PRICE", "COUNT", "RATE", "PERCENT"]
  require_metric = true
  require_value = true
  require_unique_metric = false
  require_unique_value = false
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 10
}

text_rule "v24.change" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increased", "grew", "rose", "decreased", "declined", "fell", "up", "down", "expansion", "contraction", "increase", "decrease"]
  quantity_kinds = ["PERCENT", "BASIS_POINTS", "MONEY", "COUNT"]
  require_metric = true
  require_value = true
  require_unique_metric = false
  require_unique_value = false
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 20
}

text_rule "v24.range" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expects", "expected", "guidance", "between", "range", "from"]
  quantity_kinds = ["MONEY", "PRICE", "COUNT", "PERCENT"]
  relation_words = ["between", "from", "to", "and"]
  require_metric = true
  require_value = true
  require_unique_metric = false
  require_unique_value = false
  output_metric_suffix = "_GUIDANCE"
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 30
}

text_rule "v24.causal" {
  version = 1
  frame = "CAUSE_EFFECT"
  triggers = ["due to", "because", "driven by", "resulted from", "reflecting", "increased"]
  require_metric = true
  require_value = false
  require_unique_metric = false
  require_unique_value = false
  qualitative = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_DIAGNOSTIC"
  priority = 40
  relation = "MANAGEMENT_CAUSAL_CLAIM"
}
