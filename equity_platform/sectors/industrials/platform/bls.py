from __future__ import annotations

import pandas as pd


# Each output series was verified against BLS PPI detailed-report Table 9/11.
# Proxy use is explicit; no proxy is relabeled as a dedicated company KPI.
OUTPUT_SERIES: dict[str, tuple[str, str, str]] = {
    "aerospace_defense": ("WPU142", "Aircraft and aircraft equipment", "DEDICATED_INDUSTRY_OUTPUT"),
    "building_products": ("PCU333415333415", "Air-conditioning and refrigeration equipment", "DEDICATED_INDUSTRY_OUTPUT"),
    "construction_engineering": ("PCU23822X23822X", "Nonresidential plumbing heating and air-conditioning contractors", "CONSTRUCTION_CONTRACTOR_PROXY"),
    "electrical_components": ("PCU335313335313", "Switchgear and switchboard apparatus", "DEDICATED_INDUSTRY_OUTPUT"),
    "heavy_electrical": ("PCU333611333611", "Turbine and turbine generator sets", "DEDICATED_INDUSTRY_OUTPUT"),
    "industrial_conglomerates": ("WPU117", "Electrical machinery and equipment", "CONGLOMERATE_OUTPUT_PROXY"),
    "construction_machinery": ("PCU333120333120", "Construction machinery", "DEDICATED_INDUSTRY_OUTPUT"),
    "agricultural_machinery": ("PCU333111333111", "Farm machinery and equipment", "DEDICATED_INDUSTRY_OUTPUT"),
    "industrial_machinery": ("PCU333998333998", "Miscellaneous general purpose machinery", "INDUSTRIAL_MACHINERY_PROXY"),
    "trading_distributors": ("PCU423800423800", "Machinery and supply merchant wholesalers", "DEDICATED_INDUSTRY_OUTPUT"),
    "commercial_printing": ("PCU323113323113", "Commercial screen printing", "PRINTING_OUTPUT_PROXY"),
    "environmental_services": ("PCU562111562111", "Solid waste collection", "DEDICATED_INDUSTRY_OUTPUT"),
    "office_services": ("PCU322230322230", "Stationery product manufacturing", "OFFICE_SUPPLY_OUTPUT_PROXY"),
    "diversified_support": ("PCU561720561720", "Janitorial services", "DIVERSIFIED_SUPPORT_OUTPUT_PROXY"),
    "security_alarm": ("PCU561612561612", "Security guards and patrol services", "SECURITY_SERVICE_OUTPUT_PROXY"),
    "human_resources": ("PCU561380561380", "Staffing services except PEOs", "DEDICATED_INDUSTRY_OUTPUT"),
    "research_consulting": ("PCU541610541610", "Management consulting services", "CONSULTING_OUTPUT_PROXY"),
    "air_freight_logistics": ("PCU492110492110", "Couriers and express delivery services", "DEDICATED_INDUSTRY_OUTPUT"),
    "passenger_airlines": ("PCU481111481111", "Scheduled passenger air transportation", "DEDICATED_INDUSTRY_OUTPUT"),
    "marine_transportation": ("PCU483111483111", "Deep sea freight transportation", "DEDICATED_INDUSTRY_OUTPUT"),
    "rail_transportation": ("PCU482111482111", "Line-haul railroads", "DEDICATED_INDUSTRY_OUTPUT"),
    "cargo_ground_transport": ("PCU484484", "Truck transportation", "DEDICATED_INDUSTRY_OUTPUT"),
    "passenger_ground_transport": ("PCU484484", "Truck transportation", "PASSENGER_GROUND_OUTPUT_PROXY"),
    "airport_services": ("PCU488119488119", "Other airport operations", "DEDICATED_INDUSTRY_OUTPUT"),
    "highways_railtracks": ("PCU23822X23822X", "Nonresidential specialty contractors", "INFRASTRUCTURE_OUTPUT_PROXY"),
    "marine_ports_services": ("PCU488310488310", "Port and harbor operations", "DEDICATED_INDUSTRY_OUTPUT"),
}


MANUFACTURING_COST = (
    ("WPU102", "Nonferrous metals", 0.35),
    ("WPU107", "Fabricated structural metal products", 0.40),
    ("WPU117", "Electrical machinery and equipment", 0.25),
)
TRANSPORT_DIESEL_COST = (("WPU057303", "No. 2 diesel fuel", 1.0),)
TRANSPORT_JET_COST = (("WPU057203", "Jet fuel", 1.0),)


def _costs(code: str, output: tuple[str, str, str]) -> tuple[tuple[str, str, float], ...]:
    if code in {
        "aerospace_defense", "building_products", "construction_engineering",
        "electrical_components", "heavy_electrical", "industrial_conglomerates",
        "construction_machinery", "agricultural_machinery", "industrial_machinery",
        "trading_distributors",
    }:
        return MANUFACTURING_COST
    if code == "commercial_printing":
        return (("WPU0913", "Paper", 0.70), ("WPU06790919", "Printing ink", 0.30))
    if code == "air_freight_logistics":
        return (("WPU057203", "Jet fuel", 0.50), ("WPU057303", "No. 2 diesel fuel", 0.50))
    if code in {"passenger_airlines", "airport_services"}:
        return TRANSPORT_JET_COST
    if code in {
        "environmental_services", "office_services", "marine_transportation",
        "rail_transportation", "cargo_ground_transport", "passenger_ground_transport",
        "highways_railtracks", "marine_ports_services",
    }:
        return TRANSPORT_DIESEL_COST
    # Labor is the main cost for these services, but historical CES release vintages
    # are not in the lake. A zero-spread fallback keeps price PIT coverage while
    # explicitly disabling a structural price-cost claim.
    return ((output[0], output[1], 1.0),)


def build_industrials_bls_sensor_map() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for code, output in OUTPUT_SERIES.items():
        series_id, title, quality = output
        rows.append(
            {
                "sensor_id": f"{code}_output",
                "series_id": series_id,
                "series_title": title,
                "role": "output_price",
                "segment": code,
                "weight": 1.0,
                "route_note": quality,
                "structural_cost_claim_allowed": False,
            }
        )
        for index, (cost_id, cost_title, weight) in enumerate(_costs(code, output)):
            fallback = cost_id == series_id
            rows.append(
                {
                    "sensor_id": f"{code}_cost_{index + 1}",
                    "series_id": cost_id,
                    "series_title": cost_title,
                    "role": "input_cost",
                    "segment": code,
                    "weight": weight,
                    "route_note": "OUTPUT_PRICE_AS_COST_FALLBACK_NO_STRUCTURAL_SPREAD" if fallback else "PIT_INPUT_COST_PROXY",
                    "structural_cost_claim_allowed": not fallback,
                }
            )
    return pd.DataFrame(rows)
