# Frozen V3.4 champion

`manifest.json` is the immutable byte-level contract for the production
champion as of 2026-08-31. It covers the executable model code, configuration,
local and Arcana consensus inputs, declared input schemas, and material model
artifacts. `energy_nowcast.operations.champion.verify_champion` must pass before
any live forecast snapshot is appended.

The champion is not edited in place. Any changed byte requires a new candidate
version and the promotion gates; existing forecast snapshots remain immutable.

