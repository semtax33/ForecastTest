from __future__ import annotations

from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v273.router import route_document_blocks_v273
from equity_platform.text_ie.v273.semantics import augment_candidates_v273
from scripts.architecture.parser_holdout import build_candidate_pool, select_candidate_blocks
from scripts.architecture.v272_fifteenth_holdout_candidates import _generate as generate_v272


CONFIG = PROJECT_ROOT / "configs/certification/platform_v273_sixteenth_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_7_3_spacy_semantic_clause"
CANDIDATES = OUTPUT / "sixteenth_holdout_candidates.csv"
ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
SNAPSHOT = {
    "compiler": PROJECT_ROOT / "equity_platform/text_ie/dsl/compiler.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/runtime.py",
    "spacy_backend": PROJECT_ROOT / "equity_platform/text_ie/spacy_backend.py",
    "ontology": PROJECT_ROOT / "equity_platform/text_ie/ontology.py",
    "quantities": PROJECT_ROOT / "equity_platform/text_ie/quantities.py",
    "validation": PROJECT_ROOT / "equity_platform/text_ie/validation.py",
    "v271_semantics": PROJECT_ROOT / "equity_platform/text_ie/v271/semantics.py",
    "v271_runtime": PROJECT_ROOT / "equity_platform/text_ie/v271/runtime.py",
    "v271_router": PROJECT_ROOT / "equity_platform/text_ie/v271/router.py",
    "v271_init": PROJECT_ROOT / "equity_platform/text_ie/v271/__init__.py",
    "v271_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v271_semantic_laws.arc",
    "v272_semantics": PROJECT_ROOT / "equity_platform/text_ie/v272/semantics.py",
    "v272_runtime": PROJECT_ROOT / "equity_platform/text_ie/v272/runtime.py",
    "v272_router": PROJECT_ROOT / "equity_platform/text_ie/v272/router.py",
    "v272_init": PROJECT_ROOT / "equity_platform/text_ie/v272/__init__.py",
    "v272_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v272_semantic_laws.arc",
    "v273_semantics": PROJECT_ROOT / "equity_platform/text_ie/v273/semantics.py",
    "v273_runtime": PROJECT_ROOT / "equity_platform/text_ie/v273/runtime.py",
    "v273_router": PROJECT_ROOT / "equity_platform/text_ie/v273/router.py",
    "v273_init": PROJECT_ROOT / "equity_platform/text_ie/v273/__init__.py",
    "v273_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v273_semantic_laws.arc",
}


def load_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["code_snapshot_sha256"])
    mismatch = {
        name: sha256_file(path)
        for name, path in SNAPSHOT.items()
        if sha256_file(path) != expected[name]
    }
    if mismatch:
        raise ValueError(f"V2.7.3 changed after sixteenth holdout declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.7.3 sixteenth holdout source hash mismatch: {ticker}")
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
    return augment_candidates_v273(document, generate_v272(document))


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_snapshot(config)
    return build_candidate_pool(
        config=config,
        documents=documents(),
        generate_candidates=_generate,
        route_blocks=route_document_blocks_v273,
    )


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    return select_candidate_blocks(
        candidate_pool(), config, benchmark_label="V2.7.3 sixteenth holdout"
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
