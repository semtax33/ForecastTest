from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v13lite.ir_segments import _find_segment_table, _numbers, _row


APPLICATIONS = {
    "oil_gas_sales_usd": ("Oil and Gas",),
    "power_generation_sales_usd": ("Power Generation",),
    "industrial_sales_usd": ("Industrial",),
    "transportation_sales_usd": ("Transportation",),
}


def build_power_energy_application_mix(ir_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sources = ir_history.loc[ir_history["segment"].eq("power_energy")].drop_duplicates("source_path")
    rows: list[dict[str, object]] = []
    for _, source in sources.iterrows():
        tables = pd.read_html(Path(source["source_path"]))
        try:
            table = _find_segment_table(tables, "Sales by Application")
        except ValueError:
            rows.append(
                {
                    "period": source["period"],
                    "filing_date": source["filing_date"],
                    "table_found": False,
                    "application_rows_found": 0,
                    "source_url": source["source_url"],
                    "source_sha256": source["source_sha256"],
                }
            )
            continue
        row: dict[str, object] = {
            "period": source["period"],
            "filing_date": source["filing_date"],
            "table_found": True,
            "source_url": source["source_url"],
            "source_sha256": source["source_sha256"],
        }
        found = 0
        for metric, aliases in APPLICATIONS.items():
            try:
                numbers = _numbers(_row(table, aliases))
                row[metric] = numbers[0] * 1e6 if numbers else np.nan
                found += int(bool(numbers))
            except ValueError:
                row[metric] = np.nan
        row["application_rows_found"] = found
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values("period").reset_index(drop=True)
    metrics = list(APPLICATIONS)
    frame["disclosed_application_sales_usd"] = frame[metrics].sum(axis=1, min_count=1)
    for metric in metrics:
        share = metric.replace("_sales_usd", "_mix_pct")
        frame[share] = frame[metric] / frame["disclosed_application_sales_usd"] * 100.0
    frame["application_scope"] = frame[metrics].notna().apply(
        lambda row: "|".join(metric.replace("_sales_usd", "") for metric, present in row.items() if present),
        axis=1,
    )
    frame["application_scope_change"] = frame["application_scope"].ne(frame["application_scope"].shift(1))
    if not frame.empty:
        frame.loc[frame.index[0], "application_scope_change"] = False
    summary = pd.DataFrame(
        [
            {
                "quarters": len(frame),
                "tables_found": int(frame["table_found"].sum()),
                "full_four_application_quarters": int(frame["application_rows_found"].eq(4).sum()),
                "scope_change_rows": int(frame["application_scope_change"].sum()),
                "latest_scope": frame.iloc[-1]["application_scope"],
                "product_mix_history_ready": bool(frame["table_found"].all()),
                "unexpected_scope_forecasted": False,
            }
        ]
    )
    return {"power_energy_application_mix": frame, "power_energy_application_mix_summary": summary}
