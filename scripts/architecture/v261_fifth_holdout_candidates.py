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
from equity_platform.text_ie.v261 import BlockRoute, route_document_blocks_v261


CONFIG = PROJECT_ROOT / "configs/certification/platform_v261_fifth_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_6_1_segment_domain_guards"
CANDIDATES = OUTPUT / "fifth_holdout_candidates.csv"
ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
SNAPSHOT = {
    "router": PROJECT_ROOT / "equity_platform/text_ie/v261/router.py",
    "semantics": PROJECT_ROOT / "equity_platform/text_ie/v261/semantics.py",
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/v261/runtime.py",
    "init": PROJECT_ROOT / "equity_platform/text_ie/v261/__init__.py",
}


def load_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def verify_snapshot(config: dict[str, object]) -> None:
    expected = dict(config["code_snapshot_sha256"])
    mismatch = {
        name: sha256_file(path) for name, path in SNAPSHOT.items()
        if sha256_file(path) != expected[name]
    }
    if mismatch:
        raise ValueError(f"V2.6.1 changed after fifth holdout declaration: {mismatch}")


def documents() -> dict[str, object]:
    config = load_config()
    output = {}
    for source in config["sources"]:
        ticker = str(source["ticker"])
        path = ARCANA_IR / ticker / str(source["file_name"])
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"V2.6.1 fifth holdout source hash mismatch: {ticker}")
        available_at = path.name[:10]
        output[ticker] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(
                ticker, "COMPANY_IR", "EARNINGS_RELEASE_OR_PRESENTATION",
                available_at, str(pd.Timestamp(available_at).to_period("Q")),
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
    rows = []
    for ticker, document in documents().items():
        candidates, _ = generate_recall_candidates(document)
        grouped = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.block.char_start, candidate.block.char_end)].append(candidate)
        route_by_span = {
            (route.char_start, route.char_end): route
            for route in route_document_blocks_v261(document)
            if route.char_start is not None and route.char_end is not None
        }
        for (start, end), group in grouped.items():
            block = group[0].block
            route = route_by_span[(start, end)]
            quantities = {
                (item.char_start, item.char_end, item.raw)
                for candidate in group for item in candidate.quantities
            }
            concepts = tuple(dict.fromkeys(item.metric.concept for item in group))
            if route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
                stratum = "TABLE_ROUTE"
            elif quantities:
                stratum = "NUMERIC_KPI"
            else:
                stratum = "QUALITATIVE_KPI"
            block_id = sha256(f"{document.source.sha256}:{start}:{end}".encode()).hexdigest()[:20]
            rows.append({
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
                "sampling_key": sha256(f"{config['sampling_hash_salt']}:{block_id}".encode()).hexdigest(),
                "text": block.text,
            })
    return pd.DataFrame(rows)


def candidate_blocks() -> pd.DataFrame:
    config = load_config()
    pool = candidate_pool()
    selected_ids = set()
    target = int(config["blocks_per_issuer"])
    for ticker in config["evaluation_tickers"]:
        subset = pool.loc[pool["ticker"].eq(ticker)]
        chosen_ids = set()
        for stratum in ("TABLE_ROUTE", "NUMERIC_KPI", "QUALITATIVE_KPI"):
            match = subset.loc[subset["sampling_stratum"].eq(stratum)].sort_values("sampling_key")
            if len(match):
                chosen_ids.add(match.iloc[0]["candidate_id"])
        remaining = subset.loc[~subset["candidate_id"].isin(chosen_ids)].sort_values("sampling_key")
        chosen_ids.update(remaining.head(max(0, target - len(chosen_ids)))["candidate_id"])
        selected_ids.update(chosen_ids)
    selected = pool.loc[pool["candidate_id"].isin(selected_ids)].copy()
    expected = int(config["target_annotated_blocks"])
    if len(selected) < expected:
        supplement = pool.loc[~pool["candidate_id"].isin(selected_ids)].sort_values("sampling_key")
        selected_ids.update(supplement.head(expected - len(selected))["candidate_id"])
        selected = pool.loc[pool["candidate_id"].isin(selected_ids)].copy()
    if len(selected) != expected:
        raise ValueError(f"V2.6.1 fifth holdout requires {expected} blocks, selected {len(selected)}")
    return selected.sort_values(["ticker", "sampling_key"]).reset_index(drop=True)


def main() -> int:
    frame = candidate_blocks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CANDIDATES, index=False)
    print(frame.groupby(["sampling_stratum"]).size().to_string())
    print(f"TOTAL={len(frame)}")
    print(f"CANDIDATE_SHA256={sha256_file(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
