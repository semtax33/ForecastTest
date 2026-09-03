# Entrypoint layout

- `energy/operations`: append-only monitoring and scheduled operating runs.
- `energy/research`: Energy research that is not part of an immutable legacy
  benchmark.
- `energy/research/revenue`: Revenue, KPI, component, and macro research.
- `energy/validation`: audits and backtests.
- `industrials`: Industrials research and valuation runs.

Run entrypoints from the repository root with `python -m`, for example:

```powershell
python -m scripts.energy.operations.live_forward_v2 --as-of 2026-09-03
python -m scripts.energy.research.ep.v1_10_project_to_company_roic
python -m scripts.industrials.valuation_v1
python -m scripts.industrials.valuation_v1_1
node scripts/industrials/fetch_v1_5_bls_archives.mjs
python -m scripts.industrials.valuation_v1_5
python -m scripts.industrials.freeze_v1_5_pit_data
python -m scripts.industrials.valuation_v1_6
python -m scripts.industrials.valuation_v5_2_hii
python -m scripts.industrials.freeze_hii_v5_2
```

Industrials V1.5 uses archived BLS PPI XLSX releases and CAT SEC IR HTML
vintages for historical point-in-time segment-route validation. It deliberately
does not parse PDFs or run DCF/Reverse DCF while the strengthened freeze gate is
closed.

The V1.5 freeze command pins only the PIT data infrastructure. V1.6 keeps the
forecast model unfrozen, separates segment-cost recasts from comparable
economic cost changes, and tests predeclared cost-recognition lags without
changing the six-quarter OOS window.

Root-level Python files are retained only when an immutable benchmark manifest
or its historical parent chain depends on their path and bytes.
