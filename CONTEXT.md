# Evidence-Based Equity Forecasting

This context describes how sourced observations become research evidence, forecasts, and valuation inputs without silently increasing their authority.

## Language

**Candidate Graph**:
A recall-oriented graph of possible metric mentions, quantities, and relationships that have not yet been approved as facts.
_Avoid_: Extracted facts, final facts

**Learned Span Proposal**:
An exact source-bounded KPI mention suggested by a token or schema model and
merged into the Candidate Graph. It carries model provenance and confidence
but no fact or forecast authority.
_Avoid_: NER fact, model-extracted KPI

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

**Annotation Review Item**:
A source-bounded context and optional metric–quantity proposal awaiting explicit human judgment.
_Avoid_: Gold example, accepted fact

**Generated Annotation Template**:
A label-blind assignment artifact whose human judgment fields are intentionally empty; its existence proves workload preparation only.
_Avoid_: Completed annotation, human submission

**Annotation Chunk**:
A delivery-only subset that keeps every row from one candidate context together and is reassembled under exact pair/context identity checks; it does not change quality tier or dataset split.
_Avoid_: Dataset shard, train split, partial gold

**Candidate-graph Recovery**:
A review-only pass over contexts that either annotator marked incomplete. Explicit omission hints are source-span validated, unresolved hints require a source reread, and no context is promoted until every added pair receives a new blind A/B judgment and separate adjudication.
_Avoid_: Automatic repair, completeness override, recovered GOLD_A

**Adjudication Hydration**:
Mechanical transcription of completed A/B answers into the adjudication form, with exact agreements optionally prefilled; it is not the third person's judgment.
_Avoid_: Automatic adjudication, majority vote

**Completed Human Submission**:
The matching A/B pair files, context audits, and adjudication file after required human fields are populated and their independent identities, complete candidate graph, source spans, and transcription lineage pass ingestion validation.
_Avoid_: Template, generated batch, GOLD_A

**Calibration Champion**:
The one encoder initialization selected after all concept, binding, and role heads meet frozen precision constraints on every benchmark source slice in the calibration split.
_Avoid_: Best model, certified model, production model

**Certification Holdout**:
An issuer- and document-disjoint GOLD_A partition that remains sealed throughout training, threshold calibration, and champion selection and is opened once for the frozen champion.
_Avoid_: Validation set, tuning set, test sample used for model selection

**Task Certification**:
Evidence that the frozen champion met concept, binding, and role precision constraints on every source slice; end-to-end deterministic-reducer and frame-level gates are still required for production.
_Avoid_: Production approval, parser certification

**Adjudication**:
The resolution of independently produced annotations into one final semantic judgment.
_Avoid_: Review, model agreement

**GOLD_A**:
A certification-eligible annotation independently labeled by two people and resolved by an adjudicator.
_Avoid_: Gold, verified example

**GOLD_B**:
A single-human-verified annotation suitable for research training but not certification.
_Avoid_: Gold, certified example

**Pair-Adjudicated GOLD_B**:
An individually valid A/B/adjudicated metric–quantity judgment from a context whose full candidate graph was incomplete; it may enter `TRAIN` after holdout issuers are excluded, but never `CALIBRATION` or `CERTIFICATION`.
_Avoid_: GOLD_A, complete-context gold, certification example

**SILVER**:
An annotation supported by independent automated signals but not verified by a person.
_Avoid_: Verified, gold

**WEAK**:
A parser- or legacy-derived proposal that has not received human verification.
_Avoid_: Label, ground truth

**Transcript Source Slice**:
A prepared-remarks, Q&A, or unspecified document region assigned only from
structured speaker roles and explicit call-control boundaries.
_Avoid_: Sentiment segment, model-inferred section

**Archive Availability**:
The timestamp at which an immutable source payload was retrieved and retained;
it is a conservative PIT cutoff and is not the event or publication time.
_Avoid_: Call date, earnings date
