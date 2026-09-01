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
