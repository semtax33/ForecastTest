from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.segments import _group_value
from equity_platform.sectors.industrials.v13lite.ir_segments import SEGMENT_ALIASES, _find_segment_table, _row


def build_ir_pq_bridge(ir_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    core = ir_history.loc[ir_history["segment"].isin(["construction", "resource", "power_energy"])]
    rows: list[dict[str, object]] = []
    for source_path, source_rows in core.groupby("source_path"):
        sales = _find_segment_table(pd.read_html(Path(source_path)), "Sales and Revenues by Segment")
        for _, actual in source_rows.iterrows():
            segment = str(actual["segment"])
            row = _row(sales, SEGMENT_ALIASES[segment])
            prior, volume, pricing, currency, other, current, reported_change = [_group_value(row, index) for index in range(7)]
            rows.append(
                {
                    "period": actual["period"],
                    "segment": segment,
                    "filing_date": actual["filing_date"],
                    "prior_sales_usd": prior,
                    "volume_change_usd": volume,
                    "price_realization_change_usd": pricing,
                    "currency_change_usd": currency,
                    "mix_intersegment_other_change_usd": other,
                    "current_sales_usd": current,
                    "reported_change_usd": reported_change,
                    "volume_contribution_pct": volume / prior * 100.0,
                    "price_contribution_pct": pricing / prior * 100.0,
                    "currency_other_contribution_pct": (currency + other) / prior * 100.0,
                    "reported_revenue_growth_pct": current / prior * 100.0 - 100.0,
                    "bridge_identity_error_usd": current - prior - volume - pricing - currency - other,
                    "reported_change_error_usd": current - prior - reported_change,
                    "source_url": actual["source_url"],
                    "source_sha256": actual["source_sha256"],
                }
            )
    bridge = pd.DataFrame(rows).sort_values(["period", "segment"]).reset_index(drop=True)
    bridge["bridge_identity_pass"] = bridge["bridge_identity_error_usd"].abs().le(1.0)
    bridge["reported_change_pass"] = bridge["reported_change_error_usd"].abs().le(1.0)
    summary = pd.DataFrame(
        [
            {
                "quarter_segment_rows": len(bridge),
                "quarters": bridge["period"].nunique(),
                "segments": bridge["segment"].nunique(),
                "bridge_identity_mismatches": int((~bridge["bridge_identity_pass"]).sum()),
                "reported_change_mismatches": int((~bridge["reported_change_pass"]).sum()),
                "pq_bridge_gate_pass": bool(bridge["bridge_identity_pass"].all() and bridge["reported_change_pass"].all()),
                "production_eligible": False,
            }
        ]
    )
    return {"ir_segment_pq_bridge": bridge, "ir_segment_pq_summary": summary}
