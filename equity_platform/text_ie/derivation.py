from __future__ import annotations

from equity_platform.ir import (
    AuthorityLevel,
    EvidenceStatus,
    FactIR,
    FactOrigin,
    LineageRef,
    RelationType,
)


def derive_difference(
    total: FactIR,
    excluded: FactIR,
    *,
    metric: str,
    period: str,
) -> FactIR:
    """Create an auditable identity fact; extraction never performs this math."""

    if total.entity != excluded.entity or total.scope != excluded.scope:
        raise ValueError("Identity inputs must share entity and scope")
    if total.unit != excluded.unit:
        raise ValueError("Identity inputs must share a unit")
    value = total.value - excluded.value
    if value < 0:
        raise ValueError("Identity result cannot be negative")
    return FactIR(
        entity=total.entity,
        metric=metric,
        scope=total.scope,
        period=period,
        unit=total.unit,
        value=value,
        origin=FactOrigin.DERIVED,
        relation=RelationType.IDENTITY,
        evidence=EvidenceStatus.DIAGNOSTIC,
        authority=min(
            total.authority,
            excluded.authority,
            AuthorityLevel.RESEARCH_EVIDENCE,
        ),
        source=total.source,
        lineage=LineageRef(
            rule_id="text_ie.identity.difference",
            rule_version=1,
            match_trace={
                "total_metric": total.metric,
                "excluded_metric": excluded.metric,
                "excluded_source_sha256": excluded.source.sha256,
            },
            capture_trace={
                "formula": "total - excluded",
                "total": total.value,
                "excluded": excluded.value,
                "result": value,
            },
        ),
    )
