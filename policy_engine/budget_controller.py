"""
Budget controller: maps complexity score → budget class, with GPU-pressure override.

Per CLAUDE.md Section 12 (assign_budget_class pseudocode):

    def assign_budget_class(complexity_score, policy, fleet_state):
        # Base class from complexity thresholds
        if complexity_score <= policy.complexity_thresholds.low_max:
            base = "low"
        elif complexity_score <= policy.complexity_thresholds.medium_max:
            base = "medium"
        elif complexity_score <= policy.complexity_thresholds.high_max:
            base = "high"
        else:
            base = "critical"

        # GPU pressure downgrade
        if fleet_state.gpu_kv_cache_utilization > GPU_PRESSURE_THRESHOLD:
            if base in ("high", "critical"):
                return ("medium", "gpu_pressure_downgrade")

        return (base, None)

FleetState schema defined in CLAUDE.md Section 32 (Architectural Assumptions).
Implements the Budget Controller described in CLAUDE.md Section 12.
Resides in policy_engine/ per Part IX (not gateway/routing/ from Component 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class FleetState:
    """Snapshot of vLLM fleet health. Per CLAUDE.md Section 32."""
    gpu_kv_cache_utilization: float   # 0.0–1.0
    running_requests: int
    waiting_requests: int
    gpu_pressure_circuit_open: bool
    latency_circuit_open: bool


def assign_budget_class(
    complexity_score: float,
    policy: object,
    fleet_state: FleetState,
) -> Tuple[str, Optional[str]]:
    """
    Return (budget_class, downgrade_reason).
    downgrade_reason is None when no downgrade applied.
    Per CLAUDE.md Section 12 pseudocode.
    """
    raise NotImplementedError("Implement per CLAUDE.md Section 12 (Week 1)")
