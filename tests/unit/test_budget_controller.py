"""
Unit tests for budget controller (policy_engine/budget_controller.py).

Coverage:
  - All four budget classes from complexity score
  - Boundary values: exactly at 3.5/6.5/8.5
  - Model routing (cheap vs reasoning)
  - Circuit breaker downgrades (latency CB + GPU pressure CB)
  - Priority tier derivation
  - downgrade_one() helper
  - BudgetDecision immutability
  - DecisionRecord factory and serialization
  - Fast-path score (-1) → medium class
  - Policy provenance fields are populated
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

from policy_engine.validator import Policy
from policy_engine.budget_controller import (
    BudgetDecision,
    DecisionRecord,
    FleetState,
    assign_budget_class,
    downgrade_one,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

POLICY_DIR = Path(__file__).parent.parent.parent / "policy_engine" / "policies"


def _load_policy(filename: str) -> Policy:
    data = yaml.safe_load((POLICY_DIR / filename).read_text(encoding="utf-8"))
    return Policy.model_validate(data)


@pytest.fixture
def acme_policy() -> Policy:
    return _load_policy("acme_corp_general_qa_v1.yaml")


@pytest.fixture
def fleet_nominal() -> FleetState:
    return FleetState.nominal()


def _assign(score: float, policy: Policy, fleet: FleetState = None) -> BudgetDecision:
    return assign_budget_class(score, policy, fleet or FleetState.nominal())


# ── 1. Basic budget class mapping ─────────────────────────────────────────────

class TestBasicMapping:

    def test_score_zero_is_low(self, acme_policy, fleet_nominal):
        result = _assign(0.0, acme_policy, fleet_nominal)
        assert result.base_class == "low"
        assert result.effective_class == "low"

    def test_score_one_is_low(self, acme_policy, fleet_nominal):
        result = _assign(1.0, acme_policy, fleet_nominal)
        assert result.base_class == "low"

    def test_score_at_low_max_is_low(self, acme_policy, fleet_nominal):
        # Per CLAUDE.md Section 12.1: complexity_score <= low_max → "low"
        result = _assign(3.5, acme_policy, fleet_nominal)
        assert result.base_class == "low"

    def test_score_just_above_low_max_is_medium(self, acme_policy, fleet_nominal):
        result = _assign(3.51, acme_policy, fleet_nominal)
        assert result.base_class == "medium"

    def test_score_at_medium_max_is_medium(self, acme_policy, fleet_nominal):
        result = _assign(6.5, acme_policy, fleet_nominal)
        assert result.base_class == "medium"

    def test_score_just_above_medium_max_is_high(self, acme_policy, fleet_nominal):
        result = _assign(6.51, acme_policy, fleet_nominal)
        assert result.base_class == "high"

    def test_score_at_high_max_is_high(self, acme_policy, fleet_nominal):
        result = _assign(8.5, acme_policy, fleet_nominal)
        assert result.base_class == "high"

    def test_score_just_above_high_max_is_critical(self, acme_policy, fleet_nominal):
        result = _assign(8.51, acme_policy, fleet_nominal)
        assert result.base_class == "critical"

    def test_score_ten_is_critical(self, acme_policy, fleet_nominal):
        result = _assign(10.0, acme_policy, fleet_nominal)
        assert result.base_class == "critical"

    def test_fast_path_score_negative_one_is_medium(self, acme_policy, fleet_nominal):
        # CLAUDE.md Section 6 Step 4: fast-path → medium budget class
        result = _assign(-1.0, acme_policy, fleet_nominal)
        assert result.base_class == "medium"
        assert result.effective_class == "medium"


# ── 2. Model routing ──────────────────────────────────────────────────────────

class TestModelRouting:

    def test_low_class_uses_cheap_model(self, acme_policy):
        result = _assign(1.0, acme_policy)
        assert result.model == "qwen25-3b"
        assert result.route == "cheap_model"

    def test_medium_class_uses_reasoning_model(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.model == "deepseek-r1-7b"
        assert result.route == "reasoning_model"

    def test_high_class_uses_reasoning_model(self, acme_policy):
        result = _assign(7.5, acme_policy)
        assert result.model == "deepseek-r1-7b"
        assert result.route == "reasoning_model"

    def test_critical_class_uses_reasoning_model(self, acme_policy):
        result = _assign(9.5, acme_policy)
        assert result.model == "deepseek-r1-7b"
        assert result.route == "reasoning_model"

    def test_low_class_zero_reasoning_tokens(self, acme_policy):
        result = _assign(1.0, acme_policy)
        assert result.max_reasoning_tokens == 0

    def test_medium_class_512_reasoning_tokens(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.max_reasoning_tokens == 512

    def test_high_class_1024_reasoning_tokens(self, acme_policy):
        result = _assign(7.5, acme_policy)
        assert result.max_reasoning_tokens == 1024

    def test_critical_class_2048_reasoning_tokens(self, acme_policy):
        result = _assign(9.5, acme_policy)
        assert result.max_reasoning_tokens == 2048


# ── 3. Priority tier derivation ───────────────────────────────────────────────

class TestPriorityTier:

    def test_low_class_has_low_priority(self, acme_policy):
        result = _assign(1.0, acme_policy)
        assert result.priority_tier == "low"

    def test_medium_class_has_standard_priority(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.priority_tier == "standard"

    def test_high_class_has_standard_priority(self, acme_policy):
        result = _assign(7.5, acme_policy)
        assert result.priority_tier == "standard"

    def test_critical_class_has_high_priority(self, acme_policy):
        result = _assign(9.5, acme_policy)
        assert result.priority_tier == "high"


# ── 4. downgrade_one() ────────────────────────────────────────────────────────

class TestDowngradeOne:

    def test_critical_downgrades_to_high(self):
        assert downgrade_one("critical") == "high"

    def test_high_downgrades_to_medium(self):
        assert downgrade_one("high") == "medium"

    def test_medium_downgrades_to_low(self):
        assert downgrade_one("medium") == "low"

    def test_low_stays_low(self):
        assert downgrade_one("low") == "low"


# ── 5. Latency circuit breaker downgrade ─────────────────────────────────────

class TestLatencyCBDowngrade:

    def test_latency_cb_open_medium_downgrades_to_low(self, acme_policy):
        fleet = FleetState(latency_cb_open=True)
        result = _assign(5.0, acme_policy, fleet)
        assert result.effective_class == "low"
        assert result.base_class == "medium"
        assert result.downgrade_reason == "latency_circuit_breaker"

    def test_latency_cb_open_high_downgrades_to_medium(self, acme_policy):
        fleet = FleetState(latency_cb_open=True)
        result = _assign(7.5, acme_policy, fleet)
        assert result.effective_class == "medium"
        assert result.downgrade_reason == "latency_circuit_breaker"

    def test_latency_cb_open_critical_not_downgraded(self, acme_policy):
        # Per CLAUDE.md Section 12.1: "if fleet_state.latency_cb_open and base_class != 'critical'"
        fleet = FleetState(latency_cb_open=True)
        result = _assign(9.5, acme_policy, fleet)
        assert result.effective_class == "critical"
        assert result.downgrade_reason is None

    def test_latency_cb_open_low_downgrades_to_low(self, acme_policy):
        # low → downgrade_one("low") = "low" — no-op downgrade
        fleet = FleetState(latency_cb_open=True)
        result = _assign(1.0, acme_policy, fleet)
        assert result.effective_class == "low"
        assert result.downgrade_reason == "latency_circuit_breaker"

    def test_latency_cb_closed_no_downgrade(self, acme_policy):
        fleet = FleetState(latency_cb_open=False)
        result = _assign(7.5, acme_policy, fleet)
        assert result.effective_class == "high"
        assert result.downgrade_reason is None


# ── 6. GPU pressure circuit breaker ──────────────────────────────────────────

class TestGPUPressureCB:

    def test_gpu_pressure_cb_open_low_stays_low(self, acme_policy):
        # Per CLAUDE.md Section 12.1: "gpu_pressure_cb_open and base_class == 'low'"
        # → effective_class = "low", downgrade_reason = None
        fleet = FleetState(gpu_pressure_cb_open=True)
        result = _assign(1.0, acme_policy, fleet)
        assert result.effective_class == "low"
        assert result.downgrade_reason is None

    def test_gpu_pressure_cb_open_medium_not_downgraded(self, acme_policy):
        # GPU pressure CB only affects low-priority routing for low class
        # Per CLAUDE.md Section 12.1: the elif branch only applies when base_class == "low"
        fleet = FleetState(gpu_pressure_cb_open=True)
        result = _assign(5.0, acme_policy, fleet)
        assert result.effective_class == "medium"
        assert result.downgrade_reason is None

    def test_gpu_pressure_cb_open_high_not_downgraded(self, acme_policy):
        fleet = FleetState(gpu_pressure_cb_open=True)
        result = _assign(7.5, acme_policy, fleet)
        assert result.effective_class == "high"

    def test_both_cbs_open_latency_takes_precedence(self, acme_policy):
        # Per CLAUDE.md Section 12.1: latency CB checked first (elif chain)
        fleet = FleetState(latency_cb_open=True, gpu_pressure_cb_open=True)
        result = _assign(5.0, acme_policy, fleet)
        assert result.effective_class == "low"
        assert result.downgrade_reason == "latency_circuit_breaker"

    def test_fleet_nominal_no_downgrade(self, acme_policy, fleet_nominal):
        result = _assign(7.5, acme_policy, fleet_nominal)
        assert result.effective_class == "high"
        assert result.downgrade_reason is None


# ── 7. BudgetDecision immutability ────────────────────────────────────────────

class TestBudgetDecisionImmutability:

    def test_budget_decision_is_frozen(self, acme_policy):
        result = _assign(5.0, acme_policy)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.base_class = "critical"  # type: ignore[misc]

    def test_budget_decision_is_hashable(self, acme_policy):
        result = _assign(5.0, acme_policy)
        # Frozen dataclasses are hashable by default
        _ = hash(result)


# ── 8. Policy provenance in BudgetDecision ────────────────────────────────────

class TestPolicyProvenance:

    def test_policy_id_populated(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.policy_id == "enterprise_standard_v1"

    def test_policy_version_populated(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.policy_version == 1

    def test_cost_ceiling_from_policy(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.cost_ceiling_usd == 0.05

    def test_p95_latency_from_policy(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.p95_latency_ms == 4000

    def test_quality_floor_from_policy(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.quality_floor_score == 3.5

    def test_escalation_fields_from_policy(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.escalation_enabled is True
        assert result.escalation_max_retries == 1
        assert result.escalation_on_exhaustion == "return_low_confidence"

    def test_cache_fields_from_policy(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.cache_enabled is True
        assert result.cache_similarity_threshold == 0.92
        assert result.cache_ttl_seconds == 3600

    def test_guardrail_fields_from_policy(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.guardrail_pii_redaction == "standard"
        assert result.guardrail_injection_check == "conditional"
        assert result.guardrail_safety_check == "conditional"
        assert result.guardrail_output_safety == "async"


# ── 9. Verification policy ────────────────────────────────────────────────────

class TestVerificationPolicy:

    def test_low_class_verification_none(self, acme_policy):
        result = _assign(1.0, acme_policy)
        assert result.verification == "none"

    def test_medium_class_verification_verifiable_only(self, acme_policy):
        result = _assign(5.0, acme_policy)
        assert result.verification == "verifiable_only"

    def test_high_class_verification_required(self, acme_policy):
        result = _assign(7.5, acme_policy)
        assert result.verification == "required"

    def test_critical_class_verification_required(self, acme_policy):
        result = _assign(9.5, acme_policy)
        assert result.verification == "required"


# ── 10. DecisionRecord factory ────────────────────────────────────────────────

class TestDecisionRecord:

    def test_from_budget_decision_populates_all_fields(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_abc123",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
        )
        assert record.request_id == "req_abc123"
        assert record.tenant_id == "acme_corp"
        assert record.domain == "general_qa"
        assert record.policy_id == "enterprise_standard_v1"
        assert record.policy_version == 1
        assert record.complexity_score == 5.0
        assert record.fast_path_used is False
        assert record.base_budget_class == "medium"
        assert record.effective_budget_class == "medium"
        assert record.route == "reasoning_model"
        assert record.model_version == "deepseek-r1-7b"

    def test_decision_record_has_record_type(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_xyz",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
        )
        assert record.record_type == "decision"

    def test_fast_path_flag_propagated(self, acme_policy):
        budget = _assign(-1.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_fast",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=-1.0,
            fast_path_used=True,
            budget=budget,
            policy=acme_policy,
        )
        assert record.fast_path_used is True
        assert record.complexity_score == -1.0

    def test_policy_fallback_flag(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_fallback",
            tenant_id="unknown_tenant",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
            policy_fallback_used=True,
        )
        assert record.policy_fallback_used is True

    def test_to_audit_dict_has_all_section_19_1_fields(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_audit",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
        )
        d = record.to_audit_dict()

        # Per CLAUDE.md Section 19.1 — exact field list
        required_fields = {
            "record_type", "timestamp_iso", "request_id", "tenant_id", "domain",
            "policy_id", "policy_version", "model_version", "prompt_version",
            "guardrail_version", "verifier_version", "complexity_score",
            "fast_path_used", "base_budget_class", "effective_budget_class",
            "downgrade_reason", "priority_tier", "max_reasoning_tokens",
            "max_output_tokens", "route", "cache_hit", "admission_result",
            "estimated_cost_usd",
        }
        assert required_fields.issubset(set(d.keys()))

    def test_to_audit_dict_excludes_internal_flags(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_audit",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
            policy_fallback_used=True,
        )
        d = record.to_audit_dict()
        # Internal flag should NOT appear in serialized audit record
        assert "policy_fallback_used" not in d

    def test_to_audit_dict_values_are_correct_types(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_types",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
        )
        d = record.to_audit_dict()
        assert isinstance(d["complexity_score"], float)
        assert isinstance(d["policy_version"], int)
        assert isinstance(d["fast_path_used"], bool)
        assert isinstance(d["max_reasoning_tokens"], int)
        assert isinstance(d["estimated_cost_usd"], float)
        assert d["record_type"] == "decision"

    def test_timestamp_iso_is_utc_formatted(self, acme_policy):
        budget = _assign(5.0, acme_policy)
        record = DecisionRecord.from_budget_decision(
            request_id="req_ts",
            tenant_id="acme_corp",
            domain="general_qa",
            complexity_score=5.0,
            fast_path_used=False,
            budget=budget,
            policy=acme_policy,
        )
        # ISO format with timezone offset or Z suffix
        assert record.timestamp_iso != ""
        assert "T" in record.timestamp_iso


# ── 11. FleetState ────────────────────────────────────────────────────────────

class TestFleetState:

    def test_nominal_all_closed(self):
        fleet = FleetState.nominal()
        assert fleet.gpu_pressure_cb_open is False
        assert fleet.latency_cb_open is False

    def test_defaults_are_closed(self):
        fleet = FleetState()
        assert fleet.gpu_pressure_cb_open is False
        assert fleet.latency_cb_open is False
