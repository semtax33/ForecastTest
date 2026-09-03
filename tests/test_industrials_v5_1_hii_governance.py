from __future__ import annotations

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii.benchmark import (
    verify_hii_v5_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v51_governance,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v5_1_hii_governance_research"


def test_v5_parent_remains_immutable() -> None:
    parent = verify_hii_v5_evidence(PROJECT_ROOT)
    assert parent["manifest_sha256"] == "c1a9e4e2ea3f9586472ed8e2ef13cb9ea9e3155a32b4394145d10a5150214f36"


def test_same_oos_minimum_is_diagnostic_and_predeclared_route_is_clean() -> None:
    audit = pd.read_csv(OUTPUT / "hii_route_selection_leakage_audit.csv").iloc[0]
    routes = pd.read_csv(OUTPUT / "hii_company_route_registry.csv").set_index("route")
    assert audit["routes_tested_on_same_oos"] == 6
    assert audit["route_selection_leakage_present"]
    assert audit["v5_reported_route"] == "PIT_INDUSTRY_BRIDGE"
    assert audit["v5_reported_mase"] == pytest.approx(0.6781519925)
    assert audit["corrected_v51_class"] == "BEST_TESTED_DIAGNOSTIC"
    assert audit["clean_predeclared_route"] == "PREDECLARED_EQUAL_BLEND"
    assert audit["clean_predeclared_mase"] == pytest.approx(0.8001205899)
    assert routes.loc["PIT_INDUSTRY_BRIDGE", "selection_class"] == "BEST_TESTED_DIAGNOSTIC"
    assert routes.loc["PREDECLARED_EQUAL_BLEND", "selection_class"] == "CLEAN_PROSPECTIVE_BENCHMARK"
    assert routes["registry_status"].eq("IMMUTABLE_FAILED_AND_ALTERNATE_ROUTE_RECORD").all()


def test_point_and_causal_authorities_are_separate() -> None:
    authority = pd.read_csv(OUTPUT / "hii_authority_namespaces.csv").set_index(
        "authority_namespace"
    )
    assert len(authority) == 7
    assert authority.loc["SEGMENT_REVENUE_POINT_AUTHORITY", "status"] == "RESEARCH_PROSPECTIVE_BENCHMARK"
    assert authority.loc["SEGMENT_REVENUE_CAUSAL_ATTRIBUTION_AUTHORITY", "status"] == "DENIED"
    assert authority.loc["MARGIN_COMPONENT_CAUSAL_AUTHORITY", "status"] == "DENIED"
    assert authority.loc["ROIC_ATTRIBUTION_AUTHORITY", "status"] == "DENIED_HISTORICAL_DIAGNOSTIC_ONLY"
    assert authority.loc["TERMINAL_AUTHORITY", "status"] == "DENIED_CONDITIONAL_SURFACE_ONLY"


def test_v51_governance_manifest_is_frozen() -> None:
    manifest = verify_hii_v51_governance(PROJECT_ROOT)
    assert manifest["immutable"]
    assert manifest["assertions"]["route_selection_leakage_present"]
    assert manifest["assertions"]["clean_predeclared_mase"] == pytest.approx(0.8001205899)
    assert not manifest["assertions"]["terminal_input_allowed"]
    assert not manifest["assertions"]["production_promoted"]
