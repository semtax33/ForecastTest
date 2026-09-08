from __future__ import annotations

from types import SimpleNamespace

import pytest

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.document import document_text_blocks
from equity_platform.text_ie.learned import HfTokenSpanBackend, LearnedSpanUnavailableError
from equity_platform.text_ie.llm import EncoderSourceSlice, TransformerDevicePolicy


def _block(text: str):
    document = adapt_html_fragments(
        fragments=(HtmlFragment(
            f"<p>{text}</p>".encode(),
            "test://hf-span",
            "HF-SPAN",
            numeric_rows_only=False,
        ),),
        metadata=DocumentMetadata("TEST", "SEC", "10-Q", "2026-09-08", "2026Q2"),
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


class _Pipeline:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return self.rows


def test_hf_token_backend_is_lazy_local_only_and_cuda_required_by_default() -> None:
    factory_calls = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return _Pipeline([])

    backend = HfTokenSpanBackend(
        pipeline_factory=factory,
        torch_module=_Torch(),
    )

    assert backend.device == "cuda:pending"
    assert backend.local_files_only
    assert factory_calls == []

    assert backend.propose(_block("Revenue increased."), EncoderSourceSlice.SEC_10Q) == ()
    assert factory_calls[0]["device"] == "cuda"
    assert factory_calls[0]["local_files_only"] is True
    assert factory_calls[0]["aggregation_strategy"] == "none"


def test_hf_token_backend_accepts_no_bio_taxonomy_label_as_raw_span_only() -> None:
    text = "DRAM bit shipments increased approximately 17% year over year."
    start = text.index("DRAM bit shipments")
    pipeline = _Pipeline([
        {
            "entity_group": "us-gaap:SalesRevenueGoodsNet",
            "score": 0.93,
            "start": start,
            "end": start + len("DRAM bit shipments"),
            "word": "untrusted tokenizer rendering",
        },
        {"entity": "O", "score": 0.99, "start": 20, "end": 29},
    ])
    backend = HfTokenSpanBackend(
        pipeline_factory=lambda **kwargs: pipeline,
        torch_module=_Torch(),
    )

    proposals = backend.propose(_block(text), EncoderSourceSlice.SEC_10K)

    assert len(proposals) == 1
    assert proposals[0].raw_text == "DRAM bit shipments"
    assert proposals[0].raw_label == "us-gaap:SalesRevenueGoodsNet"
    assert proposals[0].canonical_concept is None
    assert proposals[0].confidence == 0.93


def test_local_checkpoint_path_is_separate_from_canonical_model_provenance() -> None:
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return _Pipeline([
            {"entity": "custom:metric", "score": 0.95, "start": 0, "end": 7},
        ])

    backend = HfTokenSpanBackend(
        checkpoint="D:/models/bert-sl1000/pinned-revision",
        model_id="AAU-NLP/BERT-SL1000",
        model_revision="abc123",
        pipeline_factory=factory,
        torch_module=_Torch(),
    )

    proposals = backend.propose(_block("Revenue increased."), EncoderSourceSlice.SEC_10Q)

    assert calls[0]["checkpoint"] == "D:/models/bert-sl1000/pinned-revision"
    assert proposals[0].model_id == "AAU-NLP/BERT-SL1000"
    assert proposals[0].model_revision == "abc123"


def test_sec_token_backend_refuses_ir_source_slice() -> None:
    backend = HfTokenSpanBackend(
        pipeline_factory=lambda **kwargs: _Pipeline([]),
        torch_module=_Torch(),
    )

    with pytest.raises(LearnedSpanUnavailableError, match="SEC_10K/SEC_10Q"):
        backend.propose(_block("Revenue increased."), EncoderSourceSlice.IR_QA)


def test_no_bio_wordpieces_are_grouped_by_exact_source_offsets() -> None:
    text = "DRAM bit shipments increased 17%."
    label = "custom:dramShipment"
    pipeline = _Pipeline([
        {"entity": label, "score": 0.98, "start": 0, "end": 4},
        {"entity": label, "score": 0.96, "start": 5, "end": 8},
        {"entity": label, "score": 0.97, "start": 9, "end": 18},
    ])
    backend = HfTokenSpanBackend(
        pipeline_factory=lambda **kwargs: pipeline,
        torch_module=_Torch(),
    )

    proposals = backend.propose(_block(text), EncoderSourceSlice.SEC_10Q)

    assert [(item.raw_text, item.confidence) for item in proposals] == [
        ("DRAM bit shipments", 0.96),
    ]


def test_hf_token_backend_never_silently_downloads_missing_model() -> None:
    def factory(**kwargs):
        assert kwargs["local_files_only"] is True
        raise OSError("model not in local cache")

    backend = HfTokenSpanBackend(
        pipeline_factory=factory,
        torch_module=_Torch(),
    )

    with pytest.raises(LearnedSpanUnavailableError, match="model not in local cache"):
        backend.propose(_block("Revenue increased."), EncoderSourceSlice.SEC_10Q)


def test_malformed_model_output_fails_closed() -> None:
    backend = HfTokenSpanBackend(
        pipeline_factory=lambda **kwargs: _Pipeline([
            {"entity": "KPI", "score": 0.99},
        ]),
        torch_module=_Torch(),
    )

    with pytest.raises(LearnedSpanUnavailableError, match="malformed"):
        backend.propose(_block("Revenue increased."), EncoderSourceSlice.SEC_10Q)


def test_cpu_execution_requires_an_explicit_test_policy() -> None:
    backend = HfTokenSpanBackend(
        pipeline_factory=lambda **kwargs: _Pipeline([]),
        device_policy=TransformerDevicePolicy.CPU_TEST_ONLY,
        torch_module=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    assert backend.propose(_block("Revenue increased."), EncoderSourceSlice.SEC_10Q) == ()
    assert backend.device == "cpu"
