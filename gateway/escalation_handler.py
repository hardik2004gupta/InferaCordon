"""
Budget class escalation handler.

Per CLAUDE.md Section 16:
  - Triggered when verification returns "incorrect" (NOT "unverifiable" — that is
    not a quality failure and does not justify additional compute spend).
  - Monotonic upward: low → medium → high → critical.
  - Cannot escalate beyond "critical".
  - Max retries governed by policy.escalation.max_retries (MVP default: 1).
  - On exhaustion: on_exhaustion = "return_low_confidence" — response is returned
    with confidence_level: "low" added to the response body.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_BUDGET_CLASS_ORDER = ["low", "medium", "high", "critical"]


@dataclass
class EscalationDecision:
    escalate: bool
    next_budget_class: Optional[str]
    reason: str    # "escalating" | "max_retries_exhausted" | "already_at_max"
                   # | "verification_not_failed" | "escalation_disabled"
                   # | "unknown_budget_class"


class EscalationHandler:
    """
    Stateless escalation logic.
    One instance can be shared across all concurrent requests.
    """

    def should_escalate(
        self,
        current_budget_class: str,
        verification_result: str,
        retry_count: int,
        policy_escalation_enabled: bool,
        policy_max_retries: int,
    ) -> EscalationDecision:
        """
        Determine whether a failed verification justifies escalating to the
        next budget class.

        Args:
            current_budget_class:    Current effective class ("low"|"medium"|"high"|"critical").
            verification_result:     "correct"|"incorrect"|"unverifiable"|"skipped".
                                     Only "incorrect" triggers escalation.
            retry_count:             Number of escalation retries already performed
                                     (0 = this is the first attempt).
            policy_escalation_enabled: policy.escalation.enabled
            policy_max_retries:      policy.escalation.max_retries (MVP = 1)

        Returns:
            EscalationDecision with escalate=True when escalation should proceed.
        """
        if not policy_escalation_enabled:
            return EscalationDecision(
                escalate=False, next_budget_class=None, reason="escalation_disabled",
            )

        # UNVERIFIABLE is not a quality failure — do not escalate.
        if verification_result != "incorrect":
            return EscalationDecision(
                escalate=False, next_budget_class=None, reason="verification_not_failed",
            )

        if retry_count >= policy_max_retries:
            return EscalationDecision(
                escalate=False, next_budget_class=None, reason="max_retries_exhausted",
            )

        try:
            idx = _BUDGET_CLASS_ORDER.index(current_budget_class)
        except ValueError:
            return EscalationDecision(
                escalate=False, next_budget_class=None, reason="unknown_budget_class",
            )

        if idx >= len(_BUDGET_CLASS_ORDER) - 1:
            return EscalationDecision(
                escalate=False, next_budget_class=None, reason="already_at_max",
            )

        return EscalationDecision(
            escalate=True,
            next_budget_class=_BUDGET_CLASS_ORDER[idx + 1],
            reason="escalating",
        )
