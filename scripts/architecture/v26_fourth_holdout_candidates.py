from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.document import document_text_blocks
from equity_platform.text_ie.v24 import generate_recall_candidates
from equity_platform.text_ie.v26 import BlockRoute, route_document_blocks
from equity_platform.text_ie.v26.evidence import load_holdout_evidence_sources


CONFIG = PROJECT_ROOT / "configs/certification/platform_v26_fourth_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_6_route_aware_recall"
CANDIDATES = OUTPUT / "fourth_holdout_candidates.csv"
SNAPSHOT_FILES = {
    "model": PROJECT_ROOT / "equity_platform/text_ie/v26/model.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/v26/runtime.py",
    "router": PROJECT_ROOT / "equity_platform/text_ie/v26/router.py",
    "semantics": PROJECT_ROOT / "equity_platform/text_ie/v26/semantics.py",
    "candidate_generator": PROJECT_ROOT / "equity_platform/text_ie/v24/candidate_generator.py",
    "candidate_dsl": PROJECT_ROOT / "configs/parser_rules/text_ie/v24_high_recall.arc",
}


def load_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_code_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["code_snapshot_sha256"])
    mismatch = {
        name: sha256_file(path)
        for name, path in SNAPSHOT_FILES.items()
        if sha256_file(path) != expected[name]
    }
    if mismatch:
        raise ValueError(f"V2.6 semantic code changed after holdout declaration: {mismatch}")


def documents() -> dict[tuple[str, str], object]:
    output = {}
    for source in load_holdout_evidence_sources():
        source_kind = source.channel.value
        document_kind = {
            "SEC_10K": "ANNUAL_REPORT_WITH_NOTES",
            "SEC_10Q": "QUARTERLY_REPORT_WITH_NOTES",
            "COMPANY_IR": "EARNINGS_RELEASE_OR_PRESENTATION",
        }[source_kind]
        output[(str(source.ticker), source_kind)] = adapt_html_document(
            path=source.path,
            metadata=DocumentMetadata(
                str(source.ticker), source_kind, document_kind,
                str(source.available_at),
                str(pd.Timestamp(source.available_at).to_period("Q")),
            ),
            expected_sha256=source.sha256,
            source_uri=source.path.as_uri(),
            # The route-aware flattened-table path is dependency-free and keeps
            # the exact SEC/IR source spans used by the holdout annotations.
            include_tables=False,
            include_inline_facts=True,
        )
    return output


def candidate_pool() -> pd.DataFrame:
    config = load_config()
    verify_code_snapshot(config)
    rows = []
    for (ticker, source_kind), document in documents().items():
        candidates, _ = generate_recall_candidates(document)
        grouped = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.block.char_start, candidate.block.char_end)].append(candidate)
        route_by_span = {
            (route.char_start, route.char_end): route
            for route in route_document_blocks(document)
            if route.char_start is not None and route.char_end is not None
        }
        for (start, end), group in grouped.items():
            block = group[0].block
            route = route_by_span.get((start, end))
            concepts = tuple(dict.fromkeys(item.metric.concept for item in group))
            quantities = {
                (item.char_start, item.char_end, item.raw)
                for candidate in group for item in candidate.quantities
            }
            if route and route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
                stratum = "TABLE_ROUTE"
            elif quantities:
                stratum = "NUMERIC_KPI"
            else:
                stratum = "QUALITATIVE_KPI"
            block_id = sha256(f"{document.source.sha256}:{start}:{end}".encode()).hexdigest()[:20]
            rows.append({
                "candidate_id": block_id,
                "ticker": ticker,
                "source_kind": source_kind,
                "source_path": document.source.local_path,
                "source_sha256": document.source.sha256,
                "sentence_index": block.sentence_index,
                "char_start": start,
                "char_end": end,
                "heading": block.nearest_heading,
                "section": block.section,
                "concepts": "|".join(concepts),
                "quantity_count": len(quantities),
                "sampling_stratum": stratum,
                "route": route.route.value if route else BlockRoute.PROSE.value,
                "sampling_key": sha256(
                    f"{config['sampling_hash_salt']}:{block_id}".encode()
                ).hexdigest(),
                "text": block.text,
            })
    return pd.DataFrame(rows)


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    pool = candidate_pool()
    selected_ids = set()
    for ticker in config["evaluation_tickers"]:
        for source_kind, target in (
            ("SEC_10K", int(config["blocks_per_issuer_10k"])),
            ("SEC_10Q", int(config["blocks_per_issuer_10q"])),
            ("COMPANY_IR", int(config["blocks_per_issuer_ir"])),
        ):
            subset = pool.loc[
                pool["ticker"].eq(ticker) & pool["source_kind"].eq(source_kind)
            ]
            chosen = []
            for stratum in ("TABLE_ROUTE", "NUMERIC_KPI", "QUALITATIVE_KPI"):
                match = subset.loc[subset["sampling_stratum"].eq(stratum)]
                if len(match):
                    chosen.append(match.sort_values("sampling_key").iloc[0])
            chosen_ids = {row.candidate_id for row in chosen[:target]}
            remaining = subset.loc[~subset["candidate_id"].isin(chosen_ids)].sort_values("sampling_key")
            chosen_ids.update(remaining.head(max(0, target - len(chosen_ids)))["candidate_id"])
            selected_ids.update(chosen_ids)
    expected = int(config["target_annotated_blocks"])
    if len(selected_ids) < expected:
        supplement = pool.loc[~pool["candidate_id"].isin(selected_ids)].sort_values("sampling_key")
        selected_ids.update(supplement.head(expected - len(selected_ids))["candidate_id"])
    selected = pool.loc[pool["candidate_id"].isin(selected_ids)].copy()
    if len(selected) != expected:
        raise ValueError(f"V2.6 holdout requires {expected} blocks, selected {len(selected)}")
    return selected.sort_values(["ticker", "source_kind", "sampling_key"]).reset_index(drop=True)


def main() -> int:
    frame = candidate_blocks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CANDIDATES, index=False)
    print(frame.groupby(["source_kind", "sampling_stratum"]).size().to_string())
    print(f"TOTAL={len(frame)}")
    print(f"CANDIDATE_SHA256={sha256_file(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
