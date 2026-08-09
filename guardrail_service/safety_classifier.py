"""
Safety classifier using LlamaGuard ONNX model.

Per CLAUDE.md Section 14 (guardrail_version: llamaguard_onnx_v1):
- ONNX Runtime inference (CPU, <100ms target)
- Model file: models/llamaguard_onnx_v1.onnx
- Categories: unsafe content, hate speech, self-harm, etc.
- Returns: safe (bool), categories_flagged (list), probability (float)
- Applied to both input (safety_check) and output (output_safety)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyResult:
    safe: bool
    categories_flagged: list[str]
    probability: float
    latency_ms: float


class SafetyClassifier:
    """LlamaGuard ONNX safety classifier."""

    def __init__(self, model_path: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")

    def classify(self, text: str) -> SafetyResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")
