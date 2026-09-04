from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v24 import generate_recall_candidates
from equity_platform.text_ie.v262 import augment_candidates_v262
from equity_platform.text_ie.v265.router import route_document_blocks_v265
from equity_platform.text_ie.v265.semantics import augment_candidates_v265


CONFIG = PROJECT_ROOT / "configs/certification/platform_v265_eighth_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_6_5_spacy_semantic_recovery"
CANDIDATES = OUTPUT / "eighth_holdout_candidates.csv"
ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
SNAPSHOT = {
    "spacy_backend": PROJECT_ROOT / "equity_platform/text_ie/spacy_backend.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/runtime.py",
    "compiler": PROJECT_ROOT / "equity_platform/text_ie/dsl/compiler.py",
    "ontology": PROJECT_ROOT / "equity_platform/text_ie/ontology.py",
    "quantities": PROJECT_ROOT / "equity_platform/text_ie/quantities.py",
    "validation": PROJECT_ROOT / "equity_platform/text_ie/validation.py",
    "v262_semantics": PROJECT_ROOT / "equity_platform/text_ie/v262/semantics.py",
    "v262_runtime": PROJECT_ROOT / "equity_platform/text_ie/v262/runtime.py",
    "v263_router": PROJECT_ROOT / "equity_platform/text_ie/v263/router.py",
    "v264_semantics": PROJECT_ROOT / "equity_platform/text_ie/v264/semantics.py",
    "v264_runtime": PROJECT_ROOT / "equity_platform/text_ie/v264/runtime.py",
    "v264_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v264_semantic_laws.arc",
    "v265_semantics": PROJECT_ROOT / "equity_platform/text_ie/v265/semantics.py",
    "v265_runtime": PROJECT_ROOT / "equity_platform/text_ie/v265/runtime.py",
    "v265_router": PROJECT_ROOT / "equity_platform/text_ie/v265/router.py",
    "v265_init": PROJECT_ROOT / "equity_platform/text_ie/v265/__init__.py",
    "v265_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v265_semantic_laws.arc",
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
        raise ValueError(f"V2.6.5 changed after eighth holdout declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.6.5 eighth holdout source hash mismatch: {ticker}")
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
    rows: list[dict[str, object]] = []
    for ticker, document in documents().items():
        base_candidates, _ = generate_recall_candidates(document)
        v262_candidates = augment_candidates_v262(document, base_candidates)
        candidates = augment_candidates_v265(document, v262_candidates)
        grouped: dict[tuple[int, int], list[object]] = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.block.char_start, candidate.block.char_end)].append(candidate)
        route_by_span = {
            (route.char_start, route.char_end): route
            for route in route_document_blocks_v265(document)
            if route.char_start is not None and route.char_end is not None
        }
        for (start, end), group in grouped.items():
            block = group[0].block
            route = route_by_span[(start, end)]
            quantities = {
                (quantity.char_start, quantity.char_end, quantity.raw)
                for candidate in group
                for quantity in candidate.quantities
            }
            concepts = tuple(
                dict.fromkeys(candidate.metric.concept for candidate in group)
            )
            if route.route.value in {"FLATTENED_TABLE", "MIXED"}:
                stratum = "TABLE_ROUTE"
            elif quantities:
                stratum = "NUMERIC_KPI"
            else:
                stratum = "QUALITATIVE_KPI"
            block_id = sha256(
                f"{document.source.sha256}:{start}:{end}".encode()
            ).hexdigest()[:20]
            rows.append(
                {
                    "candidate_id": block_id,
                    "ticker": ticker,
                    "source_path": document.source.local_path,
                    "source_sha256": document.source.sha256,
                    "char_start": start,
                    "char_end": end,
                    "heading": block.nearest_heading,
                    "section": block.section,
                    "concepts": "|".join(concepts),
                    "quantity_count": len(quantities),
                    "sampling_stratum": stratum,
                    "route": route.route.value,
                    "sampling_key": sha256(
                        f"{config['sampling_hash_salt']}:{block_id}".encode()
                    ).hexdigest(),
                    "text": block.text,
                }
            )
    return pd.DataFrame(rows)


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    pool = candidate_pool()
    selected_ids: set[str] = set()
    target = int(config["blocks_per_issuer"])
    for ticker in config["evaluation_tickers"]:
        subset = pool.loc[pool["ticker"].eq(ticker)]
        chosen_ids: set[str] = set()
        for stratum in ("TABLE_ROUTE", "NUMERIC_KPI", "QUALITATIVE_KPI"):
            match = subset.loc[subset["sampling_stratum"].eq(stratum)].sort_values(
                "sampling_key"
            )
            if len(match):
                chosen_ids.add(str(match.iloc[0]["candidate_id"]))
        remaining = subset.loc[
            ~subset["candidate_id"].isin(chosen_ids)
        ].sort_values("sampling_key")
        chosen_ids.update(
            str(value)
            for value in remaining.head(max(0, target - len(chosen_ids)))[
                "candidate_id"
            ]
        )
        if len(chosen_ids) != target:
            raise ValueError(f"{ticker} has only {len(chosen_ids)} eligible blocks")
        selected_ids.update(chosen_ids)
    selected = pool.loc[pool["candidate_id"].isin(selected_ids)].copy()
    expected = int(config["target_annotated_blocks"])
    if len(selected) != expected:
        raise ValueError(
            f"V2.6.5 eighth holdout requires {expected} blocks, selected {len(selected)}"
        )
    return selected.sort_values(["ticker", "sampling_key"]).reset_index(drop=True)


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
