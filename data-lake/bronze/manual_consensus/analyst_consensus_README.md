# Analyst consensus input

Arcana FMP and Alpha Vantage snapshots are the primary inputs. Append manual
point-in-time overrides or missing snapshots to `analyst_consensus.csv` using:

```text
ticker,quarter,snapshot_date,consensus_revenue,source
EOG,2026Q3,2026-08-31,8500000000,provider-name
```

`consensus_revenue` must use dollars, matching the SEC revenue values in the
model panel. The pipeline keeps only the latest snapshot published on or
before that quarter's forecast cutoff. It never backfills a later consensus
snapshot into historical validation.
