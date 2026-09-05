from __future__ import annotations

from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v284.router import route_document_blocks_v284
from equity_platform.text_ie.v284.semantics import augment_candidates_v284
from scripts.architecture.parser_holdout import build_candidate_pool, select_candidate_blocks
import scripts.architecture.v283_twenty_sixth_holdout_candidates as parent


CONFIG = PROJECT_ROOT / "configs/certification/platform_v284_twenty_seventh_b_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_8_4_economic_roles"
CANDIDATES = OUTPUT / "twenty_seventh_b_holdout_candidates.csv"
ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
V284_SNAPSHOT = {
    "semantics": PROJECT_ROOT / "equity_platform/text_ie/v284/semantics.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/v284/runtime.py",
    "router": PROJECT_ROOT / "equity_platform/text_ie/v284/router.py",
    "init": PROJECT_ROOT / "equity_platform/text_ie/v284/__init__.py",
    "rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v284_economic_roles.arc",
}


def load_config() -> dict[str, object]:
    inherited = parent.load_config()
    inherited.update(tomllib.loads(CONFIG.read_text(encoding="utf-8")))
    return inherited


def verify_snapshot(config: dict[str, object]) -> None:
    parent.verify_snapshot(config)
    expected = dict(config["v284_code_snapshot_sha256"])
    mismatch = {name: sha256_file(path) for name, path in V284_SNAPSHOT.items() if sha256_file(path) != expected[name]}
    if mismatch:
        raise ValueError(f"V2.8.4 changed after twenty-seventh-B declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.8.4 twenty-seventh-B source hash mismatch: {ticker}")
        available_at = path.name[:10]
        output[ticker] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(ticker, "COMPANY_IR", "EARNINGS_RELEASE_OR_PRESENTATION", available_at, str(pd.Timestamp(available_at).to_period("Q"))),
            expected_sha256=str(source["sha256"]),
            source_uri=path.as_uri(),
            include_tables=False,
            include_inline_facts=False,
        )
    return output


def _generate(document: object):
    return augment_candidates_v284(document, tuple(parent._generate(document)))


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_snapshot(config)
    return build_candidate_pool(config=config, documents=documents(), generate_candidates=_generate, route_blocks=route_document_blocks_v284)


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    pool = candidate_pool()
    target = int(config["blocks_per_issuer"])
    insufficient = {ticker: int(pool["ticker"].eq(ticker).sum()) for ticker in config["evaluation_tickers"] if int(pool["ticker"].eq(ticker).sum()) < target}
    if insufficient:
        raise ValueError(f"Insufficient eligible blocks before artifact write: {insufficient}")
    return select_candidate_blocks(pool, config, benchmark_label="V2.8.4 twenty-seventh-B holdout")


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
