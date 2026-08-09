"""
Pydantic v2 schema for InferaCordon policy YAML files.

Per CLAUDE.md Section 11 — complete field set documented there.
Schema is versioned via schema_version field.
Validation runs at startup; invalid policies cause process abort.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class BudgetProfile(BaseModel):
    model: str
    max_reasoning_tokens: int
    max_output_tokens: int
    verification: str
    context_template: str


class GuardrailConfig(BaseModel):
    pii_redaction: str
    injection_check: str
    safety_check: str
    output_safety: str


class LimitsConfig(BaseModel):
    requests_per_minute: int
    tokens_per_hour: int
    max_cost_per_request_usd: float
    max_prompt_tokens: int


class SLOConfig(BaseModel):
    p95_latency_ms: int
    quality_floor_score: float
    quality_regression_pp: float


class CacheConfig(BaseModel):
    enabled: bool
    similarity_threshold: float
    ttl_seconds: int


class EscalationConfig(BaseModel):
    enabled: bool
    max_retries: int
    on_exhaustion: str


class VersionsConfig(BaseModel):
    policy: int
    system_prompt: str
    complexity_scorer: str
    guardrail_model: str
    injection_model: str
    verifier: str


class ComplexityThresholds(BaseModel):
    low_max: float
    medium_max: float
    high_max: float


class Policy(BaseModel):
    policy_id: str
    tenant: str
    domain: str
    schema_version: int
    budget_profiles: dict[str, BudgetProfile]
    complexity_thresholds: ComplexityThresholds
    guardrails: GuardrailConfig
    limits: LimitsConfig
    slo: SLOConfig
    cache: CacheConfig
    escalation: EscalationConfig
    versions: VersionsConfig
    trace_retention_days: int
    store_reasoning_trace: bool
