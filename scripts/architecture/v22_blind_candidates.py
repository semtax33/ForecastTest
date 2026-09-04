from __future__ import annotations

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
from scripts.architecture.universe_certification_v21 import _latest_ir_source


CONFIG = PROJECT_ROOT / "configs/certification/platform_v22_blind_set.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_2_parser_generalization"
PARSER_SOURCES = {
    "semantic_frames": PROJECT_ROOT / "configs/parser_rules/text_ie/semantic_frames.arc",
    "context_validation": PROJECT_ROOT / "equity_platform/text_ie/context_validation.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/runtime.py",
    "ontology": PROJECT_ROOT / "equity_platform/text_ie/ontology.py",
}


def load_blind_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_parser_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["parser_snapshot_sha256"])
    mismatches = {
        name: {"expected": expected[name], "actual": sha256_file(path)}
        for name, path in PARSER_SOURCES.items()
        if sha256_file(path) != expected[name]
    }
    if mismatches:
        raise ValueError(f"Parser changed after blind-set declaration: {mismatches}")


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


def candidate_blocks() -> pd.DataFrame:
    config = load_blind_config()
    verify_parser_snapshot(config)
    salt = str(config["sampling_hash_salt"])
    rows: list[dict[str, object]] = []
    for ticker in config["evaluation_tickers"]:
        path, document = _document(str(ticker))
        for block in document_text_blocks(document):
            concepts = find_concepts(block.text)
            if not concepts:
                continue
            quantities = extract_quantities(block.text)
            critical = any(
                definition_for(item.concept).tier is FactTier.CRITICAL
                for item in concepts
            )
            numeric = critical and bool(quantities)
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{block.char_end}".encode()
            ).hexdigest()[:20]
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
                    "concepts": "|".join(dict.fromkeys(item.concept for item in concepts)),
                    "quantities_json": json.dumps(
                        [
                            {"value": item.value, "unit": item.unit, "raw": item.raw}
                            for item in quantities
                        ],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "sampling_stratum": "CRITICAL_NUMERIC" if numeric else "OTHER",
                    "sampling_key": sha256(f"{salt}:{candidate_id}".encode()).hexdigest(),
                    "text": block.text,
                }
            )
    candidates = pd.DataFrame(rows)
    selected: list[pd.DataFrame] = []
    numeric_n = int(config["numeric_blocks_per_issuer"])
    other_n = int(config["other_blocks_per_issuer"])
    for ticker, group in candidates.groupby("ticker"):
        numeric = group.loc[group["sampling_stratum"].eq("CRITICAL_NUMERIC")]
        other = group.loc[group["sampling_stratum"].eq("OTHER")]
        selected.append(numeric.sort_values("sampling_key").head(numeric_n))
        selected.append(other.sort_values("sampling_key").head(other_n))
    result = pd.concat(selected, ignore_index=True)
    return result.sort_values(["ticker", "sampling_stratum", "sampling_key"]).reset_index(drop=True)


def main() -> int:
    candidates = candidate_blocks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OUTPUT / "blind_sentence_candidates.csv", index=False)
    print(
        candidates.groupby(["ticker", "sampling_stratum"], as_index=False)
        .agg(blocks=("candidate_id", "size"))
        .to_string(index=False)
    )
    print(f"TOTAL={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
