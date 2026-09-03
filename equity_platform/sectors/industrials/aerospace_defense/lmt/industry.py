from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_lmt_industry_evidence(*, arcana_pqci_root: Path, sensor_map: pd.DataFrame, bls_vintage_audit: pd.DataFrame, pit_feature_summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    census_path = arcana_pqci_root / "census/latest_manufacturing_orders_shipments_inventories.json"
    bea_path = arcana_pqci_root / "bea/latest_input_output_requirements.json"
    payload = json.loads(census_path.read_text(encoding="utf-8"))
    header, records = payload["response"][0], payload["response"][1:]
    frame = pd.DataFrame(records, columns=header)
    context = frame.loc[
        frame["category_code"].isin({"DAP", "NAP", "DEF"})
        & frame["data_type_code"].isin({"VS", "NO", "UO"})
        & frame["seasonally_adj"].eq("yes")
    ].copy()
    context["cell_value"] = pd.to_numeric(context["cell_value"], errors="coerce")
    context["category_title"] = context["category_code"].map({
        "DAP": "Defense aircraft and parts", "NAP": "Nondefense aircraft and parts", "DEF": "Defense capital goods",
    })
    context["measure"] = context["data_type_code"].map({"VS": "shipments", "NO": "new_orders", "UO": "unfilled_orders"})
    context["source"] = "US_CENSUS_M3_ARCANA_PQCI"
    context["retrieved_at"] = payload["retrieved_at"]
    context["source_path"] = str(census_path)
    context["source_sha256"] = _sha256(census_path)
    context["historical_pit_eligible"] = False
    context["model_input_allowed"] = False
    context["use"] = "REVISED_CONTEXT_ONLY_NO_RELEASE_VINTAGE"
    context = context.sort_values(["category_code", "data_type_code", "time"]).reset_index(drop=True)

    authority_rows = [
        {
            "source": "BLS", "dataset": "PPI_AS_RELEASED_VINTAGE", "series_id": row.series_id,
            "title": row.series_title, "role": row.role, "segments": "|".join(sorted(sensor_map.loc[sensor_map["series_id"].eq(row.series_id), "segment"].unique())),
            "historical_pit_eligible": True, "model_input_allowed": True, "authority": "MODEL_INPUT",
        }
        for row in sensor_map.drop_duplicates("series_id").itertuples()
    ]
    for category, title in {"DAP": "Defense aircraft and parts", "NAP": "Nondefense aircraft and parts", "DEF": "Defense capital goods"}.items():
        for measure in ("VS", "NO", "UO"):
            authority_rows.append({
                "source": "Census", "dataset": "M3", "series_id": f"{category}:{measure}", "title": f"{title} {measure}",
                "role": "industry_context", "segments": "all", "historical_pit_eligible": False,
                "model_input_allowed": False, "authority": "CONTEXT_ONLY_REVISED_SERIES",
            })
    authority_rows.append({
        "source": "BEA", "dataset": "INPUT_OUTPUT_REQUIREMENTS", "series_id": "NAICS_3364_CONTEXT",
        "title": "Aerospace product and parts input-output requirements", "role": "cost_map_context",
        "segments": "all", "historical_pit_eligible": False, "model_input_allowed": False,
        "authority": "CONTEXT_ONLY_LATEST_SNAPSHOT",
    })
    authority = pd.DataFrame(authority_rows)
    summary = pd.DataFrame([{
        "bls_model_series": sensor_map["series_id"].nunique(),
        "bls_archive_vintage_rows": int(bls_vintage_audit.iloc[0]["vintage_rows"]),
        "bls_historical_pit_ready": bool(bls_vintage_audit.iloc[0]["historical_pit_ready"]),
        "pit_feature_rows": int(pit_feature_summary.iloc[0]["feature_rows"]),
        "census_aerospace_defense_context_rows": len(context),
        "census_context_categories": context["category_code"].nunique(),
        "census_context_measures": context["data_type_code"].nunique(),
        "census_source_sha256": _sha256(census_path),
        "bea_io_source_sha256": _sha256(bea_path),
        "revised_census_used_in_oos_claim": False,
        "bea_latest_snapshot_used_in_oos_claim": False,
        "historical_pit_ready": bool(bls_vintage_audit.iloc[0]["historical_pit_ready"] and pit_feature_summary.iloc[0]["historical_pit_ready"]),
        "pdf_parsing_used": False,
    }])
    return {"lmt_industry_sensor_authority": authority, "lmt_census_m3_aerospace_context": context, "lmt_industry_data_summary": summary}

