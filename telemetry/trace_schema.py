"""
RequestTrace dataclass — canonical trace schema for all InferaCordon requests.

Per CLAUDE.md Section 18. All fields defined here are authoritative.
Every field that appears in the audit log, Grafana dashboard, or Jaeger
trace is sourced from a RequestTrace instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestTrace:
    # ── Identity ─────────────────────────────────────────────────────────────
    request_id: str                        # UUID v4
    traceparent: Optional[str]             # W3C traceparent propagated to all services
    tenant_id: str
    domain: str
    timestamp_iso: str                     # ISO 8601, gateway ingress

    # ── Policy ───────────────────────────────────────────────────────────────
    policy_id: str
    policy_version: int
    prompt_version: str
    complexity_scorer_version: str
    guardrail_model_version: str
    injection_model_version: str
    verifier_version: str

    # ── Complexity + Budget ──────────────────────────────────────────────────
    complexity_score: float                # 0.0–10.0
    fast_path_used: bool                   # True if cache hit short-circuited pipeline
    base_budget_class: str                 # From complexity threshold mapping
    effective_budget_class: str            # After GPU pressure override (may differ)
    downgrade_reason: Optional[str]        # "gpu_pressure_downgrade" or None
    priority_tier: str                     # "standard" | "priority"
    max_reasoning_tokens: int              # Per effective budget class
    max_output_tokens: int

    # ── Routing ──────────────────────────────────────────────────────────────
    route: str                             # "cheap_model" | "reasoning_model"
    model_version: str                     # "deepseek-r1-7b-q4" | "qwen25-3b"

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_hit: bool
    cache_similarity: Optional[float]      # Cosine similarity if hit
    cache_stored: bool                     # True if response was stored after serving

    # ── Guardrail ─────────────────────────────────────────────────────────────
    admission_result: str                  # "pass" | "block"
    guardrail_input_decision: str          # "pass" | "block" | "degraded"
    guardrail_output_result: Optional[str] # "pass" | "block" | "degraded" | None

    # ── Inference ─────────────────────────────────────────────────────────────
    actual_reasoning_tokens: int
    actual_output_tokens: int
    ttft_ms: float                         # Time to first token
    total_latency_ms: float
    finish_reason: str                     # "stop" | "budget_ceiling" | "length"

    # ── Verification ─────────────────────────────────────────────────────────
    verification_result: Optional[str]     # "correct" | "incorrect" | "unverifiable" | None
    escalation_count: int                  # Number of budget escalations

    # ── Cost ─────────────────────────────────────────────────────────────────
    estimated_cost_usd: float
    actual_cost_usd: float

    # ── Quality ──────────────────────────────────────────────────────────────
    quality_score: Optional[float]         # LLM judge score (1-5), populated async
