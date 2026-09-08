# Learned span challenger

The learned span layer expands metric recall without changing the authority
boundary of the text extraction system.

```text
SEC narrative -> BERT-SL1000 candidates -----+
                                                |
IR / call ----> GLiNER2 benchmark candidates --+--> Candidate Graph
                                                       |
                              CONCEPT -> BINDING -> ROLE
                                                       |
                                           Deterministic Reducer
                                                       |
                                                Fact or Abstain
```

`V292` remains the deterministic/spaCy baseline. The common
`equity_platform.text_ie.learned` package wraps it and augments only
`RecallCandidate` objects. This avoids another version-directory clone while
preserving the frozen baseline result for exact comparison.

## Runtime policy

- Standard statements remain sourced from XBRL/Companyfacts. Learned spans are
  intended for non-standard operational KPIs in narrative text.
- A proposal must reproduce source hash, block coordinates, and its exact
  literal before it enters the Candidate Graph.
- Raw BERT-SL1000 taxonomy labels are not treated as canonical concepts.
  Canonicalization remains a separate semantic task.
- An exact overlap with a deterministic candidate merges provenance instead of
  creating a duplicate candidate.
- A span backend never emits `KPIFrame`, `FactIR`, or valuation authority.
- CUDA is required outside explicit unit-test policy. Missing local checkpoints
  produce `CHALLENGER_UNAVAILABLE`; CPU fallback and network download are not
  implicit.
- No source-specific model is a runtime champion until issuer/document-disjoint
  human evaluation passes the existing precision and promotion gates.

## Source hypotheses

| Source slice | Candidate model | Role |
| --- | --- | --- |
| SEC 10-K / 10-Q | `AAU-NLP/BERT-SL1000` | raw KPI span proposal |
| SEC 10-K / 10-Q | `AAU-NLP/Cal-BERT-SL1000` | taxonomy abstraction challenger |
| IR prepared remarks / Q&A | `fastino/gliner2-base-v1` | novel KPI schema challenger |

These are benchmark hypotheses, not deployed routing decisions.

## Evaluation order

Safety gates are applied in economic-semantic order: period, unit, KPI/value
binding, actual-versus-guidance role, product/segment scope, then span recall.
Recall is gated after semantic safety while explicit abstention remains an
acceptable outcome; a semantic error or silent miss cannot be offset by higher
NER recall.

## LLM fallback

The fallback policy is provider-neutral. Low-confidence or unknown-KPI clauses
route to a fast structured tier; complex guidance and cross-sentence relations
route to a deeper reasoning tier. Deployment configuration may assign a local
Qwen-family model or a remote model to either tier, but every returned frame
still passes the existing exact-source verifier and remains capped at research
diagnostic authority.
