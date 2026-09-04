from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_document, adapt_html_fragments
from equity_platform.ir import (
    AuthorityLevel,
    ExtractionMethod,
    FactOrigin,
    RelationType,
    SourceSpan,
)
from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials import (
    build_cat_backlog_history,
    load_cat_10k_sources,
    parse_cat_backlog_semantic_ir,
)
from equity_platform.text_ie import (
    DEFAULT_TEXT_RULES,
    TextDslCompileError,
    VerificationStatus,
    compile_text_rules,
    compile_text_program_file,
    derive_difference,
    document_text_blocks,
    extract_text_kpis,
    SpacySemanticBackend,
)
from equity_platform.text_ie.llm import verify_llm_frame
from equity_platform.text_ie.training import (
    corpus_metrics,
    evaluate_gold_corpus,
    load_review_annotations,
    review_precision,
    weak_labels_from_result,
)


GOLD = PROJECT_ROOT / "data-lake/gold/parser/text_ie/semantic_frames.jsonl"
CONTROLLED_GOLD = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/controlled_semantic_frames.jsonl"
)
REVIEW_GOLD = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/multisector_review_annotations.jsonl"
)


def _document(text: str, *, heading: str | None = None):
    heading_html = f"<h2>{heading}</h2>" if heading else ""
    content = f"<html><body>{heading_html}<p>{text}</p></body></html>".encode()
    return adapt_html_fragments(
        fragments=(HtmlFragment(content, "test://text-ie", "TEXT_IE_TEST", numeric_rows_only=False),),
        metadata=DocumentMetadata(
            entity="TEST",
            source_kind="TEST",
            document_kind="TEXT_IE",
            available_at="2026-09-04",
            report_period="2025",
        ),
    )


def test_text_rule_dsl_is_typed_hashed_and_non_turing() -> None:
    assert len(DEFAULT_TEXT_RULES) == 10
    assert len({rule.source_sha256 for rule in DEFAULT_TEXT_RULES}) == 1
    assert all(len(rule.source_sha256) == 64 for rule in DEFAULT_TEXT_RULES)
    program = compile_text_program_file(
        PROJECT_ROOT / "configs/parser_rules/text_ie/semantic_frames.arc"
    )
    assert len(program.variables) == 6
    assert len(program.frames) == 10
    change_to = next(rule for rule in program.rules if rule.rule_id == "semantic.change_to")
    assert [step.label for step in change_to.pattern] == [
        "metric",
        "trigger",
        "change",
        "relation",
        "value",
    ]
    assert {backend.value for backend in change_to.backends} == {"PHRASE", "SEQUENCE"}
    with pytest.raises(TextDslCompileError, match="Unknown or forbidden"):
        compile_text_rules(
            'text_rule "bad" {\nversion = 1\nframe = "RATE"\n'
            'triggers = ["was"]\npython = "eval()"\n}'
        )
    with pytest.raises(TextDslCompileError, match="terminal authority"):
        compile_text_rules(
            'text_rule "bad" {\nversion = 1\nframe = "RATE"\n'
            'triggers = ["was"]\nauthority = "TERMINAL_INPUT"\n}'
        )
    with pytest.raises(TextDslCompileError, match="Unregistered operation"):
        compile_text_rules(
            'text_rule "bad" {\nversion = 1\nframe = "RATE"\n'
            'triggers = ["was"]\noperations = ["issuer_callback"]\n}'
        )


def test_gold_corpus_and_weak_supervision_labels_are_deterministic() -> None:
    rows = evaluate_gold_corpus(GOLD)
    assert len(rows) == 10
    assert all(row["passed"] for row in rows)
    result = extract_text_kpis(
        _document("Revenue and backlog increased 12% to $4.2 billion.")
    )
    assert result.backend_name == "SPACY"
    labels = weak_labels_from_result(result)
    assert len(labels) == 1
    assert labels[0].abstained
    assert labels[0].label == "REVIEW_AMBIGUOUS"


def test_controlled_250_example_corpus_has_exact_precision_recall() -> None:
    rows = evaluate_gold_corpus(CONTROLLED_GOLD)
    metrics = corpus_metrics(rows)
    assert metrics == {
        "examples": 250,
        "exact_passed": 250,
        "exact_accuracy": 1.0,
        "frame_precision": 1.0,
        "frame_recall": 1.0,
        "review_precision": 1.0,
        "review_recall": 1.0,
    }


def test_multisector_review_annotations_are_complete_and_scored() -> None:
    annotations = load_review_annotations(REVIEW_GOLD)
    assert len(annotations) == 48
    metrics = review_precision({row.review_id for row in annotations}, annotations)
    assert metrics["annotation_coverage"] == 1.0
    assert metrics["queue_annotation_coverage"] == 1.0
    assert metrics["precision"] == 45 / 48
    assert metrics["recall"] == 1.0

    incomplete = review_precision(
        {row.review_id for row in annotations} | {"unannotated-review"},
        annotations,
    )
    assert incomplete["annotation_coverage"] == 1.0
    assert incomplete["queue_annotation_coverage"] == 48 / 49


def test_spacy_lemma_pos_and_dependency_backends_execute() -> None:
    rules = compile_text_rules(
        '''
        var "METRIC" { expression = {"concept": "*"} }
        var "VERB" { expression = {"all": [{"lemma": "increase"}, {"pos": "VERB"}]} }
        var "VALUE" { expression = {"quantity": "MONEY"} }
        text_rule "spacy.change" {
          version = 1
          frame = "CHANGE_TO"
          triggers = ["increased"]
          relation_words = ["to"]
          quantity_kinds = ["MONEY"]
          pattern = [{"label":"metric","var":"METRIC"},{"label":"trigger","var":"VERB"},{"label":"value","var":"VALUE"}]
          backends = ["SEQUENCE", "DEPENDENCY"]
        }
        '''
    )
    backend = SpacySemanticBackend()
    result = extract_text_kpis(
        _document("Revenue increased to $4.2 billion."),
        rules,
        backend=backend,
    )
    assert len(result.frames) == 1
    assert result.frames[0].value == 4_200_000_000.0
    causal = extract_text_kpis(
        _document("We do not expect supply constraints to materially affect deliveries."),
        backend=backend,
    )
    assert causal.relations
    assert all(
        frame.extraction_method is ExtractionMethod.DEPENDENCY_RULE
        for frame in causal.frames
    )


def test_energy_unit_prices_and_scaled_volumes_are_normalized() -> None:
    price = extract_text_kpis(
        _document("Average realized price was $3.25 per Mcf.")
    )
    assert len(price.facts) == 1
    assert price.facts[0].metric == "REALIZED_PRICE"
    assert price.facts[0].value == 3.25
    assert price.facts[0].unit == "USD_PER_MCF"

    production = extract_text_kpis(
        _document("Production was 1.2 million barrels during the period.")
    )
    assert len(production.facts) == 1
    assert production.facts[0].metric == "PRODUCTION"
    assert production.facts[0].value == 1_200_000.0


def test_context_resolution_and_identity_derivation_stay_separate() -> None:
    result = extract_text_kpis(
        _document(
            "Total backlog at year-end was $51.2 billion. "
            "Of this amount, $19.3 billion is not expected to be filled in 2026.",
            heading="Marine Systems",
        )
    )
    facts = {fact.metric: fact for fact in result.facts}
    assert facts["BACKLOG"].scope == "MARINE_SYSTEMS"
    assert facts["BACKLOG_NOT_EXPECTED"].period == "2026"
    assert facts["BACKLOG_NOT_EXPECTED"].lineage.match_trace["extraction_method"] == "CONTEXT_RULE"
    derived = derive_difference(
        facts["BACKLOG"],
        facts["BACKLOG_NOT_EXPECTED"],
        metric="BACKLOG_EXPECTED_WITHIN_NEXT_YEAR",
        period="2026",
    )
    assert derived.value == 31_900_000_000.0
    assert derived.origin is FactOrigin.DERIVED
    assert derived.relation is RelationType.IDENTITY
    assert all(fact.value != derived.value for fact in result.facts)


def test_range_qualitative_negation_and_ambiguity_fail_closed() -> None:
    guidance = extract_text_kpis(
        _document("Revenue is expected between $4.0 billion and $4.5 billion in 2026.")
    )
    assert guidance.frames[0].value == 4_250_000_000.0
    assert guidance.frames[0].lower_value == 4_000_000_000.0
    assert guidance.frames[0].upper_value == 4_500_000_000.0
    assert {fact.metric for fact in guidance.facts} == {
        "REVENUE_GUIDANCE_LOW",
        "REVENUE_GUIDANCE_HIGH",
    }
    assert all(fact.authority <= AuthorityLevel.RESEARCH_EVIDENCE for fact in guidance.facts)

    qualitative = extract_text_kpis(
        _document("We do not expect supply constraints to materially affect deliveries.")
    )
    assert not qualitative.facts
    assert len(qualitative.evidence_claims) == 2
    assert len(qualitative.relations) == 1
    assert qualitative.relations[0].cause == "SUPPLY_CONSTRAINT"
    assert qualitative.relations[0].effect == "DELIVERIES"
    assert qualitative.relations[0].direction == "NEGATED"
    assert {claim.predicate for claim in qualitative.evidence_claims} == {
        "MATERIAL_EFFECT_NEGATED"
    }
    assert all(
        claim.authority <= AuthorityLevel.RESEARCH_DIAGNOSTIC
        for claim in qualitative.evidence_claims
    )

    ambiguous = extract_text_kpis(
        _document("Revenue and backlog increased 12% to $4.2 billion.")
    )
    assert not ambiguous.frames and not ambiguous.facts
    assert ambiguous.reviews[0].status == "REVIEW_AMBIGUOUS"

    incompatible = compile_text_rules(
        'text_rule "bad.unit" {\nversion = 1\nframe = "ABSOLUTE_VALUE"\n'
        'triggers = ["was"]\nconcepts = ["BACKLOG"]\n'
        'quantity_kinds = ["PERCENT"]\nambiguity = "REVIEW"\n}'
    )
    rejected = extract_text_kpis(_document("Backlog was 15%."), incompatible)
    assert not rejected.frames and not rejected.facts
    assert rejected.reviews[0].status == "REVIEW_VALIDATION_FAILED"


def test_inline_xbrl_anchor_and_llm_source_span_verifier(tmp_path: Path) -> None:
    html = """
    <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
          xmlns:xbrli="http://www.xbrl.org/2003/instance">
      <body><p>Total backlog was
      <ix:nonfraction name="us-gaap:RevenueRemainingPerformanceObligation"
          contextRef="C1" unitRef="USD" scale="9">$51.2</ix:nonfraction> billion.</p>
      <xbrli:context id="C1"><xbrli:entity><xbrli:identifier scheme="test">X</xbrli:identifier>
      </xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant>
      </xbrli:period></xbrli:context></body></html>
    """
    path = tmp_path / "inline.htm"
    path.write_text(html, encoding="utf-8")
    document = adapt_html_document(
        path=path,
        metadata=DocumentMetadata(
            entity="TEST",
            source_kind="SEC_10K",
            document_kind="ANNUAL_REPORT",
            available_at="2026-02-01",
            report_period="2025",
        ),
        expected_sha256=sha256(path.read_bytes()).hexdigest(),
        source_uri="test://inline",
        include_tables=False,
        include_inline_facts=True,
    )
    result = extract_text_kpis(document)
    assert len(document.inline_facts) == 1
    assert result.frames[0].extraction_method is ExtractionMethod.INLINE_XBRL

    block = next(block for block in document_text_blocks(document) if "backlog" in block.text.casefold())
    proposal = replace(
        result.frames[0],
        extraction_method=ExtractionMethod.LLM,
        verification_status=VerificationStatus.PROPOSED,
        verified_by=None,
    )
    verified = verify_llm_frame(proposal, block)
    assert not hasattr(verified, "reason")
    assert verified.verification_status is VerificationStatus.VERIFIED
    assert verified.authority is AuthorityLevel.RESEARCH_DIAGNOSTIC
    rejected = verify_llm_frame(
        replace(
            proposal,
            source_span=SourceSpan(None, block.char_start, block.char_end, "hallucinated"),
        ),
        block,
    )
    assert rejected.status == "REVIEW_LLM_SOURCE_SPAN_MISMATCH"


def test_cat_five_year_semantic_frames_match_frozen_parser() -> None:
    sources = load_cat_10k_sources(
        PROJECT_ROOT,
        PROJECT_ROOT / "configs/industrials_v1_1_cat_10k_sources.csv",
        pd.Timestamp("2026-09-03"),
    )
    frozen = build_cat_backlog_history(sources).set_index("fiscal_year")
    assert len(sources) == 5
    for _, source in sources.iterrows():
        fiscal_year = int(source["fiscal_year"])
        semantic = parse_cat_backlog_semantic_ir(source)
        expected = frozen.loc[fiscal_year]
        assert semantic.current.value == expected["firm_backlog_usd"]
        assert semantic.prior.value == expected["prior_year_firm_backlog_usd"]
        assert semantic.not_expected_next_year.value == expected["not_expected_next_year_usd"]
        assert semantic.expected_within_next_year.value == pytest.approx(
            expected["expected_within_next_year_usd"], abs=0.01
        )
