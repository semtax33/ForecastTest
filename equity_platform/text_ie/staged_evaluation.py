from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any


DEFAULT_STAGED_GATES: dict[str, float | int] = {
    "candidate_recall": 0.99,
    "quantity_recall": 0.995,
    "concept_precision": 0.99,
    "binding_precision": 0.99,
    "role_precision": 0.99,
    "frame_precision": 0.99,
    "frame_recall": 0.97,
    "table_route_accuracy": 0.95,
    "abstention_coverage": 1.0,
    "duplicate_auto_emission": 0,
    "illegal_cross_clause_auto_binding": 0,
    "silent_frame_miss": 0,
}


@dataclass(frozen=True)
class StageCounts:
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 1.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 1.0


def _number(value: Any) -> float:
    return round(float(value), 8)


def base_concept(concept: str) -> str:
    output = concept
    if output.startswith("PRIOR_YEAR_"):
        output = output[len("PRIOR_YEAR_"):]
    for suffix in ("_CHANGE_GUIDANCE", "_GUIDANCE"):
        if output.endswith(suffix):
            output = output[: -len(suffix)]
            break
    return output


def explicit_quantity_values(frame: Mapping[str, Any]) -> tuple[float, ...]:
    """Return stated quantities, excluding a reducer-derived range midpoint."""

    lower = frame.get("lower_value")
    upper = frame.get("upper_value")
    if frame.get("frame") == "RANGE_GUIDANCE" and lower is not None and upper is not None:
        return (_number(lower), _number(upper))
    output = []
    if frame.get("value") is not None:
        output.append(_number(frame["value"]))
    if frame.get("change") is not None:
        output.append(_number(frame["change"]))
    return tuple(output)


def frame_concepts(frame: Mapping[str, Any]) -> tuple[str, ...]:
    return (base_concept(str(frame["concept"])),)


def frame_owner_bindings(frame: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    concept = base_concept(str(frame["concept"]))
    return tuple(sorted((concept, value) for value in explicit_quantity_values(frame)))


def frame_quantity_roles(frame: Mapping[str, Any]) -> tuple[tuple[str, str, float], ...]:
    concept_name = str(frame["concept"])
    concept = base_concept(concept_name)
    semantic = str(frame["frame"])
    values = explicit_quantity_values(frame)
    if semantic == "RANGE_GUIDANCE" and len(values) == 2:
        prefix = "GUIDANCE_DELTA" if concept_name.endswith("_CHANGE_GUIDANCE") else "GUIDANCE"
        return (
            (concept, f"{prefix}_LOW", values[0]),
            (concept, f"{prefix}_HIGH", values[1]),
        )
    if semantic == "COMPARATIVE" and values:
        role = "VALUE_PRIOR" if concept_name.startswith("PRIOR_YEAR_") else "VALUE_CURRENT"
        return ((concept, role, values[0]),)
    if semantic == "CHANGE_TO" and values:
        output = [(concept, "VALUE_CURRENT", values[0])]
        if len(values) > 1:
            output.append((concept, "DELTA", values[1]))
        return tuple(output)
    if semantic == "CHANGE_BY" and values:
        role = "GUIDANCE_DELTA" if concept_name.endswith("_CHANGE_GUIDANCE") else "DELTA"
        return ((concept, role, values[0]),)
    if semantic == "COMPOSITION" and values:
        return ((concept, "COMPOSITION", values[0]),)
    if values:
        role = "GUIDANCE_VALUE" if concept_name.endswith("_GUIDANCE") else "VALUE_CURRENT"
        return ((concept, role, values[0]),)
    return ()


def score_stage(expected: Iterable[Hashable], actual: Iterable[Hashable]) -> StageCounts:
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    overlap = expected_counts & actual_counts
    true_positive = sum(overlap.values())
    return StageCounts(
        true_positive=true_positive,
        false_positive=sum(actual_counts.values()) - true_positive,
        false_negative=sum(expected_counts.values()) - true_positive,
    )


def _frame_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    for field in ("concept", "frame", "value", "change", "lower_value", "upper_value"):
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if field in {"value", "change", "lower_value", "upper_value"}:
            if expected_value is None or actual_value is None:
                if expected_value is not actual_value:
                    return False
            elif _number(expected_value) != _number(actual_value):
                return False
        elif expected_value != actual_value:
            return False
    if "polarity" in expected and expected.get("polarity") != actual.get("polarity"):
        return False
    return True


def _score_frames(
    expected: Iterable[Mapping[str, Any]],
    actual: Iterable[Mapping[str, Any]],
) -> StageCounts:
    expected_items = list(expected)
    available = list(actual)
    unmatched = []
    for target in expected_items:
        match_index = next(
            (index for index, candidate in enumerate(available) if _frame_matches(target, candidate)),
            None,
        )
        if match_index is None:
            unmatched.append(target)
            continue
        available.pop(match_index)
    true_positive = len(expected_items) - len(unmatched)
    return StageCounts(
        true_positive=true_positive,
        false_positive=len(available),
        false_negative=len(expected_items) - true_positive,
    )


def unmatched_expected_frames(
    expected: Iterable[Mapping[str, Any]],
    actual: Iterable[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    available = list(actual)
    unmatched = []
    for target in expected:
        match_index = next(
            (
                index
                for index, candidate in enumerate(available)
                if _frame_matches(target, candidate)
            ),
            None,
        )
        if match_index is None:
            unmatched.append(target)
        else:
            available.pop(match_index)
    return tuple(unmatched)


def _flatten(frames: Iterable[Mapping[str, Any]], transform) -> tuple[Hashable, ...]:
    return tuple(item for frame in frames for item in transform(frame))


def summarize_staged_validation(
    rows: Iterable[Mapping[str, Any]],
    *,
    exclude_table_intermediate: bool = False,
) -> dict[str, float | int]:
    items = list(rows)
    expected_frames = [frame for row in items for frame in row["expected_frames"]]
    stage_totals = {
        name: [0, 0, 0]
        for name in ("quantity", "concept", "binding", "role")
    }
    frame_tp = frame_fp = frame_fn = 0
    route_frame_counts = {
        "TEXT_IE": [0, 0, 0],
        "TABLE_DSL": [0, 0, 0],
        "NO_FACT": [0, 0, 0],
    }
    observable_abstained = silent = 0
    abstained_blocks = reviewed_blocks = eligible_blocks = 0
    candidate_expected = candidate_hits = 0
    for row in items:
        expected = list(row["expected_frames"])
        actual = list(row["actual_frames"])
        score_intermediate = not (
            exclude_table_intermediate and row.get("gold_route") == "TABLE_DSL"
        )
        if score_intermediate:
            candidate_expected += int(row.get("candidate_expected", len(expected)))
            candidate_hits += int(row.get("candidate_hits", 0))
        expected_quantities = (
            tuple(row["expected_quantities"])
            if "expected_quantities" in row
            else _flatten(expected, explicit_quantity_values)
        )
        expected_concepts = (
            tuple(row["expected_concepts"])
            if "expected_concepts" in row
            else _flatten(expected, frame_concepts)
        )
        expected_bindings = (
            tuple(tuple(item) for item in row["expected_bindings"])
            if "expected_bindings" in row
            else _flatten(expected, frame_owner_bindings)
        )
        expected_roles = (
            tuple(tuple(item) for item in row["expected_roles"])
            if "expected_roles" in row
            else _flatten(expected, frame_quantity_roles)
        )
        detected_concepts = (
            tuple(row["detected_concepts"])
            if "detected_concepts" in row
            else _flatten(actual, frame_concepts)
        )
        detected_bindings = (
            tuple(tuple(item) for item in row["detected_bindings"])
            if "detected_bindings" in row
            else _flatten(actual, frame_owner_bindings)
        )
        detected_roles = (
            tuple(tuple(item) for item in row["detected_roles"])
            if "detected_roles" in row
            else _flatten(actual, frame_quantity_roles)
        )
        stage_pairs = {
            "quantity": (
                expected_quantities,
                tuple(row.get("detected_quantities", ())),
            ),
            "concept": (
                expected_concepts,
                detected_concepts,
            ),
            "binding": (
                expected_bindings,
                detected_bindings,
            ),
            "role": (
                expected_roles,
                detected_roles,
            ),
        }
        if score_intermediate:
            for name, (stage_expected, stage_actual) in stage_pairs.items():
                stage = score_stage(stage_expected, stage_actual)
                stage_totals[name][0] += stage.true_positive
                stage_totals[name][1] += stage.false_positive
                stage_totals[name][2] += stage.false_negative
        counts = _score_frames(expected, actual)
        frame_tp += counts.true_positive
        frame_fp += counts.false_positive
        frame_fn += counts.false_negative
        route_counts = route_frame_counts[str(row.get("gold_route", "NO_FACT"))]
        route_counts[0] += counts.true_positive
        route_counts[1] += counts.false_positive
        route_counts[2] += counts.false_negative
        observable = int(row.get("rejection_count", 0)) > 0 or int(row.get("review_count", 0)) > 0
        if counts.false_negative:
            if "observable_abstained_frames" in row:
                observed = max(
                    0,
                    min(
                        counts.false_negative,
                        int(row["observable_abstained_frames"]),
                    ),
                )
                observable_abstained += observed
                silent += counts.false_negative - observed
            elif observable:
                observable_abstained += counts.false_negative
            else:
                silent += counts.false_negative
        if row.get("gold_route") != "TABLE_DSL":
            eligible_blocks += 1
            if not actual and observable:
                abstained_blocks += 1
            if int(row.get("review_count", 0)) > 0:
                reviewed_blocks += 1

    quantity, concept, binding, role = (
        StageCounts(*stage_totals[name])
        for name in ("quantity", "concept", "binding", "role")
    )
    frame = StageCounts(frame_tp, frame_fp, frame_fn)
    table_correct = sum(
        bool(row.get("predicted_table")) == (row.get("gold_route") == "TABLE_DSL")
        for row in items
    )
    route_stage_counts = {
        route: StageCounts(*counts)
        for route, counts in route_frame_counts.items()
    }
    return {
        "annotated_blocks": len(items),
        "expected_frames": len(expected_frames),
        "expected_candidates": candidate_expected,
        "candidate_hits": candidate_hits,
        "candidate_recall": candidate_hits / candidate_expected if candidate_expected else 1.0,
        "quantity_true_positive": quantity.true_positive,
        "quantity_false_positive": quantity.false_positive,
        "quantity_false_negative": quantity.false_negative,
        "quantity_precision": quantity.precision,
        "quantity_recall": quantity.recall,
        "concept_true_positive": concept.true_positive,
        "concept_false_positive": concept.false_positive,
        "concept_false_negative": concept.false_negative,
        "concept_precision": concept.precision,
        "concept_recall": concept.recall,
        "binding_true_positive": binding.true_positive,
        "binding_false_positive": binding.false_positive,
        "binding_false_negative": binding.false_negative,
        "binding_precision": binding.precision,
        "binding_recall": binding.recall,
        "role_true_positive": role.true_positive,
        "role_false_positive": role.false_positive,
        "role_false_negative": role.false_negative,
        "role_precision": role.precision,
        "role_recall": role.recall,
        "frame_true_positive": frame.true_positive,
        "frame_false_positive": frame.false_positive,
        "frame_false_negative": frame.false_negative,
        "frame_precision": frame.precision,
        "frame_recall": frame.recall,
        "text_ie_frame_precision": route_stage_counts["TEXT_IE"].precision,
        "text_ie_frame_recall": route_stage_counts["TEXT_IE"].recall,
        "table_frame_precision": route_stage_counts["TABLE_DSL"].precision,
        "table_frame_recall": route_stage_counts["TABLE_DSL"].recall,
        "no_fact_frame_false_positive": route_stage_counts["NO_FACT"].false_positive,
        "observable_abstained_frames": observable_abstained,
        "silent_frame_miss": silent,
        "abstention_coverage": observable_abstained / frame_fn if frame_fn else 1.0,
        "abstained_blocks": abstained_blocks,
        "abstention_rate": abstained_blocks / eligible_blocks if eligible_blocks else 0.0,
        "reviewed_blocks": reviewed_blocks,
        "review_rate": reviewed_blocks / eligible_blocks if eligible_blocks else 0.0,
        "table_route_accuracy": table_correct / len(items) if items else 1.0,
    }


def summarize_route_aware_staged_validation(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, float | int]:
    """Score table routing separately from the TEXT_IE semantic graph.

    TABLE_DSL is an intentional bypass of candidate/binding/role inference.
    Its extracted facts still participate in end-to-end frame scores, while
    its absent text-graph edges do not become artificial false negatives.
    NO_FACT blocks remain in the intermediate scores so false-positive
    concepts, quantities, bindings, and roles still reduce precision.
    """

    return summarize_staged_validation(rows, exclude_table_intermediate=True)


def staged_gate_results(
    summary: Mapping[str, float | int],
    gates: Mapping[str, float | int] = DEFAULT_STAGED_GATES,
) -> dict[str, bool]:
    maximum_metrics = {
        "duplicate_auto_emission",
        "illegal_cross_clause_auto_binding",
        "silent_frame_miss",
    }
    return {
        metric: (
            float(summary.get(metric, 0)) <= float(limit)
            if metric in maximum_metrics
            else float(summary.get(metric, 0)) >= float(limit)
        )
        for metric, limit in gates.items()
    }
