from __future__ import annotations

from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v24 import generate_recall_candidates
from equity_platform.text_ie.v262 import augment_candidates_v262
from equity_platform.text_ie.v265.semantics import augment_candidates_v265
from equity_platform.text_ie.v266.semantics import augment_candidates_v266
from equity_platform.text_ie.v267.semantics import augment_candidates_v267
from equity_platform.text_ie.v268.semantics import augment_candidates_v268
from equity_platform.text_ie.v269.semantics import augment_candidates_v269
from equity_platform.text_ie.v270.semantics import augment_candidates_v270
from equity_platform.text_ie.v271.router import route_document_blocks_v271
from equity_platform.text_ie.v271.semantics import augment_candidates_v271
from scripts.architecture.parser_holdout import build_candidate_pool, select_candidate_blocks


CONFIG = PROJECT_ROOT / "configs/certification/platform_v271_fourteenth_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_7_1_spacy_semantic_ownership"
CANDIDATES = OUTPUT / "fourteenth_holdout_candidates.csv"
ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
SNAPSHOT = {
    "compiler": PROJECT_ROOT / "equity_platform/text_ie/dsl/compiler.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/runtime.py",
    "spacy_backend": PROJECT_ROOT / "equity_platform/text_ie/spacy_backend.py",
    "ontology": PROJECT_ROOT / "equity_platform/text_ie/ontology.py",
    "quantities": PROJECT_ROOT / "equity_platform/text_ie/quantities.py",
    "validation": PROJECT_ROOT / "equity_platform/text_ie/validation.py",
    "v270_semantics": PROJECT_ROOT / "equity_platform/text_ie/v270/semantics.py",
    "v270_runtime": PROJECT_ROOT / "equity_platform/text_ie/v270/runtime.py",
    "v270_router": PROJECT_ROOT / "equity_platform/text_ie/v270/router.py",
    "v270_init": PROJECT_ROOT / "equity_platform/text_ie/v270/__init__.py",
    "v270_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v270_semantic_laws.arc",
    "v271_semantics": PROJECT_ROOT / "equity_platform/text_ie/v271/semantics.py",
    "v271_runtime": PROJECT_ROOT / "equity_platform/text_ie/v271/runtime.py",
    "v271_router": PROJECT_ROOT / "equity_platform/text_ie/v271/router.py",
    "v271_init": PROJECT_ROOT / "equity_platform/text_ie/v271/__init__.py",
    "v271_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v271_semantic_laws.arc",
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
        raise ValueError(f"V2.7.1 changed after fourteenth holdout declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.7.1 fourteenth holdout source hash mismatch: {ticker}")
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
    base, _ = generate_recall_candidates(document)
    v262 = augment_candidates_v262(document, base)
    v265 = augment_candidates_v265(document, v262)
    v266 = augment_candidates_v266(document, v265)
    v267 = augment_candidates_v267(document, v266)
    v268 = augment_candidates_v268(document, v267)
    v269 = augment_candidates_v269(document, v268)
    v270 = augment_candidates_v270(document, v269)
    return augment_candidates_v271(document, v270)


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_snapshot(config)
    return build_candidate_pool(
        config=config,
        documents=documents(),
        generate_candidates=_generate,
        route_blocks=route_document_blocks_v271,
    )


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    return select_candidate_blocks(
        candidate_pool(), config, benchmark_label="V2.7.1 fourteenth holdout"
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
