"""
Pydantic v2 schema for InferaCordon policy YAML files.

Per CLAUDE.md Section 11 — complete field set documented there.
Schema is versioned via schema_version field.
Validation runs at startup; invalid policies cause process abort.

Design decisions:
- frozen=True: Policies are immutable after load (CLAUDE.md Section 11.4).
- Strict field validation: model names, verification values, token limits, etc.
- All four budget classes (low/medium/high/critical) are required.
- Complexity thresholds must be strictly ordered: low_max < medium_max < high_max.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── Allowed values (per CLAUDE.md Sections 8, 11, 12) ────────────────────────

ALLOWED_MODELS: frozenset[str] = frozenset({"qwen25-3b", "deepseek-r1-7b"})
ALLOWED_VERIFICATION: frozenset[str] = frozenset({"none", "verifiable_only", "required"})
ALLOWED_BUDGET_CLASSES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})
ALLOWED_PII_REDACTION: frozenset[str] = frozenset({"standard", "strict", "none"})
ALLOWED_CHECK_MODE: frozenset[str] = frozenset({"always", "conditional", "never", "none"})
ALLOWED_OUTPUT_SAFETY: frozenset[str] = frozenset({"sync", "async", "none"})
ALLOWED_ON_EXHAUSTION: frozenset[str] = frozenset({"return_low_confidence", "raise_error"})


# ── Sub-schemas ────────────────────────────────────────────────────────────────

class BudgetProfile(BaseModel):
    """Per-budget-class inference configuration. Per CLAUDE.md Section 12.3."""
    model_config = ConfigDict(frozen=True)

    model: str
    max_reasoning_tokens: int = Field(ge=0)
    max_output_tokens: int = Field(gt=0)
    verification: str
    context_template: str

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if v not in ALLOWED_MODELS:
            raise ValueError(
                f"model {v!r} is not an approved model identifier. "
                f"Allowed: {sorted(ALLOWED_MODELS)}. "
                "Any substitution requires the Architecture Deviation Protocol (CLAUDE.md Section 28)."
            )
        return v

    @field_validator("verification")
    @classmethod
    def validate_verification(cls, v: str) -> str:
        if v not in ALLOWED_VERIFICATION:
            raise ValueError(
                f"verification {v!r} is invalid. Allowed: {sorted(ALLOWED_VERIFICATION)}"
            )
        return v


class ComplexityThresholds(BaseModel):
    """Budget class thresholds derived from complexity score. Per CLAUDE.md Section 10.5."""
    model_config = ConfigDict(frozen=True)

    low_max: float = Field(gt=0.0, le=10.0)
    medium_max: float = Field(gt=0.0, le=10.0)
    high_max: float = Field(gt=0.0, le=10.0)

    @model_validator(mode="after")
    def validate_threshold_ordering(self) -> "ComplexityThresholds":
        if not (self.low_max < self.medium_max < self.high_max):
            raise ValueError(
                f"Complexity thresholds must be strictly ordered: "
                f"low_max ({self.low_max}) < medium_max ({self.medium_max}) < high_max ({self.high_max})"
            )
        return self


class GuardrailConfig(BaseModel):
    """Guardrail configuration. Per CLAUDE.md Section 14."""
    model_config = ConfigDict(frozen=True)

    pii_redaction: str
    injection_check: str
    safety_check: str
    output_safety: str

    @field_validator("pii_redaction")
    @classmethod
    def validate_pii(cls, v: str) -> str:
        if v not in ALLOWED_PII_REDACTION:
            raise ValueError(f"pii_redaction {v!r} invalid. Allowed: {sorted(ALLOWED_PII_REDACTION)}")
        return v

    @field_validator("injection_check", "safety_check")
    @classmethod
    def validate_check_mode(cls, v: str) -> str:
        if v not in ALLOWED_CHECK_MODE:
            raise ValueError(f"check mode {v!r} invalid. Allowed: {sorted(ALLOWED_CHECK_MODE)}")
        return v

    @field_validator("output_safety")
    @classmethod
    def validate_output_safety(cls, v: str) -> str:
        if v not in ALLOWED_OUTPUT_SAFETY:
            raise ValueError(f"output_safety {v!r} invalid. Allowed: {sorted(ALLOWED_OUTPUT_SAFETY)}")
        return v


class LimitsConfig(BaseModel):
    """Rate limits and cost ceilings. Per CLAUDE.md Section 11.5."""
    model_config = ConfigDict(frozen=True)

    requests_per_minute: int = Field(gt=0)
    tokens_per_hour: int = Field(gt=0)
    max_cost_per_request_usd: float = Field(gt=0.0)
    max_prompt_tokens: int = Field(gt=0)


class SLOConfig(BaseModel):
    """Service Level Objectives. Per CLAUDE.md Section 11.5."""
    model_config = ConfigDict(frozen=True)

    p95_latency_ms: int = Field(gt=0)
    quality_floor_score: float = Field(ge=1.0, le=5.0)
    quality_regression_pp: float = Field(ge=0.0)


class CacheConfig(BaseModel):
    """Semantic cache configuration. Per CLAUDE.md Section 13."""
    model_config = ConfigDict(frozen=True)

    enabled: bool
    similarity_threshold: float = Field(ge=0.0, lt=1.0)
    ttl_seconds: int = Field(gt=0)


class EscalationConfig(BaseModel):
    """Escalation behavior. Per CLAUDE.md Section 16."""
    model_config = ConfigDict(frozen=True)

    enabled: bool
    max_retries: int = Field(ge=0)
    on_exhaustion: str

    @field_validator("on_exhaustion")
    @classmethod
    def validate_on_exhaustion(cls, v: str) -> str:
        if v not in ALLOWED_ON_EXHAUSTION:
            raise ValueError(
                f"on_exhaustion {v!r} invalid. Allowed: {sorted(ALLOWED_ON_EXHAUSTION)}"
            )
        return v


class VersionsConfig(BaseModel):
    """Component version pinning for governance traceability. Per CLAUDE.md Section 11.5."""
    model_config = ConfigDict(frozen=True)

    policy: int = Field(ge=1)
    system_prompt: str
    complexity_scorer: str
    guardrail_model: str
    injection_model: str
    verifier: str


# ── Top-level Policy schema ────────────────────────────────────────────────────

class Policy(BaseModel):
    """
    Complete immutable policy document.

    Per CLAUDE.md Section 11.4: immutable after load. Version bump required for changes.
    Per CLAUDE.md Section 11.3: validation failure raises startup exception.
    """
    model_config = ConfigDict(frozen=True)

    policy_id: str
    tenant: str
    domain: str
    schema_version: int = Field(ge=1)
    budget_profiles: dict[str, BudgetProfile]
    complexity_thresholds: ComplexityThresholds
    guardrails: GuardrailConfig
    limits: LimitsConfig
    slo: SLOConfig
    cache: CacheConfig
    escalation: EscalationConfig
    versions: VersionsConfig
    trace_retention_days: int = Field(gt=0)
    store_reasoning_trace: bool

    @model_validator(mode="after")
    def validate_budget_profiles_completeness(self) -> "Policy":
        """All four budget classes must be present. Per CLAUDE.md Section 12.3."""
        missing = ALLOWED_BUDGET_CLASSES - set(self.budget_profiles.keys())
        if missing:
            raise ValueError(
                f"Policy {self.policy_id!r} is missing required budget classes: {sorted(missing)}. "
                "All four classes (low, medium, high, critical) must be defined."
            )
        extra = set(self.budget_profiles.keys()) - ALLOWED_BUDGET_CLASSES
        if extra:
            raise ValueError(
                f"Policy {self.policy_id!r} contains unrecognized budget classes: {sorted(extra)}. "
                f"Allowed: {sorted(ALLOWED_BUDGET_CLASSES)}"
            )
        return self

    @model_validator(mode="after")
    def validate_low_budget_model(self) -> "Policy":
        """Low budget class must use the cheap model (no reasoning tokens)."""
        low = self.budget_profiles.get("low")
        if low and low.max_reasoning_tokens != 0:
            raise ValueError(
                f"Policy {self.policy_id!r}: low budget class must have max_reasoning_tokens=0 "
                "(cheap model route, no chain-of-thought). "
                f"Got max_reasoning_tokens={low.max_reasoning_tokens}."
            )
        return self

    @model_validator(mode="after")
    def validate_reasoning_model_for_high_classes(self) -> "Policy":
        """medium/high/critical classes must use the reasoning model."""
        reasoning_classes = {"medium", "high", "critical"}
        for cls_name in reasoning_classes:
            profile = self.budget_profiles.get(cls_name)
            if profile and profile.model != "deepseek-r1-7b":
                raise ValueError(
                    f"Policy {self.policy_id!r}: budget class {cls_name!r} must use "
                    f"model 'deepseek-r1-7b' (reasoning route). Got {profile.model!r}. "
                    "Per CLAUDE.md Section 8."
                )
        return self
