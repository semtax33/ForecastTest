# Energy driver forecasting and valuation platform

The active code is the modular `energy_nowcast` package. The historical
The monolithic `energy_revenue_regression_v*.py` scripts are preserved under
`archive/energy_revenue/` as research records; V3.3 is frozen and verified by
`benchmarks/v3_3/manifest.json`. Active entrypoints are grouped under
`scripts/` by operating responsibility.

## Run order

Activate the project Python environment, then run:

```powershell
python -m scripts.energy.operations.nowcast --verify-benchmark-only
python -m scripts.energy.operations.nowcast --config configs/v3_3_1.json
python -m scripts.energy.operations.nowcast --config configs/v3_4.json
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
`data-lake/bronze/manual_consensus/analyst_consensus.csv` remains a manual fallback. A formal
model-vs-consensus comparison starts only after the configured sample minimum.

## Frozen champion and live-forward operations

V3.4 is frozen in `benchmarks/v3_4/manifest.json`. The manifest pins the model
code, config, inputs, input schemas, and material artifacts. Every forecast
capture verifies it before writing an immutable SQLite row.

```powershell
python -m scripts.energy.operations.revenue_nowcast
python -m scripts.energy.operations.revenue_nowcast --as-of 2026-10-17 --timing-label T-15
python -m scripts.energy.operations.revenue_nowcast --as-of 2026-10-27 --timing-label T-5
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
python -m scripts.energy.operations.revenue_nowcast --actuals-csv path\to\released_actuals.csv
```

The scorecard calculates model and consensus errors, disagreement, 80/95% PI
coverage, and model-consensus directional accuracy. Model changes stay locked
until at least 20 matched live observations exist, even if a candidate passes
the other six promotion conditions.

## E&P universe validation

```powershell
python -m scripts.energy.validation.universe_backtest
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
python -m scripts.energy.research.revenue.v35
python -m scripts.energy.research.revenue.v35 --reuse-standardized-kpis
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
python -m scripts.energy.research.revenue.v351_audit
python -m scripts.energy.research.revenue.v351_audit --reuse-standardized-kpis
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
python -m scripts.energy.research.revenue.v352_clean_component
python -m scripts.energy.research.revenue.v352_clean_component --reuse-audit-kpis
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
python -m scripts.energy.research.revenue.v353_grouped_component
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
python -m scripts.energy.research.revenue.v353_gas
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
python -m scripts.energy.research.revenue.v36_macro_overlay --refresh-macro-data
python -m scripts.energy.research.revenue.v36_macro_overlay
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
python -m scripts.energy.research.revenue.structural_phase2_4 --refresh-free-data
python -m scripts.energy.research.revenue.structural_phase2_4
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
python -m scripts.energy.research.revenue.company_kpi_phase2_4 --refresh-company-kpis
python -m scripts.energy.validation.kpi_parser_gold
python -m scripts.energy.research.revenue.company_kpi_phase2_4
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
python -m scripts.energy.research.revenue.target_aligned_phase2_5 --refresh-macro-data
python -m scripts.energy.research.revenue.target_aligned_phase2_5
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

## Phase 6 value-driver targets and conditional bridges

```powershell
python -m scripts.energy.research.revenue.value_driver_phase6
```

Phase 6 renames the working architecture to **Subindustry Driver Forecast →
Financial Bridge → Valuation**. Revenue models are frozen under
`benchmarks/phase5_revenue_research/manifest.json`; every run verifies all ten
frozen Phase-5 artifacts and upstream benchmark manifests before and after the
new target research. V3.4 remains production and live changes remain 0/20.

The hierarchy is economic rather than accounting-order driven. E&P starts from
production and realized prices; Refining from throughput and refining margin;
Midstream from volume, fees, and Adjusted EBITDA; Services from activity,
pricing, and operating margin; Integrated from segment earnings. Revenue,
earnings, cash flow, FCFF, and ROIC are secondary or validation targets. The
machine-readable registry is `output/phase6_value_driver_research/target_hierarchy.csv`.

XOM and CVX Integrated consolidated-revenue tuning is stopped. The new parser
extracts 131 quarterly GAAP segment-earnings rows and passes a 20-row manual
gold audit at 100% for number, unit, period, and semantics. Eight-quarter TIME
tests are segment-specific: Downstream passes the strict gate at MASE 0.780 and
1.378 percentage-point MAE; Upstream fails at MASE 3.622; Chemicals remains on
the prior-year zero-change baseline because its candidate lacks sufficient
training history. Since the disclosures are segment earnings rather than EBIT,
the first consolidation bridge targets net-income margin and labels EBIT/FCFF
as locked until the remaining accounting semantics are standardized.

Midstream retains Adjusted EBITDA as its primary financial anchor. Its selected
lag baseline has TIME MASE 0.586 and WAPE 4.754%. A separate bridge converts
the EBITDA forecast to a revenue range using only company history available by
the target-quarter day-61 cutoff. The bridge uses trailing empirical margin
quantiles—not one fixed margin—and separately reports anchor, bridge, total,
and interaction errors. The same scenario-only rule applies to the Integrated
corporate/unmodeled bridge.

New GAAP target studies remain research-only. Refining operating margin is
promising on the covered names (TIME MASE 0.727) but is locked because PSX lacks
the standardized tag and interval coverage fails. Services operating margin,
E&P operating margin, and E&P cash CapEx all fail their strict gates and fall
back to prior-year zero-change baselines. Detailed TIME/LOCO predictions,
scorecards, gates, bridge attribution, common target schema, and the concise
decision report are written to `output/phase6_value_driver_research/`.

Analyst consensus uses Arcana's local `alpha-vantage`, `fmp`, and `finnworlds`
folders. Alpha Vantage and FMP estimates are normalized under the same
release-date cutoff. Finnworlds is retained as ratings-only coverage and is not
treated as revenue consensus. Current forward spreads are reported, while
historical model-versus-consensus performance remains `TRACKING` until at least
20 matched point-in-time observations exist.

## Energy Valuation Platform V1

```powershell
python -m scripts.energy.research.valuation.v1
python -m scripts.energy.research.valuation.v1 --freeze
```

V1 completes the common economic chain for all 26 companies and five Energy
subindustries: `Economic Anchor → Revenue/EBIT → NOPAT → Reinvestment → FCFF →
ROIC → DCF → Reverse DCF → Expectations Gap`. The anchor remains industry
specific—production and realized price for E&P, throughput and refining margin
for Refining, volume/fees and Adjusted EBITDA for Midstream, activity/pricing
and margin for Services, and segment earnings for Integrated.

Bear/Base/Bull assumptions carry separate growth, operating-margin,
reinvestment, ROIC, WACC, and terminal-growth values. Possible/Plausible/
Probable labels are checked against point-in-time historical distributions and
subindustry guardrails. Missing CapEx taxonomy is never replaced by one fixed
margin: the bridge uses company trailing history first and then a disclosed,
prior-only subindustry peer distribution. `OVV` and `ET` currently use dated
August 21 price overrides because their Arcana yfinance files are pending;
those inputs and conservative beta fallback are explicitly frozen.

The benchmark is frozen under `benchmarks/energy_valuation_v1/manifest.json`.
V1 code and research are complete, while production remains deliberately not
promoted at `0/20` matched live observations. Analyst consensus continues to
come only from Arcana's Alpha Vantage, FMP, and Finnworlds coverage described
above; historical model-versus-consensus performance is therefore still a
tracking result, not evidence for promotion.

## Energy Valuation Platform V1.1 sanity audit

```powershell
python -m scripts.energy.research.valuation.v1_1
python -m scripts.energy.research.valuation.v1_1 --freeze
```

V1.1 preserves the immutable V1.0 benchmark and adds a fail-closed validation
layer before any successor can be frozen. Every scenario assumption now stores
its raw value, clipped value, lower and upper bounds, and boundary-hit side.
Subindustry/variable saturation is green below 10%, yellow from 10% through
25%, and freeze-prohibited above 25%; any ticker putting all three scenarios on
the same boundary is also freeze-prohibited.

The valuation perimeter is explicitly reconciled from operating enterprise
value through adjusted debt, noncontrolling interest, preferred claims, cash,
standardized nonoperating assets, common equity, and shares. Total-debt concepts
are no longer added to current debt twice. A disclosed lease liability is not
added without reversing the matching lease expense, and a current debt taxonomy
gap may use only an exposed last-point-in-time-disclosed fallback. PSX's net
`PaymentsForProceedsFromOtherInvestingActivities` concept is rejected as gross
CapEx; an observation is either replaced from a prior-only subindustry
distribution or excluded from complete history.

Forward and reverse DCF now have two round-trip checks: forward base EV must
recover its originating assumption, and a solved market-implied assumption must
reprice market EV. An unbracketed market value is reported as no solution in the
declared domain, never as a fake boundary solution. Historical FCFF cash
conversion, forward `NOPAT - Reinvestment = FCFF`, and
`Growth = Reinvestment Rate × Normalized ROIC` are separately audited.
Historical incremental ROIC remains a diagnostic and is not substituted for
forecast normalized ROIC.

The 60/20/20 inputs are named default scenario weights, not empirical
probabilities. Terminal-value dependence (<70 normal, 70–80 warning, >80 high),
nonpositive/unstable enterprise values, company expectations-gap outliers, and
subindustry valuation skew are written as explicit diagnostic flags. These
flags are not investment recommendations, and production remains locked at
`0/20` matched live-forward observations even when the V1.1 code/research audit
passes.

## Energy V1.1 live-forward monitoring

```powershell
python -m scripts.energy.operations.valuation_v1_1 --as-of 2026-09-02
python -m scripts.energy.operations.valuation_v1_1 --as-of 2026-09-02 `
  --market-prices path/to/market_prices.csv `
  --settlements path/to/settlements.csv
```

The live runner verifies the immutable V1.0 parent and frozen V1.1 manifest
before and after every run. It reads the frozen fair value, Year-1 base FCFF,
scenario, and terminal artifacts without rebuilding or tuning them. Market
prices, actual releases, Arcana Alpha Vantage/FMP consensus vintages,
Finnworlds ratings coverage, snapshots, settlements, attribution, and reports
are append-only observations. Re-running the same as-of date is idempotent; a
different value under an existing snapshot key is rejected.

FCFF attribution stores `NOPAT + D&A - Cash CapEx - Delta operating NWC + Other
cash conversion = FCFF`. The explicit `Other` term prevents stock compensation,
deferred tax, asset-sale, and other cash-conversion effects from being
mislabelled as working capital. When standardized D&A or current-balance facts
are unavailable, the row is marked partial and retains the exact combined CFO
bridge. Every attribution row is diagnostic-only and cannot feed back into the
frozen valuation.

E&P expectations skew, terminal dependence, and the E&P FCFF-versus-operating-
margin difference are materialized as `MONITOR` hypotheses. They cannot change
WACC, scenario bounds, terminal growth, bridges, parser semantics, E&P values,
or scenario weights. A proven implementation error routes to V1.1.1; a new
economic idea routes to V1.2. Production remains locked until at least 20
forward settlements and a separate promotion review are complete.

## E&P V1.2 expectations-surface research

```powershell
python -m scripts.energy.research.ep.expectations_attribution
python -m scripts.energy.research.ep.v1_2_expectations_surface
```

V1.2 research remains outside the frozen V1.1 package and verifies both Energy
manifests before and after every run. Company through-cycle margin and ROIC
quantiles use historical observations with an eight-observation E&P peer prior
and retain explicit confidence labels. They are research distributions rather
than replacements for V1.1 assumptions.

The expectations layer builds terminal-margin/WACC, growth/operating-margin,
and growth/normalized-ROIC surfaces. Reverse results are stored as iso-value
curves: each solved row is only one of many assumption combinations capable of
matching the same market price. Unbracketed rows remain unsolved and never use a
domain boundary as a fake implied value. Hormuz and AIS inputs are deferred to a
future regime/scenario overlay; they do not determine through-cycle economics.

Freeze the approved V1.2 research surface with:

```powershell
python freeze_ep_expectations_surface_v1_2.py
```

## E&P V1.3 normalized unit-economics research

```powershell
python -m scripts.energy.research.ep.v1_3_normalized_unit_economics
```

V1.3 reads the frozen V1.2 surface but does not recalibrate it. Audited
production mix is combined with a pre-recent 2015Q1-2024Q4 WTI, Henry Hub, and
propane distribution. Reserve life, organic replacement, development cost per
added BOE, normalized accounting margin, and replacement-cash margin are
calculated only when standardized SEC reserve facts reconcile to the separate
production KPI. Missing chains remain locked.

The WACC diagnostic uses adjusted-total-return beta term structures and reports
symmetric/downside ranges without fitting current price. Commodity, decline,
replacement cost, and geopolitical operating shocks belong to cash-flow
scenarios; broad systematic return and capital-structure risk belong to WACC.
Hormuz is not added to both. V1.1 and V1.2 remain immutable and production stays
locked at 0/20.

## E&P V1.4 standardized cost-scope research

```powershell
python -m scripts.energy.research.ep.v1_4_cost_scope
python freeze_ep_cost_scope_v1_4.py
```

V1.4 is a research-only child of the frozen V1.3 benchmark. It expands the
three core reserve-replacement cross-checks with standardized transport,
production tax, G&A, reported hedge gains/losses, and an exact-upstream-revenue
basis against the production-mix benchmark basket. Every annual value retains
its SEC source tag and scope. Missing components remain null and produce an
explicit known-cost upper bound instead of being treated as zero.

Reported hedging is quantified separately and normalized to zero for the
long-run diagnostic, but is not netted against revenue without proof that the
selected revenue fact includes it. The realized-revenue basis is also labelled
as a broad upstream-revenue-minus-benchmark measure, not a pure price
differential. V1.4 cannot replace a terminal anchor, choose a single WACC, or
promote production; those gates remain locked at 0/14 and 0/20 respectively.

## E&P V1.5 accounting-perimeter and reserve-coverage research

```powershell
python -m scripts.energy.research.ep.v1_5_accounting_perimeter
python freeze_ep_accounting_perimeter_v1_5.py
```

V1.5 keeps frozen V1.4 immutable and adds a same-year accounting-perimeter
reconciliation gate. Reconstructed upstream unit margin is compared with the
consolidated EBIT margin using provisional green/yellow/red absolute-gap bands
of 5 and 10 percentage points. A numerical match cannot pass if cost scope or
revenue coverage is incomplete, and alternative hedge-presentation bridges
remain unapplied diagnostics.

Reserve extraction now routes per year across equivalent Energy and generic
standardized tags while independently calibrating production quantities to the
audited production KPI. Project development ROIC is shown separately from a
broader development-plus-exploration-plus-acquisition reserve-investment
proxy. Neither is labelled company incremental ROIC, and the sector terminal
gate remains locked until at least 8/14 reserve chains and the missing capital
perimeter are independently verified.

## E&P V1.6 coverage-completion and accounting-proof research

```powershell
python -m scripts.energy.research.ep.v1_6_coverage_accounting_proof
```

V1.6 verifies the frozen V1.0 through V1.5 manifests before and after every
run. Supplemental IR extraction preserves separate total-proved event-chain
and total stock-flow semantics, requires an independent operational-production
check, and enforces both the 8/14 sector gate and oil-heavy/gas-heavy/mixed
coverage gates. A stock-flow row that includes acquisitions is never labelled
organic replacement.

FANG annual Selected Operating Data supplies actual oil/NGL/gas mix and exact
reported gathering, processing, transportation, and production-tax evidence.
Development ROIC, reserve-replacement ROIC, and company incremental ROIC are
reported as three distinct levels. Company incremental ROIC remains diagnostic
until M&A normalization and accounting-perimeter proof are complete. V1.6 does
not alter frozen WACC or terminal economics, and production remains locked at
0/20 live matched observations.

## E&P V1.6.1 accounting-proven frozen benchmark

```powershell
python -m scripts.energy.research.ep.v1_6_1_accounting_proof
python freeze_ep_accounting_proof_v1_6_1.py
```

V1.6.1 proves the AR composite lifting-cost scope, reconciles CNX production
revenue with realized and unrealized hedge presentation, and attributes the
FANG 2025 margin anomaly to the reported impairment and duplicate composite
cost additions. The 3/3 accounting-perimeter gate is frozen without changing
WACC, terminal assumptions, or production status. Its M&A bridge remains a
denominator-only diagnostic and is not a terminal ROIC input.

## E&P V1.7 organic company-economics research

```powershell
python -m scripts.energy.research.ep.v1_7_organic_company_economics
```

V1.7 preserves the frozen V1.6.1 manifest and reads event-specific evidence
from the SEC Financial Statement and Notes data set. Purchase-price allocation
net assets, acquired debt, acquired cash, equity consideration, acquiree net
income since close, and operating acquisition costs are kept as separate
fields. Acquiree net income is explicitly an after-tax proxy rather than
NOPAT. Material divestitures without divested book capital and operating
contribution fail closed, as do asset acquisitions whose operating contribution
cannot be separated from the buyer. Purchase-accounting step-up, validated
organic company ROIC, terminal replacement, and production promotion all stay
locked.

## E&P V1.7.1 M&A numerator and purchase-accounting proof research

```powershell
python -m scripts.energy.research.ep.v1_7_1_mna_numerator
```

V1.7.1 preserves both the frozen V1.6.1 benchmark and the V1.7 parent research
snapshot. Public-target deals use the last pre-close 10-Q to reconstruct book
invested capital and compare it with purchase-price-allocation economic capital.
Post-close acquiree net income is calendar-day normalized for a separate
run-rate return diagnostic, while the buyer's same-period organic bridge removes
only the actually reported post-close contribution.

Deal cohorts retain separate `t`, `t+1`, and `t+2` annual observations and a
cumulative diagnostic. Net income and tax-adjusted divested-business earnings
remain explicit proxies rather than NOPAT. Incomplete additional acquisitions,
divestitures, private-target book bases, and partial cohort windows fail closed.
The layer cannot recalibrate WACC or terminal economics and cannot promote
production.

## E&P V1.7.2 acquiree NOPAT and cycle-normalized cohort research

```powershell
python -m scripts.energy.research.ep.v1_7_2_acquiree_nopat_cycle
```

V1.7.2 preserves the V1.7.1 parent snapshot and adds an evidence-backed
net-income-to-NOPAT bridge for public acquirees. It annualizes pre-deal target
interest expense, applies the target tax rate, scales the financing burden to
PPA-assumed debt, and keeps pre-deal non-operating items unapplied when they do
not share the post-close period. The result is labelled a bridged NOPAT proxy,
never directly disclosed NOPAT.

Reported deal-cohort ROIC is shown separately from a commodity-cycle-normalized
view based on normalized price, production, and normalized unit cost. DVN uses
SEC upstream cost components, FANG uses the V1.6.1 accounting-proven component
scope, and incomplete peers retain an explicit hierarchical-margin-implied cost
route. Contaminated deal years and incomplete `t` through `t+2` windows continue
to fail closed. The layer cannot replace terminal economics or promote
production.

## E&P V1.7.3 normalization-attribution and NOPAT-triangulation research

```powershell
python -m scripts.energy.research.ep.v1_7_3_normalization_attribution
```

V1.7.3 preserves the complete V1.7.2 parent snapshot. It predeclares a 10%
symmetric tolerance and compares target NOPAT through `net income + after-tax
interest` and `operating income x (1-tax)` on the same target period. Historical
FANG–Energen evidence adds a third evidence-backed bridge without pretending
that direct operating expense is complete NOPAT.

The cycle bridge separates reported GAAP NOPAT, accounting-scope residual,
price normalization, cost normalization, and tax normalization. DVN and FANG
receive Grade A only after every production and cost component is checked back
to SEC/IR source cells; hierarchical-implied Grade C rows receive zero sector
inference weight. A complete independent methodology cohort is distinct from a
complete organic ROIC cohort. Missing disposed-asset operating contribution
therefore keeps FANG organic validation locked even when its book-capital bridge
is proven. Terminal economics, WACC, and production status remain unchanged.

## E&P V1.7.4 cohort closure and organic ROIC validation research

```powershell
python -m scripts.energy.research.ep.v1_7_4_cohort_closure
python freeze_ep_cohort_closure_v1_7_4.py
```

V1.7.4 preserves the complete V1.7.3 parent snapshot and closes only the two
predeclared bottlenecks. FANG–Energen uses retrospective, disclosure-bounded
2019 disposed-asset production and after-tax operating-contribution ranges to
remove acquisition full-yearization and divestiture contamination. It does not
label the bounded contribution as directly disclosed NOPAT.

DVN–WPX retains the failed V1.7.3 25.48% route result and adds a separate
validation route on consolidated continuing-operations scope. Noncontrolling
interest and discontinued operations explain the material perimeter mismatch;
the residual two-route gap is 0.61%, below the unchanged predeclared 10%
tolerance. Two reported and independent full-cycle cohorts are complete, and
two company organic ROIC research ranges are validated. These ranges are not
called normal ROIC and cannot replace V1.1 terminal economics. WACC and
production status remain unchanged.

## E&P V1.8 through-cycle organic ROIC distribution research

```powershell
python -m scripts.energy.research.ep.v1_8_through_cycle_distribution
```

V1.8 verifies the frozen V1.7.4 manifest before and after execution and adds a
deterministically selected gas-heavy clean-organic cohort. AR 2022-2024 is
selected from AR/CNX/EQT/RRC using evidence coverage, transaction-perimeter,
reserve-event, numerator-completeness, and positive-denominator rules without
using ROIC outcomes. Direct AR E&P segment identities provide a complete
reported cost scope for the gas cohort.

The layer compares reported economic and full-cycle company ranges across
oil-heavy FANG, mixed DVN, and gas-heavy AR; applies predeclared range-width and
company-confidence weights; and performs leave-one-cohort-out robustness. The
pooled output is descriptive research only, not a posterior distribution or a
normal-ROIC estimate. V1.8 cannot replace terminal inputs, recalibrate WACC, or
promote production. A freeze is allowed only when at least two company ranges
are Strong/Usable and every leave-one-cohort-out P50 shift is at most 10
percentage points.

## E&P V1.9 sample-stability and uncertainty-decomposition research

```powershell
python -m scripts.energy.research.ep.v1_9_sample_stability
```

V1.9 preserves a 19-file V1.8 parent snapshot and the frozen V1.7.4 manifest.
At a fixed 2025-03-01 research cutoff, it selects the latest eligible RRC clean
window without reading ROIC outcomes. Revenue, total costs, and pretax income
are re-read from SEC companyfacts; reserve and single-segment cells use a
curated local SEC FNSD gold registry with exact stock-flow and accounting
identity checks.

The layer decomposes DVN and FANG range width through denominator, price, cost,
tax, and accounting-perimeter channels. Signed offsets are retained so the
components exactly reproduce each observed range. The fourth RRC cohort lifts
Strong/Usable coverage to two and reduces the maximum leave-one-cohort-out P50
shift below the unchanged 10 percentage-point gate. V1.9 is frozen as an
immutable research benchmark with its own manifest. Normal ROIC, terminal
replacement, WACC recalibration, and production promotion remain locked.

```powershell
python freeze_ep_sample_stability_v1_9.py
```

## Common multi-sector platform and Energy live-forward V2

New sector work uses `equity_platform` for sector definitions, point-in-time
SEC fact selection, DCF identities, immutable manifests, and append-only live
evidence. Frozen Energy code remains untouched; adapters translate its outputs
into the common snapshot contract.

```powershell
python -m scripts.energy.operations.live_forward_v2 --as-of 2026-09-03
```

Each snapshot stores `forecast_as_of`, `model_version`, `input_hash`, Revenue,
EBIT, margin, FCFF, ROIC, Forward DCF, Reverse DCF, expectations gap, and the
matching consensus vintage. Actual outcomes and error attribution append to a
separate immutable store. A repeated identical run is idempotent; conflicting
history fails closed. The runtime SQLite file is not a source artifact.

## E&P V1.10 project-to-company ROIC waterfall

```powershell
python -m scripts.energy.research.ep.v1_10_project_to_company_roic
```

V1.10 reconciles project, reserve-replacement, and company organic ROIC without
allocating ratio effects across cost components by assumption. Disclosed
development, exploration, and acquisition costs are retained as composition
evidence. Leasehold, shared infrastructure, corporate overhead, acquisition
premium, maintenance/replacement timing, and impairment/timing remain an
explicit unexplained residual until independent data identify them. The layer
does not estimate normal ROIC or alter terminal inputs.

## Industrials Valuation Platform V1

```powershell
python -m scripts.industrials.valuation_v1
```

The first cross-sector slice uses CAT and the causal chain Orders/Backlog →
Shipments → Revenue → Margin → Reinvestment → ROIC/FCFF → Valuation. SEC
remaining performance obligation is admitted as an anchor only if an expanding
walk-forward model has the predeclared sample and strictly beats prior-year
Revenue on MASE. Otherwise the transparent naive baseline remains selected.
Forward DCF preserves the growth/reinvestment/ROIC identity; Reverse DCF emits
an explicit unbracketed status when market value has no solution in the
predeclared growth domain. Production remains locked at 0/20.

## HII V5.1 governance and V5.2 conditional valuation

```powershell
python -m scripts.industrials.valuation_v5_2_hii
python -m scripts.industrials.freeze_hii_v5_2
```

V5.1 preserves frozen HII V5 while reclassifying the same-OOS minimum route as
`BEST_TESTED_DIAGNOSTIC`; the predeclared equal blend is the clean prospective
benchmark. It also freezes the three-company A&D aggregate Revenue replication
as a research hypothesis, explicitly not an industry law or cross-regime test.

V5.2 joins HII 10-K/10-Q XBRL, SEC IR HTML guidance, as-released BLS vintages,
backlog, three analyst-consensus providers, market prices, Treasury yields, and
weekly A&D peer returns. It restores the quarterly working-capital chain,
reconciles the full FCFF identity, and runs conditional DCF, Reverse DCF, and a
terminal-margin/WACC expectations surface. Terminal and production authority
remain locked; PDF parsing remains disabled.

## Industrials Valuation Platform V1.1 — CAT semantic/SOTP audit

```powershell
python -m scripts.industrials.valuation_v1_1
```

V1.1 retires CAT's standardized remaining-performance-obligation concept as a
backlog anchor and directly parses firm order backlog plus the portion not
expected to be filled in the following year from official CAT 10-K filings.
The resulting next-12-month conversion bridge remains locked until it has the
predeclared out-of-sample evidence.

The valuation separates MP&E from Financial Products. MP&E DCF subtracts only
MP&E debt and adds only MP&E cash; Financial Products funding debt remains in
that business and its equity is valued separately using disclosed book equity,
normalized ROE, credit losses, finance receivables, funding-cost diagnostics,
and a residual-income/P-B identity. The SOTP gap and reverse DCF are research
diagnostics rather than mispricing claims. Terminal inputs and production stay
locked at 0/20.
