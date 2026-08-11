"""
Budget controller: maps complexity score + policy + fleet state → BudgetDecision.

Per CLAUDE.md Section 12. The canonical pseudocode in Section 12.1 is reproduced
verbatim in assign_budget_class() below.

Key design principle (CLAUDE.md Section 12.2):
  Quality budget    ≠ scheduling priority
  Scheduling priority ≠ cost ceiling
  Cost ceiling      ≠ latency SLO

These are four independent policy concepts returned separately in BudgetDecision.

Priority tier derivation (CLAUDE.md Section 6 Step 6 + Section 32 Assumptions):
  low class     → priority_tier "low"    (cheap model; minimal resource demand)
  medium class  → priority_tier "standard"
  high class    → priority_tier "standard"
  critical class → priority_tier "high"  (highest-importance requests)

Route derivation (CLAUDE.md Section 8):
  low class    → route "cheap_model"     (Qwen2.5-3B-Instruct, 0 reasoning tokens)
  others       → route "reasoning_model" (DeepSeek-R1-7B-Q4)
"""
from __future__ import annotations

import dataclasses
import datetime
from typing import Optional

from policy_engine.validator import Policy

# ── Fleet state ───────────────────────────────────────────────────────────────

@dataclasses.dataclass
class FleetState:
    """
    Snapshot of vLLM fleet health.

    Per CLAUDE.md Section 12.1 canonical pseudocode field names:
      fleet_state.latency_cb_open
      fleet_state.gpu_pressure_cb_open

    Defaults represent nominal operation (all circuit breakers closed).
    Phase 7 will populate these from Prometheus metrics in real-time.
    """
    gpu_pressure_cb_open: bool = False    # GPU KV-cache pressure CB open
    latency_cb_open: bool = False         # P99 TTFT latency CB open

    @classmethod
    def nominal(cls) -> "FleetState":
        """All circuit breakers closed — normal fleet operation."""
        return cls(gpu_pressure_cb_open=False, latency_cb_open=False)


# ── Budget decision ────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class BudgetDecision:
    """
    Immutable budget and routing decision for a single request.

    Per CLAUDE.md Section 12.1 (canonical return type).
    Contains all fields needed to assemble the pre-inference decision record
    (CLAUDE.md Section 19.1) and drive later pipeline stages.
    """
    # ── Core budget assignment (CLAUDE.md Section 12.1) ───────────────────────
    base_class: str              # The class complexity maps to
    effective_class: str         # After circuit-breaker downgrade
    downgrade_reason: Optional[str]  # "latency_circuit_breaker" | None

    # ── Model routing (CLAUDE.md Section 8) ──────────────────────────────────
    model: str                   # "deepseek-r1-7b" or "qwen25-3b"
    route: str                   # "reasoning_model" | "cheap_model"

    # ── Token budgets (CLAUDE.md Section 12.3) ────────────────────────────────
    max_reasoning_tokens: int
    max_output_tokens: int

    # ── Scheduling priority (CLAUDE.md Section 12.2) ─────────────────────────
    priority_tier: str           # "low" | "standard" | "high"

    # ── Verification policy (CLAUDE.md Section 15) ───────────────────────────
    verification: str            # "none" | "verifiable_only" | "required"
    context_template: str

    # ── Escalation policy (CLAUDE.md Section 16) ─────────────────────────────
    escalation_enabled: bool
    escalation_max_retries: int
    escalation_on_exhaustion: str

    # ── Constraints for gateway enforcement ──────────────────────────────────
    cost_ceiling_usd: float      # max_cost_per_request_usd from policy limits
    p95_latency_ms: int          # from policy slo
    quality_floor_score: float   # from policy slo

    # ── Policy provenance (CLAUDE.md Section 19.1) ────────────────────────────
    policy_id: str
    policy_version: int

    # ── Guardrail configuration (consumed by Phase 5 guardrail) ───────────────
    guardrail_pii_redaction: str
    guardrail_injection_check: str
    guardrail_safety_check: str
    guardrail_output_safety: str

    # ── Cache configuration (consumed by Phase 4 semantic cache) ──────────────
    cache_enabled: bool
    cache_similarity_threshold: float
    cache_ttl_seconds: int


# ── Decision record ────────────────────────────────────────────────────────────

@dataclasses.dataclass
class DecisionRecord:
    """
    Pre-inference governance record.

    Per CLAUDE.md Section 19.1. Two records are written per request:
      - decision record (this class) — written before inference begins
      - outcome record — written after response delivery (Phase 5)

    Fields marked PHASE4+ are filled by the gateway pipeline (Phase 4).
    The policy engine populates fields it can determine from budget assignment.

    Per CLAUDE.md Section 19: never store raw prompt text.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    record_type: str = "decision"
    timestamp_iso: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    request_id: str = ""
    tenant_id: str = ""
    domain: str = ""

    # ── Policy provenance ─────────────────────────────────────────────────────
    policy_id: str = ""
    policy_version: int = 0
    model_version: str = ""           # e.g. "deepseek-r1-7b"
    prompt_version: str = ""          # from policy.versions.system_prompt
    guardrail_version: str = ""       # from policy.versions.guardrail_model
    verifier_version: str = ""        # from policy.versions.verifier

    # ── Complexity ────────────────────────────────────────────────────────────
    complexity_score: float = -1.0    # -1 when fast_path_used
    fast_path_used: bool = False

    # ── Budget decision ───────────────────────────────────────────────────────
    base_budget_class: str = ""
    effective_budget_class: str = ""
    downgrade_reason: Optional[str] = None
    priority_tier: str = ""
    max_reasoning_tokens: int = 0
    max_output_tokens: int = 0
    route: str = ""                   # "reasoning_model" | "cheap_model"

    # ── Pipeline state (filled by gateway — Phase 4+) ────────────────────────
    cache_hit: bool = False           # PHASE4: filled at Step 8
    admission_result: str = "pending" # PHASE4: filled at Step 9
    estimated_cost_usd: float = 0.0   # PHASE4: filled by cost estimator

    # ── Internal flag (not serialized to JSONL) ───────────────────────────────
    policy_fallback_used: bool = False  # True when system default was used (FM7)

    @classmethod
    def from_budget_decision(
        cls,
        request_id: str,
        tenant_id: str,
        domain: str,
        complexity_score: float,
        fast_path_used: bool,
        budget: BudgetDecision,
        policy: Policy,
        policy_fallback_used: bool = False,
    ) -> "DecisionRecord":
        """
        Construct a DecisionRecord from budget assignment output.
        Gateway fills in pipeline-state fields (cache_hit, admission_result) in Phase 4.
        """
        return cls(
            request_id=request_id,
            tenant_id=tenant_id,
            domain=domain,
            policy_id=budget.policy_id,
            policy_version=budget.policy_version,
            model_version=budget.model,
            prompt_version=policy.versions.system_prompt,
            guardrail_version=policy.versions.guardrail_model,
            verifier_version=policy.versions.verifier,
            complexity_score=complexity_score,
            fast_path_used=fast_path_used,
            base_budget_class=budget.base_class,
            effective_budget_class=budget.effective_class,
            downgrade_reason=budget.downgrade_reason,
            priority_tier=budget.priority_tier,
            max_reasoning_tokens=budget.max_reasoning_tokens,
            max_output_tokens=budget.max_output_tokens,
            route=budget.route,
            policy_fallback_used=policy_fallback_used,
        )

    def to_audit_dict(self) -> dict:
        """
        Serialize to the exact audit JSONL format from CLAUDE.md Section 19.1.
        Excludes internal flags (policy_fallback_used) — those go to the trace.
        """
        return {
            "record_type": self.record_type,
            "timestamp_iso": self.timestamp_iso,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "guardrail_version": self.guardrail_version,
            "verifier_version": self.verifier_version,
            "complexity_score": self.complexity_score,
            "fast_path_used": self.fast_path_used,
            "base_budget_class": self.base_budget_class,
            "effective_budget_class": self.effective_budget_class,
            "downgrade_reason": self.downgrade_reason,
            "priority_tier": self.priority_tier,
            "max_reasoning_tokens": self.max_reasoning_tokens,
            "max_output_tokens": self.max_output_tokens,
            "route": self.route,
            "cache_hit": self.cache_hit,
            "admission_result": self.admission_result,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


# ── Budget class assignment ────────────────────────────────────────────────────

_BUDGET_CLASS_ORDER = ["low", "medium", "high", "critical"]


def downgrade_one(budget_class: str) -> str:
    """
    Downgrade a budget class by one step. Per CLAUDE.md Section 12.1.
    "low" cannot be downgraded further — returns "low".
    """
    idx = _BUDGET_CLASS_ORDER.index(budget_class)
    return _BUDGET_CLASS_ORDER[max(0, idx - 1)]


def _derive_priority_tier(base_class: str) -> str:
    """
    Map budget class to scheduling priority tier.
    Per CLAUDE.md Section 6 Step 6 and Section 32 (Architectural Assumptions).
    Priority tier governs queue scheduling preference, NOT quality budget.
    """
    if base_class == "low":
        return "low"
    elif base_class == "critical":
        return "high"
    else:  # medium, high
        return "standard"


def _derive_route(model_name: str) -> str:
    """
    Map model name to route identifier. Per CLAUDE.md Section 8.
    """
    return "cheap_model" if model_name == "qwen25-3b" else "reasoning_model"


def escalate_budget_class(
    target_class: str,
    policy: "Policy",
    fleet_state: FleetState,
) -> BudgetDecision:
    """
    Build a BudgetDecision for a specific target class, bypassing complexity
    score mapping. Used by the escalation handler in gateway/main.py.

    Per CLAUDE.md Section 16: "Repeat from admission control at next higher
    budget class." The budget decision is constructed directly from the policy
    profile for the requested class; circuit-breaker downgrade does NOT apply
    to escalated requests (the escalation itself is the override decision).

    Args:
        target_class: The escalated budget class ("medium"|"high"|"critical").
        policy:       Current validated policy.
        fleet_state:  Current fleet state (passed through for consistency).

    Returns:
        BudgetDecision for the target class with downgrade_reason="escalation".
    """
    profile = policy.budget_profiles[target_class]

    return BudgetDecision(
        base_class=target_class,
        effective_class=target_class,
        downgrade_reason="escalation",
        model=profile.model,
        route=_derive_route(profile.model),
        max_reasoning_tokens=profile.max_reasoning_tokens,
        max_output_tokens=profile.max_output_tokens,
        priority_tier=_derive_priority_tier(target_class),
        verification=profile.verification,
        context_template=profile.context_template,
        escalation_enabled=policy.escalation.enabled,
        escalation_max_retries=policy.escalation.max_retries,
        escalation_on_exhaustion=policy.escalation.on_exhaustion,
        cost_ceiling_usd=policy.limits.max_cost_per_request_usd,
        p95_latency_ms=policy.slo.p95_latency_ms,
        quality_floor_score=policy.slo.quality_floor_score,
        policy_id=policy.policy_id,
        policy_version=policy.versions.policy,
        guardrail_pii_redaction=policy.guardrails.pii_redaction,
        guardrail_injection_check=policy.guardrails.injection_check,
        guardrail_safety_check=policy.guardrails.safety_check,
        guardrail_output_safety=policy.guardrails.output_safety,
        cache_enabled=policy.cache.enabled,
        cache_similarity_threshold=policy.cache.similarity_threshold,
        cache_ttl_seconds=policy.cache.ttl_seconds,
    )


def assign_budget_class(
    complexity_score: float,
    policy: Policy,
    fleet_state: FleetState,
) -> BudgetDecision:
    """
    Canonical budget assignment per CLAUDE.md Section 12.1.

    Maps complexity score → base class via policy thresholds,
    then applies circuit-breaker downgrades from fleet state.
    Returns an immutable BudgetDecision carrying all downstream configuration.

    Args:
        complexity_score: Float 0.0–10.0 from ComplexityScorer.
                          -1.0 when fast_path_used (default medium class applied).
        policy:           Validated immutable Policy from PolicyRegistry.
        fleet_state:      Current circuit-breaker state (nominal = all closed).

    Returns:
        BudgetDecision: frozen dataclass with all routing/budget/policy fields.
    """
    # Fast-path: when complexity scorer was skipped, use medium class as documented.
    if complexity_score < 0:
        base_class = "medium"
    elif complexity_score <= policy.complexity_thresholds.low_max:
        base_class = "low"
    elif complexity_score <= policy.complexity_thresholds.medium_max:
        base_class = "medium"
    elif complexity_score <= policy.complexity_thresholds.high_max:
        base_class = "high"
    else:
        base_class = "critical"

    # ── Apply fleet pressure downgrade (per CLAUDE.md Section 12.1 verbatim) ─
    if fleet_state.latency_cb_open and base_class != "critical":
        effective_class = downgrade_one(base_class)
        downgrade_reason: Optional[str] = "latency_circuit_breaker"
    elif fleet_state.gpu_pressure_cb_open and base_class == "low":
        # Already cheap route — no change needed
        effective_class = base_class
        downgrade_reason = None
    else:
        effective_class = base_class
        downgrade_reason = None

    profile = policy.budget_profiles[effective_class]

    return BudgetDecision(
        base_class=base_class,
        effective_class=effective_class,
        downgrade_reason=downgrade_reason,
        model=profile.model,
        route=_derive_route(profile.model),
        max_reasoning_tokens=profile.max_reasoning_tokens,
        max_output_tokens=profile.max_output_tokens,
        priority_tier=_derive_priority_tier(base_class),
        verification=profile.verification,
        context_template=profile.context_template,
        escalation_enabled=policy.escalation.enabled,
        escalation_max_retries=policy.escalation.max_retries,
        escalation_on_exhaustion=policy.escalation.on_exhaustion,
        cost_ceiling_usd=policy.limits.max_cost_per_request_usd,
        p95_latency_ms=policy.slo.p95_latency_ms,
        quality_floor_score=policy.slo.quality_floor_score,
        policy_id=policy.policy_id,
        policy_version=policy.versions.policy,
        guardrail_pii_redaction=policy.guardrails.pii_redaction,
        guardrail_injection_check=policy.guardrails.injection_check,
        guardrail_safety_check=policy.guardrails.safety_check,
        guardrail_output_safety=policy.guardrails.output_safety,
        cache_enabled=policy.cache.enabled,
        cache_similarity_threshold=policy.cache.similarity_threshold,
        cache_ttl_seconds=policy.cache.ttl_seconds,
    )
