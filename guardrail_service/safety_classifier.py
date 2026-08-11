"""
Safety classifier using Llama Guard ONNX model.

Production path: Llama Guard 3-1B ONNX, ~80-120ms CPU.
Dev / fallback path: keyword heuristic for obvious harm categories, <1ms, deterministic.

Per CLAUDE.md Section 14.3:
- Model file: models/llamaguard_onnx_v1.onnx (Docker volume in production)
- Used for both input safety check and output safety check
- Output: category string ("safe" or named harm category), confidence float
- model_version: "llamaguard_onnx_v1" (ONNX) or "heuristic_safety_v1" (fallback)

Design note: heuristic is deliberately conservative — only matches unambiguous harm
phrasing. False negatives (missed harm) are accepted; false positives block legitimate
requests. The heuristic covers the most safety-critical categories.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_MODEL_VERSION_ONNX = "llamaguard_onnx_v1"
_MODEL_VERSION_HEURISTIC = "heuristic_safety_v1"

# Harm categories and their keyword patterns (heuristic path only).
# Each pattern is matched case-insensitively against the full text.
# First matching category wins.
_HARM_PATTERNS: list[tuple[str, list[str]]] = [
    ("CHILD_SAFETY", [
        "child pornography",
        "csam",
        "sexual content involving minor",
        "lolita content",
    ]),
    ("SELF_HARM", [
        "how to kill myself",
        "how do i kill myself",
        "suicide methods",
        "ways to commit suicide",
        "how to end my life",
        "self harm methods",
        "how to cut myself",
        "lethal dose of",
        "how to overdose on",
    ]),
    ("VIOLENCE", [
        "how to make a bomb",
        "how to build a bomb",
        "step by step bomb",
        "how to poison someone",
        "how to kill a person",
        "detailed instructions to kill",
        "how to strangle",
        "attack plan for",
    ]),
    ("ILLEGAL_WEAPONS", [
        "how to make a gun without",
        "3d print untraceable",
        "convert semi to full auto",
        "how to build an explosive",
        "pipe bomb instructions",
    ]),
    ("MALWARE", [
        "write ransomware",
        "create malware code",
        "deploy a trojan",
        "create a keylogger",
        "botnet control code",
        "write a rootkit",
    ]),
]

# Pre-compile all patterns
_COMPILED_HARM: list[tuple[str, list[re.Pattern[str]]]] = [
    (category, [re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords])
    for category, keywords in _HARM_PATTERNS
]


@dataclass
class SafetyResult:
    category: str     # "safe" or a harm category name from _HARM_PATTERNS
    confidence: float
    model_version: str
    latency_ms: float

    @property
    def is_safe(self) -> bool:
        return self.category == "safe"


class SafetyClassifier:
    """
    Safety classifier with ONNX primary path and keyword heuristic fallback.
    Used for both input and output safety checks per CLAUDE.md Section 14.3-14.5.
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
                log.info("SafetyClassifier: ONNX model loaded from %s", model_path)
            except Exception as exc:
                log.warning(
                    "SafetyClassifier: ONNX load failed (%s) — heuristic fallback active",
                    exc,
                )
        else:
            log.info(
                "SafetyClassifier: model not found at %r — heuristic fallback active",
                model_path,
            )

    @property
    def model_version(self) -> str:
        return _MODEL_VERSION_ONNX if self._onnx_active else _MODEL_VERSION_HEURISTIC

    def classify(self, text: str) -> SafetyResult:
        t0 = time.perf_counter()
        result = self._classify_onnx(text) if self._onnx_active else self._classify_heuristic(text)
        result.latency_ms = (time.perf_counter() - t0) * 1000.0
        return result

    def _classify_onnx(self, text: str) -> SafetyResult:
        """
        Llama Guard 3-1B ONNX inference path.
        Falls back to heuristic on any runtime error.
        Only reached when self._session is not None.
        """
        try:
            from transformers import AutoTokenizer  # type: ignore[import]

            tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-Guard-3-1B")
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

            # Binary classification: outputs[0] shape (1, 2) [safe_logit, unsafe_logit]
            import numpy as np  # type: ignore[import]

            logits = outputs[0][0]
            exp_logits = np.exp(logits - logits.max())
            probs = exp_logits / exp_logits.sum()
            safe_prob = float(probs[0])

            if safe_prob >= 0.5:
                return SafetyResult(
                    category="safe",
                    confidence=safe_prob,
                    model_version=_MODEL_VERSION_ONNX,
                    latency_ms=0.0,
                )
            return SafetyResult(
                category="UNSAFE",
                confidence=1.0 - safe_prob,
                model_version=_MODEL_VERSION_ONNX,
                latency_ms=0.0,
            )
        except Exception as exc:
            log.error(
                "SafetyClassifier ONNX inference failed: %s — falling back to heuristic",
                exc,
            )
            return self._classify_heuristic(text)

    def _classify_heuristic(self, text: str) -> SafetyResult:
        """
        Keyword heuristic. First matching category wins with high confidence.
        If nothing matches, returns safe. Deterministic, <1ms.
        """
        for category, patterns in _COMPILED_HARM:
            for pattern in patterns:
                if pattern.search(text):
                    return SafetyResult(
                        category=category,
                        confidence=0.95,
                        model_version=_MODEL_VERSION_HEURISTIC,
                        latency_ms=0.0,
                    )
        return SafetyResult(
            category="safe",
            confidence=0.98,
            model_version=_MODEL_VERSION_HEURISTIC,
            latency_ms=0.0,
        )
