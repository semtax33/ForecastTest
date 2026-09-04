from __future__ import annotations

from collections import defaultdict

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import SourceSpan

from ..model import (
    AbstentionItem,
    FactTier,
    ReviewItem,
    SemanticFrame,
    TextExtractionResult,
)
from ..runtime import (
    DEFAULT_TEXT_RULES,
    _frame_claim,
    _frame_facts,
    _frame_relations,
    extract_text_kpis,
)
from .binder import bind_recall_candidates
from .candidate_generator import V24_RULES, generate_recall_candidates
from .llm_rescue import AbstentionRescueBackend, ground_llm_proposals
from .model import HighRecallExtractionResult
from .verifier import verify_bound_candidates


def _in_table(item: object, tables: tuple[object, ...]) -> bool:
    return any(
        item.source_span.char_start >= table.char_start
        and item.source_span.char_end <= table.char_end
        for table in tables
    )


def extract_text_kpis_v24(
    document: CanonicalDocument,
    *,
    llm_backend: AbstentionRescueBackend | None = None,
) -> HighRecallExtractionResult:
    base = extract_text_kpis(document)
    candidates, table_routes = generate_recall_candidates(document)
    bindings = bind_recall_candidates(candidates)
    verification = list(verify_bound_candidates(document, bindings))

    if llm_backend is not None:
        bound_ids = {item.candidate_id for item in bindings}
        by_block: dict[tuple[int, int], list[object]] = defaultdict(list)
        for candidate in candidates:
            if candidate.candidate_id not in bound_ids:
                by_block[(candidate.block.char_start, candidate.block.char_end)].append(candidate)
        for group in by_block.values():
            proposals = llm_backend.propose(group[0].block, tuple(group))
            grounded = ground_llm_proposals(proposals, tuple(group))
            verification.extend(verify_bound_candidates(document, grounded))
            bindings += grounded

    base_frames = tuple(frame for frame in base.frames if not _in_table(frame, table_routes))
    accepted = tuple(
        decision.frame
        for decision in verification
        if decision.accepted and decision.frame is not None
    )
    frame_keys = {
        (
            frame.source.sha256,
            frame.source_span.char_start,
            frame.concept,
            frame.frame,
            frame.value,
        )
        for frame in base_frames
    }
    additional = []
    for frame in accepted:
        key = (
            frame.source.sha256,
            frame.source_span.char_start,
            frame.concept,
            frame.frame,
            frame.value,
        )
        if key not in frame_keys:
            frame_keys.add(key)
            additional.append(frame)
    frames = base_frames + tuple(additional)

    reviews = [review for review in base.reviews if not _in_table(review, table_routes)]
    seen_review = {
        (review.source_span.char_start, review.rule_id, review.reason)
        for review in reviews
    }
    for decision in verification:
        if decision.accepted:
            continue
        item = decision.candidate
        key = (item.block.char_start, item.rule_id, decision.reason)
        if key in seen_review:
            continue
        seen_review.add(key)
        reviews.append(
            ReviewItem(
                sentence_index=item.block.sentence_index,
                rule_id=item.rule_id,
                status="REVIEW_V24_STRICT_VERIFIER_REJECTED",
                reason=decision.reason,
                source_span=SourceSpan(
                    section=item.block.section,
                    char_start=item.block.char_start,
                    char_end=item.block.char_end,
                    literal=item.block.text,
                ),
                candidates=(item.output_concept,),
                tier=item.frame is not SemanticFrame.CAUSE_EFFECT and FactTier.CRITICAL or FactTier.NARRATIVE,
            )
        )

    abstentions = [
        item for item in base.abstentions if not _in_table(item, table_routes)
    ]
    for table in table_routes:
        abstentions.append(
            AbstentionItem(
                sentence_index=table.sentence_index,
                rule_id="v24.document.table_reconstruction",
                reason="FLATTENED_TABLE_RECONSTRUCTED_FOR_TABLE_DSL",
                failure_class="TABLE_TEXT_BOUNDARY",
                source_span=SourceSpan(
                    section=None,
                    char_start=table.char_start,
                    char_end=table.char_end,
                    literal=table.source_literal,
                ),
                tier=FactTier.CRITICAL,
                candidates=table.metric_labels,
            )
        )
    facts = tuple(fact for frame in frames for fact in _frame_facts(frame))
    claims = tuple(
        claim
        for frame in frames
        if (claim := _frame_claim(frame)) is not None
    )
    relations = tuple(
        relation for relation in base.relations if not _in_table(relation, table_routes)
    ) + _frame_relations(
        tuple(
            frame
            for frame in additional
            if frame.rule_id in {rule.rule_id for rule in V24_RULES}
        ),
        V24_RULES,
    )
    extraction = TextExtractionResult(
        frames=frames,
        facts=facts,
        evidence_claims=claims,
        relations=relations,
        reviews=tuple(reviews),
        abstentions=tuple(abstentions),
        backend_name=f"{base.backend_name}+V24_HIGH_RECALL",
    )
    return HighRecallExtractionResult(
        extraction=extraction,
        candidates=candidates,
        bindings=bindings,
        verification=tuple(verification),
        table_routes=table_routes,
    )
