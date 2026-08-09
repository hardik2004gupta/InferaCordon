"""
HTTP client for the verifier microservice.

Per CLAUDE.md Section 15:
- POST http://verifier:8002/v1/verify
- Verifier types: gsm8k (numeric answer extraction), math (SymPy), humaneval (sandboxed exec), schema (JSON Schema)
- Returns: correct / incorrect / unverifiable
- Required for budget classes: required (high/critical), verifiable_only (medium)
- Propagates W3C traceparent
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class VerificationResult(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNVERIFIABLE = "unverifiable"


@dataclass
class VerifierResponse:
    result: VerificationResult
    verifier_type: str
    latency_ms: float
    verifier_version: str


class VerifierClient:
    """Async HTTP client for verifier service."""

    def __init__(self, base_url: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")

    async def verify(
        self,
        domain: str,
        prompt: str,
        response: str,
        verification_level: str,
        traceparent: Optional[str],
    ) -> VerifierResponse:
        raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")
