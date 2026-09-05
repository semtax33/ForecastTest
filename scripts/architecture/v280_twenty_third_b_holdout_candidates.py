from __future__ import annotations

import tomllib

from equity_platform.paths import PROJECT_ROOT
import scripts.architecture.v280_twenty_third_holdout_candidates as base


CONFIG = PROJECT_ROOT / "configs/certification/platform_v280_twenty_third_b_holdout.toml"
BASE_CONFIG = PROJECT_ROOT / "configs/certification/platform_v280_twenty_third_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_8_0_hierarchical_semantic_context"
CANDIDATES = OUTPUT / "twenty_third_b_holdout_candidates.csv"


def load_config() -> dict[str, object]:
    inherited = tomllib.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    override = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    inherited.update(override)
    return inherited


base.CONFIG = CONFIG
base.CANDIDATES = CANDIDATES
base.load_config = load_config

documents = base.documents
verify_snapshot = base.verify_snapshot
candidate_pool = base.candidate_pool
candidate_blocks = base.candidate_blocks


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())

