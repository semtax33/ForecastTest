# Evidence-Based Equity Forecasting

This context describes how sourced observations become research evidence, forecasts, and valuation inputs without silently increasing their authority.

## Language

**Candidate Graph**:
A recall-oriented graph of possible metric mentions, quantities, and relationships that have not yet been approved as facts.
_Avoid_: Extracted facts, final facts

**Semantic Challenger**:
A fallible proposal source that scores a candidate's economic concept, ownership relationship, or numeric role without approving a fact.
_Avoid_: Parser of record, fact generator

**Deterministic Reducer**:
The authority boundary that applies span, scope, unit, period, accounting, and ambiguity invariants before a semantic graph can become a fact.
_Avoid_: Model post-processor, confidence threshold

**Evidence Route**:
The mutually exclusive path by which source material is interpreted, such as narrative text, a positional table, or direct structured disclosure.
_Avoid_: Parser mode

**Abstention**:
An observable decision that available evidence is insufficient to assign ownership or a semantic role safely.
_Avoid_: Miss, empty result

**Research Fact**:
A source-grounded metric assertion that passed the deterministic reducer but has no automatic right to become a forecast or valuation input.
_Avoid_: Candidate, model prediction

**Promotion**:
An explicit authority transition from evidence toward forecast or valuation use after the applicable validation gates pass.
_Avoid_: Extraction, scoring
