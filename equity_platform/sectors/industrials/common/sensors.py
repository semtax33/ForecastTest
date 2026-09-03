from __future__ import annotations

import pandas as pd


def build_industry_sensor_authority(
    *,
    registry: pd.DataFrame,
    registry_subindustry: str,
    model_sensor_map: pd.DataFrame,
    vintage_audit: pd.DataFrame,
    feature_summary: pd.DataFrame,
    model_source: str = "BLS",
) -> dict[str, pd.DataFrame]:
    """Keep true PIT inputs separate from revised/context-only registry rows."""
    selected = registry.loc[
        registry["sector"].eq("Industrials")
        & registry["subindustry"].eq(registry_subindustry)
    ].copy()
    selected["model_authority"] = "CONTEXT_ONLY_NO_HISTORICAL_VINTAGE"
    selected.loc[
        selected["source"].eq(model_source), "model_authority"
    ] = "REPLACED_BY_AS_RELEASED_SERIES_MAP"
    model = model_sensor_map.copy()
    model["source"] = model_source
    model["dataset"] = "PPI_AS_RELEASED_VINTAGE"
    model["model_authority"] = "HISTORICAL_PIT_MODEL_INPUT"
    model["pit_eligible"] = True
    summary = pd.DataFrame(
        [
            {
                "registry_subindustry": registry_subindustry,
                "registry_sensors": len(selected),
                "model_sensor_rows": len(model_sensor_map),
                "model_unique_series": model_sensor_map["series_id"].nunique(),
                "context_only_sensors": int(
                    selected["model_authority"].str.startswith("CONTEXT_ONLY").sum()
                ),
                "archive_vintage_rows": int(vintage_audit.iloc[0]["vintage_rows"]),
                "pit_feature_rows": int(feature_summary.iloc[0]["feature_rows"]),
                "minimum_series_coverage_pct": float(
                    feature_summary.iloc[0]["minimum_series_coverage_pct"]
                ),
                "cutoff_violations": int(feature_summary.iloc[0]["cutoff_violations"]),
                "historical_pit_ready": bool(
                    vintage_audit.iloc[0]["historical_pit_ready"]
                    and feature_summary.iloc[0]["historical_pit_ready"]
                ),
                "revised_context_data_used_in_oos_claim": False,
            }
        ]
    )
    return {
        "industry_sensor_authority": pd.concat(
            [selected, model], ignore_index=True, sort=False
        ),
        "industry_data_summary": summary,
    }
