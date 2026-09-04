from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.document import document_text_blocks
from equity_platform.text_ie.model import FactTier
from equity_platform.text_ie.ontology import definition_for, find_concepts
from equity_platform.text_ie.quantities import extract_quantities
from equity_platform.text_ie.retrieval import narrative_candidate
from scripts.architecture.universe_certification_v21 import _latest_ir_source


CONFIG = PROJECT_ROOT / "configs/certification/platform_v23_blind_set.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_3_parser_calibration"
CANDIDATES = OUTPUT / "blind_sentence_candidates.csv"
PARSER_SOURCES = {
    "semantic_frames": PROJECT_ROOT / "configs/parser_rules/text_ie/semantic_frames.arc",
    "model": PROJECT_ROOT / "equity_platform/text_ie/model.py",
    "ontology": PROJECT_ROOT / "equity_platform/text_ie/ontology.py",
    "quantities": PROJECT_ROOT / "equity_platform/text_ie/quantities.py",
    "context": PROJECT_ROOT / "equity_platform/text_ie/context.py",
    "context_validation": PROJECT_ROOT / "equity_platform/text_ie/context_validation.py",
    "semantic_binding": PROJECT_ROOT / "equity_platform/text_ie/semantic_binding.py",
    "retrieval": PROJECT_ROOT / "equity_platform/text_ie/retrieval.py",
    "document": PROJECT_ROOT / "equity_platform/text_ie/document.py",
    "matcher": PROJECT_ROOT / "equity_platform/text_ie/matcher.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/runtime.py",
    "validation": PROJECT_ROOT / "equity_platform/text_ie/validation.py",
    "dsl_compiler": PROJECT_ROOT / "equity_platform/text_ie/dsl/compiler.py",
    "spacy_backend": PROJECT_ROOT / "equity_platform/text_ie/spacy_backend.py",
    "document_model": PROJECT_ROOT / "equity_platform/documents/model.py",
    "document_html": PROJECT_ROOT / "equity_platform/documents/html.py",
    "source_locator": PROJECT_ROOT / "scripts/architecture/universe_certification_v21.py",
}


def load_blind_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_parser_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["parser_snapshot_sha256"])
    missing = sorted(set(PARSER_SOURCES) ^ set(expected))
    if missing:
        raise ValueError(f"Parser snapshot source mismatch: {missing}")
    mismatches = {
        name: {"expected": expected[name], "actual": sha256_file(path)}
        for name, path in PARSER_SOURCES.items()
        if sha256_file(path) != expected[name]
    }
    if mismatches:
        raise ValueError(f"Parser changed after blind-set declaration: {mismatches}")


def verify_candidate_artifact(config: dict[str, object]) -> None:
    expected = str(dict(config["candidate_artifact"])["sha256"])
    if expected.startswith("PENDING_"):
        raise ValueError("Candidate artifact hash must be fixed before sentence review")
    actual = sha256_file(CANDIDATES)
    if actual != expected:
        raise ValueError(
            f"Blind candidate artifact changed after selection: expected={expected}, actual={actual}"
        )


def _document(ticker: str):
    path = _latest_ir_source(ticker)
    if path is None:
        raise FileNotFoundError(f"No latest Arcana IR HTML for blind issuer {ticker}")
    digest = sha256_file(path)
    available_at = path.name[:10]
    return path, adapt_html_document(
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


def candidate_pool() -> pd.DataFrame:
    config = load_blind_config()
    verify_parser_snapshot(config)
    salt = str(config["sampling_hash_salt"])
    required = set(config["required_critical_concepts"])
    rows: list[dict[str, object]] = []
    for ticker in config["evaluation_tickers"]:
        path, document = _document(str(ticker))
        for block in document_text_blocks(document):
            mentions = find_concepts(block.text)
            if not mentions:
                continue
            concepts = tuple(dict.fromkeys(item.concept for item in mentions))
            critical = tuple(
                concept
                for concept in concepts
                if definition_for(concept).tier is FactTier.CRITICAL
            )
            narrative = tuple(
                concept
                for concept in concepts
                if definition_for(concept).tier is FactTier.NARRATIVE
            )
            quantities = extract_quantities(block.text)
            route = narrative_candidate(block)
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{block.char_end}".encode()
            ).hexdigest()[:20]
            eligible_critical = tuple(sorted(set(critical) & required))
            numeric = bool(eligible_critical and quantities)
            stratum = (
                "CRITICAL_NUMERIC"
                if numeric
                else "NARRATIVE"
                if narrative
                else "OTHER_TARGET"
            )
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "ticker": ticker,
                    "source_path": str(path),
                    "source_sha256": document.source.sha256,
                    "sentence_index": block.sentence_index,
                    "char_start": block.char_start,
                    "char_end": block.char_end,
                    "document_period": block.document_period,
                    "heading": block.nearest_heading,
                    "concepts": "|".join(concepts),
                    "critical_concepts": "|".join(eligible_critical),
                    "narrative_concepts": "|".join(narrative),
                    "quantity_count": len(quantities),
                    "quantities_json": json.dumps(
                        [
                            {"value": item.value, "unit": item.unit, "raw": item.raw}
                            for item in quantities
                        ],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "gold_route_hint": "TEXT_IE" if route.accepted else "TABLE_DSL",
                    "route_reason": route.reason,
                    "sampling_stratum": stratum,
                    "sampling_key": sha256(f"{salt}:{candidate_id}".encode()).hexdigest(),
                    "text": block.text,
                }
            )
    return pd.DataFrame(rows)


def candidate_blocks() -> pd.DataFrame:
    config = load_blind_config()
    pool = candidate_pool()
    required = tuple(str(item) for item in config["required_critical_concepts"])
    per_concept = int(config["blocks_per_required_concept"])
    per_issuer_numeric = int(config["numeric_blocks_per_issuer"])
    per_issuer_qualitative = int(config["qualitative_blocks_per_issuer"])
    reasons: dict[str, set[str]] = defaultdict(set)

    for concept in required:
        mask = pool["critical_concepts"].str.split("|").map(lambda values: concept in values)
        choices = pool.loc[mask & pool["quantity_count"].gt(0)].copy()
        choices["concept_key"] = choices["candidate_id"].map(
            lambda candidate_id: sha256(
                f"{config['sampling_hash_salt']}:{concept}:{candidate_id}".encode()
            ).hexdigest()
        )
        for candidate_id in choices.sort_values("concept_key").head(per_concept)["candidate_id"]:
            reasons[candidate_id].add(f"CONCEPT:{concept}")

    for ticker in config["evaluation_tickers"]:
        issuer = pool.loc[pool["ticker"].eq(ticker)]
        numeric = issuer.loc[issuer["sampling_stratum"].eq("CRITICAL_NUMERIC")]
        for candidate_id in numeric.sort_values("sampling_key").head(per_issuer_numeric)["candidate_id"]:
            reasons[candidate_id].add("ISSUER:CRITICAL_NUMERIC")
        qualitative = issuer.loc[~issuer["sampling_stratum"].eq("CRITICAL_NUMERIC")]
        for candidate_id in qualitative.sort_values("sampling_key").head(
            per_issuer_qualitative
        )["candidate_id"]:
            reasons[candidate_id].add("ISSUER:QUALITATIVE_OR_NEGATIVE")

    selected = pool.loc[pool["candidate_id"].isin(reasons)].copy()
    selected["selection_reason"] = selected["candidate_id"].map(
        lambda candidate_id: "|".join(sorted(reasons[candidate_id]))
    )
    return selected.sort_values(["ticker", "sampling_key"]).reset_index(drop=True)


def selection_summary(candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    by_issuer = (
        candidates.groupby(["ticker", "sampling_stratum"], as_index=False)
        .agg(blocks=("candidate_id", "size"))
        .sort_values(["ticker", "sampling_stratum"])
    )
    required = tuple(load_blind_config()["required_critical_concepts"])
    concept_rows = []
    for concept in required:
        count = candidates["critical_concepts"].str.split("|").map(
            lambda values: concept in values
        ).sum()
        concept_rows.append({"concept": concept, "selected_blocks": int(count)})
    return by_issuer, pd.DataFrame(concept_rows)


def main() -> int:
    candidates = candidate_blocks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(CANDIDATES, index=False)
    by_issuer, by_concept = selection_summary(candidates)
    print(by_issuer.to_string(index=False))
    print(by_concept.to_string(index=False))
    print(f"TOTAL={len(candidates)}")
    print(f"CANDIDATE_SHA256={sha256_file(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
