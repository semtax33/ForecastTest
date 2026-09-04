from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie import (
    SpacySemanticBackend,
    TextDslCompileError,
    compile_text_rules,
    extract_text_kpis,
    match_sequence_pattern,
)
from equity_platform.text_ie.ontology import find_concepts
from equity_platform.text_ie.quantities import extract_quantities


def _rule(max_gap: int = 4):
    return compile_text_rules(
        f'''
        var "METRIC" {{ expression = {{"concept": "*"}} }}
        var "CHANGE" {{ expression = {{"any": [{{"lemma": "increase"}}, {{"lemma": "grow"}}]}} }}
        var "VALUE" {{ expression = {{"quantity": "MONEY"}} }}
        text_rule "law.change_to" {{
          version = 1
          frame = "CHANGE_TO"
          triggers = ["increased", "grew"]
          pattern = [
            {{"label":"metric","var":"METRIC"}},
            {{"label":"trigger","var":"CHANGE","max_gap":{max_gap}}},
            {{"label":"value","var":"VALUE","max_gap":{max_gap}}}
          ]
          backends = ["SEQUENCE", "DEPENDENCY"]
          operations = ["bind_labeled_roles", "require_same_clause", "require_dependency_path", "emit_frame"]
        }}
        '''
    )[0]


def _match(text: str, *, max_gap: int = 4):
    backend = SpacySemanticBackend()
    result = backend.match_pattern(
        _rule(max_gap),
        text,
        find_concepts(text),
        extract_quantities(text),
    )
    return backend, result


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://semantic-law",
                "SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            entity="TEST",
            source_kind="TEST",
            document_kind="TEXT_IE",
            available_at="2026-09-04",
            report_period="2025",
        ),
    )


def test_hmrb_style_labels_are_preserved_by_spacy_matcher() -> None:
    backend, matched = _match("Revenue increased to $4.2 billion.")
    assert matched is not None
    assert [span.label for span in matched] == ["metric", "trigger", "value"]
    assert matched[0].value == "REVENUE"
    assert "SPACY_MATCHER" in backend.last_match_trace
    assert "SPACY_DEPENDENCY_MATCHER" in backend.last_match_trace


def test_max_gap_and_clause_boundary_fail_closed() -> None:
    _, distant = _match(
        "Revenue, after a long discussion of unrelated strategy and market conditions, "
        "increased to $4.2 billion.",
        max_gap=2,
    )
    assert distant is None
    _, cross_clause = _match("Revenue improved; costs increased to $4.2 billion.")
    assert cross_clause is None


def test_dsl_rejects_unregistered_callback_but_accepts_pure_operations() -> None:
    assert _rule().operations == (
        "bind_labeled_roles",
        "require_same_clause",
        "require_dependency_path",
        "emit_frame",
    )


def test_runtime_consumes_labeled_roles_without_cross_clause_quantity_leakage() -> None:
    result = extract_text_kpis(
        _document("Backlog was $10 billion; Revenue increased to $4.2 billion."),
        backend=SpacySemanticBackend(),
    )
    assert [(frame.concept, frame.value) for frame in result.frames] == [
        ("REVENUE", 4_200_000_000.0)
    ]
    assert result.frames[0].context_trace["matcher_trace"] == [
        "SPACY_MATCHER",
        "SPACY_DEPENDENCY_MATCHER",
    ]


def test_runtime_keeps_same_clause_conjunction_ambiguous() -> None:
    result = extract_text_kpis(
        _document("Revenue and backlog increased 12% to $4.2 billion."),
        backend=SpacySemanticBackend(),
    )
    assert not result.frames
    assert result.reviews


def test_backend_neutral_fallback_honors_same_gap_and_clause_contract() -> None:
    rule = compile_text_rules(
        '''
        var "METRIC" { expression = {"concept": "*"} }
        var "TRIGGER" { expression = {"lower": "increased"} }
        var "VALUE" { expression = {"quantity": "MONEY"} }
        text_rule "fallback.change" {
          version = 1
          frame = "CHANGE_TO"
          triggers = ["increased"]
          pattern = [
            {"label":"metric","var":"METRIC"},
            {"label":"trigger","var":"TRIGGER","max_gap":2},
            {"label":"value","var":"VALUE","max_gap":2}
          ]
          operations = ["require_same_clause", "emit_frame"]
        }
        '''
    )[0]
    text = "Revenue increased to $4.2 billion."
    assert match_sequence_pattern(
        rule,
        text,
        find_concepts(text),
        extract_quantities(text),
    )
    cross_clause = "Revenue improved; costs increased to $4.2 billion."
    assert match_sequence_pattern(
        rule,
        cross_clause,
        find_concepts(cross_clause),
        extract_quantities(cross_clause),
    ) is None


def test_dsl_rejects_invalid_gap_and_arbitrary_callback() -> None:
    invalid = '''
    var "METRIC" { expression = {"concept": "*"} }
    text_rule "bad.gap" {
      version = 1
      frame = "ABSOLUTE_VALUE"
      triggers = ["was"]
      pattern = [{"label":"metric","var":"METRIC","max_gap":-1}]
    }
    '''
    import pytest

    with pytest.raises(TextDslCompileError, match="max_gap"):
        compile_text_rules(invalid)
    with pytest.raises(TextDslCompileError, match="Unregistered operation"):
        compile_text_rules(
            invalid.replace('"max_gap":-1', '"max_gap":1').replace(
                'pattern = [{"label":"metric","var":"METRIC","max_gap":1}]',
                'pattern = [{"label":"metric","var":"METRIC","max_gap":1}]\n'
                'operations = ["issuer_specific_callback"]',
            )
        )
