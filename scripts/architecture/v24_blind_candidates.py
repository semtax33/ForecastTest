from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.model import FactTier
from equity_platform.text_ie.ontology import definition_for
from equity_platform.text_ie.v24 import generate_recall_candidates


CONFIG = PROJECT_ROOT / "configs/certification/platform_v24_blind_set.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_4_high_recall"
CANDIDATES = OUTPUT / "blind_sentence_candidates.csv"
ARCANA_IR = Path(
    os.environ.get(
        "ARCANA_IR_ROOT",
        "D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir",
    )
)
V24_SOURCES = {
    "v24_dsl": PROJECT_ROOT / "configs/parser_rules/text_ie/v24_high_recall.arc",
    "table_reconstruction": PROJECT_ROOT / "equity_platform/documents/table_reconstruction.py",
    "documents_init": PROJECT_ROOT / "equity_platform/documents/__init__.py",
    "v24_model": PROJECT_ROOT / "equity_platform/text_ie/v24/model.py",
    "v24_candidate_generator": PROJECT_ROOT / "equity_platform/text_ie/v24/candidate_generator.py",
    "v24_binder": PROJECT_ROOT / "equity_platform/text_ie/v24/binder.py",
    "v24_verifier": PROJECT_ROOT / "equity_platform/text_ie/v24/verifier.py",
    "v24_llm_rescue": PROJECT_ROOT / "equity_platform/text_ie/v24/llm_rescue.py",
    "v24_runtime": PROJECT_ROOT / "equity_platform/text_ie/v24/runtime.py",
    "v24_init": PROJECT_ROOT / "equity_platform/text_ie/v24/__init__.py",
    "v23_dependency_manifest": PROJECT_ROOT / "benchmarks/platform_v2_3_parser_calibration/manifest.json",
}


def load_blind_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_v24_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["v24_snapshot_sha256"])
    if set(expected) != set(V24_SOURCES):
        raise ValueError("V2.4 source snapshot is incomplete")
    mismatches = {
        name: {"expected": expected[name], "actual": sha256_file(path)}
        for name, path in V24_SOURCES.items()
        if sha256_file(path) != expected[name]
    }
    if mismatches:
        raise ValueError(f"V2.4 parser changed after blind declaration: {mismatches}")


def verify_candidate_artifact(config: dict[str, object]) -> None:
    expected = str(dict(config["candidate_artifact"])["sha256"])
    if expected.startswith("PENDING_"):
        raise ValueError("V2.4 candidate hash must be fixed before sentence review")
    actual = sha256_file(CANDIDATES)
    if actual != expected:
        raise ValueError(f"V2.4 candidate artifact changed: {actual} != {expected}")


def _documents() -> dict[str, object]:
    config = load_blind_config()
    documents: dict[str, object] = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256_file(path)
        if digest != source["sha256"]:
            raise ValueError(f"Unseen source hash changed for {ticker}")
        available_at = path.name[:10]
        documents[ticker] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(
                entity=ticker,
                source_kind="COMPANY_IR_SEC",
                document_kind="EARNINGS_RELEASE",
                available_at=available_at,
                report_period=str(pd.Timestamp(available_at).to_period("Q")),
            ),
            expected_sha256=digest,
            source_uri=path.as_uri(),
            include_tables=False,
            include_inline_facts=False,
        )
    return documents


def candidate_pool() -> pd.DataFrame:
    config = load_blind_config()
    verify_v24_snapshot(config)
    salt = str(config["sampling_hash_salt"])
    rows: list[dict[str, object]] = []
    for ticker, document in _documents().items():
        candidates, tables = generate_recall_candidates(document)
        groups: dict[tuple[int, int], list[object]] = defaultdict(list)
        for candidate in candidates:
            groups[(candidate.block.char_start, candidate.block.char_end)].append(candidate)
        for (start, end), group in groups.items():
            block = group[0].block
            concepts = tuple(dict.fromkeys(item.metric.concept for item in group))
            critical = tuple(
                concept
                for concept in concepts
                if definition_for(concept).tier is FactTier.CRITICAL
            )
            quantities = {
                (item.char_start, item.char_end, item.raw)
                for candidate in group
                for item in candidate.quantities
            }
            block_id = sha256(
                f"{document.source.sha256}:{start}:{end}".encode()
            ).hexdigest()[:20]
            rows.append(
                {
                    "candidate_id": block_id,
                    "ticker": ticker,
                    "source_path": document.source.local_path,
                    "source_sha256": document.source.sha256,
                    "sentence_index": block.sentence_index,
                    "char_start": start,
                    "char_end": end,
                    "document_period": block.document_period,
                    "heading": block.nearest_heading,
                    "concepts": "|".join(concepts),
                    "critical_concepts": "|".join(critical),
                    "candidate_count": len(group),
                    "quantity_count": len(quantities),
                    "candidate_origins": "|".join(
                        sorted({origin.value for item in group for origin in item.origins})
                    ),
                    "sampling_stratum": (
                        "CRITICAL_NUMERIC" if critical and quantities else "QUALITATIVE"
                    ),
                    "sampling_key": sha256(f"{salt}:{block_id}".encode()).hexdigest(),
                    "gold_route_hint": "TEXT_IE",
                    "text": block.text,
                }
            )
        for table in tables:
            block_id = sha256(
                f"{document.source.sha256}:{table.char_start}:{table.char_end}".encode()
            ).hexdigest()[:20]
            rows.append(
                {
                    "candidate_id": block_id,
                    "ticker": ticker,
                    "source_path": document.source.local_path,
                    "source_sha256": document.source.sha256,
                    "sentence_index": table.sentence_index,
                    "char_start": table.char_start,
                    "char_end": table.char_end,
                    "document_period": document.metadata.report_period,
                    "heading": "",
                    "concepts": "|".join(table.metric_labels),
                    "critical_concepts": "|".join(table.metric_labels),
                    "candidate_count": 0,
                    "quantity_count": table.numeric_cells,
                    "candidate_origins": "TABLE_RECONSTRUCTION",
                    "sampling_stratum": "TABLE_RECONSTRUCTION",
                    "sampling_key": sha256(f"{salt}:{block_id}".encode()).hexdigest(),
                    "gold_route_hint": "TABLE_DSL",
                    "text": table.source_literal,
                }
            )
    return pd.DataFrame(rows)


def candidate_blocks() -> pd.DataFrame:
    config = load_blind_config()
    pool = candidate_pool()
    reasons: dict[str, set[str]] = defaultdict(set)
    for concept in config["required_critical_concepts"]:
        matched = pool["critical_concepts"].fillna("").str.split("|").map(
            lambda values: concept in values
        )
        choices = pool.loc[matched & pool["sampling_stratum"].eq("CRITICAL_NUMERIC")]
        for candidate_id in choices.sort_values("sampling_key").head(
            int(config["blocks_per_required_concept"])
        )["candidate_id"]:
            reasons[candidate_id].add(f"CONCEPT:{concept}")
    for ticker in config["evaluation_tickers"]:
        issuer = pool.loc[pool["ticker"].eq(ticker)]
        strata = (
            ("CRITICAL_NUMERIC", int(config["numeric_blocks_per_issuer"])),
            ("QUALITATIVE", int(config["qualitative_blocks_per_issuer"])),
            ("TABLE_RECONSTRUCTION", int(config["table_blocks_per_issuer"])),
        )
        for stratum, count in strata:
            choices = issuer.loc[issuer["sampling_stratum"].eq(stratum)]
            for candidate_id in choices.sort_values("sampling_key").head(count)["candidate_id"]:
                reasons[candidate_id].add(f"ISSUER:{stratum}")
    selected = pool.loc[pool["candidate_id"].isin(reasons)].copy()
    selected["selection_reason"] = selected["candidate_id"].map(
        lambda candidate_id: "|".join(sorted(reasons[candidate_id]))
    )
    return selected.sort_values(["ticker", "sampling_key"]).reset_index(drop=True)


def main() -> int:
    candidates = candidate_blocks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(CANDIDATES, index=False)
    print(
        candidates.groupby(["ticker", "sampling_stratum"], as_index=False)
        .agg(blocks=("candidate_id", "size"))
        .to_string(index=False)
    )
    concepts = sorted(
        {
            concept
            for payload in candidates["critical_concepts"].fillna("")
            for concept in payload.split("|")
            if concept
        }
    )
    print(f"SELECTED_CONCEPTS={json.dumps(concepts)}")
    print(f"TOTAL={len(candidates)}")
    print(f"CANDIDATE_SHA256={sha256_file(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
