# Platform V2.6 — Route-Aware Semantic Recall Recovery

## Final verdict

`HOLD_RESEARCH_UNFROZEN`. V2.6 fixes the impossible provenance ladder and passes
the disclosed V2.5.1 development set, but it fails the newly frozen fourth
issuer/document-disjoint holdout. Forecast, DCF, reverse DCF, terminal inputs,
and production were not changed or executed.

## Version comparison

| version | evaluation | critical_precision | critical_recall | candidate_recall | table_route_accuracy | status |
| --- | --- | --- | --- | --- | --- | --- |
| V2.5.1 | third_disjoint_holdout | 1.0 | 0.1627906977 | 1.0 | 0.5789473684 | HOLD_RESEARCH_UNFROZEN |
| V2.6 | v251_disclosed_development_set | 1.0 | 0.813953488372093 | 1.0 | 1.0 | DEVELOPMENT_GATE_PASS_NOT_BLIND |
| V2.6 | fourth_disjoint_holdout | 0.75 | 0.3333333333333333 | 0.925925925925926 | 0.94 | HOLD_RESEARCH_UNFROZEN |

The development result improves critical recall from 16.28% to 81.40% while
holding critical precision at 100% and table routing at 100%. This is a useful
implementation result, not a generalization claim. The fourth holdout falls to
75.00% critical precision, 33.33% critical recall, 92.59% candidate recall, and
94.00% table-route classification accuracy, so every substantive V2.6 gate fails.

## Fourth holdout coverage ladder

| stage | hits | opportunities | recall |
| --- | --- | --- | --- |
| CANDIDATE | 25 | 27 | 0.925925925925926 |
| TEXT_BINDING | 7 | 27 | 0.2592592592592592 |
| TABLE_BINDING | 0 | 27 | 0.0 |
| XBRL_DIRECT | 0 | 27 | 0.0 |
| ADJUDICATED_DIRECT | 2 | 27 | 0.074074074074074 |
| ALL_BINDING_ROUTES | 9 | 27 | 0.3333333333333333 |
| FINAL_FACT | 9 | 27 | 0.3333333333333333 |

Unlike V2.5.1's impossible `BINDING 0 -> FINAL 7`, all V2.6 final facts have an
explicit route binding. The holdout ladder is `ALL_BINDING_ROUTES 9 = FINAL_FACT
9`; no final fact appears from an unmeasured stage.

## Evidence used

| channel | evidence_units | authority_role |
| --- | --- | --- |
| SEC_10K | 10 | COMPANY_EVIDENCE |
| SEC_10Q | 10 | COMPANY_EVIDENCE |
| COMPANY_IR | 10 | COMPANY_EVIDENCE |
| SEC_FINANCIAL_STATEMENT_NOTE | 70 | COMPANY_EVIDENCE |
| INDUSTRY_STATISTIC | 34 | CONTEXT_ONLY_NOT_COMPANY_FACT |

The 100-block holdout uses 30 hash-pinned local Arcana documents: ten 10-Ks, ten
10-Qs, and ten IR releases/presentations. Seventy selected blocks come from 10-K
or 10-Q documents that include financial statements and notes. Thirty-four
sector/subindustry public-statistic sensor mappings (EIA, BLS, Census, FDIC and
related registry sources) were loaded only as context; they cannot emit company
facts or enter valuation authority.

## Error taxonomy

| split | error_class | count |
| --- | --- | --- |
| FOURTH_HOLDOUT | FP_NEGATION_SCOPE | 1 |
| FOURTH_HOLDOUT | FP_NARRATIVE_AMOUNT_OWNERSHIP | 1 |
| FOURTH_HOLDOUT | FP_SECURITIES_SALES_ALIAS | 1 |
| FOURTH_HOLDOUT | FP_CROSS_METRIC_CLAUSE_OWNERSHIP | 1 |
| FOURTH_HOLDOUT | FP_SECURITIES_PRICE_DOMAIN | 1 |
| FOURTH_HOLDOUT | FN_ABSOLUTE_MONETARY_DELTA | 4 |
| FOURTH_HOLDOUT | FN_POINTS_DELTA | 1 |
| FOURTH_HOLDOUT | FN_INDIRECT_DEFERRED_REVENUE | 1 |
| FOURTH_HOLDOUT | FN_TABLE_FALSE_POSITIVE_SUPPRESSION | 10 |
| FOURTH_HOLDOUT | FN_MULTI_QUANTITY_PRODUCTION_LEVEL | 1 |
| FOURTH_HOLDOUT | FN_PARALLEL_CLAUSE_OWNERSHIP | 1 |
| FOURTH_HOLDOUT | CANDIDATE_BARE_CASH_DEBT_ALIAS | 2 |
| FOURTH_HOLDOUT | TABLE_CLASSIFICATION_ERROR | 6 |

The largest recall loss is not the relation solver itself. Ten of eighteen false
negatives are valid bullet/comparison/CapEx facts suppressed by false table
routing. Critical false positives come from negation scope (`no debt ... other
than $25,000`), securities `sales` being treated as operating revenue, and a
parallel expense clause donating its 3.1% change to revenue. Narrative false
positives add tariff cost assigned to customer demand and public-offering price
assigned to operating price realization.

## What improved

- Every final KPI frame carries one of `TEXT_BINDING`, `TABLE_BINDING`,
  `XBRL_DIRECT`, or `ADJUDICATED_DIRECT` provenance.
- Every unbound semantic candidate receives exactly one primary rejection root
  cause plus optional secondary detail.
- DOM/flattened/prose/list/mixed routing is explicit and runs before semantic
  recovery.
- `KPIChange` and ordered `ComparisonFrame` intermediates recover change-to,
  parallel comparison, and explanatory-amount cases without duplicates on the
  development set.
- Source-span accuracy remains 100%; duplicates, illegal cross-clause emissions,
  silent misses, and LLM usage remain zero on the fourth holdout.

## Required next fixes

1. Split list bullets and parallel clauses before grid classification; dense
   numbers alone must not turn coherent KPI bullets into tables.
2. Add negative/exclusion scope and securities-domain guards before numeric
   binding.
3. Extend `KPIChange` to carry both absolute and relative deltas without treating
   either as the ending level.
4. Add position-aware aliases for `$X in Revenue`, bare `cash`, and bare `debt`
   while keeping securities and tax-language exclusions.
5. Represent multiple comparators explicitly (`prior_year`, `prior_quarter`) and
   preserve bullet-local metric ownership.

V2.6 therefore remains a research diagnostic layer. The fourth holdout is frozen
for future error analysis only and must not be reused as a tuning validation set.
