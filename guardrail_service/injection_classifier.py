"""
Prompt injection classifier using DeBERTa ONNX model.

Per CLAUDE.md Section 14 (guardrail_version: deberta_inject_v1):
- ONNX Runtime inference (CPU, <50ms target)
- Model file: models/deberta_inject_v1.onnx
- Returns: injection_probability (float), decision (pass/block)
- Block threshold configurable via policy (injection_check: conditional)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InjectionResult:
    injection_probability: float
    decision: str    # "pass" or "block"
    latency_ms: float


class InjectionClassifier:
    """DeBERTa ONNX injection classifier."""

    def __init__(self, model_path: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")

    def classify(self, text: str) -> InjectionResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")
