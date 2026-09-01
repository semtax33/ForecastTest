from __future__ import annotations

import pandas as pd

from .taxonomy import SUBINDUSTRY_TICKERS, phase_for_subindustry


_DRIVER_COVERAGE = {
    "integrated": {
        "primary_operating_driver": "SEGMENT_PRICE_AND_VOLUME_SUM_OF_PARTS",
        "company_specific_operating_kpi": False,
        "active_proxy": "EIA_STEO_PRICE_AND_US_PRODUCTION_WITH_FIXED_SEGMENT_WEIGHTS",
        "proxy_scope": "US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR",
        "configuration_status": "FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED",
    },
    "refining": {
        "primary_operating_driver": "FORWARD_PRODUCT_PRICE_X_THROUGHPUT",
        "company_specific_operating_kpi": False,
        "active_proxy": "EIA_STEO_US_REFINERY_CRUDE_INPUT",
        "proxy_scope": "US_GROUP_PROXY_NOT_COMPANY_GUIDANCE",
        "configuration_status": "COMPANY_THROUGHPUT_GUIDANCE_UNAVAILABLE_IN_STRUCTURED_INPUT",
    },
    "midstream": {
        "primary_operating_driver": "CONTRACT_FEE_X_GAS_AND_LIQUID_VOLUME",
        "company_specific_operating_kpi": False,
        "active_proxy": "EIA_STEO_PRODUCTION_WITH_FIXED_FEE_AND_VOLUME_MIX",
        "proxy_scope": "US_MACRO_PLUS_COMPANY_RESEARCH_PRIOR",
        "configuration_status": "FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED",
    },
    "services": {
        "primary_operating_driver": "RIG_ACTIVITY_X_SERVICE_INTENSITY_X_PRICING",
        "company_specific_operating_kpi": False,
        "active_proxy": "EIA_BAKER_HUGHES_RIGS_AND_STEO_PRODUCTION_PRICE",
        "proxy_scope": "US_AND_GLOBAL_MACRO_PLUS_COMPANY_RESEARCH_PRIOR",
        "configuration_status": "FIXED_RESEARCH_PRIOR_NOT_FILING_PARSED",
    },
}


def operational_kpi_coverage() -> pd.DataFrame:
    """Declare where the research model uses transparent operating-data proxies."""
    rows: list[dict[str, object]] = []
    for subindustry, tickers in SUBINDUSTRY_TICKERS.items():
        specification = _DRIVER_COVERAGE[subindustry]
        for ticker in tickers:
            rows.append(
                {
                    "phase": phase_for_subindustry(subindustry),
                    "subindustry": subindustry,
                    "ticker": ticker,
                    **specification,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["phase", "subindustry", "ticker"]
    ).reset_index(drop=True)


def macro_overlay_status(research_gates: pd.DataFrame) -> pd.DataFrame:
    """Allow macro residual overlays only after the structural gate passes."""
    rows: list[dict[str, object]] = []
    for _, gate in research_gates.iterrows():
        passed = bool(gate["research_gate"])
        rows.append(
            {
                "phase": int(gate["phase"]),
                "subindustry": gate["subindustry"],
                "structural_gate": passed,
                "macro_residual_overlay_enabled": False,
                "status": (
                    "ELIGIBLE_FOR_SEPARATE_OVERLAY_RESEARCH"
                    if passed
                    else "DISABLED_UNTIL_STRUCTURAL_GATE_PASSES"
                ),
                "promotion_effect": "NONE_RESEARCH_ONLY",
            }
        )
    return pd.DataFrame(rows)
