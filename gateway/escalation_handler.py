"""
Budget class escalation handler.

Per CLAUDE.md Section 12 and policy escalation config:
- Retry at next-higher budget class when verification fails (INCORRECT)
- Max retries per policy (default: 1)
- On retry exhaustion: policy.escalation.on_exhaustion → return_low_confidence
- Escalation path: low→medium→high→critical (cannot escalate beyond critical)
- Emits ic_escalation_total metric (CLAUDE.md Section 18)
- Escalation reason recorded in audit decision record (downgrade_reason / escalation)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class EscalationDecision:
    escalate: bool
    next_budget_class: Optional[str]
    reason: str


class EscalationHandler:
    """Determines whether and how to escalate a failed request."""

    def should_escalate(
        self,
        current_budget_class: str,
        verification_result: str,
        retry_count: int,
        policy: dict,
    ) -> EscalationDecision:
        raise NotImplementedError("Implement per CLAUDE.md Section 12 (Week 3)")
