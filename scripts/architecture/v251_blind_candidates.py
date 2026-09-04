from __future__ import annotations

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
import scripts.architecture.v25_blind_candidates as base


CONFIG = PROJECT_ROOT / "configs/certification/platform_v251_blind_set.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_5_1_precision_adjudication"
CANDIDATES = OUTPUT / "blind_sentence_candidates.csv"


def _configure() -> None:
    base.CONFIG = CONFIG
    base.OUTPUT = OUTPUT
    base.CANDIDATES = CANDIDATES


def load_blind_config():
    _configure()
    return base.load_blind_config()


def verify_candidate_artifact(config):
    _configure()
    return base.verify_candidate_artifact(config)


def _documents():
    _configure()
    return base._documents()


def main() -> int:
    _configure()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
