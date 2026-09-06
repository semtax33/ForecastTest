---
status: accepted
---

# Earnings-call sectioning is structural and fail-closed

Alpha Vantage transcript envelopes enter the common document IR only after
provider, dataset, storage-partition identity, completeness, timezone, and
content-hash checks pass. Prepared remarks and Q&A are separated by an explicit
Operator Q&A cue, with a structured `analyst` title token as the sole fallback;
no issuer aliases or learned model scores participate. Calls lacking either
signal remain `IR_UNSPECIFIED`, and remarks after an explicit Q&A close are also
unspecified. The archived `retrieved_at` timestamp is preserved as conservative
availability but never represented as the call occurrence date. Transcript
candidate graphs stay WEAK and unreviewed until the existing human annotation
and adjudication workflow promotes them.
