from __future__ import annotations

import pandas as pd

from .domain import DataAuthority, DriverRole, SourceDefinition, SubindustryProfile


P, Q, C, I = (
    DriverRole.PRICE,
    DriverRole.QUANTITY,
    DriverRole.COST,
    DriverRole.INVESTMENT,
)


SEC = SourceDefinition(
    "SEC",
    "EDGAR 10-K/10-Q Inline XBRL including tagged notes",
    "https://www.sec.gov/edgar/search/",
    (C, I),
    DataAuthority.COMPANY_DISCLOSED_PIT_INPUT,
)
IR = SourceDefinition(
    "Company IR",
    "Earnings releases and operating KPI tables",
    "COMPANY_SPECIFIC_IR_URL",
    (P, Q, C, I),
    DataAuthority.COMPANY_DISCLOSED_PIT_INPUT,
)
BLS_PPI = SourceDefinition(
    "BLS",
    "PPI archived as-released detailed reports",
    "https://www.bls.gov/ppi/",
    (P, C),
    DataAuthority.HISTORICAL_PIT_MODEL_INPUT,
)
BLS_CES = SourceDefinition(
    "BLS",
    "Current Employment Statistics employment, hours and wages",
    "https://www.bls.gov/ces/",
    (Q, C),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
CENSUS_M3 = SourceDefinition(
    "Census",
    "Manufacturers shipments, inventories and orders",
    "https://www.census.gov/manufacturing/m3/",
    (Q, I),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
CENSUS_CONSTRUCTION = SourceDefinition(
    "Census",
    "Construction spending, permits and starts",
    "https://www.census.gov/construction/",
    (P, Q, I),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
BEA_IO = SourceDefinition(
    "BEA",
    "Input-output requirements and industry accounts",
    "https://www.bea.gov/industry/input-output-accounts-data",
    (P, Q, C),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
BTS = SourceDefinition(
    "BTS",
    "Transportation statistics, T-100 and freight indicators",
    "https://www.bts.gov/browse-statistical-products-and-data",
    (P, Q, C),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
EIA = SourceDefinition(
    "EIA",
    "Petroleum and transportation fuel prices",
    "https://www.eia.gov/opendata/",
    (P, C),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
USASPENDING = SourceDefinition(
    "USAspending.gov",
    "Federal contract awards and obligations",
    "https://api.usaspending.gov/",
    (P, Q),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
USDA = SourceDefinition(
    "USDA NASS",
    "Crop production, prices and farm machinery demand context",
    "https://quickstats.nass.usda.gov/",
    (P, Q),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
EPA = SourceDefinition(
    "EPA",
    "Waste, recycling and environmental facility statistics",
    "https://www.epa.gov/facts-and-figures-about-materials-waste-and-recycling",
    (Q, C),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
STB = SourceDefinition(
    "Surface Transportation Board",
    "Rail carloads, waybill and service data",
    "https://www.stb.gov/reports-data/",
    (P, Q, C, I),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
FHWA = SourceDefinition(
    "FHWA",
    "Highway traffic volumes and freight analysis framework",
    "https://www.fhwa.dot.gov/policyinformation/travel_monitoring/tvt.cfm",
    (Q, I),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
FAA = SourceDefinition(
    "FAA",
    "Airport operations and passenger activity",
    "https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats",
    (Q, I),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)
USACE = SourceDefinition(
    "USACE Waterborne Commerce Statistics Center",
    "Waterborne commerce, ports and vessel movements",
    "https://www.iwr.usace.army.mil/about/technical-centers/wcsc-waterborne-commerce-statistics-center/",
    (Q, I),
    DataAuthority.CURRENT_REVISED_CONTEXT_ONLY,
)


def _profile(
    code: str,
    name: str,
    group: str,
    ticker: str,
    target: str,
    price: str,
    quantity: str,
    cost: str,
    investment: str,
    bridge: str,
    *industry_sources: SourceDefinition,
    sec_form_regime: str = "10-K_10-Q",
) -> SubindustryProfile:
    return SubindustryProfile(
        code=code,
        name=name,
        industry_group=group,
        representative_ticker=ticker,
        primary_target=target,
        price_anchor=price,
        quantity_anchor=quantity,
        cost_anchor=cost,
        investment_anchor=investment,
        economic_bridge=bridge,
        sources=(SEC, IR, *industry_sources),
        sec_form_regime=sec_form_regime,
    )


INDUSTRIALS_SUBINDUSTRIES: tuple[SubindustryProfile, ...] = (
    _profile("aerospace_defense", "Aerospace & Defense", "Capital Goods", "GD", "segment_revenue_margin", "contract escalation and platform pricing", "funded/total backlog, deliveries and awards", "labor, material and program execution", "capex, working capital and program development", "backlog conversion plus PPI -> revenue; mix and price-cost -> margin", BLS_PPI, BLS_CES, CENSUS_M3, USASPENDING),
    _profile("building_products", "Building Products", "Capital Goods", "CARR", "organic_sales_margin", "equipment and aftermarket price", "HVAC equipment volumes, orders and installed base", "metals, electronics and labor", "capacity, product development and acquisitions", "price x equipment/aftermarket volume -> sales; mix-price-cost -> margin", BLS_PPI, CENSUS_CONSTRUCTION, BEA_IO),
    _profile("construction_engineering", "Construction & Engineering", "Capital Goods", "PWR", "revenue_ebitda", "contract rate and change-order realization", "backlog burn, awards and construction put-in-place", "skilled labor, materials and subcontractors", "equipment, acquisitions and working capital", "beginning backlog x conversion plus awards -> revenue; execution spread -> margin", BLS_CES, CENSUS_CONSTRUCTION, BLS_PPI),
    _profile("electrical_components", "Electrical Components & Equipment", "Capital Goods", "ETN", "organic_sales_segment_margin", "electrical equipment price", "orders, backlog and data-center/nonresidential activity", "copper, electrical components and labor", "capacity and R&D", "orders/backlog conversion x price -> organic sales; price-cost/mix -> margin", BLS_PPI, CENSUS_M3, CENSUS_CONSTRUCTION),
    _profile("heavy_electrical", "Heavy Electrical Equipment", "Capital Goods", "GEV", "orders_revenue_margin", "grid equipment and service pricing", "orders, backlog and generation/grid additions", "steel, copper, labor and warranty", "factory capacity and product development", "orders and backlog burn -> revenue; service mix and cost execution -> margin", BLS_PPI, CENSUS_M3, EIA),
    _profile("industrial_conglomerates", "Industrial Conglomerates", "Capital Goods", "HON", "segment_sales_profit", "segment-specific realized price", "segment orders/backlog/installed base", "segment-specific material and labor basket", "segment capex, R&D and M&A", "forecast each segment anchor then consolidate with corporate bridge", BLS_PPI, CENSUS_M3, BEA_IO),
    _profile("construction_machinery", "Construction Machinery & Heavy Transportation Equipment", "Capital Goods", "CAT", "dealer_sales_revenue_margin", "machine price and used-equipment residuals", "dealer retail sales and end-user activity", "steel, freight, engines and labor", "dealer inventory, capex and R&D", "dealer sales plus inventory channel and price -> revenue; price-cost -> margin", BLS_PPI, CENSUS_M3, CENSUS_CONSTRUCTION),
    _profile("agricultural_machinery", "Agricultural & Farm Machinery", "Capital Goods", "DE", "production_sales_margin", "equipment price", "retail sales, acres, crop economics and dealer inventory", "steel, engines, logistics and labor", "R&D, precision-ag platform and inventory", "farm income/order cycle x price -> equipment sales; production mix -> margin", BLS_PPI, USDA, CENSUS_M3),
    _profile("industrial_machinery", "Industrial Machinery & Components", "Capital Goods", "ITW", "organic_growth_margin", "price realization", "industrial production and customer capex", "materials and labor", "R&D, capex and working capital", "end-market volume plus price -> organic growth; 80/20 mix and price-cost -> margin", BLS_PPI, CENSUS_M3, BEA_IO),
    _profile("trading_distributors", "Trading Companies & Distributors", "Capital Goods", "GWW", "daily_sales_gross_margin", "price and product mix", "daily volume, customer count and industrial activity", "product acquisition and freight", "inventory, distribution centers and digital platform", "daily sales = price x volume x selling days; spread -> gross/operating margin", BLS_PPI, CENSUS_M3, BEA_IO),
    _profile("commercial_printing", "Commercial Printing", "Commercial Services", "QUAD", "net_sales_ebitda", "print and marketing-service pricing", "pages, campaigns and client activity", "paper, ink, postage and labor", "press utilization, capex and working capital", "volume x price plus services mix -> sales; utilization-price-cost -> EBITDA", BLS_PPI, BLS_CES, BEA_IO),
    _profile("environmental_services", "Environmental & Facilities Services", "Commercial Services", "WM", "revenue_ebitda", "yield and commodity price", "collection volume, landfill tons and recycling volume", "labor, fuel and maintenance", "fleet, landfill development and working capital", "volume x yield plus recycling commodities -> revenue; route density-price-cost -> EBITDA", BLS_PPI, EIA, EPA),
    _profile("office_services", "Office Services & Supplies", "Commercial Services", "ACCO", "sales_margin", "product price", "units and channel inventory", "paper, resin, freight and labor", "inventory, tooling and restructuring", "price x volume plus channel inventory -> sales; sourcing and mix -> margin", BLS_PPI, BEA_IO),
    _profile("diversified_support", "Diversified Support Services", "Commercial Services", "CTAS", "organic_revenue_margin", "price per customer/route", "customer locations, employment and retention", "labor, energy and garments", "route density, facilities and rental inventory", "customers x penetration x price -> revenue; route density -> margin", BLS_CES, BLS_PPI, BEA_IO),
    _profile("security_alarm", "Security & Alarm Services", "Commercial Services", "ADT", "recurring_revenue_ebitda", "monthly recurring revenue per customer", "gross adds, attrition and subscriber base", "installation, equipment and service labor", "subscriber acquisition cost and capitalized equipment", "opening subscribers + adds - attrition x ARPU -> recurring revenue", BLS_CES, BLS_PPI),
    _profile("human_resources", "Human Resource & Employment Services", "Commercial Services", "MAN", "revenue_gross_profit", "billing rate and wage spread", "billable hours and temporary employment", "wages and recruiter labor", "working capital and digital platform", "billable hours x bill rate -> revenue; bill-pay spread -> gross profit", BLS_CES, BEA_IO),
    _profile("research_consulting", "Research & Consulting Services", "Commercial Services", "VRSK", "subscription_revenue_margin", "subscription price and seat mix", "renewal, seats and data usage", "professional labor, cloud and data", "data assets, software development and M&A", "opening ARR + bookings - churn -> revenue; incremental margin -> EBIT", BLS_CES, BEA_IO),
    _profile("air_freight_logistics", "Air Freight & Logistics", "Transportation", "UPS", "revenue_operating_profit", "revenue per piece and fuel surcharge", "pieces per day, weight and network days", "labor, jet/diesel fuel and purchased transport", "aircraft, hubs, vehicles and working capital", "pieces x revenue per piece -> revenue; network density-price-cost -> margin", BTS, EIA, BLS_CES),
    _profile("passenger_airlines", "Passenger Airlines", "Transportation", "DAL", "passenger_revenue_casm", "passenger revenue per ASM and ancillary yield", "ASM, load factor and RPM", "jet fuel, labor and maintenance", "fleet capex, leases and working capital", "ASM x load factor x yield -> revenue; CASM and fuel -> operating margin", BTS, EIA, BLS_CES),
    _profile("marine_transportation", "Marine Transportation", "Transportation", "MATX", "revenue_ebitda", "freight rate and fuel surcharge", "container volume, voyages and utilization", "bunker fuel, charter and labor", "vessels, containers and drydock capex", "container volume x freight rate plus logistics -> revenue; voyage economics -> EBITDA", BTS, EIA, USACE),
    _profile("rail_transportation", "Rail Transportation", "Transportation", "UNP", "revenue_operating_ratio", "revenue per carload", "carloads and revenue ton-miles", "fuel, labor and purchased services", "track, locomotives and working capital", "carloads x revenue/carload -> revenue; velocity and price-cost -> operating ratio", STB, EIA, BLS_CES),
    _profile("cargo_ground_transport", "Cargo Ground Transportation", "Transportation", "ODFL", "revenue_operating_ratio", "revenue per hundredweight excluding fuel", "shipments per day and weight per shipment", "driver wages, diesel and purchased transport", "tractors, trailers and service centers", "shipments x weight x yield -> revenue; density and cost -> operating ratio", BTS, EIA, BLS_CES),
    _profile("passenger_ground_transport", "Passenger Ground Transportation", "Transportation", "UBER", "gross_bookings_ebitda", "gross bookings per trip", "trips and monthly active platform consumers", "driver incentives, insurance and support", "platform development and working capital", "trips x bookings/trip -> gross bookings; take rate -> revenue -> EBITDA", BTS, BLS_CES, BEA_IO),
    _profile("airport_services", "Airport Services", "Transportation Infrastructure", "PAC", "passenger_aeronautical_revenue", "tariff and commercial revenue per passenger", "domestic/international passengers and operations", "labor, utilities and concession costs", "terminal/runway capex and concessions", "passengers x aeronautical/commercial yield -> revenue; concession economics -> cash flow", FAA, BTS, sec_form_regime="20-F_6-K_IFRS"),
    _profile("highways_railtracks", "Highways & Railtracks", "Transportation Infrastructure", "FER", "traffic_revenue_ebitda", "toll per vehicle and access charge", "traffic, passenger journeys and train-km", "maintenance, labor and energy", "concession capex and regulated asset base", "traffic x tariff -> revenue; maintenance and concession capex -> FCFF", FHWA, STB, sec_form_regime="20-F_6-K_IFRS"),
    _profile("marine_ports_services", "Marine Ports & Services", "Transportation Infrastructure", "KEX", "revenue_operating_income", "day rate, towage or handling yield", "barge utilization, tonnage and port calls", "fuel, crews and maintenance", "vessels, terminals and drydock capex", "utilization x capacity x rate -> revenue; voyage/port economics -> margin", USACE, BTS, EIA),
)


for _item in INDUSTRIALS_SUBINDUSTRIES:
    _item.validate()


def get_subindustry_profile(code: str) -> SubindustryProfile:
    for profile in INDUSTRIALS_SUBINDUSTRIES:
        if profile.code == code:
            return profile
    raise KeyError(code)


def registry_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile in INDUSTRIALS_SUBINDUSTRIES:
        pit_sources = [
            source.source
            for source in profile.sources
            if source.authority == DataAuthority.HISTORICAL_PIT_MODEL_INPUT
        ]
        rows.append(
            {
                "subindustry_code": profile.code,
                "subindustry": profile.name,
                "industry_group": profile.industry_group,
                "representative_ticker": profile.representative_ticker,
                "sec_form_regime": profile.sec_form_regime,
                "primary_target": profile.primary_target,
                "price_anchor": profile.price_anchor,
                "quantity_anchor": profile.quantity_anchor,
                "cost_anchor": profile.cost_anchor,
                "investment_anchor": profile.investment_anchor,
                "economic_bridge": profile.economic_bridge,
                "source_count": len(profile.sources),
                "historical_pit_industry_sources": "|".join(sorted(set(pit_sources))),
                "industry_pit_model_ready": bool(pit_sources),
                "terminal_input_allowed": False,
                "production_promotable": False,
            }
        )
    return pd.DataFrame(rows)
