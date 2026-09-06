# Text IE Annotation Guideline V1

## Purpose

The queue accelerates human annotation by presenting legacy parser proposals. A proposal is never ground truth. Annotators must judge the exact source text and may replace every proposed field.

## Unit of annotation

One pair item represents one metric mention × one quantity mention inside a bounded source context. Store offsets relative to the exact `text` value and verify that each span literal is an exact substring. Do not normalize punctuation or whitespace before recording offsets.

For every fully annotated context, label the complete metric × quantity cross-product:

- `BELONGS_TO`: the quantity is owned by the metric mention.
- `NOT_RELATED`: both mentions are valid candidates, but this metric does not own this quantity.

Assign a role only to `BELONGS_TO` pairs. Use the shared runtime vocabulary: `VALUE_CURRENT`, `VALUE_PRIOR`, `DELTA`, `COMPOSITION`, `GUIDANCE_VALUE`, `GUIDANCE_LOW`, or `GUIDANCE_HIGH`.

## Source slices

Use document archetypes, never issuer identity:

- `SEC_10K`
- `SEC_10Q`
- `IR_PREPARED_REMARKS`
- `IR_QA`
- `IR_UNSPECIFIED` when an IR exhibit cannot be separated reliably
- `INDUSTRY_DATA`
- `UNKNOWN`

Do not infer prepared remarks or Q&A from a ticker, model score, or vague marketing language. Leave the slice unspecified and route it for document-structure review.

For structured earnings-call transcripts, section boundaries are document
structure rather than KPI semantics. A call may be split only when either an
Operator turn explicitly opens Q&A or a structured speaker title contains the
role token `analyst`. Once an Operator explicitly closes Q&A, later closing
remarks are `IR_UNSPECIFIED`; they are not relabeled as prepared remarks.
Calls without either boundary signal remain entirely `IR_UNSPECIFIED`.

Provider `no_data`, malformed, incomplete, and identity-mismatched payloads do
not yield annotation contexts. Provider retrieval time is conservative archive
availability, not the call occurrence or public release time. It may establish
that evidence existed by the retrieval timestamp, but it must never be shifted
back to the fiscal quarter for PIT backtests.

## Human workflow

1. Annotator A labels the source without seeing model probabilities or another annotator’s answer.
2. Annotator B independently labels certification candidates under the same conditions.
3. Disagreements remain `DISAGREEMENT`; they are not silently resolved by majority vote or legacy output.
4. A separate adjudicator records the final pair, scope, and period.
5. Only this resolved record becomes `GOLD_A`.

## Quality tiers

- `WEAK`: legacy/rule proposal only.
- `SILVER`: independent automated systems agree; no human verification.
- `GOLD_B`: one human verifier; training/research only.
- `GOLD_A`: two independent annotators plus adjudication; certification eligible.

TABLE_DSL evidence stays on its positional-table route and must not be inserted into the narrative transformer corpus. Contexts whose exact source or mention spans cannot be recovered become `ARCHIVE_ONLY` and do not enter training.

## Dataset splits

Assign `TRAIN`, `CALIBRATION`, and `CERTIFICATION` only after adjudication. Certification must be issuer-disjoint and document-disjoint from training. Thresholds are calibrated by model × source slice × task only after the calibration split is large enough; the queue must not encode a guessed threshold.
