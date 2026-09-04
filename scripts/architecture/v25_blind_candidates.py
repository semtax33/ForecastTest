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
from equity_platform.text_ie.document import document_text_blocks
from equity_platform.text_ie.model import FactTier
from equity_platform.text_ie.ontology import definition_for
from equity_platform.text_ie.v24 import generate_recall_candidates
from equity_platform.text_ie.v25 import route_financial_grid


CONFIG = PROJECT_ROOT / "configs/certification/platform_v25_blind_set.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_5_binding_precision"
CANDIDATES = OUTPUT / "blind_sentence_candidates.csv"
ARCANA_IR = Path(os.environ.get("ARCANA_IR_ROOT", "D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir"))
V25_SOURCES = {
    "v25_model": PROJECT_ROOT / "equity_platform/text_ie/v25/model.py",
    "v25_clause": PROJECT_ROOT / "equity_platform/text_ie/v25/clause.py",
    "v25_table_router": PROJECT_ROOT / "equity_platform/text_ie/v25/table_router.py",
    "v25_binding": PROJECT_ROOT / "equity_platform/text_ie/v25/binding.py",
    "v25_runtime": PROJECT_ROOT / "equity_platform/text_ie/v25/runtime.py",
    "v25_init": PROJECT_ROOT / "equity_platform/text_ie/v25/__init__.py",
    "v24_candidate_generator": PROJECT_ROOT / "equity_platform/text_ie/v24/candidate_generator.py",
    "v24_candidate_dsl": PROJECT_ROOT / "configs/parser_rules/text_ie/v24_high_recall.arc",
}


def load_blind_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_v25_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["v25_snapshot_sha256"])
    if set(expected) != set(V25_SOURCES):
        raise ValueError("V2.5 source snapshot is incomplete")
    mismatch = {name: sha256_file(path) for name, path in V25_SOURCES.items() if sha256_file(path) != expected[name]}
    if mismatch:
        raise ValueError(f"V2.5 changed after blind declaration: {mismatch}")


def verify_candidate_artifact(config: dict[str, object]) -> None:
    expected = str(config["candidate_artifact"]["sha256"])
    if expected.startswith("PENDING") or sha256_file(CANDIDATES) != expected:
        raise ValueError("V2.5 candidate artifact is not frozen")


def _documents() -> dict[str, object]:
    documents = {}
    for source in load_blind_config()["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.5 source hash changed for {ticker}")
        available_at = path.name[:10]
        documents[ticker] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(ticker, "COMPANY_IR_SEC", "EARNINGS_RELEASE", available_at, str(pd.Timestamp(available_at).to_period("Q"))),
            expected_sha256=str(source["sha256"]),
            source_uri=path.as_uri(),
            include_tables=False,
            include_inline_facts=False,
        )
    return documents


def candidate_pool() -> pd.DataFrame:
    config = load_blind_config()
    verify_v25_snapshot(config)
    rows = []
    for ticker, document in _documents().items():
        candidates, old_tables = generate_recall_candidates(document)
        table_by_span = {(item.char_start, item.char_end): item for item in old_tables}
        for block in document_text_blocks(document):
            table = route_financial_grid(block)
            if table is not None:
                table_by_span.setdefault((table.char_start, table.char_end), table)
        groups = defaultdict(list)
        for candidate in candidates:
            groups[(candidate.block.char_start, candidate.block.char_end)].append(candidate)
        table_spans = set(table_by_span)
        for (start, end), group in groups.items():
            if (start, end) in table_spans:
                continue
            block = group[0].block
            concepts = tuple(dict.fromkeys(item.metric.concept for item in group))
            critical = tuple(concept for concept in concepts if definition_for(concept).tier is FactTier.CRITICAL)
            quantities = {(item.char_start, item.char_end, item.raw) for candidate in group for item in candidate.quantities}
            block_id = sha256(f"{document.source.sha256}:{start}:{end}".encode()).hexdigest()[:20]
            rows.append({
                "candidate_id": block_id, "ticker": ticker, "source_path": document.source.local_path,
                "source_sha256": document.source.sha256, "sentence_index": block.sentence_index,
                "char_start": start, "char_end": end, "document_period": block.document_period,
                "heading": block.nearest_heading, "concepts": "|".join(concepts),
                "critical_concepts": "|".join(critical), "candidate_count": len(group),
                "quantity_count": len(quantities), "sampling_stratum": "CRITICAL_NUMERIC" if critical and quantities else "QUALITATIVE",
                "sampling_key": sha256(f"{config['sampling_hash_salt']}:{block_id}".encode()).hexdigest(),
                "gold_route_hint": "TEXT_IE", "text": block.text,
            })
        for table in table_by_span.values():
            block_id = sha256(f"{document.source.sha256}:{table.char_start}:{table.char_end}".encode()).hexdigest()[:20]
            rows.append({
                "candidate_id": block_id, "ticker": ticker, "source_path": document.source.local_path,
                "source_sha256": document.source.sha256, "sentence_index": table.sentence_index,
                "char_start": table.char_start, "char_end": table.char_end, "document_period": document.metadata.report_period,
                "heading": "", "concepts": "|".join(table.metric_labels), "critical_concepts": "|".join(table.metric_labels),
                "candidate_count": 0, "quantity_count": table.numeric_cells, "sampling_stratum": "TABLE_RECONSTRUCTION",
                "sampling_key": sha256(f"{config['sampling_hash_salt']}:{block_id}".encode()).hexdigest(),
                "gold_route_hint": "TABLE_DSL", "text": table.source_literal,
            })
    return pd.DataFrame(rows)


def candidate_blocks() -> pd.DataFrame:
    config = load_blind_config()
    pool = candidate_pool()
    reasons = defaultdict(set)
    for concept in config["required_critical_concepts"]:
        matches = pool["critical_concepts"].fillna("").str.split("|").map(lambda values: concept in values)
        for candidate_id in pool.loc[matches & pool["sampling_stratum"].eq("CRITICAL_NUMERIC")].sort_values("sampling_key").head(int(config["blocks_per_required_concept"]))["candidate_id"]:
            reasons[candidate_id].add(f"CONCEPT:{concept}")
    for ticker in config["evaluation_tickers"]:
        issuer = pool.loc[pool["ticker"].eq(ticker)]
        for stratum, count in (("CRITICAL_NUMERIC", config["numeric_blocks_per_issuer"]), ("QUALITATIVE", config["qualitative_blocks_per_issuer"]), ("TABLE_RECONSTRUCTION", config["table_blocks_per_issuer"])):
            for candidate_id in issuer.loc[issuer["sampling_stratum"].eq(stratum)].sort_values("sampling_key").head(int(count))["candidate_id"]:
                reasons[candidate_id].add(f"ISSUER:{stratum}")
    selected = pool.loc[pool["candidate_id"].isin(reasons)].copy()
    selected["selection_reason"] = selected["candidate_id"].map(lambda item: "|".join(sorted(reasons[item])))
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
