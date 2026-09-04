from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from typing import Callable, Iterable

import pandas as pd


def build_candidate_pool(
    *,
    config: dict[str, object],
    documents: dict[str, object],
    generate_candidates: Callable[[object], Iterable[object]],
    route_blocks: Callable[[object], Iterable[object]],
) -> pd.DataFrame:
    """Build the shared, content-addressed parser holdout candidate schema."""

    rows: list[dict[str, object]] = []
    for ticker, document in documents.items():
        candidates = tuple(generate_candidates(document))
        grouped: dict[tuple[int, int], list[object]] = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.block.char_start, candidate.block.char_end)].append(
                candidate
            )
        route_by_span = {
            (route.char_start, route.char_end): route
            for route in route_blocks(document)
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


def select_candidate_blocks(
    pool: pd.DataFrame,
    config: dict[str, object],
    *,
    benchmark_label: str,
) -> pd.DataFrame:
    """Select a deterministic stratified sample without viewing predictions."""

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
            f"{benchmark_label} requires {expected} blocks, selected {len(selected)}"
        )
    return selected.sort_values(["ticker", "sampling_key"]).reset_index(drop=True)
