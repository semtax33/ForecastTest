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
