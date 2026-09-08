from .fallback import LLMTextIEBackend, verify_llm_frame
from .encoder_registry import (
    DEFAULT_ENCODER_CANDIDATES,
    EncoderBenchmarkCell,
    EncoderCandidate,
    EncoderSourceSlice,
    build_encoder_benchmark_matrix,
)
from .transformer_backend import (
    TransformerDevice,
    TransformerDevicePolicy,
    TransformerSemanticBackend,
    TransformerUnavailableError,
    resolve_transformer_device,
)
from .routing import (
    LLMFallbackDecision,
    LLMFallbackPolicy,
    LLMFallbackSignals,
    LLMFallbackTier,
)

__all__ = [
    "LLMTextIEBackend",
    "LLMFallbackDecision",
    "LLMFallbackPolicy",
    "LLMFallbackSignals",
    "LLMFallbackTier",
    "DEFAULT_ENCODER_CANDIDATES",
    "EncoderBenchmarkCell",
    "EncoderCandidate",
    "EncoderSourceSlice",
    "TransformerDevice",
    "TransformerDevicePolicy",
    "TransformerSemanticBackend",
    "TransformerUnavailableError",
    "resolve_transformer_device",
    "build_encoder_benchmark_matrix",
    "verify_llm_frame",
]
