# Company-agnostic semantic-frame rules. The runtime provides only bounded
# span matching, local context and deterministic validation primitives.

# HMRB-inspired reusable semantic macros. They compile into backend-neutral
# PatternExprIR; no third-party matcher is a core dependency.
var "KPI_METRIC" {
  expression = {"concept": "*"}
}

var "CHANGE_VERB" {
  expression = {"any": [{"lower": "increased"}, {"lower": "rose"}, {"lower": "grew"}, {"lower": "decreased"}, {"lower": "declined"}, {"lower": "fell"}]}
}

var "PERCENT_CHANGE" {
  expression = {"any": [{"quantity": "PERCENT"}, {"quantity": "BASIS_POINTS"}]}
}

var "KPI_VALUE" {
  expression = {"any": [{"quantity": "MONEY"}, {"quantity": "PRICE"}, {"quantity": "COUNT"}, {"quantity": "RATE"}, {"quantity": "PERCENT"}]}
}

var "TO_RELATION" {
  expression = {"lower": "to"}
}

var "CAUSAL_TRIGGER" {
  expression = {"any": [{"lower": "affect"}, {"lower": "increased"}, {"lower": "driven by"}, {"lower": "due to"}]}
}

# Frame schemas are stable contracts; many surface patterns may target one
# schema without changing FactIR compilation.
frame "CHANGE_TO" { roles = ["metric:Concept", "change:Quantity?", "value:Quantity", "scope:Scope?", "period:Period?"] }
frame "CHANGE_BY" { roles = ["metric:Concept", "change:Quantity", "scope:Scope?", "period:Period?"] }
frame "RANGE_GUIDANCE" { roles = ["metric:Concept", "low:Quantity", "high:Quantity", "period:Period"] }
frame "NOT_EXPECTED" { roles = ["metric:Concept", "value:Quantity", "antecedent:Concept?", "period:Period"] }
frame "COMPARATIVE" { roles = ["metric:Concept", "value:Quantity?", "comparator:Comparator?"] }
frame "COMPOSITION" { roles = ["metric:Concept", "value:Quantity", "whole:Concept?"] }
frame "COUNT_ACTIVITY" { roles = ["metric:Concept", "value:Quantity", "period:Period?"] }
frame "RATE" { roles = ["metric:Concept", "value:Quantity", "period:Period?"] }
frame "ABSOLUTE_VALUE" { roles = ["metric:Concept", "value:Quantity", "period:Period?"] }
frame "CAUSE_EFFECT" { roles = ["cause:Concept", "effect:Concept", "direction:Direction?"] }

text_rule "semantic.change_to" {
  version = 1
  frame = "CHANGE_TO"
  triggers = ["increased", "rose", "grew", "decreased", "declined", "fell"]
  quantity_kinds = ["MONEY", "PRICE", "COUNT", "RATE", "PERCENT"]
  relation_words = ["to"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  allow_context_metric = false
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 10
  pattern = [{"label": "metric", "var": "KPI_METRIC"}, {"label": "trigger", "var": "CHANGE_VERB"}, {"label": "change", "var": "PERCENT_CHANGE", "optional": true}, {"label": "relation", "var": "TO_RELATION", "optional": true}, {"label": "value", "var": "KPI_VALUE"}]
  backends = ["PHRASE", "SEQUENCE"]
  operations = ["normalize_money", "normalize_percent", "resolve_scope", "resolve_period", "assert_unique", "emit_frame"]
}

text_rule "semantic.change_by" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["increased", "rose", "grew", "decreased", "declined", "fell"]
  quantity_kinds = ["PERCENT", "BASIS_POINTS"]
  relation_words = ["by"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 20
}

text_rule "semantic.range_guidance" {
  version = 1
  frame = "RANGE_GUIDANCE"
  triggers = ["expects", "expected", "guidance", "between", "range"]
  quantity_kinds = ["MONEY", "PRICE", "COUNT", "PERCENT"]
  relation_words = ["between", "from"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = false
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 30
}

text_rule "semantic.not_expected" {
  version = 1
  frame = "NOT_EXPECTED"
  triggers = ["not expected", "does not expect", "do not expect", "no longer expects"]
  quantity_kinds = ["MONEY", "COUNT", "PERCENT"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  allow_context_metric = true
  output_metric_suffix = "_NOT_EXPECTED"
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 40
  backends = ["SEQUENCE", "CONTEXT"]
  operations = ["resolve_scope", "resolve_period", "assert_unique", "emit_frame"]
}

text_rule "semantic.comparative" {
  version = 1
  frame = "COMPARATIVE"
  triggers = ["versus", "compared with", "compared to", "prior year", "and", "improved", "remained robust"]
  quantity_kinds = ["MONEY", "PRICE", "COUNT", "PERCENT", "RATE"]
  require_metric = true
  require_value = false
  require_unique_metric = false
  require_unique_value = false
  qualitative = false
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 50
}

text_rule "semantic.composition" {
  version = 1
  frame = "COMPOSITION"
  triggers = ["of the backlog", "of total backlog", "included", "was funded"]
  quantity_kinds = ["MONEY", "COUNT", "PERCENT"]
  relation_words = ["of"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  allow_context_metric = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 60
}

text_rule "semantic.count_activity" {
  version = 1
  frame = "COUNT_ACTIVITY"
  triggers = ["delivered", "deliveries", "produced"]
  quantity_kinds = ["COUNT"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 70
}

text_rule "semantic.rate" {
  version = 1
  frame = "RATE"
  triggers = ["was", "were", "is", "stood at"]
  quantity_kinds = ["RATE"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 80
}

text_rule "semantic.absolute" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["was", "were", "is", "stood at", "totaled"]
  quantity_kinds = ["MONEY", "PRICE", "COUNT", "PERCENT", "RATE"]
  require_metric = true
  require_value = true
  require_unique_metric = true
  require_unique_value = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_EVIDENCE"
  priority = 90
}

text_rule "semantic.cause_effect" {
  version = 1
  frame = "CAUSE_EFFECT"
  triggers = ["due to", "because", "driven by", "resulted from", "affect", "increased"]
  require_metric = true
  require_value = false
  require_unique_metric = false
  require_unique_value = false
  qualitative = true
  ambiguity = "REVIEW"
  authority = "RESEARCH_DIAGNOSTIC"
  priority = 100
  pattern = [{"label": "cause", "var": "KPI_METRIC"}, {"label": "relation", "var": "CAUSAL_TRIGGER"}, {"label": "effect", "var": "KPI_METRIC"}]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["resolve_scope", "resolve_period", "assert_unique", "emit_frame", "emit_relation"]
  relation = "MANAGEMENT_CAUSAL_CLAIM"
}
