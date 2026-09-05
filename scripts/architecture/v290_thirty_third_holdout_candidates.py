from __future__ import annotations

from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v290.router import route_document_blocks_v290
from equity_platform.text_ie.v290.semantics import augment_candidates_v290
from scripts.architecture.parser_holdout import build_candidate_pool, select_candidate_blocks
import scripts.architecture.v289_thirty_second_holdout_candidates as parent


CONFIG = PROJECT_ROOT / "configs/certification/platform_v290_thirty_third_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_9_0_semantic_role_graph"
CANDIDATES = OUTPUT / "thirty_third_holdout_candidates.csv"
ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
V290_SNAPSHOT = {
    "semantics": PROJECT_ROOT / "equity_platform/text_ie/v290/semantics.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/v290/runtime.py",
    "router": PROJECT_ROOT / "equity_platform/text_ie/v290/router.py",
    "init": PROJECT_ROOT / "equity_platform/text_ie/v290/__init__.py",
    "rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v290_semantic_role_graph.arc",
    "test": PROJECT_ROOT / "tests/test_spacy_semantic_role_graph_v290.py",
}


def load_config() -> dict[str, object]:
    inherited = parent.load_config()
    inherited.update(tomllib.loads(CONFIG.read_text(encoding="utf-8")))
    return inherited


def verify_snapshot(config: dict[str, object]) -> None:
    parent.verify_snapshot(config)
    expected = dict(config["v290_code_snapshot_sha256"])
    mismatch = {
        name: sha256_file(path)
        for name, path in V290_SNAPSHOT.items()
        if sha256_file(path) != expected[name]
    }
    if mismatch:
        raise ValueError(f"V2.9.0 changed after thirty-third declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.9.0 thirty-third source hash mismatch: {ticker}")
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


def _generate(document: object):
    return augment_candidates_v290(document, tuple(parent._generate(document)))


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_snapshot(config)
    return build_candidate_pool(
        config=config,
        documents=documents(),
        generate_candidates=_generate,
        route_blocks=route_document_blocks_v290,
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
    return select_candidate_blocks(pool, config, benchmark_label="V2.9.0 thirty-third holdout")


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
