"""
Unit tests for telemetry/trace_schema.py.

Per CLAUDE.md §18.1:
  - Field names must match §18.1 exactly — no renaming, no omission
  - to_dict() must produce a complete serializable dict
  - to_otel_span_attributes() must not contain raw text fields
  - entropy_samples defaults to empty list
"""
from __future__ import annotations

import dataclasses

import pytest

from telemetry.trace_schema import RequestTrace

# ── Exact field list from CLAUDE.md §18.1 ─────────────────────────────────────

_REQUIRED_FIELDS = [
    # Identity
    "request_id", "trace_id", "tenant_id", "domain",
    # Governance
    "policy_id", "policy_version", "model_version", "prompt_version",
    "guardrail_version", "verifier_version", "complexity_scorer_version",
    # Decision
    "complexity_score", "fast_path_used", "base_budget_class",
    "effective_budget_class", "downgrade_reason", "priority_tier",
    "max_reasoning_tokens", "route", "cache_hit", "admission_decision",
    # Execution
    "reasoning_tokens_used", "output_tokens", "tokens_saved",
    "stop_reason", "escalation_count", "fallback_used",
    # Guardrails
    "guardrail_input_result", "guardrail_input_ms", "guardrail_injection_score",
    "guardrail_output_result", "guardrail_output_ms",
    # Verification
    "verification_result", "verification_type", "verification_ms",
    # Latency breakdown
    "queue_ms", "prefill_ms", "decode_ms", "ttft_ms", "e2e_latency_ms",
    # Cost
    "estimated_cost_usd", "actual_cost_usd",
    # Circuit breakers
    "gpu_cb_state", "latency_cb_state",
    # Entropy telemetry
    "entropy_samples",
]


def _make_trace(**overrides) -> RequestTrace:
    defaults = {
        "request_id": "req_abc123def456",
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "tenant_id": "acme_corp",
        "domain": "general_qa",
        "policy_id": "enterprise_standard_v1",
        "policy_version": 1,
        "model_version": "deepseek-r1-7b-q4",
        "prompt_version": "prompt_v2",
        "guardrail_version": "llamaguard_onnx_v1",
        "verifier_version": "verifier_v1",
        "complexity_scorer_version": "scorer_v1",
        "complexity_score": 6.4,
        "fast_path_used": False,
        "base_budget_class": "medium",
        "effective_budget_class": "medium",
        "downgrade_reason": None,
        "priority_tier": "standard",
        "max_reasoning_tokens": 512,
        "route": "reasoning_model",
        "cache_hit": False,
        "admission_decision": "pass",
        "reasoning_tokens_used": 341,
        "output_tokens": 203,
        "tokens_saved": 171,
        "stop_reason": "natural_boundary",
        "escalation_count": 0,
        "fallback_used": False,
        "guardrail_input_result": "pass",
        "guardrail_input_ms": 24,
        "guardrail_injection_score": 0.12,
        "guardrail_output_result": "pass",
        "guardrail_output_ms": 31,
        "verification_result": "correct",
        "verification_type": "gsm8k",
        "verification_ms": 5,
        "queue_ms": 18,
        "prefill_ms": 187,
        "decode_ms": 810,
        "ttft_ms": 205,
        "e2e_latency_ms": 1167,
        "estimated_cost_usd": 0.0062,
        "actual_cost_usd": 0.0058,
        "gpu_cb_state": "closed",
        "latency_cb_state": "closed",
        "entropy_samples": [],
    }
    defaults.update(overrides)
    return RequestTrace(**defaults)


class TestFieldSchema:
    """Verify field names match CLAUDE.md §18.1 exactly."""

    def test_all_required_fields_present(self):
        actual = {f.name for f in dataclasses.fields(RequestTrace)}
        missing = set(_REQUIRED_FIELDS) - actual
        extra = actual - set(_REQUIRED_FIELDS)
        assert not missing, f"Fields missing from RequestTrace: {sorted(missing)}"
        assert not extra, f"Unexpected fields in RequestTrace (not in §18.1): {sorted(extra)}"

    def test_field_count(self):
        assert len(dataclasses.fields(RequestTrace)) == len(_REQUIRED_FIELDS)

    def test_field_order_matches_spec(self):
        actual = [f.name for f in dataclasses.fields(RequestTrace)]
        assert actual == _REQUIRED_FIELDS, (
            "Field ORDER must match CLAUDE.md §18.1. "
            f"Diff: {list(zip(_REQUIRED_FIELDS, actual))}"
        )

    def test_instantiation_with_all_fields(self):
        t = _make_trace()
        assert t.request_id == "req_abc123def456"
        assert t.policy_version == 1
        assert t.reasoning_tokens_used == 341


class TestEntrySamples:
    def test_entropy_samples_default_empty(self):
        t = _make_trace()
        assert t.entropy_samples == []

    def test_entropy_samples_accepts_list(self):
        t = _make_trace(entropy_samples=[0.5, 1.2, 0.8])
        assert t.entropy_samples == [0.5, 1.2, 0.8]

    def test_entropy_samples_default_not_shared(self):
        t1 = _make_trace()
        t2 = _make_trace()
        t1.entropy_samples.append(99.0)
        assert t2.entropy_samples == [], "Default list must not be shared between instances"


class TestSerialization:
    def test_to_dict_returns_dict(self):
        t = _make_trace()
        d = t.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_all_fields_present(self):
        t = _make_trace()
        d = t.to_dict()
        for field_name in _REQUIRED_FIELDS:
            assert field_name in d, f"Missing key {field_name!r} in to_dict()"

    def test_to_dict_values_correct(self):
        t = _make_trace()
        d = t.to_dict()
        assert d["request_id"] == "req_abc123def456"
        assert d["complexity_score"] == 6.4
        assert d["tokens_saved"] == 171
        assert d["downgrade_reason"] is None

    def test_to_dict_entropy_samples_serialized(self):
        t = _make_trace(entropy_samples=[0.5, 1.2])
        d = t.to_dict()
        assert d["entropy_samples"] == [0.5, 1.2]


class TestOtelSpanAttributes:
    def test_returns_dict(self):
        t = _make_trace()
        attrs = t.to_otel_span_attributes()
        assert isinstance(attrs, dict)

    def test_all_keys_prefixed_ic(self):
        t = _make_trace()
        attrs = t.to_otel_span_attributes()
        for key in attrs:
            assert key.startswith("ic."), f"Non-ic key in OTel attributes: {key!r}"

    def test_no_raw_text_fields(self):
        """OTel attributes must never contain raw prompt or response text."""
        t = _make_trace()
        attrs = t.to_otel_span_attributes()
        # Verify no field name suggests raw content
        forbidden_keys = {"prompt", "response", "raw_prompt", "raw_response", "content"}
        for key in attrs:
            short = key.replace("ic.", "")
            assert short not in forbidden_keys, f"Forbidden key {key!r} in OTel attributes"

    def test_scalar_values_only(self):
        """OTel span attributes must be scalars: str, bool, int, float."""
        t = _make_trace(entropy_samples=[0.5, 1.2])
        attrs = t.to_otel_span_attributes()
        for key, val in attrs.items():
            assert isinstance(val, (str, bool, int, float)), (
                f"Non-scalar value for key {key!r}: {type(val).__name__}"
            )

    def test_entropy_samples_not_in_attributes(self):
        t = _make_trace(entropy_samples=[0.5, 1.2])
        attrs = t.to_otel_span_attributes()
        assert "ic.entropy_samples" not in attrs, (
            "entropy_samples must not appear in OTel span attributes (non-scalar list)"
        )

    def test_downgrade_reason_none_becomes_empty_string(self):
        t = _make_trace(downgrade_reason=None)
        attrs = t.to_otel_span_attributes()
        assert attrs["ic.downgrade_reason"] == ""

    def test_downgrade_reason_value_preserved(self):
        t = _make_trace(downgrade_reason="latency_circuit_breaker")
        attrs = t.to_otel_span_attributes()
        assert attrs["ic.downgrade_reason"] == "latency_circuit_breaker"


class TestFieldTypes:
    def test_policy_version_is_int(self):
        t = _make_trace(policy_version=3)
        assert isinstance(t.policy_version, int)

    def test_complexity_score_is_float(self):
        t = _make_trace(complexity_score=7.5)
        assert isinstance(t.complexity_score, float)

    def test_cache_hit_is_bool(self):
        t = _make_trace(cache_hit=True)
        assert t.cache_hit is True

    def test_gpu_cb_state_valid(self):
        for state in ("open", "closed"):
            t = _make_trace(gpu_cb_state=state)
            assert t.gpu_cb_state == state
