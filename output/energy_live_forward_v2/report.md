# Energy live-forward V2

Frozen Energy V1.1 and E&P V1.9 were verified before and after the run.
Snapshots are append-only; a conflicting replay fails closed.

- Stored forecast snapshots: 26
- Settled post-forecast observations: 0/20
- Production promoted: False
- Current run: {'snapshots': {'INSERTED': 26, 'UNCHANGED': 0}, 'consensus': {'INSERTED': 3158, 'UNCHANGED': 0}, 'actuals': {'INSERTED': 0, 'UNCHANGED': 0}}

Each snapshot stores the forecast date, version, input hash, Revenue, EBIT,
margin, FCFF, ROIC, Forward DCF, Reverse DCF diagnostic, expectations gap,
and the matching consensus vintage when available. Historical snapshots are
never updated in place.
