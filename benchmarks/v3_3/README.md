# V3.3 champion benchmark

This manifest freezes the exact V3.3 code and output artifacts at commit
`29ee447`. The files remain in their original tracked locations so there is
only one byte-for-byte source of truth. `energy_nowcast.benchmark` verifies
their SHA-256 hashes and the expected benchmark metrics before a later model
can be evaluated or promoted.

Do not regenerate or edit the V3.3 artifacts. New runs write versioned files
under `output/`.
