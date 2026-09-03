from pathlib import Path

from energy_nowcast.research.ep_v19.benchmark import verify_v19


ROOT = Path(__file__).resolve().parents[1]


def test_v19_is_frozen_without_terminal_or_production_authority() -> None:
    manifest = verify_v19(ROOT)
    assertions = manifest["assertions"]
    assert manifest["research_frozen"] is True
    assert assertions["sample_stability_issue_resolved"] is True
    assert assertions["normal_roic_claimed"] is False
    assert assertions["terminal_anchor_replacement_allowed"] is False
    assert assertions["production_promoted"] is False
    assert assertions["live_matched_observations"] == "0/20"
