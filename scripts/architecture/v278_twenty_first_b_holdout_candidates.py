from __future__ import annotations

import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v278.router import route_document_blocks_v278
from scripts.architecture.parser_holdout import build_candidate_pool, select_candidate_blocks
from scripts.architecture.v278_twenty_first_holdout_candidates import (
    ARCANA_IR,
    SNAPSHOT,
    _generate,
)


CONFIG = PROJECT_ROOT / "configs/certification/platform_v278_twenty_first_b_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_7_8_spacy_semantic_roles"
CANDIDATES = OUTPUT / "twenty_first_b_holdout_candidates.csv"


def load_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_snapshot(config: dict[str, object]) -> None:
    snapshot_config = PROJECT_ROOT / str(config["code_snapshot_source"])
    expected = dict(
        tomllib.loads(snapshot_config.read_text(encoding="utf-8"))[
            "code_snapshot_sha256"
        ]
    )
    mismatch = {
        name: sha256_file(path)
        for name, path in SNAPSHOT.items()
        if sha256_file(path) != expected[name]
    }
    if mismatch:
        raise ValueError(f"V2.7.8 changed after twenty-first-B declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.7.8 twenty-first-B source hash mismatch: {ticker}")
        available_at = path.name[:10]
        output[ticker] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(
                ticker,
                "COMPANY_IR",
                "EARNINGS_RELEASE_OR_PRESENTATION",
                available_at,
                str(pd.Timestamp(available_at).to_period("Q")),
            ),
            expected_sha256=str(source["sha256"]),
            source_uri=path.as_uri(),
            include_tables=False,
            include_inline_facts=False,
        )
    return output


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_snapshot(config)
    return build_candidate_pool(
        config=config,
        documents=documents(),
        generate_candidates=_generate,
        route_blocks=route_document_blocks_v278,
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
    return select_candidate_blocks(
        pool, config, benchmark_label="V2.7.8 twenty-first-B holdout"
    )


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
