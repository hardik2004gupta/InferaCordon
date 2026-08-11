"""
RequestTrace — canonical trace schema per CLAUDE.md §18.1.

Field names are AUTHORITATIVE. Every field must match §18.1 exactly.
No renaming, no omission, no addition of fields not in §18.1.
All OTel span attributes, audit record fields, and Grafana queries
source from a RequestTrace instance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class RequestTrace:
    # ── Identity (CLAUDE.md §18.1) ────────────────────────────────────────────
    request_id: str
    trace_id: str
    tenant_id: str
    domain: str

    # ── Governance (CLAUDE.md §18.1) ──────────────────────────────────────────
    policy_id: str
    policy_version: int
    model_version: str
    prompt_version: str
    guardrail_version: str
    verifier_version: str
    complexity_scorer_version: str

    # ── Decision (CLAUDE.md §18.1) ────────────────────────────────────────────
    complexity_score: float
    fast_path_used: bool
    base_budget_class: str
    effective_budget_class: str
    downgrade_reason: Optional[str]
    priority_tier: str
    max_reasoning_tokens: int
    route: str
    cache_hit: bool
    admission_decision: str

    # ── Execution (CLAUDE.md §18.1) ───────────────────────────────────────────
    reasoning_tokens_used: int
    output_tokens: int
    tokens_saved: int
    stop_reason: str
    escalation_count: int
    fallback_used: bool

    # ── Guardrails (CLAUDE.md §18.1) ──────────────────────────────────────────
    guardrail_input_result: str
    guardrail_input_ms: int
    guardrail_injection_score: float
    guardrail_output_result: str
    guardrail_output_ms: int

    # ── Verification (CLAUDE.md §18.1) ────────────────────────────────────────
    verification_result: str
    verification_type: str
    verification_ms: int

    # ── Latency breakdown (CLAUDE.md §18.1) ───────────────────────────────────
    queue_ms: int
    prefill_ms: int
    decode_ms: int
    ttft_ms: int
    e2e_latency_ms: int

    # ── Cost (CLAUDE.md §18.1) ────────────────────────────────────────────────
    estimated_cost_usd: float
    actual_cost_usd: float

    # ── Circuit breakers (CLAUDE.md §18.1) ───────────────────────────────────
    gpu_cb_state: str       # "open" | "closed"
    latency_cb_state: str   # "open" | "closed"

    # ── Entropy telemetry — every 10th value per §9.7 ─────────────────────────
    entropy_samples: list[float] = field(default_factory=list)

    # ── Serialization helpers ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Full serialization including entropy_samples."""
        return asdict(self)

    def to_otel_span_attributes(self) -> dict[str, str | int | float | bool]:
        """
        Flat attribute dict for OTel span.set_attributes().
        Scalar types only (OTel requirement).
        No raw prompt/response text — governance metadata only.
        """
        return {
            "ic.request_id": self.request_id,
            "ic.trace_id": self.trace_id,
            "ic.tenant_id": self.tenant_id,
            "ic.domain": self.domain,
            "ic.policy_id": self.policy_id,
            "ic.policy_version": self.policy_version,
            "ic.model_version": self.model_version,
            "ic.prompt_version": self.prompt_version,
            "ic.guardrail_version": self.guardrail_version,
            "ic.verifier_version": self.verifier_version,
            "ic.complexity_scorer_version": self.complexity_scorer_version,
            "ic.complexity_score": self.complexity_score,
            "ic.fast_path_used": self.fast_path_used,
            "ic.base_budget_class": self.base_budget_class,
            "ic.effective_budget_class": self.effective_budget_class,
            "ic.downgrade_reason": self.downgrade_reason or "",
            "ic.priority_tier": self.priority_tier,
            "ic.max_reasoning_tokens": self.max_reasoning_tokens,
            "ic.route": self.route,
            "ic.cache_hit": self.cache_hit,
            "ic.admission_decision": self.admission_decision,
            "ic.reasoning_tokens_used": self.reasoning_tokens_used,
            "ic.output_tokens": self.output_tokens,
            "ic.tokens_saved": self.tokens_saved,
            "ic.stop_reason": self.stop_reason,
            "ic.escalation_count": self.escalation_count,
            "ic.fallback_used": self.fallback_used,
            "ic.guardrail_input_result": self.guardrail_input_result,
            "ic.guardrail_input_ms": self.guardrail_input_ms,
            "ic.guardrail_injection_score": self.guardrail_injection_score,
            "ic.guardrail_output_result": self.guardrail_output_result,
            "ic.guardrail_output_ms": self.guardrail_output_ms,
            "ic.verification_result": self.verification_result,
            "ic.verification_type": self.verification_type,
            "ic.verification_ms": self.verification_ms,
            "ic.queue_ms": self.queue_ms,
            "ic.prefill_ms": self.prefill_ms,
            "ic.decode_ms": self.decode_ms,
            "ic.ttft_ms": self.ttft_ms,
            "ic.e2e_latency_ms": self.e2e_latency_ms,
            "ic.estimated_cost_usd": self.estimated_cost_usd,
            "ic.actual_cost_usd": self.actual_cost_usd,
            "ic.gpu_cb_state": self.gpu_cb_state,
            "ic.latency_cb_state": self.latency_cb_state,
        }
