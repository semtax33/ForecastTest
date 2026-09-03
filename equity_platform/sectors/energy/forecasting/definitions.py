from __future__ import annotations

from dataclasses import dataclass

from equity_platform.ir import DriverRole


@dataclass(frozen=True)
class SubindustryForecastDefinition:
    """Explicit Anchor -> Bridge -> validation contract for one subindustry."""

    primary_targets: tuple[str, ...]
    secondary_targets: tuple[str, ...]
    validation_targets: tuple[str, ...]
    driver_roles: tuple[tuple[str, DriverRole], ...]
    bridge: str


ENERGY_SUBINDUSTRIES = {
    "exploration_production": SubindustryForecastDefinition(
        primary_targets=("production", "realized_price"),
        secondary_targets=("revenue", "operating_margin"),
        validation_targets=("fcff", "roic"),
        driver_roles=(
            ("production", DriverRole.QUANTITY),
            ("realized_price", DriverRole.PRICE),
            ("unit_cost", DriverRole.COST),
            ("reserve_replacement", DriverRole.INVESTMENT),
        ),
        bridge="production_x_realized_price_minus_unit_cost",
    ),
    "refining": SubindustryForecastDefinition(
        primary_targets=("throughput", "refining_margin"),
        secondary_targets=("revenue", "adjusted_ebitda"),
        validation_targets=("operating_income", "fcff", "roic"),
        driver_roles=(
            ("throughput", DriverRole.QUANTITY),
            ("product_price", DriverRole.PRICE),
            ("crude_and_opex", DriverRole.COST),
            ("maintenance_capex", DriverRole.INVESTMENT),
        ),
        bridge="throughput_x_product_price_and_crack_capture",
    ),
    "midstream": SubindustryForecastDefinition(
        primary_targets=("volume", "adjusted_ebitda"),
        secondary_targets=("revenue",),
        validation_targets=("fcff", "roic"),
        driver_roles=(
            ("pipeline_volume", DriverRole.QUANTITY),
            ("fee_tariff", DriverRole.PRICE),
            ("operating_cost", DriverRole.COST),
            ("maintenance_capex", DriverRole.INVESTMENT),
        ),
        bridge="volume_x_fee_contract_mix_to_adjusted_ebitda",
    ),
    "services": SubindustryForecastDefinition(
        primary_targets=("activity", "pricing", "utilization"),
        secondary_targets=("revenue", "operating_margin"),
        validation_targets=("ebit", "fcff", "roic"),
        driver_roles=(
            ("activity", DriverRole.QUANTITY),
            ("pricing", DriverRole.PRICE),
            ("labor_and_input_cost", DriverRole.COST),
            ("growth_capex", DriverRole.INVESTMENT),
        ),
        bridge="activity_x_pricing_x_utilization_to_margin",
    ),
    "integrated": SubindustryForecastDefinition(
        primary_targets=("upstream_earnings", "downstream_earnings", "chemical_earnings"),
        secondary_targets=("consolidated_revenue", "consolidated_ebit"),
        validation_targets=("fcff", "roic"),
        driver_roles=(
            ("segment_volume", DriverRole.QUANTITY),
            ("segment_price", DriverRole.PRICE),
            ("segment_cost", DriverRole.COST),
            ("segment_capex", DriverRole.INVESTMENT),
        ),
        bridge="segment_earnings_sum_of_parts",
    ),
}
