from pathlib import Path

from energy_nowcast.config import ProjectPaths, load_config
from energy_nowcast.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]
PATHS = ProjectPaths(root=ROOT)


def test_v331_validation_infrastructure_and_shrinkage():
    result = run_pipeline(load_config(ROOT / "configs" / "v3_3_1.json"), PATHS)
    overall = result.metrics.loc[
        result.metrics["ticker"].eq("ALL")
        & result.metrics["evaluation_split"].eq("all")
    ].iloc[0]
    assert overall["mase"] < 1.0
    assert overall["mae_log_points"] < 9.3
    assert len(result.validation.loc[result.validation["evaluation_split"].eq("untouched_test")]) == 8
    eog = result.weights.set_index("ticker").loc["EOG"]
    assert eog["raw_structural_weight"] == 1.0
    assert eog["shrunk_structural_weight"] == 0.875
    assert not result.cutoff_audit["cutoff_status"].eq("FAIL_AFTER_CUTOFF").any()
    assert result.metadata["validation_gates"]["v3_3_1_infrastructure"]["passed"]


def test_v34_promotes_basis_but_rejects_weak_company_expansions():
    result = run_pipeline(load_config(ROOT / "configs" / "v3_4.json"), PATHS)
    decisions = result.promotion_decisions.set_index(["stage", "ticker"])
    assert bool(decisions.loc[("V3.4_REALIZED_BASIS", "EOG"), "promoted"])
    assert not bool(decisions.loc[("COMPONENT_EXPANSION", "COP"), "promoted"])
    assert not bool(decisions.loc[("COMPONENT_EXPANSION", "FANG"), "promoted"])
    assert not bool(decisions.loc[("COMPONENT_EXPANSION", "DVN"), "promoted"])
    overall = result.metrics.loc[
        result.metrics["ticker"].eq("ALL")
        & result.metrics["evaluation_split"].eq("all")
    ].iloc[0]
    assert overall["mae_log_points"] < 9.08
    assert result.nowcast.set_index("ticker").loc["EOG", "structural_model_type"] == "V3_4_REALIZED_BASIS"
