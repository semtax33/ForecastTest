from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.sectors.industrials.v15.pit import (
    build_pit_forecast_features,
    parse_bls_ppi_vintages,
)


def build_forecast_origins(
    company_history: pd.DataFrame,
    start_period: str = "2023Q1",
) -> pd.DataFrame:
    history = company_history.copy()
    history["quarter"] = history["period"].map(lambda value: pd.Period(value, freq="Q"))
    releases = history.set_index("quarter")["filing_date"].to_dict()
    rows: list[dict[str, object]] = []
    for row in history.loc[history["quarter"].ge(pd.Period(start_period, freq="Q"))].itertuples():
        prior = row.quarter - 1
        if prior not in releases:
            continue
        rows.append({
            "period": row.period,
            "forecast_as_of": releases[prior],
            "actual_available_at": row.filing_date,
            "actual_after_forecast": pd.Timestamp(row.filing_date) > pd.Timestamp(releases[prior]),
            "origin_rule": "PRIOR_QUARTER_EARNINGS_RELEASE_DATE",
        })
    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)


def build_hii_industry_evidence(
    *, project_root: Path, archive_manifest_path: Path, sensor_map_path: Path,
    company_history: pd.DataFrame, cutoff: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    origins = build_forecast_origins(company_history)
    sensor_map = pd.read_csv(sensor_map_path)
    bls = parse_bls_ppi_vintages(
        project_root=project_root,
        archive_manifest_path=archive_manifest_path,
        sensor_map_path=sensor_map_path,
        cutoff=cutoff,
    )
    pit = build_pit_forecast_features(
        vintages=bls["bls_ppi_vintage_canonical"],
        sensor_map=sensor_map,
        forecast_origins=origins,
    )
    selection = pit["pit_vintage_selection_audit"].copy()
    selection["historical_pit_eligible"] = selection["cutoff_respected"].astype(bool)
    selection["selected_vintage_date"] = selection["latest_selected_release_date"]
    pit["pit_vintage_selection_audit"] = selection
    authority = sensor_map.copy()
    authority["source"] = "BLS"
    authority["historical_pit_eligible"] = True
    authority["model_input_allowed"] = True
    authority["authority"] = "MODEL_INPUT_PROXY"
    authority["dedicated_shipbuilding_output_series"] = False
    context = pd.DataFrame([
        {
            "source": "Census", "dataset": "M3_DEFENSE_CAPITAL_GOODS",
            "historical_pit_eligible": False, "model_input_allowed": False,
            "use": "REVISED_CONTEXT_ONLY", "reason": "NO_RELEASE_VINTAGE_IN_LOCAL_ARCANA_SNAPSHOT",
        },
        {
            "source": "BEA", "dataset": "INPUT_OUTPUT_REQUIREMENTS",
            "historical_pit_eligible": False, "model_input_allowed": False,
            "use": "LATEST_CONTEXT_ONLY", "reason": "NO_HISTORICAL_RELEASE_VINTAGE",
        },
    ])
    summary = pd.DataFrame([{
        "bls_model_series": sensor_map["series_id"].nunique(),
        "bls_archive_vintage_rows": int(bls["bls_ppi_vintage_audit"].iloc[0]["vintage_rows"]),
        "pit_feature_rows": len(pit["pit_segment_features"]),
        "pit_forecast_periods": int(pit["pit_segment_features"]["period"].nunique()),
        "cutoff_violations": int((~selection["cutoff_respected"]).sum()),
        "historical_pit_ready": bool(pit["pit_feature_summary"].iloc[0]["historical_pit_ready"]),
        "dedicated_shipbuilding_output_series_available": False,
        "proxy_limitation": "WPU107_FABRICATED_METAL_AND_WPU117_ELECTRICAL_ARE_PROXIES",
        "census_or_bea_revised_data_used_in_oos": False,
        "pdf_parsing_used": False,
    }])
    return {
        "hii_forecast_origins": origins,
        **{key.replace("bls_", "hii_bls_"): value for key, value in bls.items()},
        **{key.replace("pit_", "hii_pit_"): value for key, value in pit.items()},
        "hii_industry_sensor_authority": authority,
        "hii_industry_context_authority": context,
        "hii_industry_data_summary": summary,
    }
