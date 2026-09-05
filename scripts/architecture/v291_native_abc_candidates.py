from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.document import document_text_blocks


CONFIG = PROJECT_ROOT / "configs/certification/platform_v291_native_abc_holdout.toml"
OUTPUT = PROJECT_ROOT / "output/platform_v2_9_1_staged_validation"
CANDIDATES = OUTPUT / "native_abc_candidate_blocks.csv"
METADATA = OUTPUT / "native_abc_candidate_metadata.json"
SCRIPT = PROJECT_ROOT / "scripts/architecture/v291_native_abc_candidates.py"
ARCANA_FILINGS = Path(
    "D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings"
)

PARSER_SNAPSHOT = {
    "role_graph": PROJECT_ROOT / "equity_platform/text_ie/role_graph.py",
    "v290_semantics": PROJECT_ROOT / "equity_platform/text_ie/v290/semantics.py",
    "v290_runtime": PROJECT_ROOT / "equity_platform/text_ie/v290/runtime.py",
    "v290_router": PROJECT_ROOT / "equity_platform/text_ie/v290/router.py",
    "v291_model": PROJECT_ROOT / "equity_platform/text_ie/v291/model.py",
    "v291_runtime": PROJECT_ROOT / "equity_platform/text_ie/v291/runtime.py",
    "v291_evaluation": PROJECT_ROOT / "equity_platform/text_ie/v291/evaluation.py",
    "staged_evaluation": PROJECT_ROOT / "equity_platform/text_ie/staged_evaluation.py",
    "staged_gold": PROJECT_ROOT / "equity_platform/text_ie/training/staged_gold.py",
    "v290_rules": PROJECT_ROOT / "configs/parser_rules/text_ie/v290_semantic_role_graph.arc",
}
TEST_SNAPSHOT = {
    "native_telemetry": PROJECT_ROOT / "tests/test_spacy_native_telemetry_v291.py",
    "staged_evaluation": PROJECT_ROOT / "tests/test_text_ie_staged_evaluation_v291.py",
    "staged_gold": PROJECT_ROOT / "tests/test_text_ie_staged_gold.py",
}


def load_config() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def _source_path(source: dict[str, object]) -> Path:
    source_kind = str(source["source_kind"])
    entity = str(source["entity"])
    return ARCANA_FILINGS / source_kind / entity / str(source["file_name"])


def _prior_holdout_entities() -> set[str]:
    output: set[str] = set()
    for path in (PROJECT_ROOT / "configs/certification").glob("platform_v*.toml"):
        if path == CONFIG:
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        output.update(str(item) for item in data.get("evaluation_tickers", ()))
        for source in data.get("sources", ()):
            entity = source.get("entity", source.get("ticker"))
            if entity:
                output.add(str(entity))
    return output


def verify_predeclaration(config: dict[str, object]) -> None:
    mismatch = {}
    for section, paths in (
        ("parser_snapshot_sha256", PARSER_SNAPSHOT),
        ("test_snapshot_sha256", TEST_SNAPSHOT),
    ):
        expected = dict(config[section])
        for name, path in paths.items():
            actual = sha256_file(path)
            if actual != expected[name]:
                mismatch[f"{section}.{name}"] = {
                    "expected": expected[name],
                    "actual": actual,
                }
    if mismatch:
        raise ValueError(f"V2.9.1 native holdout snapshot mismatch: {mismatch}")

    prior_manifests = tuple(
        path
        for path in (PROJECT_ROOT / "configs/certification").glob("platform_v*.toml")
        if path != CONFIG
    )
    prior_text = "\n".join(path.read_text(encoding="utf-8") for path in prior_manifests)
    source_mismatch = {}
    for source in config["sources"]:
        path = _source_path(source)
        actual = sha256_file(path)
        if actual != source["sha256"]:
            source_mismatch[path.as_posix()] = {
                "expected": source["sha256"],
                "actual": actual,
            }
        if str(source["sha256"]) in prior_text:
            source_mismatch[path.as_posix()] = "PRIOR_HOLDOUT_SOURCE_HASH_OVERLAP"
    for source in config["industry_sources"]:
        path = PROJECT_ROOT / str(source["path"])
        actual = sha256_file(path)
        if actual != source["sha256"]:
            source_mismatch[path.as_posix()] = {
                "expected": source["sha256"],
                "actual": actual,
            }
    if source_mismatch:
        raise ValueError(f"V2.9.1 native holdout source mismatch: {source_mismatch}")

    prior_entities = _prior_holdout_entities()
    overlap = sorted(
        str(source["entity"])
        for source in config["sources"]
        if str(source["axis"]) in {"B", "C"}
        and str(source["entity"]) in prior_entities
    )
    if overlap:
        raise ValueError(f"issuer-disjoint axes overlap prior holdouts: {overlap}")


def _source_id(source: dict[str, object]) -> str:
    available_at = str(source["file_name"])[:10].replace("-", "")
    kind = str(source["source_kind"]).replace("-", "")
    return f"{source['axis']}_{source['entity']}_{kind}_{available_at}"


def corporate_documents(config: dict[str, object]) -> dict[str, object]:
    output = {}
    for source in config["sources"]:
        path = _source_path(source)
        available_at = path.name[:10]
        output[_source_id(source)] = adapt_html_document(
            path=path,
            metadata=DocumentMetadata(
                str(source["entity"]),
                "SEC",
                str(source["source_kind"]),
                available_at,
                str(pd.Timestamp(available_at).to_period("Q")),
            ),
            expected_sha256=str(source["sha256"]),
            source_uri=path.as_uri(),
            include_tables=False,
            include_inline_facts=False,
        )
    return output


def _heading_note_context(heading: object, section: object) -> bool:
    text = f"{heading or ''} {section or ''}".casefold()
    punctuation = "()[]{}:;,.—–-_"
    words = set(text.translate(str.maketrans(punctuation, " " * len(punctuation))).split())
    return bool(words & {"note", "notes"})


def note_context_flags(texts: tuple[str, ...]) -> tuple[bool, ...]:
    output = []
    inside_notes = False
    for text in texts:
        folded = text.casefold().replace("’", "'").strip()
        note_start = "notes to" in folded and "financial statements" in folded
        note_end = (
            folded.startswith("item 2.")
            or folded.startswith("item 2 ")
            or folded.startswith("part ii")
            or folded.startswith("signatures")
        )
        if note_end:
            inside_notes = False
        if note_start:
            inside_notes = True
        output.append(inside_notes)
    return tuple(output)


def corporate_candidate_pool(config: dict[str, object]) -> pd.DataFrame:
    documents = corporate_documents(config)
    sources = {_source_id(source): source for source in config["sources"]}
    rows = []
    for source_id, document in documents.items():
        source = sources[source_id]
        available_at = str(source["file_name"])[:10]
        blocks = document_text_blocks(document)
        region_flags = (
            note_context_flags(tuple(block.text for block in blocks))
            if str(source["source_kind"]) in {"10-K", "10-Q"}
            else (False,) * len(blocks)
        )
        for block, region_note_context in zip(blocks, region_flags):
            numeric_tokens = sum(
                any(char.isdigit() for char in token)
                for token in block.text.split()
            )
            stratum = (
                "DENSE_NUMERIC"
                if numeric_tokens >= 8
                else "NUMERIC"
                if numeric_tokens
                else "NON_NUMERIC"
            )
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{block.char_end}".encode()
            ).hexdigest()[:20]
            rows.append({
                "candidate_id": candidate_id,
                "source_id": source_id,
                "entity": str(source["entity"]),
                "axis": str(source["axis"]),
                "source_kind": str(source["source_kind"]),
                "source_path": document.source.local_path,
                "source_sha256": document.source.sha256,
                "char_start": block.char_start,
                "char_end": block.char_end,
                "heading": block.nearest_heading,
                "section": block.section,
                "concepts": "NOT_EXECUTED_BEFORE_ANNOTATION",
                "quantity_count": "NOT_EXECUTED_BEFORE_ANNOTATION",
                "sampling_stratum": stratum,
                "route": "NOT_EXECUTED_BEFORE_ANNOTATION",
                "sampling_key": sha256(
                    f"{config['sampling_hash_salt']}:{candidate_id}".encode()
                ).hexdigest(),
                "text": block.text,
                "available_at": available_at,
                "document_period": str(pd.Timestamp(available_at).to_period("Q")),
                "note_context": region_note_context or _heading_note_context(
                    block.nearest_heading, block.section
                ),
            })
    return pd.DataFrame(rows)


def select_predeclared_blocks(
    pool: pd.DataFrame,
    *,
    source_ids: tuple[str, ...],
    blocks_per_source: int,
    note_blocks_per_filing_source: int,
    filing_source_ids: set[str],
    max_block_chars: int,
) -> pd.DataFrame:
    selected_ids: set[str] = set()
    for source_id in source_ids:
        subset = pool.loc[
            pool["source_id"].eq(source_id)
            & pool["text"].str.len().le(max_block_chars)
        ].sort_values("sampling_key")
        chosen: set[str] = set()
        if source_id in filing_source_ids:
            notes = subset.loc[subset["note_context"]].head(note_blocks_per_filing_source)
            chosen.update(str(value) for value in notes["candidate_id"])
            if len(notes) != note_blocks_per_filing_source:
                raise ValueError(
                    f"{source_id} has only {len(notes)} note-context candidate blocks"
                )
        for stratum in ("DENSE_NUMERIC", "NUMERIC", "NON_NUMERIC"):
            chosen_rows = subset.loc[subset["candidate_id"].isin(chosen)]
            if stratum in set(chosen_rows["sampling_stratum"]):
                continue
            available = subset.loc[
                subset["sampling_stratum"].eq(stratum)
                & ~subset["candidate_id"].isin(chosen)
            ]
            if len(available):
                chosen.add(str(available.iloc[0]["candidate_id"]))
        remaining = subset.loc[~subset["candidate_id"].isin(chosen)]
        chosen.update(
            str(value)
            for value in remaining.head(max(0, blocks_per_source - len(chosen)))[
                "candidate_id"
            ]
        )
        if len(chosen) != blocks_per_source:
            raise ValueError(
                f"{source_id} has only {len(chosen)} eligible candidate blocks"
            )
        selected_ids.update(chosen)
    selected = pool.loc[pool["candidate_id"].isin(selected_ids)].copy()
    return selected.sort_values(["sampling_key", "source_id"]).reset_index(drop=True)


def industry_negative_controls(config: dict[str, object]) -> pd.DataFrame:
    source = config["industry_sources"][0]
    path = PROJECT_ROOT / str(source["path"])
    frame = pd.read_csv(path)
    rows = []
    salt = str(config["sampling_hash_salt"])
    target = int(config["industry_rows_per_series"])
    for series in config["industry_series"]:
        subset = frame.loc[frame["series"].eq(series)].copy()
        subset["sampling_key"] = [
            sha256(f"{salt}:{series}:{date}:{available}".encode()).hexdigest()
            for date, available in zip(subset["date"], subset["availability_date"])
        ]
        selected = subset.sort_values("sampling_key").head(target)
        if len(selected) != target:
            raise ValueError(f"industry series {series} has only {len(selected)} rows")
        for item in selected.itertuples(index=False):
            text = json.dumps(
                {
                    "availability_date": str(item.availability_date),
                    "date": str(item.date),
                    "series": str(item.series),
                    "source_url": str(item.source_url),
                    "value": float(item.value),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            candidate_id = sha256(
                f"{source['sha256']}:{text}".encode()
            ).hexdigest()[:20]
            rows.append({
                "candidate_id": candidate_id,
                "source_id": f"C_INDUSTRY_{series}",
                "entity": str(source["entity"]),
                "axis": "C",
                "source_kind": "INDUSTRY_DATA",
                "source_path": path.as_posix(),
                "source_sha256": str(source["sha256"]),
                "char_start": 0,
                "char_end": len(text),
                "heading": "PUBLIC INDUSTRY SENSOR",
                "section": str(series),
                "concepts": "",
                "quantity_count": 1,
                "sampling_stratum": "INDUSTRY_NEGATIVE",
                "route": "NOT_EXECUTED_BEFORE_ANNOTATION",
                "sampling_key": str(item.sampling_key),
                "text": text,
                "available_at": str(item.availability_date),
                "document_period": str(pd.Timestamp(item.date).to_period("Q")),
                "note_context": False,
                "gold_route_predeclared": "NO_FACT",
            })
    return pd.DataFrame(rows)


def candidate_blocks(config: dict[str, object]) -> pd.DataFrame:
    pool = corporate_candidate_pool(config)
    source_ids = tuple(_source_id(source) for source in config["sources"])
    filing_ids = {
        _source_id(source)
        for source in config["sources"]
        if str(source["source_kind"]) in {"10-K", "10-Q"}
    }
    corporate = select_predeclared_blocks(
        pool,
        source_ids=source_ids,
        blocks_per_source=int(config["blocks_per_corporate_source"]),
        note_blocks_per_filing_source=int(config["note_blocks_per_filing_source"]),
        filing_source_ids=filing_ids,
        max_block_chars=int(config["max_annotation_block_chars"]),
    )
    corporate["gold_route_predeclared"] = "ANNOTATION_PENDING"
    selected = pd.concat(
        [corporate, industry_negative_controls(config)],
        ignore_index=True,
        sort=False,
    )
    axis_counts = selected.groupby("axis").size().to_dict()
    expected_axis_counts = {
        "A": int(config["axis_a_target_blocks"]),
        "B": int(config["axis_b_target_blocks"]),
        "C": int(config["axis_c_corporate_target_blocks"])
        + int(config["axis_c_industry_negative_controls"]),
    }
    if axis_counts != expected_axis_counts:
        raise ValueError(
            f"native A/B/C axis counts {axis_counts} != {expected_axis_counts}"
        )
    if len(selected) != int(config["target_annotated_blocks"]):
        raise ValueError("native A/B/C total block count does not match predeclaration")
    return selected.sort_values(["axis", "sampling_key", "source_id"]).reset_index(
        drop=True
    )


def main() -> int:
    config = load_config()
    verify_predeclaration(config)
    frame = candidate_blocks(config)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CANDIDATES, index=False)
    metadata = {
        "holdout_id": config["holdout_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "config_sha256": sha256_file(CONFIG),
        "generator": SCRIPT.relative_to(PROJECT_ROOT).as_posix(),
        "generator_sha256": sha256_file(SCRIPT),
        "candidate_artifact": CANDIDATES.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_artifact_sha256": sha256_file(CANDIDATES),
        "rows": len(frame),
        "max_annotation_block_chars": int(config["max_annotation_block_chars"]),
        "max_selected_block_chars": int(frame["text"].str.len().max()),
        "axis_counts": frame.groupby("axis").size().to_dict(),
        "source_kind_counts": frame.groupby("source_kind").size().to_dict(),
        "selection_artifact_frozen_before_annotation": True,
        "selection_independent_of_candidate_generator_and_router": True,
        "parser_predictions_generated": False,
        "annotation_status": "PENDING",
        "certification_eligible": False,
    }
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(frame.groupby(["axis", "source_kind", "sampling_stratum"]).size())
    print(f"TOTAL={len(frame)}")
    print(f"CANDIDATE_SHA256={sha256_file(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
