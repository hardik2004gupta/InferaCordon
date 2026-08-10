"""
Unit tests for gateway/escalation_handler.py.

Coverage:
  EscalationDecision fields
  should_escalate() — all decision paths:
    escalation_disabled
    verification_not_failed (correct, unverifiable, skipped)
    max_retries_exhausted
    already_at_max (critical → no higher class)
    unknown_budget_class
    escalating (low→medium, medium→high, high→critical)
"""
from __future__ import annotations

import pytest

from gateway.escalation_handler import EscalationDecision, EscalationHandler


@pytest.fixture
def handler():
    return EscalationHandler()


# ── EscalationDecision ────────────────────────────────────────────────────────

class TestEscalationDecisionFields:
    def test_escalate_true(self):
        d = EscalationDecision(escalate=True, next_budget_class="high", reason="escalating")
        assert d.escalate is True

    def test_next_budget_class(self):
        d = EscalationDecision(escalate=True, next_budget_class="high", reason="escalating")
        assert d.next_budget_class == "high"

    def test_reason(self):
        d = EscalationDecision(escalate=False, next_budget_class=None, reason="max_retries_exhausted")
        assert d.reason == "max_retries_exhausted"

    def test_no_escalate_next_class_none(self):
        d = EscalationDecision(escalate=False, next_budget_class=None, reason="escalation_disabled")
        assert d.next_budget_class is None


# ── should_escalate() — disabled ──────────────────────────────────────────────

class TestEscalationDisabled:
    def test_disabled_incorrect_returns_no_escalate(self, handler):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=False,
            policy_max_retries=1,
        )
        assert d.escalate is False

    def test_disabled_reason(self, handler):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=False,
            policy_max_retries=1,
        )
        assert d.reason == "escalation_disabled"

    def test_disabled_next_class_none(self, handler):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=False,
            policy_max_retries=1,
        )
        assert d.next_budget_class is None


# ── should_escalate() — verification not failed ───────────────────────────────

class TestVerificationNotFailed:
    """Only 'incorrect' triggers escalation."""

    @pytest.mark.parametrize("vr", ["correct", "unverifiable", "skipped"])
    def test_non_incorrect_no_escalate(self, handler, vr):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result=vr,
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is False

    @pytest.mark.parametrize("vr", ["correct", "unverifiable", "skipped"])
    def test_non_incorrect_reason(self, handler, vr):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result=vr,
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.reason == "verification_not_failed"

    def test_unverifiable_does_not_escalate(self, handler):
        """Key CLAUDE.md §16 invariant: UNVERIFIABLE ≠ quality failure."""
        d = handler.should_escalate(
            current_budget_class="low",
            verification_result="unverifiable",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is False


# ── should_escalate() — max retries exhausted ─────────────────────────────────

class TestMaxRetriesExhausted:
    def test_retry_count_equals_max_retries(self, handler):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=1,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is False
        assert d.reason == "max_retries_exhausted"

    def test_retry_count_exceeds_max_retries(self, handler):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=5,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is False

    def test_zero_max_retries_never_escalates(self, handler):
        d = handler.should_escalate(
            current_budget_class="low",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=0,
        )
        assert d.escalate is False
        assert d.reason == "max_retries_exhausted"


# ── should_escalate() — already at max ────────────────────────────────────────

class TestAlreadyAtMax:
    def test_critical_cannot_escalate(self, handler):
        d = handler.should_escalate(
            current_budget_class="critical",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=5,
        )
        assert d.escalate is False
        assert d.reason == "already_at_max"

    def test_unknown_budget_class(self, handler):
        d = handler.should_escalate(
            current_budget_class="ultra",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is False
        assert d.reason == "unknown_budget_class"


# ── should_escalate() — successful escalation paths ──────────────────────────

class TestEscalatingPaths:
    @pytest.mark.parametrize("current,expected_next", [
        ("low", "medium"),
        ("medium", "high"),
        ("high", "critical"),
    ])
    def test_escalation_path(self, handler, current, expected_next):
        d = handler.should_escalate(
            current_budget_class=current,
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is True
        assert d.next_budget_class == expected_next
        assert d.reason == "escalating"

    def test_escalating_next_class_is_one_step_up(self, handler):
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.next_budget_class == "high"

    def test_mvp_single_retry_first_attempt_escalates(self, handler):
        """MVP: max_retries=1, retry_count=0 → should escalate."""
        d = handler.should_escalate(
            current_budget_class="medium",
            verification_result="incorrect",
            retry_count=0,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is True

    def test_mvp_single_retry_second_attempt_does_not(self, handler):
        """MVP: max_retries=1, retry_count=1 → exhausted."""
        d = handler.should_escalate(
            current_budget_class="high",
            verification_result="incorrect",
            retry_count=1,
            policy_escalation_enabled=True,
            policy_max_retries=1,
        )
        assert d.escalate is False
        assert d.reason == "max_retries_exhausted"
