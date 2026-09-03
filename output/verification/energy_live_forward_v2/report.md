# Energy live-forward V2

Frozen Energy V1.1 and E&P V1.9 were verified before and after the run.
Snapshots are append-only; a conflicting replay fails closed.

- Stored forecast snapshots: 26
- Settled post-forecast observations: 0/20
- Production promoted: False
- Revenue consensus rows by provider: {'FMP': 2471, 'ALPHA_VANTAGE': 687}
- Finnworlds ratings-only coverage rows: 24
- Current run: {'snapshots': {'INSERTED': 0, 'UNCHANGED': 26}, 'consensus': {'INSERTED': 0, 'UNCHANGED': 3158}, 'actuals': {'INSERTED': 0, 'UNCHANGED': 0}}

Each snapshot stores the forecast date, version, input hash, Revenue, EBIT,
margin, FCFF, ROIC, Forward DCF, Reverse DCF diagnostic, expectations gap,
and the matching consensus vintage when available. Historical snapshots are
never updated in place.
