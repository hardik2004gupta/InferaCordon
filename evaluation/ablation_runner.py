"""
Seven-layer ablation runner.

Per CLAUDE.md Section 20 ablation table:
  Layer 1: Full system (all components active)
  Layer 2: No semantic cache
  Layer 3: No budget enforcement (unlimited reasoning tokens)
  Layer 4: Fixed budget class (all requests → medium)
  Layer 5: No guardrails
  Layer 6: No verification
  Layer 7: No circuit breakers
Each layer measures: cost/correct, quality score, latency P95, cache hit rate.
"""
from __future__ import annotations

from dataclasses import dataclass


ABLATION_LAYERS = [
    "full_system",
    "no_semantic_cache",
    "no_budget_enforcement",
    "fixed_budget_medium",
    "no_guardrails",
    "no_verification",
    "no_circuit_breakers",
]


@dataclass
class AblationResult:
    layer: str
    dataset: str
    cost_per_correct: float
    quality_score: float
    p95_latency_ms: float
    cache_hit_rate: float


class AblationRunner:
    def __init__(self, gateway_url: str, admin_api_key: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 12)")

    def run_layer(self, layer: str, dataset: str) -> AblationResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 12)")

    def run_all(self, dataset: str) -> list[AblationResult]:
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 12)")
