"""
Model routing: select cheap (Qwen) or reasoning (DeepSeek) path per budget class.

Per CLAUDE.md Section 12 and policy budget_profiles:
- low budget class  → qwen25-3b (0 reasoning tokens, direct template)
- medium/high/critical → deepseek-r1-7b (with BudgetLogitProcessor token cap)
- Routing decision logged in RequestTrace.route field (CLAUDE.md Section 18)
- Model version included in audit decision record
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RouteTarget(str, Enum):
    CHEAP = "cheap_model"
    REASONING = "reasoning_model"


@dataclass
class RoutingDecision:
    target: RouteTarget
    model_id: str
    max_reasoning_tokens: int
    max_output_tokens: int
    prompt_version: str


class ModelRouter:
    """Selects model route from policy budget profile."""

    def route(self, budget_class: str, policy: dict) -> RoutingDecision:
        raise NotImplementedError("Implement per CLAUDE.md Section 12 (Week 1)")
