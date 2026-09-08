from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256

from equity_platform.documents import CanonicalDocument

from ..document import document_text_blocks
from ..llm.encoder_registry import EncoderSourceSlice
from ..v24.candidate_generator import extract_candidate_quantities
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v291 import V291ExtractionResult
from ..v292 import extract_text_kpis_v292
from .model import (
    LearnedSpanBackend,
    LearnedSpanProposal,
    LearnedSpanRejection,
    LearnedSpanUnavailableError,
)


@dataclass(frozen=True)
class LearnedCandidateGraphResult:
    """V292 evidence plus a research-only candidate graph augmentation."""

    baseline: V291ExtractionResult
    candidates: tuple[RecallCandidate, ...]
    proposals: tuple[LearnedSpanProposal, ...]
    rejections: tuple[LearnedSpanRejection, ...]
    added_candidate_count: int
    merged_candidate_count: int
    status: str
    diagnostic: str | None = None

    @property
    def extraction(self):
        return self.baseline.extraction

    @property
    def research_facts(self) -> tuple[()]:
        return ()


def _rejection(proposal: LearnedSpanProposal, reason: str) -> LearnedSpanRejection:
    return LearnedSpanRejection(
        model_id=proposal.model_id,
        source_sha256=proposal.source_sha256,
        block_char_start=proposal.block_char_start,
        block_char_end=proposal.block_char_end,
        char_start=proposal.char_start,
        char_end=proposal.char_end,
        reason=reason,
    )


def _rule_id(proposal: LearnedSpanProposal) -> str:
    return f"learned-span:{proposal.model_id}@{proposal.model_revision}"


def challenge_v292_span_candidates(
    document: CanonicalDocument,
    *,
    backend: LearnedSpanBackend,
    source_slice: EncoderSourceSlice,
) -> LearnedCandidateGraphResult:
    """Augment V292 recall candidates without changing frames or facts.

    Exact source identity is rechecked independently of the learned backend.
    Learned labels remain raw unless a separate canonicalizer supplied an
    explicit concept.  Nothing in this function crosses the reducer boundary.
    """

    baseline = extract_text_kpis_v292(document)
    candidates = list(baseline.candidates)
    collected: list[LearnedSpanProposal] = []
    try:
        for block in document_text_blocks(document):
            collected.extend(backend.propose(block, source_slice))
    except LearnedSpanUnavailableError as exc:
        return LearnedCandidateGraphResult(
            baseline=baseline,
            candidates=baseline.candidates,
            proposals=(),
            rejections=(),
            added_candidate_count=0,
            merged_candidate_count=0,
            status="CHALLENGER_UNAVAILABLE",
            diagnostic=str(exc),
        )

    blocks_by_hash = {}
    for block in document_text_blocks(document):
        blocks_by_hash.setdefault(block.source.sha256, []).append(block)
    accepted = []
    rejections = []
    added = 0
    merged = 0
    for proposal in collected:
        if proposal.source_sha256 != document.source.sha256:
            rejections.append(_rejection(proposal, "SOURCE_HASH_MISMATCH"))
            continue
        matching_blocks = tuple(
            block
            for block in blocks_by_hash.get(proposal.source_sha256, ())
            if block.char_start == proposal.block_char_start
            and block.char_end == proposal.block_char_end
            and proposal.char_end <= len(block.text)
            and block.text[proposal.char_start:proposal.char_end] == proposal.raw_text
        )
        if not matching_blocks:
            rejections.append(_rejection(proposal, "SOURCE_LITERAL_MISMATCH"))
            continue
        block = matching_blocks[0]
        exact_indices = [
            index
            for index, candidate in enumerate(candidates)
            if candidate.block.char_start == block.char_start
            and candidate.block.char_end == block.char_end
            and candidate.metric.char_start == proposal.char_start
            and candidate.metric.char_end == proposal.char_end
        ]
        if exact_indices:
            index = exact_indices[0]
            current = candidates[index]
            if (
                proposal.canonical_concept is not None
                and proposal.canonical_concept != current.metric.concept
            ):
                rejections.append(_rejection(proposal, "CANONICAL_CONCEPT_CONFLICT"))
                continue
            candidates[index] = replace(
                current,
                origins=tuple(sorted(
                    {*current.origins, CandidateOrigin.LEARNED_SPAN},
                    key=str,
                )),
                rule_ids=tuple(dict.fromkeys((*current.rule_ids, _rule_id(proposal)))),
            )
            accepted.append(proposal)
            merged += 1
            continue
        concept = proposal.canonical_concept or "UNRESOLVED_KPI"
        candidate_id = sha256(
            (
                f"{document.source.sha256}:{block.char_start}:LEARNED_SPAN:"
                f"{proposal.char_start}:{proposal.char_end}:{proposal.model_id}:"
                f"{proposal.model_revision}"
            ).encode()
        ).hexdigest()[:20]
        candidates.append(RecallCandidate(
            candidate_id=candidate_id,
            block=block,
            metric=MetricAnchor(
                concept=concept,
                alias=proposal.raw_text,
                char_start=proposal.char_start,
                char_end=proposal.char_end,
            ),
            quantities=extract_candidate_quantities(block.text),
            origins=(CandidateOrigin.LEARNED_SPAN,),
            rule_ids=(_rule_id(proposal),),
        ))
        accepted.append(proposal)
        added += 1

    if added or merged:
        status = "CANDIDATE_GRAPH_AUGMENTED"
    elif rejections:
        status = "PROPOSALS_REJECTED"
    else:
        status = "NO_PROPOSALS"
    return LearnedCandidateGraphResult(
        baseline=baseline,
        candidates=tuple(candidates),
        proposals=tuple(accepted),
        rejections=tuple(rejections),
        added_candidate_count=added,
        merged_candidate_count=merged,
        status=status,
    )


__all__ = ["LearnedCandidateGraphResult", "challenge_v292_span_candidates"]
