from __future__ import annotations

import pandas as pd


def apply_standard_target_authority(
    frame: pd.DataFrame,
    *,
    route_column: str,
    champion_column: str,
    structural_anchor_coverage_column: str | None = None,
) -> pd.DataFrame:
    """Attach fail-closed research, economic-causality, terminal and production rights."""
    authority = frame.copy()
    structural = authority[route_column].astype(str).str.startswith("STRUCTURAL")
    complete_anchor = True
    if structural_anchor_coverage_column is not None:
        complete_anchor = authority[structural_anchor_coverage_column].eq(100.0)
    authority["research_performance_claim_allowed"] = authority[champion_column].astype(bool)
    authority["economic_component_claim_allowed"] = structural & authority[champion_column].astype(bool) & complete_anchor
    authority["reinvestment_forecast_claim_allowed"] = False
    authority["roic_forecast_claim_allowed"] = False
    authority["terminal_input_allowed"] = False
    authority["production_input_allowed"] = False
    return authority
