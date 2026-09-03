# ForecastTest data lake

The workspace uses a medallion layout. Runtime code resolves these locations
through `equity_platform.data_catalog` instead of hard-coding physical paths.

## Bronze

Raw or minimally transformed, point-in-time inputs:

- `bronze/manual_consensus`: manual consensus fallback and its schema notes
- `bronze/snapshots`: immutable source snapshots used by research pipelines

The external Arcana lake remains the system of record for SEC, market, and
provider consensus feeds; it was not moved by this workspace refactor.

## Silver

Versioned intermediate model datasets live under `silver/models/<version>`.
The original filenames are retained so historical provenance remains obvious.

## Gold

Frozen champion-ready datasets live under `gold/champions/<version>`. V3.3 is
the current revenue champion data package.

Historical metadata may mention its original flat `data-lake/...` location.
Those strings are provenance records, not active runtime paths.

