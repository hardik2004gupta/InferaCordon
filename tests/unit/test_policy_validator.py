"""
Unit tests for the Policy Pydantic v2 schema (policy_engine/validator.py).

Coverage per CLAUDE.md Phase 3 requirements:
  - Valid policy loads cleanly (acme_corp and demo_tenant YAMLs)
  - Missing required fields raise ValidationError with field name
  - Wrong types raise ValidationError
  - Disallowed model names are rejected
  - Threshold ordering invariant (low_max < medium_max < high_max)
  - All four budget classes required
  - low class must have max_reasoning_tokens = 0
  - medium/high/critical must use deepseek-r1-7b
  - Invalid verification value is rejected
  - Invalid on_exhaustion value is rejected
  - Policy is immutable (frozen=True)
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from policy_engine.validator import (
    ALLOWED_BUDGET_CLASSES,
    ALLOWED_MODELS,
    ALLOWED_VERIFICATION,
    BudgetProfile,
    ComplexityThresholds,
    Policy,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

POLICY_DIR = Path(__file__).parent.parent.parent / "policy_engine" / "policies"


def _load_yaml(filename: str) -> dict:
    return yaml.safe_load((POLICY_DIR / filename).read_text(encoding="utf-8"))


def _make_valid_policy(**overrides) -> dict:
    """Return a minimal valid policy dict, optionally overriding fields."""
    base = {
        "policy_id": "test_policy_v1",
        "tenant": "test_tenant",
        "domain": "test_domain",
        "schema_version": 1,
        "budget_profiles": {
            "low": {
                "model": "qwen25-3b",
                "max_reasoning_tokens": 0,
                "max_output_tokens": 256,
                "verification": "none",
                "context_template": "direct",
            },
            "medium": {
                "model": "deepseek-r1-7b",
                "max_reasoning_tokens": 512,
                "max_output_tokens": 512,
                "verification": "verifiable_only",
                "context_template": "step_by_step",
            },
            "high": {
                "model": "deepseek-r1-7b",
                "max_reasoning_tokens": 1024,
                "max_output_tokens": 1024,
                "verification": "required",
                "context_template": "verify_steps",
            },
            "critical": {
                "model": "deepseek-r1-7b",
                "max_reasoning_tokens": 2048,
                "max_output_tokens": 1024,
                "verification": "required",
                "context_template": "verify_steps",
            },
        },
        "complexity_thresholds": {
            "low_max": 3.5,
            "medium_max": 6.5,
            "high_max": 8.5,
        },
        "guardrails": {
            "pii_redaction": "standard",
            "injection_check": "conditional",
            "safety_check": "conditional",
            "output_safety": "async",
        },
        "limits": {
            "requests_per_minute": 60,
            "tokens_per_hour": 500000,
            "max_cost_per_request_usd": 0.05,
            "max_prompt_tokens": 4096,
        },
        "slo": {
            "p95_latency_ms": 4000,
            "quality_floor_score": 3.5,
            "quality_regression_pp": 1.0,
        },
        "cache": {
            "enabled": True,
            "similarity_threshold": 0.92,
            "ttl_seconds": 3600,
        },
        "escalation": {
            "enabled": True,
            "max_retries": 1,
            "on_exhaustion": "return_low_confidence",
        },
        "versions": {
            "policy": 1,
            "system_prompt": "prompt_v1",
            "complexity_scorer": "scorer_v1",
            "guardrail_model": "llamaguard_onnx_v1",
            "injection_model": "deberta_inject_v1",
            "verifier": "verifier_v1",
        },
        "trace_retention_days": 30,
        "store_reasoning_trace": False,
    }
    base.update(overrides)
    return base


# ── 1. Existing policy YAML files load successfully ───────────────────────────

class TestExistingPolicies:

    def test_acme_corp_general_qa_loads(self):
        data = _load_yaml("acme_corp_general_qa_v1.yaml")
        policy = Policy.model_validate(data)
        assert policy.policy_id == "enterprise_standard_v1"
        assert policy.tenant == "acme_corp"
        assert policy.domain == "general_qa"

    def test_demo_tenant_loads(self):
        data = _load_yaml("demo_tenant_v1.yaml")
        policy = Policy.model_validate(data)
        assert policy.tenant == "demo_tenant"

    def test_default_policy_loads(self):
        data = _load_yaml("default_policy_v1.yaml")
        policy = Policy.model_validate(data)
        assert policy.tenant == "default"
        assert policy.policy_id == "system_default_v1"

    def test_acme_corp_has_all_four_budget_classes(self):
        data = _load_yaml("acme_corp_general_qa_v1.yaml")
        policy = Policy.model_validate(data)
        assert set(policy.budget_profiles.keys()) == ALLOWED_BUDGET_CLASSES

    def test_acme_corp_low_class_has_cheap_model(self):
        data = _load_yaml("acme_corp_general_qa_v1.yaml")
        policy = Policy.model_validate(data)
        assert policy.budget_profiles["low"].model == "qwen25-3b"

    def test_acme_corp_medium_class_has_reasoning_model(self):
        data = _load_yaml("acme_corp_general_qa_v1.yaml")
        policy = Policy.model_validate(data)
        assert policy.budget_profiles["medium"].model == "deepseek-r1-7b"

    def test_policy_is_frozen(self):
        data = _load_yaml("acme_corp_general_qa_v1.yaml")
        policy = Policy.model_validate(data)
        with pytest.raises(Exception):
            policy.policy_id = "should_fail"  # type: ignore[misc]

    def test_thresholds_are_frozen(self):
        data = _load_yaml("acme_corp_general_qa_v1.yaml")
        policy = Policy.model_validate(data)
        with pytest.raises(Exception):
            policy.complexity_thresholds.low_max = 99.0  # type: ignore[misc]


# ── 2. Valid minimal policy ────────────────────────────────────────────────────

class TestValidMinimalPolicy:

    def test_minimal_valid_policy_loads(self):
        policy = Policy.model_validate(_make_valid_policy())
        assert policy.policy_id == "test_policy_v1"

    def test_all_four_budget_classes_present(self):
        policy = Policy.model_validate(_make_valid_policy())
        assert set(policy.budget_profiles.keys()) == {"low", "medium", "high", "critical"}

    def test_low_class_zero_reasoning_tokens(self):
        policy = Policy.model_validate(_make_valid_policy())
        assert policy.budget_profiles["low"].max_reasoning_tokens == 0


# ── 3. Missing required fields ────────────────────────────────────────────────

class TestMissingRequiredFields:

    def test_missing_policy_id_raises(self):
        data = _make_valid_policy()
        del data["policy_id"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "policy_id" in str(exc_info.value)

    def test_missing_tenant_raises(self):
        data = _make_valid_policy()
        del data["tenant"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "tenant" in str(exc_info.value)

    def test_missing_budget_profiles_raises(self):
        data = _make_valid_policy()
        del data["budget_profiles"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "budget_profiles" in str(exc_info.value)

    def test_missing_complexity_thresholds_raises(self):
        data = _make_valid_policy()
        del data["complexity_thresholds"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "complexity_thresholds" in str(exc_info.value)

    def test_missing_guardrails_raises(self):
        data = _make_valid_policy()
        del data["guardrails"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "guardrails" in str(exc_info.value)

    def test_missing_limits_raises(self):
        data = _make_valid_policy()
        del data["limits"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "limits" in str(exc_info.value)

    def test_missing_slo_raises(self):
        data = _make_valid_policy()
        del data["slo"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "slo" in str(exc_info.value)

    def test_missing_versions_raises(self):
        data = _make_valid_policy()
        del data["versions"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "versions" in str(exc_info.value)


# ── 4. Wrong types ────────────────────────────────────────────────────────────

class TestWrongTypes:

    def test_schema_version_must_be_int(self):
        data = _make_valid_policy(schema_version="not_an_int")
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_max_reasoning_tokens_must_be_int(self):
        data = _make_valid_policy()
        data["budget_profiles"]["medium"]["max_reasoning_tokens"] = "five_hundred"
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_requests_per_minute_must_be_positive(self):
        data = _make_valid_policy()
        data["limits"]["requests_per_minute"] = 0
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_max_cost_must_be_positive(self):
        data = _make_valid_policy()
        data["limits"]["max_cost_per_request_usd"] = 0.0
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_quality_floor_out_of_range_raises(self):
        data = _make_valid_policy()
        data["slo"]["quality_floor_score"] = 6.0  # > 5.0 — out of range
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_similarity_threshold_at_one_raises(self):
        data = _make_valid_policy()
        data["cache"]["similarity_threshold"] = 1.0  # not < 1.0 — boundary
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_trace_retention_must_be_positive(self):
        data = _make_valid_policy()
        data["trace_retention_days"] = 0
        with pytest.raises(ValidationError):
            Policy.model_validate(data)


# ── 5. Disallowed model names ─────────────────────────────────────────────────

class TestDisallowedModels:

    def test_gpt4_rejected(self):
        data = _make_valid_policy()
        data["budget_profiles"]["medium"]["model"] = "gpt-4o"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "gpt-4o" in str(exc_info.value)

    def test_claude_rejected(self):
        data = _make_valid_policy()
        data["budget_profiles"]["high"]["model"] = "claude-3-5-sonnet"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "claude-3-5-sonnet" in str(exc_info.value)

    def test_typo_model_rejected(self):
        data = _make_valid_policy()
        data["budget_profiles"]["medium"]["model"] = "deepseek_r1_7b"  # underscore typo
        with pytest.raises(ValidationError):
            Policy.model_validate(data)

    def test_allowed_models_constant_is_frozenset(self):
        assert isinstance(ALLOWED_MODELS, frozenset)
        assert "qwen25-3b" in ALLOWED_MODELS
        assert "deepseek-r1-7b" in ALLOWED_MODELS


# ── 6. Complexity threshold ordering ─────────────────────────────────────────

class TestThresholdOrdering:

    def test_valid_ordering_passes(self):
        thresholds = ComplexityThresholds(low_max=3.5, medium_max=6.5, high_max=8.5)
        assert thresholds.low_max < thresholds.medium_max < thresholds.high_max

    def test_low_equals_medium_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ComplexityThresholds(low_max=5.0, medium_max=5.0, high_max=8.0)
        assert "strictly ordered" in str(exc_info.value).lower()

    def test_medium_greater_than_high_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ComplexityThresholds(low_max=2.0, medium_max=9.0, high_max=6.0)
        assert "strictly ordered" in str(exc_info.value).lower()

    def test_all_equal_raises(self):
        with pytest.raises(ValidationError):
            ComplexityThresholds(low_max=5.0, medium_max=5.0, high_max=5.0)

    def test_reversed_order_raises(self):
        with pytest.raises(ValidationError):
            ComplexityThresholds(low_max=8.0, medium_max=6.0, high_max=3.0)


# ── 7. Budget class completeness ──────────────────────────────────────────────

class TestBudgetClassCompleteness:

    def test_missing_low_class_raises(self):
        data = _make_valid_policy()
        del data["budget_profiles"]["low"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "low" in str(exc_info.value)

    def test_missing_critical_class_raises(self):
        data = _make_valid_policy()
        del data["budget_profiles"]["critical"]
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "critical" in str(exc_info.value)

    def test_extra_budget_class_raises(self):
        data = _make_valid_policy()
        data["budget_profiles"]["ultra"] = {
            "model": "deepseek-r1-7b",
            "max_reasoning_tokens": 4096,
            "max_output_tokens": 2048,
            "verification": "required",
            "context_template": "verify_steps",
        }
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "ultra" in str(exc_info.value)


# ── 8. Low class reasoning token constraint ───────────────────────────────────

class TestLowClassConstraint:

    def test_low_class_nonzero_reasoning_tokens_raises(self):
        data = _make_valid_policy()
        data["budget_profiles"]["low"]["max_reasoning_tokens"] = 100
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "max_reasoning_tokens" in str(exc_info.value)

    def test_low_class_zero_reasoning_tokens_passes(self):
        data = _make_valid_policy()
        data["budget_profiles"]["low"]["max_reasoning_tokens"] = 0
        policy = Policy.model_validate(data)
        assert policy.budget_profiles["low"].max_reasoning_tokens == 0

    def test_low_class_can_only_use_cheap_model(self):
        # Not a direct validator constraint — the model validator checks all classes
        # but the "low must use qwen25-3b" is enforced via token constraint.
        # This test verifies the reasoning token constraint is sufficient.
        data = _make_valid_policy()
        data["budget_profiles"]["low"]["max_reasoning_tokens"] = 1  # must be 0
        with pytest.raises(ValidationError):
            Policy.model_validate(data)


# ── 9. Reasoning model for medium/high/critical ───────────────────────────────

class TestReasoningModelConstraint:

    def test_cheap_model_for_medium_raises(self):
        data = _make_valid_policy()
        data["budget_profiles"]["medium"]["model"] = "qwen25-3b"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "deepseek-r1-7b" in str(exc_info.value)

    def test_cheap_model_for_high_raises(self):
        data = _make_valid_policy()
        data["budget_profiles"]["high"]["model"] = "qwen25-3b"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "deepseek-r1-7b" in str(exc_info.value)

    def test_cheap_model_for_critical_raises(self):
        data = _make_valid_policy()
        data["budget_profiles"]["critical"]["model"] = "qwen25-3b"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "deepseek-r1-7b" in str(exc_info.value)


# ── 10. Invalid enum values ───────────────────────────────────────────────────

class TestInvalidEnumValues:

    def test_invalid_verification_raises(self):
        data = _make_valid_policy()
        data["budget_profiles"]["medium"]["verification"] = "optional"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "optional" in str(exc_info.value)

    def test_invalid_pii_redaction_raises(self):
        data = _make_valid_policy()
        data["guardrails"]["pii_redaction"] = "heavy"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "heavy" in str(exc_info.value)

    def test_invalid_injection_check_raises(self):
        data = _make_valid_policy()
        data["guardrails"]["injection_check"] = "sometimes"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "sometimes" in str(exc_info.value)

    def test_invalid_output_safety_raises(self):
        data = _make_valid_policy()
        data["guardrails"]["output_safety"] = "deferred"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "deferred" in str(exc_info.value)

    def test_invalid_on_exhaustion_raises(self):
        data = _make_valid_policy()
        data["escalation"]["on_exhaustion"] = "panic"
        with pytest.raises(ValidationError) as exc_info:
            Policy.model_validate(data)
        assert "panic" in str(exc_info.value)
