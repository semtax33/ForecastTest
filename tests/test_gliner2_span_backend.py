from __future__ import annotations

from io import StringIO
import sys
from types import SimpleNamespace

import pytest

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.document import document_text_blocks
from equity_platform.text_ie.learned import GLiNER2SpanBackend, LearnedSpanUnavailableError
from equity_platform.text_ie.llm import EncoderSourceSlice, TransformerDevicePolicy


def _block(text: str):
    document = adapt_html_fragments(
        fragments=(HtmlFragment(
            f"<p>{text}</p>".encode(),
            "test://gliner2-span",
            "GLINER2-SPAN",
            numeric_rows_only=False,
        ),),
        metadata=DocumentMetadata("TEST", "IR", "CALL", "2026-09-08", "2026Q2"),
    )
    return document_text_blocks(document)[0]


class _Cuda:
    @staticmethod
    def is_available():
        return True

    @staticmethod
    def get_device_name(index):
        assert index == 0
        return "TEST GPU"


class _Torch:
    cuda = _Cuda()


class _Extractor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def extract_entities(self, text, entity_types, **kwargs):
        self.calls.append((text, entity_types, kwargs))
        return self.result

    def to(self, device):
        return self

    def eval(self):
        return self


def test_gliner2_is_lazy_local_only_and_cuda_required() -> None:
    factory_calls = []
    extractor = _Extractor({"entities": {"financial_kpi": []}})

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return extractor

    backend = GLiNER2SpanBackend(
        extractor_factory=factory,
        torch_module=_Torch(),
    )

    assert backend.device == "cuda:pending"
    assert backend.local_files_only
    assert factory_calls == []

    assert backend.propose(
        _block("HBM revenue increased."),
        EncoderSourceSlice.IR_PREPARED_REMARKS,
    ) == ()
    assert factory_calls[0]["device"] == "cuda"
    assert factory_calls[0]["local_files_only"] is True
    assert extractor.calls[0][2] == {
        "threshold": 0.50,
        "format_results": True,
        "include_confidence": True,
        "include_spans": True,
    }


def test_gliner2_returns_exact_ir_metric_spans_without_canonical_authority() -> None:
    text = "HBM3E revenue mix should reach 18% by year end."
    literal = "HBM3E revenue mix"
    extractor = _Extractor({
        "entities": {
            "financial_kpi": [{
                "text": literal,
                "confidence": 0.94,
                "start": 0,
                "end": len(literal),
            }],
        },
    })
    backend = GLiNER2SpanBackend(
        extractor_factory=lambda **kwargs: extractor,
        torch_module=_Torch(),
    )

    proposals = backend.propose(_block(text), EncoderSourceSlice.IR_QA)

    assert len(proposals) == 1
    assert proposals[0].raw_text == literal
    assert proposals[0].raw_label == "financial_kpi"
    assert proposals[0].canonical_concept is None
    assert proposals[0].confidence == 0.94


def test_gliner2_refuses_sec_source_slice() -> None:
    backend = GLiNER2SpanBackend(
        extractor_factory=lambda **kwargs: _Extractor({"entities": {}}),
        torch_module=_Torch(),
    )

    with pytest.raises(LearnedSpanUnavailableError, match="IR_PREPARED_REMARKS/IR_QA"):
        backend.propose(_block("Revenue increased."), EncoderSourceSlice.SEC_10Q)


def test_gliner2_missing_offsets_fail_closed_instead_of_literal_search() -> None:
    extractor = _Extractor({
        "entities": {
            "financial_kpi": [{"text": "revenue mix", "confidence": 0.99}],
        },
    })
    backend = GLiNER2SpanBackend(
        extractor_factory=lambda **kwargs: extractor,
        torch_module=_Torch(),
    )

    with pytest.raises(LearnedSpanUnavailableError, match="exact offsets"):
        backend.propose(
            _block("Revenue mix increased."),
            EncoderSourceSlice.IR_PREPARED_REMARKS,
        )


def test_gliner2_cpu_requires_explicit_test_policy() -> None:
    backend = GLiNER2SpanBackend(
        extractor_factory=lambda **kwargs: _Extractor({"entities": {}}),
        device_policy=TransformerDevicePolicy.CPU_TEST_ONLY,
        torch_module=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    assert backend.propose(
        _block("Revenue mix increased."),
        EncoderSourceSlice.IR_QA,
    ) == ()
    assert backend.device == "cpu"


def test_gliner2_initialization_isolated_from_windows_cp949_console(monkeypatch) -> None:
    extractor = _Extractor({"entities": {"financial_kpi": []}})

    class _AutoExtractor:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            if not isinstance(sys.stdout, StringIO):
                raise UnicodeEncodeError("cp949", "U0001f9e0", 0, 1, "illegal multibyte sequence")
            print("U0001f9e0 Model Configuration")
            return extractor

    monkeypatch.setattr(
        "equity_platform.text_ie.learned.gliner2_backend.import_module",
        lambda name: SimpleNamespace(AutoExtractor=_AutoExtractor),
    )
    backend = GLiNER2SpanBackend(torch_module=_Torch())

    assert backend.propose(
        _block("Revenue increased."),
        EncoderSourceSlice.IR_PREPARED_REMARKS,
    ) == ()
