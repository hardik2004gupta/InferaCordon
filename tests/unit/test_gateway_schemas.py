"""
Unit tests for gateway/schemas.py.

Tests cover:
- InferRequest: valid payloads, field constraints, optional fields, budget_override enum
- InferResponse: field defaults, response construction
- HealthResponse / ReadinessResponse: trivial correctness
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gateway.schemas import (
    ErrorResponse,
    HealthResponse,
    InferRequest,
    InferResponse,
    ReadinessResponse,
)


class TestInferRequest:
    def test_minimal_valid_request(self):
        req = InferRequest(prompt="Hello, world!")
        assert req.prompt == "Hello, world!"
        assert req.domain == "general_qa"
        assert req.stream is False
        assert req.budget_override is None
        assert req.response_schema is None

    def test_full_valid_request(self):
        req = InferRequest(
            prompt="Solve this problem.",
            tenant_id="acme_corp",
            domain="math",
            response_schema={"type": "object"},
            budget_override="high",
            stream=False,
        )
        assert req.budget_override == "high"
        assert req.domain == "math"

    def test_empty_prompt_raises(self):
        with pytest.raises(ValidationError):
            InferRequest(prompt="")

    def test_prompt_too_long_raises(self):
        with pytest.raises(ValidationError):
            InferRequest(prompt="x" * 32769)

    def test_prompt_exactly_max_length_valid(self):
        req = InferRequest(prompt="x" * 32768)
        assert len(req.prompt) == 32768

    def test_invalid_budget_override_raises(self):
        with pytest.raises(ValidationError):
            InferRequest(prompt="Test", budget_override="extreme")

    def test_all_valid_budget_overrides(self):
        for cls in ("low", "medium", "high", "critical"):
            req = InferRequest(prompt="Test", budget_override=cls)
            assert req.budget_override == cls

    def test_none_budget_override_valid(self):
        req = InferRequest(prompt="Test", budget_override=None)
        assert req.budget_override is None

    def test_response_schema_dict_accepted(self):
        req = InferRequest(
            prompt="Generate JSON",
            response_schema={"type": "object", "properties": {"name": {"type": "string"}}},
        )
        assert req.response_schema["type"] == "object"

    def test_tenant_id_optional(self):
        req = InferRequest(prompt="Test")
        assert req.tenant_id is None

    def test_unknown_domain_accepted(self):
        # Domain is a free string — validation is by policy resolution, not schema
        req = InferRequest(prompt="Test", domain="custom_domain")
        assert req.domain == "custom_domain"


class TestInferResponse:
    def _make(self, **overrides) -> InferResponse:
        defaults = dict(
            response="The answer is 42.",
            request_id="req_abc123def456",
            budget_class="medium",
            reasoning_tokens_used=341,
            reasoning_tokens_allocated=512,
            stop_reason="natural_boundary",
            estimated_cost_usd=0.0058,
            confidence_level="high",
            latency_ms=1167,
            policy_id="enterprise_standard_v1",
            policy_version=1,
        )
        defaults.update(overrides)
        return InferResponse(**defaults)

    def test_minimal_response(self):
        resp = self._make()
        assert resp.response == "The answer is 42."
        assert resp.verification_result == "skipped"
        assert resp.escalation_count == 0
        assert resp.policy_fallback_used is False

    def test_high_confidence_default(self):
        resp = self._make()
        assert resp.confidence_level == "high"

    def test_low_confidence_set(self):
        resp = self._make(confidence_level="low")
        assert resp.confidence_level == "low"

    def test_escalation_count_set(self):
        resp = self._make(escalation_count=1)
        assert resp.escalation_count == 1

    def test_policy_fallback_used_set(self):
        resp = self._make(policy_fallback_used=True)
        assert resp.policy_fallback_used is True

    def test_serializes_to_dict(self):
        resp = self._make()
        d = resp.model_dump()
        assert d["request_id"] == "req_abc123def456"
        assert "budget_class" in d


class TestHealthResponse:
    def test_defaults(self):
        r = HealthResponse()
        assert r.status == "ok"
        assert r.version == "0.1.0"

    def test_custom_version(self):
        r = HealthResponse(version="1.0.0")
        assert r.version == "1.0.0"


class TestReadinessResponse:
    def test_ready(self):
        r = ReadinessResponse(ready=True, policy_count=5, vllm_url="http://vllm:8080")
        assert r.ready is True
        assert r.policy_count == 5
        assert r.reason is None

    def test_not_ready(self):
        r = ReadinessResponse(
            ready=False,
            policy_count=0,
            vllm_url="",
            reason="gateway not yet initialized",
        )
        assert r.ready is False
        assert "initialized" in r.reason


class TestErrorResponse:
    def test_minimal(self):
        e = ErrorResponse(error="internal_error")
        assert e.error == "internal_error"
        assert e.detail is None
        assert e.request_id is None
        assert e.retry_after_seconds is None

    def test_rate_limit_error(self):
        e = ErrorResponse(
            error="rate_limit_exceeded",
            detail="Too many requests",
            retry_after_seconds=14,
        )
        assert e.retry_after_seconds == 14
