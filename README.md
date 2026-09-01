# Energy revenue nowcast

The active code is the modular `energy_nowcast` package. The historical
`energy_revenue_regression_v*.py` scripts remain untouched as research records;
V3.3 is frozen and verified by `benchmarks/v3_3/manifest.json`.

## Run order

Activate the project Python environment, then run:

```powershell
python run_nowcast.py --verify-benchmark-only
python run_nowcast.py --config configs/v3_3_1.json
python run_nowcast.py --config configs/v3_4.json
python -m pytest
```

V3.3.1 adds point-in-time release cutoffs, an untouched test block, MASE,
revenue-level APE, pooled empirical prediction intervals, and reliability
shrinkage of blend weights. V3.4 evaluates realized-price/basis and generalized
company component candidates. A candidate changes the active forecast only if
its point-in-time structural MAE does not regress versus the prior champion.

Analyst consensus is loaded point-in-time from Arcana's
`data-lake/bronze/consensus` snapshots. FMP and Alpha Vantage quarterly revenue
estimates are normalized and combined by median after taking each provider's
latest eligible snapshot. The local Finnworlds dataset is ratings-only, so it
is recorded in provider coverage but is not misused as revenue consensus.
`data-lake/analyst_consensus.csv` remains a manual fallback. A formal
model-vs-consensus comparison starts only after the configured sample minimum.

## Frozen champion and live-forward operations

V3.4 is frozen in `benchmarks/v3_4/manifest.json`. The manifest pins the model
code, config, inputs, input schemas, and material artifacts. Every forecast
capture verifies it before writing an immutable SQLite row.

```powershell
python run_operations.py
python run_operations.py --as-of 2026-10-17 --timing-label T-15
python run_operations.py --as-of 2026-10-27 --timing-label T-5
```

The default `FROZEN_BASELINE` label does not pretend that 2026-08-31 was a
known T-30 earnings date. For scheduled captures, pass T-30/T-15/T-5 based on
the expected release date. Re-running the same capture is idempotent; changing
an already stored forecast raises an error instead of overwriting history.

Consensus vintages come from Arcana
`data-lake/bronze/consensus/{alpha-vantage,fmp,finnworlds}`. Alpha Vantage and
FMP supply normalized quarterly revenue estimates. Finnworlds currently holds
ratings rather than revenue estimates, so it is retained as source coverage
only. After a release, provide a CSV with
`ticker,quarter,actual_revenue,release_date[,source_path]`:

```powershell
python run_operations.py --actuals-csv path\to\released_actuals.csv
```

The scorecard calculates model and consensus errors, disagreement, 80/95% PI
coverage, and model-consensus directional accuracy. Model changes stay locked
until at least 20 matched live observations exist, even if a candidate passes
the other six promotion conditions.

## E&P universe validation

```powershell
python run_universe_backtest.py
```

This runs one fixed pipeline on 14 E&P companies with both a four-quarter time
holdout and time-safe leave-one-company-out (LOCO) validation. Outputs include
per-ticker scorecards, cross-section summaries, prediction-interval coverage,
and company plus universe promotion gates in `output/universe`.

The expansion diagnostic is deliberately labeled as a proxy experiment. It
uses Arcana SEC quarterly revenue and a lagged implied volume/basis feature from
the common WTI/Henry/propane basket; it does not claim to have parsed every
company's production actuals and guidance. The frozen four-company V3.4 model
is therefore unchanged regardless of this diagnostic's result.

That shortcut is now preserved as `output/universe/experiment_status.json`
with status `REJECTED_EXPERIMENT`; it is not an active candidate.

## V3.5 KPI-first hierarchical research

```powershell
python run_v35_research.py
python run_v35_research.py --reuse-standardized-kpis
```

V3.5 replaces the rejected revenue-implied production shortcut with
point-in-time operational KPI adapters. Company parsers feed the same
`production_actuals`, `production_guidance`, and `realized_prices` schemas,
then one structural engine applies the fixed oil-heavy, gas-heavy, and mixed
taxonomy with company-to-group partial pooling. The runner writes CSV and
Parquet tables plus eight-quarter time and time-safe LOCO results to
`output/v3_5_kpi_hierarchical`.

The runner verifies the frozen V3.4 manifest both before and after execution.
Held-company revenue-derived basis labels are excluded from LOCO; public KPI
covariates remain available. There is no revenue-implied production fallback.
The macro residual overlay (OVX, curve, inventory, and lagged rig candidates)
stays disabled unless every fixed structural research gate passes. Separately,
production champion promotion remains locked until 20 matched live actuals.

## V3.5.1 audit-only

```powershell
python run_v351_audit.py
python run_v351_audit.py --reuse-standardized-kpis
```

V3.5.1 keeps the V3.5 model equation fixed and audits the data and validation
contracts. It rebuilds quarterly revenue directly from SEC Companyfacts:
Q1-Q3 use 75-105 day 10-Q facts and Q4 is `FY - Q1 - Q2 - Q3`. This prevents
later-filed comparative facts from being relabeled as the filing year's
quarter. Annual, mixed-period, and unresolved guidance is retained in the
audit but excluded from forecasts. Raw production units and conversion rules
are also retained.

The audit writes the five requested CSVs plus a company-basis diagnostic to
`output/v3_5_1_audit_only`. V3.5.1 is never promotable: time-safe holdout is
the primary research evaluation, LOCO is a cold-start diagnostic, and live
forward evidence remains the production gate. The original V3.5 artifacts are
preserved with an invalidation notice rather than overwritten.

## V3.5.2 clean component

```powershell
python run_v352_clean_component.py
python run_v352_clean_component.py --reuse-audit-kpis
```

V3.5.2 keeps the corrected revenue labels, quarterly-only guidance, unit
traces, and directional-score fix from V3.5.1, while disabling the company
basis adjustment by default. Company basis is now an optional overlay that
cannot be enabled without a future ticker-level nested walk-forward promotion
test. The TIME holdout remains the primary gate and LOCO remains a separate
cold-start gate; both report explicit, internally consistent numerators and
denominators.

Revenue diagnostics use WAPE and median APE. MAPE is retained only as a
diagnostic, and observations below 10% of their prior-eight-quarter rolling
median revenue are flagged rather than deleted. Macro overlays and champion
promotion stay disabled until the clean-component gates pass, while the frozen
V3.4 champion remains unchanged.

## V3.5.3 grouped component

```powershell
python run_v353_grouped_component.py
```

V3.5.3 evaluates the unchanged clean component separately for oil-heavy,
gas-heavy, and mixed companies. A passing group uses the clean component in
the research branch; a failing group retains the legacy structural model.
TIME remains the promotion gate and LOCO remains a cold-start diagnostic.
Macro research is unlocked per passing group, never applied automatically,
and the V3.4 production champion remains frozen.

The grouped success gate keeps the supplied thresholds unchanged: TIME median
and mean MASE at most 0.72 and 0.75, MASE below one and legacy no-regression
shares of at least 85%, at most one severe ticker regression, 75-85% PI80
coverage, and at least 65% directional accuracy.

## V3.5.3 gas-basis research

```powershell
python run_v353_gas_research.py
```

This isolated experiment covers AR, CNX, EQT, and RRC. It rejects table-of-
contents page numbers, differentials, premiums, benchmark rows, and hedge
tables when parsing absolute realized gas prices. The promotion candidate uses
an additive realized-price basis to Henry Hub and normalizes dollars per Mcf
to dollars per BOE. A parser-only ratio variant is reported for attribution
but is diagnostic-only because it retains the old unit-inconsistent equation.
Gas-heavy continues to use legacy unless the isolated gas gate passes.

## V3.6 macro-overlay research

```powershell
python run_v36_macro_overlay_research.py --refresh-macro-data
python run_v36_macro_overlay_research.py
```

V3.5.3 is frozen separately in
`benchmarks/v3_5_3_research/manifest.json` as the grouped research champion:
oil-heavy and mixed use the clean component, while gas-heavy keeps legacy.
Every V3.6 run verifies both that research benchmark and the V3.4 production
champion before and after the experiment.

Oil-heavy tests OVX regime, the WTI futures curve, commercial crude inventory
excluding SPR, U.S. crude-oil rig count, and the broad dollar index one at a
time. Mixed tests OVX, the WTI curve, Henry Hub regime, crude inventory, and a
WTI-versus-Henry regime spread. Gas macro is prohibited. Feature observations
are filtered by their source-specific release lag and maximum age at the day-61
quarter cutoff; stale data fails closed. In particular, the official EIA WTI
futures history ends in April 2024 and is not carried forward as though it were
current.

Each candidate must improve group median MASE, avoid worsening mean MASE,
avoid regression for at least 80% of baseline-qualified tickers, have zero
regressions worse than two log points, keep PI80 at 75-85%, avoid directional
regression, and retain eight forecasts per baseline-qualified ticker. Pairwise
combinations are evaluated only when both single variables pass all TIME
gates. TIME is the decision split; LOCO is reported separately as a cold-start
diagnostic. No V3.6 candidate currently passes, so no combination is formed and
V3.5.3 remains the research benchmark. V3.4 remains the production champion at
0/20 matched live observations.

## Energy platform Phase 2-4 structural research

```powershell
python run_phase2_4_structural_research.py --refresh-free-data
python run_phase2_4_structural_research.py
```

Phase 2 separates Integrated (`XOM`, `CVX`) from pure Refining (`VLO`, `MPC`,
`PSX`). Integrated uses an upstream + downstream + chemicals sum-of-parts
driver. Refining revenue uses point-in-time forecast product prices multiplied
by refinery crude input; the 3-2-1 crack is retained as a margin signal and is
not misused as a revenue driver.

Phase 3 models Midstream (`KMI`, `WMB`, `ET`, `EPD`) with explicit fee-based
shares, crude/gas volume exposure, and a fixed tariff escalator. Phase 4 models
Oilfield Services (`SLB`, `HAL`, `BKR`) with rig/activity, international liquid
production, and capped commodity-led CapEx/pricing signals. Every raw structural
forecast is preserved, while one reliability weight is learned only from the
pre-holdout subindustry history.

All forward energy inputs come from free EIA STEO Excel vintages selected under
`available_at <= day-61 cutoff`. Rig counts come from EIA's free republication
of Baker Hughes monthly history and SEC Companyfacts supplies the audited
revenue labels. Paid CME, CMA, and CME DataMine data are explicitly forbidden
and unused.

Analyst-consensus plumbing reads only Arcana's local `alpha-vantage`, `fmp`,
and `finnworlds` folders. Alpha Vantage and FMP revenue estimates must pass the
same point-in-time cutoff before they can enter a comparison. Finnworlds has
ratings rather than revenue estimates, so it is coverage-only. The current
July 2026 snapshots are later than the 2026Q2 cutoff and are therefore emitted
as a labelled post-cutoff diagnostic, never as backtest or promotion evidence.

The operating-KPI coverage artifact also distinguishes company disclosures
from macro proxies. Fixed segment, contract, and geographic weights are
explicitly marked as research priors. Macro residual overlays remain off until
the pure structural point-model gate passes.

Each subindustry receives eight-quarter TIME and time-safe LOCO results, 80/95%
prediction intervals, revenue WAPE and median APE, and the same strict research
gate. A failed gate leaves the lag-revenue baseline selected; no Phase 2-4
research result changes the frozen V3.4 production champion or the V3.5.3 E&P
research benchmark.

## Phase 2-4 company KPI and uncertainty refinement

```powershell
python run_phase2_4_company_kpi_research.py --refresh-company-kpis
python run_kpi_parser_gold_audit.py
python run_phase2_4_company_kpi_research.py
```

The original Phase 2-4 structural proxy is frozen under
`benchmarks/phase2_4_structural_proxy/manifest.toml` and verified before and
after every run. The refresh command downloads official SEC 8-K Item 2.02
earnings exhibits, stores immutable source files and SHA-256 provenance, and
standardizes only metrics that can be parsed consistently. KPI availability is
set to the SEC submission `acceptanceDateTime`; filing date plus one calendar
day is used only if that timestamp is unavailable. A verified official IR
publication timestamp can tighten this to the earlier of the two, but no IR
timestamp is inferred from a page date. A forecast may use only the immediately
preceding report quarter and only when its availability time is no later than
the day-61 cutoff; unavailable fields fail closed to the frozen proxy.
`requested_kpi_coverage.csv` separately discloses requested fields that are not
yet standardized.

Parser changes are independently gated by `KPI_PARSER_GOLD_AUDIT_V1`. The
frozen pre-audit parser snapshot is stored under
`benchmarks/phase2_4_kpi_parser_pre_audit/`. Its 75-row manual gold sample spans
Integrated (18), Refining (15), Midstream (27), and Services (15), early/middle/
recent filings, and both direct and transformation-required source rows. The
gate requires numeric accuracy >=95%, unit accuracy 100%, period accuracy 100%,
and semantic accuracy >=95% for every subindustry. The audited parser reaches
100% on all four dimensions in the sample, versus pre-audit overall accuracy of
86.67%, 94.67%, 93.33%, and 92.00%, respectively. A missing or stale audit fails
closed and prevents every company-KPI candidate from being selected.

The main parsing corrections are quarterly/YTD and annual-column selection for
Services, duplicate/region aggregation for MPC throughput, historical crude
component labels for ET liquids transportation, and EPD `MBPD` unit semantics.
Each TIME prediction emits whether KPI data was used, whether proxy fallback was
used, KPI age, rule confidence, and quality score. Quality-bucket forecast-error
diagnostics are written to `output/kpi_parser_gold_audit/`.

The four independent candidates are `P2.1_INTEGRATED_COMPANY_KPI`,
`P2.1_REFINING_COMPANY_KPI`, `P3.1_MIDSTREAM_COMPANY_KPI`, and
`P4.1_SERVICES_COMPANY_KPI`. Company effects are learned incrementally on top
of the proxy using pre-forecast history and reliability shrinkage. TIME and
LOCO retain the same eight-quarter definitions as the frozen benchmark.

Prediction intervals are recalibrated independently from point forecasts with
rolling, time-safe conformal residual quantiles and ticker/subindustry partial
pooling. The point-model gate controls whether later macro research is unlocked;
the uncertainty gate evaluates PI80, PI95, and interval score. Research
selection requires both gates, while production additionally requires 20
matched live-forward observations. Current backtests accept the company KPI
candidate only for Refining. Parser correction reduces Services median MASE from
0.7358 to 0.7015, but the proxy remains slightly better at 0.6949 and the
uncertainty gate still fails. Refining improves from proxy median MASE 0.5371 to
0.5310 and revenue WAPE from 4.3417% to 4.3011%. Integrated and Midstream also
retain the recalibrated frozen proxy, and all production selections remain the
lag-revenue baseline because live-forward coverage is still 0/20.

The main outputs are written to `output/phase2_4_company_kpi_research/`, with
the concise decision record in `report.md`, current forecasts in
`latest_research_predictions.csv`, and all model/data boundary assertions in
`metadata.json`.

## Phase 2.5 target-aligned research and Phase 5 router

```powershell
python run_phase2_5_target_aligned_research.py --refresh-macro-data
python run_phase2_5_target_aligned_research.py
```

The accepted P2.1 Refining result is frozen independently under
`benchmarks/phase2_1_refining_kpi/manifest.toml`. Each run verifies all ten
frozen files plus the Phase 2-4 proxy, V3.4 production champion, and V3.5.3 E&P
research champion before and after the experiment.

Refining tests crack spread, gasoline inventory, distillate inventory,
refinery utilization, Brent-WTI spread, and product demand as residual features
on top of P2.1. Services tests OVX, WTI, Henry Hub, and oil-rig regimes on top
of the accepted proxy. All source observations obey release-date and freshness
cutoffs. A pair can be evaluated only after both single features pass the full
TIME gate. No single currently passes every performance and interval check, so
no pair is formed and both frozen benchmarks remain selected. BKR orders are
reported at explicit t+1 and t+2 lags, but remain diagnostic because coverage is
only one of three Services companies and LOCO cannot learn a held-out company's
orders effect.

Integrated historical KPI expansion is disabled. The forward scanner records
numeric target-quarter production, maintenance, refinery, and chemicals text,
but candidates remain locked until their meaning and target quarter are
manually gold-labelled for at least eight quarters per ticker. The current
scanner finds sufficient raw numeric-candidate quarters for XOM and CVX but no
manual-gold quarters, so the proxy remains selected.

Midstream keeps its GAAP-revenue proxy and adds a separate non-GAAP Adjusted
EBITDA target. Official SEC earnings exhibits provide 132 quarterly values
across KMI, WMB, ET, and EPD; the 20-row manual parser audit is 100% accurate on
number, unit, period, and semantics. The volume-times-fee candidate reaches a
median TIME MASE of 0.573, but fails the minimum-observation, no-regression, and
PI80 gates. It therefore remains research-only and the Adjusted EBITDA route
falls back to its lag baseline.

Phase 5 is a static taxonomy router, not a trained meta-model. It emits a common
schema for GAAP Revenue and Adjusted EBITDA, preserving each child model's
forecast, intervals, validation label, target, and production status. The
target registry explicitly keeps E&P CapEx/margin, Integrated segment margin,
Refining margin/EBITDA, and Services margin/orders locked until standardized
point-in-time labels and the required eight-quarter evidence exist. Production
remains the lag-revenue baseline at 0/20 matched live observations.
