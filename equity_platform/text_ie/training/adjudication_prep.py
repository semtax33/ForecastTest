from __future__ import annotations


_ANNOTATION_FIELDS = (
    "metric_start",
    "metric_end",
    "metric_literal",
    "quantity_start",
    "quantity_end",
    "quantity_literal",
    "concept_label",
    "binding_label",
    "role_label",
    "scope",
    "period",
    "quantity_kind",
    "notes",
)
_FINAL_FIELDS = tuple(field for field in _ANNOTATION_FIELDS if field != "notes")
_REQUIRED_FIELDS = (
    "metric_start",
    "metric_end",
    "metric_literal",
    "quantity_start",
    "quantity_end",
    "quantity_literal",
    "concept_label",
    "binding_label",
    "quantity_kind",
)
_CORE_IMMUTABLE_FIELDS = (
    "context_id",
    "source_slice",
    "entity",
    "source_sha256",
    "source_path",
    "text",
)
_CANDIDATE_FIELDS = (
    "metric_candidate_start",
    "metric_candidate_end",
    "metric_candidate_literal",
    "quantity_candidate_start",
    "quantity_candidate_end",
    "quantity_candidate_literal",
    "quantity_candidate_kind",
)


def _index(rows, label: str):
    output = {}
    for row in rows:
        pair_id = str(row.get("pair_id", "")).strip()
        if not pair_id or pair_id in output:
            raise ValueError(f"{label} requires unique non-empty pair ids")
        output[pair_id] = row
    if not output:
        raise ValueError(f"{label} cannot be empty")
    return output


def _validate_annotation(values: dict[str, str], channel: str) -> None:
    if any(not values[field].strip() for field in _REQUIRED_FIELDS):
        raise ValueError(f"annotator {channel} has an incomplete reviewed annotation")
    binding = values["binding_label"].strip()
    if binding not in {"BELONGS_TO", "NOT_RELATED"}:
        raise ValueError(f"annotator {channel} has an unsupported binding label")
    if binding == "BELONGS_TO" and any(
        not values[field].strip() for field in ("role_label", "scope", "period")
    ):
        raise ValueError(f"annotator {channel} has an incomplete reviewed annotation")
    if binding == "NOT_RELATED" and values["role_label"].strip():
        raise ValueError(f"annotator {channel} NOT_RELATED pair has a role")


def hydrate_adjudication_rows(
    *,
    annotator_a_rows: tuple[dict[str, str], ...],
    annotator_b_rows: tuple[dict[str, str], ...],
    template_rows: tuple[dict[str, str], ...],
) -> tuple[dict[str, str], ...]:
    """Copy independent A/B answers into a label-blind adjudication template."""

    a_rows = _index(annotator_a_rows, "annotator A")
    b_rows = _index(annotator_b_rows, "annotator B")
    templates = _index(template_rows, "adjudication template")
    if not (set(a_rows) == set(b_rows) == set(templates)):
        raise ValueError("A/B/adjudication pair sets do not match")
    a_ids = {str(row.get("annotator_id", "")).strip() for row in a_rows.values()}
    b_ids = {str(row.get("annotator_id", "")).strip() for row in b_rows.values()}
    if "" in a_ids or "" in b_ids or a_ids & b_ids:
        raise ValueError("A/B annotator identities must be non-empty and disjoint")
    output = []
    for pair_id in sorted(templates):
        a = a_rows[pair_id]
        b = b_rows[pair_id]
        template = templates[pair_id]
        if str(a.get("annotation_channel", "")).strip() != "A":
            raise ValueError("annotator A channel mismatch")
        if str(b.get("annotation_channel", "")).strip() != "B":
            raise ValueError("annotator B channel mismatch")
        immutable_fields = (*_CORE_IMMUTABLE_FIELDS, *(
            field for field in _CANDIDATE_FIELDS if field in template
        ))
        for field in immutable_fields:
            expected = str(template.get(field, ""))
            if str(a.get(field, "")) != expected or str(b.get(field, "")) != expected:
                raise ValueError(
                    f"immutable adjudication source changed: {field}"
                )
        row = dict(template)
        annotations = {}
        for channel, source in (("a", a), ("b", b)):
            row[f"annotator_{channel}_id"] = str(source["annotator_id"])
            values = {}
            for field in _ANNOTATION_FIELDS:
                value = str(source.get(f"reviewed_{field}", ""))
                row[f"annotator_{channel}_{field}"] = value
                values[field] = value
            _validate_annotation(values, channel.upper())
            annotations[channel] = values
        agreed = annotations["a"] == annotations["b"]
        row["agreement_status"] = "AGREED" if agreed else "DISAGREEMENT"
        row["adjudicator_id"] = ""
        for field in _FINAL_FIELDS:
            row[f"final_{field}"] = annotations["a"][field] if agreed else ""
        row["adjudication_notes"] = ""
        output.append(row)
    return tuple(output)


__all__ = ["hydrate_adjudication_rows"]
