from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .domain import DataAuthority
from .registry import INDUSTRIALS_SUBINDUSTRIES


@dataclass(frozen=True)
class ContextDataset:
    provider: str
    dataset: str
    relative_path: str
    roles: tuple[str, ...]
    selector: Callable[[str], bool]


def _all(_: str) -> bool:
    return True


def _manufacturing(code: str) -> bool:
    return code in {
        "aerospace_defense",
        "building_products",
        "construction_engineering",
        "electrical_components",
        "heavy_electrical",
        "industrial_conglomerates",
        "construction_machinery",
        "agricultural_machinery",
        "industrial_machinery",
        "trading_distributors",
        "commercial_printing",
        "office_services",
    }


def _construction(code: str) -> bool:
    return code in {
        "building_products",
        "construction_engineering",
        "construction_machinery",
        "electrical_components",
        "highways_railtracks",
    }


def _energy_exposed(code: str) -> bool:
    return code in {
        "heavy_electrical",
        "environmental_services",
        "air_freight_logistics",
        "passenger_airlines",
        "marine_transportation",
        "rail_transportation",
        "cargo_ground_transport",
        "passenger_ground_transport",
        "airport_services",
        "marine_ports_services",
    }


def _agriculture(code: str) -> bool:
    return code == "agricultural_machinery"


CONTEXT_DATASETS: tuple[ContextDataset, ...] = (
    ContextDataset("BLS", "price_labor_activity", "bls/latest_price_labor_activity.json", ("P", "Q", "C"), _all),
    ContextDataset("BEA", "gdp_by_industry", "bea/latest_gdp_by_industry.json", ("P", "Q", "C", "I"), _all),
    ContextDataset("BEA", "input_output_requirements", "bea/latest_input_output_requirements.json", ("C",), _all),
    ContextDataset("CENSUS", "manufacturing_orders_shipments_inventories", "census/latest_manufacturing_orders_shipments_inventories.json", ("Q", "I"), _manufacturing),
    ContextDataset("CENSUS", "residential_construction", "census/latest_residential_construction.json", ("Q", "I"), _construction),
    ContextDataset("CENSUS", "new_residential_sales", "census/latest_new_residential_sales.json", ("P", "Q", "I"), _construction),
    ContextDataset("EIA", "wti_spot_price", "eia/latest_wti_spot_price.json", ("P", "C"), _energy_exposed),
    ContextDataset("EIA", "electricity_price", "eia/latest_electricity_price.json", ("P", "C"), lambda code: code == "heavy_electrical"),
    ContextDataset("EIA", "electricity_sales", "eia/latest_electricity_sales.json", ("Q", "I"), lambda code: code == "heavy_electrical"),
    ContextDataset("USDA_NASS", "corn", "nass/latest_corn.json", ("P", "Q", "I"), _agriculture),
    ContextDataset("USDA_NASS", "soybeans", "nass/latest_soybeans.json", ("P", "Q", "I"), _agriculture),
    ContextDataset("USDA_NASS", "wheat", "nass/latest_wheat.json", ("P", "Q", "I"), _agriculture),
)


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: object) -> float:
    if value is None:
        return np.nan
    cleaned = str(value).replace(",", "").replace("(D)", "").strip()
    if cleaned in {"", "(NA)", "NA", "N/A", "--"}:
        return np.nan
    return float(pd.to_numeric(cleaned, errors="coerce"))


def _bls(payload: dict[str, object]) -> list[dict[str, object]]:
    metadata = payload.get("pqci", {}).get("series_metadata", {})
    rows: list[dict[str, object]] = []
    for series in payload["response"]["Results"]["series"]:
        series_id = series["seriesID"]
        meta = metadata.get(series_id, {})
        for item in series["data"]:
            if item["period"] == "M13":
                continue
            month = int(str(item["period"])[1:])
            rows.append(
                {
                    "period": f"{item['year']}-{month:02d}",
                    "metric_id": series_id,
                    "metric_label": meta.get("label", series_id),
                    "value": _number(item["value"]),
                    "unit": "INDEX_OR_REPORTED_UNIT",
                    "pqci_roles": "|".join(meta.get("dimensions", [])),
                }
            )
    return rows


def _census(payload: dict[str, object]) -> list[dict[str, object]]:
    response = payload["response"]
    header = response[0]
    rows: list[dict[str, object]] = []
    for raw in response[1:]:
        item = dict(zip(header, raw))
        rows.append(
            {
                "period": item.get("time"),
                "metric_id": ":".join(
                    str(item.get(key, ""))
                    for key in ("category_code", "data_type_code", "seasonally_adj")
                ),
                "metric_label": item.get("category_code"),
                "value": _number(item.get("cell_value")),
                "unit": "CENSUS_REPORTED_UNIT",
                "pqci_roles": "|".join(payload["pqci"]["dimensions"]),
            }
        )
    return rows


def _bea(payload: dict[str, object]) -> list[dict[str, object]]:
    results = payload["response"]["BEAAPI"]["Results"]
    rows: list[dict[str, object]] = []
    for result in results if isinstance(results, list) else [results]:
        for item in result.get("Data", []):
            metric_id = ":".join(
                str(item.get(key, ""))
                for key in ("TableID", "Industry", "RowCode", "ColCode")
            )
            rows.append(
                {
                    "period": item.get("Quarter") or item.get("Year"),
                    "metric_id": metric_id,
                    "metric_label": item.get("IndustrYDescription")
                    or f"{item.get('RowDescr', '')} -> {item.get('ColDescr', '')}",
                    "value": _number(item.get("DataValue")),
                    "unit": "BEA_TABLE_SPECIFIC_UNIT",
                    "pqci_roles": "|".join(payload["pqci"]["dimensions"]),
                }
            )
    return rows


def _eia(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for page in payload["response"].get("pages", []):
        for item in page.get("response", {}).get("data", []):
            preferred = ["value", "price", "sales", "generation", "production"]
            value_key = next((key for key in preferred if key in item), None)
            if value_key is None:
                continue
            rows.append(
                {
                    "period": item.get("period"),
                    "metric_id": str(
                        item.get("series")
                        or item.get("series-description")
                        or item.get("sectorid")
                        or payload["dataset"]
                    ),
                    "metric_label": item.get("series-description")
                    or item.get("product-name")
                    or payload["dataset"],
                    "value": _number(item.get(value_key)),
                    "unit": item.get(f"{value_key}-units") or item.get("units"),
                    "pqci_roles": "|".join(payload["pqci"]["dimensions"]),
                }
            )
    return rows


def _nass(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in payload["response"].get("data", []):
        rows.append(
            {
                "period": str(item.get("year")),
                "metric_id": f"{item.get('short_desc')}:{item.get('state_alpha')}",
                "metric_label": item.get("short_desc"),
                "value": _number(item.get("Value")),
                "unit": item.get("unit_desc"),
                "pqci_roles": "|".join(payload["pqci"]["dimensions"]),
            }
        )
    return rows


PARSERS = {
    "BLS": _bls,
    "CENSUS": _census,
    "BEA": _bea,
    "EIA": _eia,
    "USDA_NASS": _nass,
}


def build_arcana_pqci_context(
    *, pqci_root: Path, cutoff: pd.Timestamp
) -> dict[str, pd.DataFrame]:
    inventory_rows: list[dict[str, object]] = []
    canonical_rows: list[dict[str, object]] = []
    payloads: dict[str, dict[str, object]] = {}
    for definition in CONTEXT_DATASETS:
        path = pqci_root / definition.relative_path
        if not path.exists():
            inventory_rows.append(
                {
                    "provider": definition.provider,
                    "dataset": definition.dataset,
                    "status": "MISSING_FAIL_CLOSED",
                    "source_path": str(path),
                }
            )
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        retrieved_at = pd.Timestamp(payload["retrieved_at"])
        cutoff_utc = pd.Timestamp(cutoff).tz_localize("UTC") + pd.Timedelta(days=1)
        cutoff_pass = retrieved_at <= cutoff_utc
        source_hash = _sha(path)
        payloads[definition.dataset] = payload
        parsed = PARSERS[definition.provider](payload) if cutoff_pass else []
        for row in parsed:
            canonical_rows.append(
                {
                    "provider": definition.provider,
                    "dataset": definition.dataset,
                    **row,
                    "authority": DataAuthority.CURRENT_REVISED_CONTEXT_ONLY.value,
                    "historical_pit_model_input_allowed": False,
                    "prospective_context_allowed": True,
                    "retrieved_at": payload["retrieved_at"],
                    "source_path": str(path),
                    "source_sha256": source_hash,
                }
            )
        inventory_rows.append(
            {
                "provider": definition.provider,
                "dataset": definition.dataset,
                "pqci_roles": "|".join(definition.roles),
                "declared_record_count": payload.get("record_count"),
                "parsed_rows": len(parsed),
                "retrieved_at": payload["retrieved_at"],
                "retrieval_before_cutoff": cutoff_pass,
                "source_path": str(path),
                "source_sha256": source_hash,
                "authority": DataAuthority.CURRENT_REVISED_CONTEXT_ONLY.value,
                "historical_pit_model_input_allowed": False,
                "status": "CURRENT_REVISED_CONTEXT_READY"
                if cutoff_pass and parsed
                else "FAIL_CLOSED",
            }
        )
    inventory = pd.DataFrame(inventory_rows)
    canonical = pd.DataFrame(canonical_rows)
    route_rows: list[dict[str, object]] = []
    for profile in INDUSTRIALS_SUBINDUSTRIES:
        applicable = [
            item for item in CONTEXT_DATASETS if item.selector(profile.code)
        ]
        ready = inventory.loc[
            inventory["dataset"].isin([item.dataset for item in applicable])
            & inventory["status"].eq("CURRENT_REVISED_CONTEXT_READY")
        ]
        covered_roles = {
            role
            for item in applicable
            if item.dataset in set(ready["dataset"])
            for role in item.roles
        }
        route_rows.append(
            {
                "subindustry_code": profile.code,
                "ticker": profile.representative_ticker,
                "context_datasets": "|".join(
                    sorted(item.dataset for item in applicable)
                ),
                "ready_context_datasets": len(ready),
                "price_context_ready": "P" in covered_roles,
                "quantity_context_ready": "Q" in covered_roles,
                "cost_context_ready": "C" in covered_roles,
                "investment_context_ready": "I" in covered_roles,
                "pqci_context_complete": covered_roles == {"P", "Q", "C", "I"},
                "historical_pit_model_input_allowed": False,
                "prospective_context_allowed": True,
                "authority": DataAuthority.CURRENT_REVISED_CONTEXT_ONLY.value,
            }
        )
    audit = pd.DataFrame(
        [
            {
                "datasets_declared": len(CONTEXT_DATASETS),
                "datasets_ready": int(
                    inventory["status"].eq("CURRENT_REVISED_CONTEXT_READY").sum()
                ),
                "canonical_rows": len(canonical),
                "source_hash_coverage_pct": float(
                    inventory["source_sha256"].notna().mean() * 100.0
                ),
                "retrieval_cutoff_violations": int(
                    (~inventory["retrieval_before_cutoff"].fillna(False)).sum()
                ),
                "subindustries_with_full_context_pqci": int(
                    pd.DataFrame(route_rows)["pqci_context_complete"].sum()
                ),
                "historical_pit_model_input_allowed": False,
                "status": "CURRENT_REVISED_CONTEXT_READY_NOT_OOS_AUTHORITY",
            }
        ]
    )
    return {
        "arcana_pqci_source_inventory": inventory,
        "arcana_pqci_current_revised_canonical": canonical,
        "subindustry_pqci_context_routes": pd.DataFrame(route_rows),
        "arcana_pqci_context_audit": audit,
    }
