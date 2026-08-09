"""
HTTP client for the guardrail microservice.

Per CLAUDE.md Section 14:
- POST http://guardrail:8001/v1/check (input check)
- POST http://guardrail:8001/v1/check-output (async output check)
- Hard timeout: 200ms (CLAUDE.md Section 14 — asymmetric failure)
- On timeout for INPUT check: BLOCK the request (safe-fail closed)
- On timeout for OUTPUT check: PASS and log degraded (safe-fail open for output)
- Propagates W3C traceparent
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GuardrailDecision(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    DEGRADED = "degraded"


@dataclass
class GuardrailResult:
    decision: GuardrailDecision
    reasons: list[str]
    latency_ms: float
    model_versions: dict[str, str]


class GuardrailClient:
    """Async HTTP client for guardrail service with strict 200ms timeout."""

    def __init__(self, base_url: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")

    async def check_input(self, prompt: str, tenant_id: str, traceparent: Optional[str]) -> GuardrailResult:
        """Check input. Times out at 200ms → BLOCK on timeout."""
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")

    async def check_output(self, response: str, tenant_id: str, traceparent: Optional[str]) -> GuardrailResult:
        """Check output asynchronously. Times out at 200ms → DEGRADED on timeout."""
        raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")
