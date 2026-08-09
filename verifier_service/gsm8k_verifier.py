"""
GSM8K verifier: numeric answer extraction from reasoning model output.

Per CLAUDE.md Section 15:
- Extract final numeric answer from response (pattern: "#### N")
- Compare against ground-truth answer (from dataset record)
- Result: correct / incorrect / unverifiable (if extraction fails)
- Used for: evaluation benchmark on GSM8K dataset (CLAUDE.md Section 20)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GSM8KResult:
    result: str           # "correct" | "incorrect" | "unverifiable"
    extracted_answer: str | None
    expected_answer: str | None
    latency_ms: float


class GSM8KVerifier:
    def verify(self, response: str, expected_answer: str | None = None) -> GSM8KResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")
