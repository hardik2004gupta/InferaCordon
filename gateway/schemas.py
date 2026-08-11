"""
Pydantic request/response schemas for the InferaCordon public API.

Per CLAUDE.md Section 7 — exact field list is authoritative.
Internal implementation objects (Policy, BudgetDecision, etc.) must NEVER
be leaked to the client. This module forms the public API boundary.

File justified per CLAUDE.md Section 31 precedent: Part IX abbreviated
listing omits files for essential documented functionality.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Request schema (CLAUDE.md Section 7.1) ────────────────────────────────────

class InferRequest(BaseModel):
    """
    Request body for POST /v1/infer.
    Per CLAUDE.md Section 7.1 request contract.
    """
    prompt: str = Field(
        min_length=1,
        max_length=32768,  # max_prompt_tokens * ~4 chars/token safety ceiling
        description="The user prompt to process.",
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description=(
            "Tenant identifier — redundant with API key but required for audit. "
            "If omitted, resolved from the Bearer token."
        ),
    )
    domain: str = Field(
        default="general_qa",
        description="Request domain. Maps to policy selection.",
    )
    response_schema: Optional[dict] = Field(
        default=None,
        description="Optional JSON Schema. When present, triggers JSON verification.",
    )
    budget_override: Optional[Literal["low", "medium", "high", "critical"]] = Field(
        default=None,
        description="Client-supplied budget class override. Capped at policy ceiling.",
    )
    stream: bool = Field(
        default=False,
        description="Streaming is not implemented in Phase 4. Reserved.",
    )


# ── Response schema (CLAUDE.md Section 7.1) ───────────────────────────────────

class InferResponse(BaseModel):
    """
    Response body for POST /v1/infer.
    Per CLAUDE.md Section 7.1 response contract.
    All numeric values in their documented types.
    """
    response: str
    request_id: str
    budget_class: str
    reasoning_tokens_used: int
    reasoning_tokens_allocated: int
    stop_reason: str
    verification_result: str = "skipped"   # Phase 5: populated by verifier
    escalation_count: int = 0              # Phase 5: populated by escalation handler
    estimated_cost_usd: float
    confidence_level: str = "high"         # Phase 5: "low" after failed escalation
    latency_ms: int

    # Governance metadata (not in CLAUDE.md 7.1 but required for auditability)
    policy_id: str
    policy_version: int
    policy_fallback_used: bool = False     # True when Failure Mode 7 triggered


# ── Health / Readiness schemas ─────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response for GET /v1/health (CLAUDE.md Section 7.2)."""
    status: str = "ok"
    version: str = "0.1.0"


class ReadinessResponse(BaseModel):
    """Response for GET /v1/readiness — reflects startup completion."""
    ready: bool
    policy_count: int
    vllm_url: str
    reason: Optional[str] = None          # Populated when ready=False


# ── Error schemas ──────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Structured error body — never expose raw stack traces or internal paths."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
    retry_after_seconds: Optional[int] = None  # Populated on 429
