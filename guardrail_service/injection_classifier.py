"""
Prompt injection classifier for the InferaCordon guardrail service.

Production path: DeBERTa-v3-small ONNX (int8), ~30-50ms CPU.
Dev / fallback path: weighted keyword heuristic, <1ms, deterministic.

Per CLAUDE.md Section 14.3:
- Model file: models/deberta_inject_v1.onnx (Docker volume in production)
- Output: injection_probability float 0.0-1.0
- Threshold: passed per-request from gateway; NOT hard-coded here
- model_version: "deberta_inject_v1" (ONNX) or "heuristic_inject_v1" (fallback)
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_MODEL_VERSION_ONNX = "deberta_inject_v1"
_MODEL_VERSION_HEURISTIC = "heuristic_inject_v1"

# Weighted patterns (phrase → max_probability_contribution).
# Uses max(matched weights), NOT sum — avoids false positives from partial matches.
_INJECTION_PATTERNS: list[tuple[str, float]] = [
    ("ignore previous instructions", 0.95),
    ("ignore all previous", 0.90),
    ("disregard your instructions", 0.90),
    ("disregard the previous", 0.85),
    ("forget your instructions", 0.90),
    ("forget everything i said", 0.85),
    ("override your instructions", 0.90),
    ("your new instructions are", 0.85),
    ("you have no restrictions", 0.85),
    ("ignore what you were told", 0.85),
    ("jailbreak", 0.82),
    ("bypass safety", 0.82),
    ("bypass filter", 0.78),
    ("bypass your", 0.70),
    ("override safety", 0.82),
    ("disable safety", 0.82),
    ("do anything now", 0.80),
    ("dan mode", 0.85),
    ("developer mode enabled", 0.76),
    ("god mode", 0.72),
    ("sudo mode", 0.72),
    ("unrestricted mode", 0.80),
    ("prompt injection", 0.75),
    ("reveal your system prompt", 0.80),
    ("print your instructions", 0.76),
    ("your real instructions", 0.76),
    ("system: you are", 0.70),
    ("pretend you are", 0.55),
    ("pretend to be", 0.55),
    ("act as if you", 0.55),
    ("roleplay as", 0.50),
    ("you are now in", 0.60),
]

# Pre-compiled for speed — called on every guardrail request
_COMPILED: list[tuple[re.Pattern[str], float]] = [
    (re.compile(re.escape(phrase), re.IGNORECASE), weight)
    for phrase, weight in _INJECTION_PATTERNS
]


@dataclass
class InjectionResult:
    injection_probability: float
    model_version: str
    latency_ms: float


class InjectionClassifier:
    """
    Injection classifier with ONNX primary path and keyword heuristic fallback.

    The ONNX path requires the model file AND onnxruntime installed.
    In dev environments without those, the heuristic path is used automatically.
    The switch is transparent — model_version field indicates which is active.
    """

    def __init__(self, model_path: str) -> None:
        self._model_path = model_path
        self._session = None
        self._onnx_active = False

        if Path(model_path).exists():
            try:
                import onnxruntime as ort  # type: ignore[import]

                self._session = ort.InferenceSession(
                    model_path,
                    providers=["CPUExecutionProvider"],
                )
                self._onnx_active = True
                log.info("InjectionClassifier: ONNX model loaded from %s", model_path)
            except Exception as exc:
                log.warning(
                    "InjectionClassifier: ONNX load failed (%s) — heuristic fallback active",
                    exc,
                )
        else:
            log.info(
                "InjectionClassifier: model not found at %r — heuristic fallback active",
                model_path,
            )

    @property
    def model_version(self) -> str:
        return _MODEL_VERSION_ONNX if self._onnx_active else _MODEL_VERSION_HEURISTIC

    def classify(self, text: str) -> InjectionResult:
        t0 = time.perf_counter()
        prob = self._classify_onnx(text) if self._onnx_active else self._classify_heuristic(text)
        return InjectionResult(
            injection_probability=prob,
            model_version=self.model_version,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def _classify_onnx(self, text: str) -> float:
        """
        DeBERTa-v3-small ONNX inference path.
        Truncates to 512 tokens. Returns injection probability (softmax pos class).
        Only reached when self._session is not None.
        Falls back to heuristic on any runtime error.
        """
        try:
            from transformers import AutoTokenizer  # type: ignore[import]

            tokenizer = AutoTokenizer.from_pretrained("microsoft/deberta-v3-small")
            inputs = tokenizer(
                text,
                return_tensors="np",
                max_length=512,
                truncation=True,
                padding=True,
            )
            input_names = {inp.name for inp in self._session.get_inputs()}
            feed = {k: v for k, v in inputs.items() if k in input_names}
            outputs = self._session.run(None, feed)

            # Binary classification: outputs[0] shape (1, 2) [neg_logit, pos_logit]
            import numpy as np  # type: ignore[import]

            logits = outputs[0][0]
            exp_logits = np.exp(logits - logits.max())
            return float(exp_logits[1] / exp_logits.sum())
        except Exception as exc:
            log.error(
                "InjectionClassifier ONNX inference failed: %s — falling back to heuristic",
                exc,
            )
            return self._classify_heuristic(text)

    def _classify_heuristic(self, text: str) -> float:
        """
        Keyword heuristic. Returns max(matching pattern weights).
        Deterministic, <1ms, no external dependencies.
        """
        max_weight = 0.0
        for pattern, weight in _COMPILED:
            if pattern.search(text):
                max_weight = max(max_weight, weight)
        return max_weight
