"""
MATH-500 verifier: symbolic equivalence check using SymPy.

Per CLAUDE.md Section 15:
- Parse LaTeX expressions from response
- Use SymPy to check symbolic equivalence with expected answer
- Result: correct / incorrect / unverifiable (if SymPy parse fails)
- Used for: evaluation benchmark on MATH-500 dataset (CLAUDE.md Section 20)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MathResult:
    result: str           # "correct" | "incorrect" | "unverifiable"
    parsed_response: str | None
    expected: str | None
    latency_ms: float


class MathVerifier:
    def verify(self, response: str, expected: str | None = None) -> MathResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")
