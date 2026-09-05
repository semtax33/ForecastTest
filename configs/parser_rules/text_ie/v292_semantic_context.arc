# V2.9.2 typed semantic context rules.  These rules classify predicate/event
# roles around an ontology concept; they are not company aliases and never
# grant terminal-input authority.

var "SHARE_METRIC" { expression = {"concept": "SHARES"} }
var "SHARE_TRANSACTION_EVENT" {
  expression = {"any": [
    {"lemma": "repurchase"},
    {"lemma": "redeem"},
    {"lemma": "retire"},
    {"lemma": "purchase"},
    {"lemma": "acquire"},
    {"lemma": "issue"}
  ]}
}
var "ACTIVITY_METRIC" { expression = {"concept": "ACTIVITY_VOLUME"} }
var "ACTIVITY_COUNT" { expression = {"quantity": "COUNT"} }
var "PERCENT_DELTA" { expression = {"quantity": "PERCENT"} }
var "IMPACT_RELATION" {
  expression = {"any": [
    {"lemma": "impact"},
    {"lemma": "effect"},
    {"lemma": "contribution"}
  ]}
}

text_rule "v292.share_transaction_event_scope" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["repurchase", "redeem", "retire", "purchase", "acquire", "issue"]
  concepts = ["SHARES"]
  quantity_kinds = ["COUNT"]
  require_unique_metric = false
  require_unique_value = false
  pattern = [
    {"label": "cause", "var": "SHARE_TRANSACTION_EVENT"},
    {"label": "effect", "var": "SHARE_METRIC", "max_gap": 12}
  ]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["require_same_clause", "require_dependency_path", "assert_unique"]
  ambiguity = "SKIP"
  priority = 10
}

text_rule "v292.activity_predicate_argument" {
  version = 1
  frame = "ABSOLUTE_VALUE"
  triggers = ["serve", "transport", "carry", "ship", "deliver", "process"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["COUNT"]
  require_unique_metric = true
  require_unique_value = true
  pattern = [
    {"label": "cause", "var": "ACTIVITY_METRIC"},
    {"label": "effect", "var": "ACTIVITY_COUNT", "max_gap": 12}
  ]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["require_same_clause", "require_dependency_path", "bind_labeled_roles", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 20
}

text_rule "v292.impact_on_metric_delta" {
  version = 1
  frame = "CHANGE_BY"
  triggers = ["impact", "effect", "contribution"]
  concepts = ["ACTIVITY_VOLUME"]
  quantity_kinds = ["PERCENT"]
  require_unique_metric = true
  require_unique_value = false
  pattern = [
    {"label": "cause", "var": "IMPACT_RELATION"},
    {"label": "effect", "var": "ACTIVITY_METRIC", "max_gap": 20},
    {"label": "value", "var": "PERCENT_DELTA", "max_gap": 3}
  ]
  backends = ["SEQUENCE", "DEPENDENCY"]
  operations = ["require_same_clause", "require_dependency_path", "bind_labeled_roles", "emit_each_value", "emit_frame"]
  ambiguity = "REVIEW"
  priority = 30
}
