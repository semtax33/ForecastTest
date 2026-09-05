from __future__ import annotations

import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v281.router import route_document_blocks_v281
from equity_platform.text_ie.v281.semantics import augment_candidates_v281
from scripts.architecture.parser_holdout import build_candidate_pool, select_candidate_blocks
import scripts.architecture.v280_twenty_third_holdout_candidates as parent


CONFIG = PROJECT_ROOT / "configs/certification/platform_v281_twenty_fourth_holdout.toml"
BASE_CONFIG = PROJECT_ROOT / "configs/certification/platform_v280_twenty_third_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_8_1_hierarchical_context_recovery"
CANDIDATES = OUTPUT / "twenty_fourth_holdout_candidates.csv"
V281_SNAPSHOT = {
    "semantics": PROJECT_ROOT / "equity_platform/text_ie/v281/semantics.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/v281/runtime.py",
    "router": PROJECT_ROOT / "equity_platform/text_ie/v281/router.py",
    "init": PROJECT_ROOT / "equity_platform/text_ie/v281/__init__.py",
    "rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v281_hierarchical_context.arc",
}


def load_config() -> dict[str, object]:
    inherited = tomllib.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    override = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    inherited.update(override)
    return inherited


def verify_snapshot(config: dict[str, object]) -> None:
    parent.verify_snapshot(config)
    expected = dict(config["v281_code_snapshot_sha256"])
    mismatch = {
        name: sha256_file(path)
        for name, path in V281_SNAPSHOT.items()
        if sha256_file(path) != expected[name]
    }
    if mismatch:
        raise ValueError(f"V2.8.1 changed after twenty-fourth declaration: {mismatch}")


def documents() -> dict[str, object]:
    original_config = parent.CONFIG
    original_loader = parent.load_config
    try:
        parent.CONFIG = CONFIG
        parent.load_config = load_config
        return parent.documents()
    finally:
        parent.CONFIG = original_config
        parent.load_config = original_loader


def _generate(document: object):
    return augment_candidates_v281(document, tuple(parent._generate(document)))


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_snapshot(config)
    return build_candidate_pool(
        config=config,
        documents=documents(),
        generate_candidates=_generate,
        route_blocks=route_document_blocks_v281,
    )


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    pool = candidate_pool()
    target = int(config["blocks_per_issuer"])
    insufficient = {
        ticker: int(pool["ticker"].eq(ticker).sum())
        for ticker in config["evaluation_tickers"]
        if int(pool["ticker"].eq(ticker).sum()) < target
    }
    if insufficient:
        raise ValueError(f"Insufficient eligible blocks before artifact write: {insufficient}")
    return select_candidate_blocks(pool, config, benchmark_label="V2.8.1 twenty-fourth holdout")


def main() -> int:
    frame = candidate_blocks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CANDIDATES, index=False)
    print(frame.groupby(["ticker", "sampling_stratum"]).size().to_string())
    print(f"TOTAL={len(frame)}")
    print(f"CANDIDATE_SHA256={sha256_file(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
