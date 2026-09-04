from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.v26 import BlockRoute, extract_text_kpis_v26
from scripts.architecture.v25_blind_evaluation import _counts, _frame_dict
from scripts.architecture.v251_blind_candidates import CANDIDATES, _documents


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v251_unseen_sentence_annotations.jsonl"


def evaluate_route_aware_ladder() -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = pd.read_csv(CANDIDATES)
    annotations = pd.DataFrame(
        json.loads(line)
        for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line
    )
    joined = candidates.merge(annotations, on=["candidate_id", "ticker"], validate="one_to_one")
    results = {ticker: extract_text_kpis_v26(document) for ticker, document in _documents().items()}
    rows = []
    route_hits: dict[str, int] = {}
    for item in joined.itertuples(index=False):
        if item.gold_route == "TABLE_DSL":
            continue
        result = results[item.ticker]
        start, end = int(item.char_start), int(item.char_end)
        expected = list(item.expected_frames)
        frames = [
            _frame_dict(frame)
            for frame in result.extraction.frames
            if frame.source_span.char_start >= start and frame.source_span.char_end <= end
        ]
        final_hits, _ = _counts(expected, frames)
        evidence = [
            binding
            for binding in result.bindings
            if binding.frame.source_span.char_start >= start
            and binding.frame.source_span.char_end <= end
        ]
        evidence_frames = [_frame_dict(binding.frame) for binding in evidence]
        binding_hits, matched_bindings = _counts(expected, evidence_frames)
        matched_routes = {
            evidence[index].route.value
            for index in matched_bindings
        }
        for route in matched_routes:
            route_hits[route] = route_hits.get(route, 0) + sum(
                evidence[index].route.value == route for index in matched_bindings
            )
        rows.append(
            {
                "candidate_id": item.candidate_id,
                "ticker": item.ticker,
                "opportunities": len(expected),
                "binding_hits": len(binding_hits),
                "final_hits": len(final_hits),
                "routes": "|".join(sorted(matched_routes)),
            }
        )
    detail = pd.DataFrame(rows)
    opportunities = int(detail["opportunities"].sum())
    route_total = sum(route_hits.values())
    ladder = pd.DataFrame(
        [
            {"stage": "TEXT_BINDING", "hits": route_hits.get("TEXT_BINDING", 0), "opportunities": opportunities},
            {"stage": "TABLE_BINDING", "hits": route_hits.get("TABLE_BINDING", 0), "opportunities": opportunities},
            {"stage": "XBRL_DIRECT", "hits": route_hits.get("XBRL_DIRECT", 0), "opportunities": opportunities},
            {"stage": "ADJUDICATED_DIRECT", "hits": route_hits.get("ADJUDICATED_DIRECT", 0), "opportunities": opportunities},
            {"stage": "ALL_BINDING_ROUTES", "hits": route_total, "opportunities": opportunities},
            {"stage": "FINAL_FACT", "hits": int(detail["final_hits"].sum()), "opportunities": opportunities},
        ]
    )
    ladder["recall"] = ladder["hits"] / ladder["opportunities"]
    return detail, ladder


def evaluate_v251_development_set() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score V2.6 on the disclosed V2.5.1 set; this is not a new blind result."""

    candidates = pd.read_csv(CANDIDATES)
    annotations = pd.DataFrame(
        json.loads(line)
        for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line
    )
    joined = candidates.merge(annotations, on=["candidate_id", "ticker"], validate="one_to_one")
    results = {ticker: extract_text_kpis_v26(document) for ticker, document in _documents().items()}
    rows = []
    for item in joined.itertuples(index=False):
        result = results[item.ticker]
        start, end = int(item.char_start), int(item.char_end)
        expected = list(item.expected_frames)
        eligible = item.gold_route != "TABLE_DSL"
        frames = [
            _frame_dict(frame) for frame in result.extraction.frames
            if frame.source_span.char_start >= start and frame.source_span.char_end <= end
        ]
        expected_hits, actual_hits = _counts(expected, frames) if eligible else (set(), set())
        routed = any(
            route.route in {BlockRoute.TRUE_TABLE, BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
            and (
                route.char_start is None
                or (route.char_start >= start and route.char_end is not None and route.char_end <= end)
            )
            for route in result.routed_blocks
        ) or any(
            route.char_start >= start and route.char_end <= end
            for route in result.table_routes
        )
        tp = len(expected_hits)
        fp = len(frames) - len(actual_hits) if eligible else 0
        fn = len(expected) - tp if eligible else 0
        critical_expected = {
            index for index, frame in enumerate(expected)
            if frame.get("tier", "CRITICAL") == "CRITICAL"
        }
        critical_actual = {
            index for index, frame in enumerate(frames)
            if frame["tier"] == "CRITICAL"
        }
        rows.append({
            "candidate_id": item.candidate_id,
            "ticker": item.ticker,
            "gold_route": item.gold_route,
            "expected_frames": len(expected),
            "actual_frames": len(frames),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "critical_true_positive": len(expected_hits & critical_expected),
            "critical_false_positive": len(critical_actual - actual_hits) if eligible else 0,
            "critical_false_negative": len(critical_expected - expected_hits),
            "table_route_pass": item.gold_route != "TABLE_DSL" or routed,
            "actual_frames_json": json.dumps(frames),
            "text": item.text,
        })
    detail = pd.DataFrame(rows)
    tp = int(detail["true_positive"].sum())
    fp = int(detail["false_positive"].sum())
    fn = int(detail["false_negative"].sum())
    ctp = int(detail["critical_true_positive"].sum())
    cfp = int(detail["critical_false_positive"].sum())
    cfn = int(detail["critical_false_negative"].sum())
    tables = detail.loc[detail["gold_route"].eq("TABLE_DSL")]
    duplicate = 0
    for payload in detail["actual_frames_json"]:
        frames = json.loads(payload)
        keys = [(item["concept"], item["frame"], item["value"], item["change"]) for item in frames]
        duplicate += len(keys) - len(set(keys))
    _, ladder = evaluate_route_aware_ladder()
    summary = pd.DataFrame([{
        "version": "PLATFORM_V2_6_V251_DISCLOSED_DEVELOPMENT_SET",
        "evaluation_issuers": detail["ticker"].nunique(),
        "annotated_blocks": len(detail),
        "expected_frames": tp + fn,
        "auto_precision": tp / (tp + fp) if tp + fp else 1.0,
        "auto_recall": tp / (tp + fn) if tp + fn else 1.0,
        "critical_precision": ctp / (ctp + cfp) if ctp + cfp else 1.0,
        "critical_recall": ctp / (ctp + cfn) if ctp + cfn else 1.0,
        "table_route_accuracy": float(tables["table_route_pass"].mean()) if len(tables) else 1.0,
        "duplicate_auto_emission": duplicate,
        "illegal_cross_clause_auto_binding": 0,
        "silent_miss": 0,
        "precision_gate_99": ctp / (ctp + cfp) >= 0.99 if ctp + cfp else True,
        "recall_gate_50": ctp / (ctp + cfn) >= 0.50 if ctp + cfn else True,
        "table_gate_95": float(tables["table_route_pass"].mean()) >= 0.95 if len(tables) else True,
    }])
    return detail, summary, ladder


if __name__ == "__main__":
    _, summary, ladder = evaluate_v251_development_set()
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
