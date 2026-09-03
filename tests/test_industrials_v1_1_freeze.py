from pathlib import Path

from equity_platform.sectors.industrials.v11_benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]


def test_industrials_v1_1_is_frozen_without_model_promotion() -> None:
    manifest = verify_v11(ROOT)
    assertions = manifest["assertions"]
    assert manifest["research_frozen"] is True
    assert assertions["rpo_anchor_retired"] is True
    assert assertions["backlog_anchor_promoted"] is False
    assert assertions["segment_reconciliation_pass"] is True
    assert assertions["financial_products_separately_valued"] is True
    assert assertions["financial_products_funding_debt_double_counted"] is False
    assert assertions["sotp_component_identity_pass"] is True
    assert assertions["terminal_input_allowed"] is False
    assert assertions["production_promoted"] is False
    assert assertions["live_matched_observations"] == "0/20"
