"""
Circuit breakers for GPU pressure and latency SLO protection.

Per CLAUDE.md Section 17 (Failure Modes 1 and 2) and Section 6:

Circuit Breaker 1 — GPU KV-Cache Pressure:
  OPEN when:  vLLM kv_cache_utilization > 0.90 (GPU_KV_CACHE_PRESSURE_THRESHOLD)
  CLOSE when: kv_cache_utilization < 0.75 for 30 consecutive seconds
  Effect:     Downgrade high/critical → medium; reject new requests above medium

Circuit Breaker 2 — Latency (P99 TTFT):
  OPEN when:  P99 TTFT > SLO threshold (LATENCY_P99_TTFT_SLO_MS env)
  CLOSE when: P99 TTFT < 0.8 × SLO for 60 consecutive seconds
  Effect:     Reject new reasoning-model requests; serve cache hits only

Both breakers:
  - Poll vLLM /metrics (Prometheus) for GPU stats
  - State exposed via /v1/circuit-breakers endpoint (CLAUDE.md Section 7)
  - State change → metric update (ic_circuit_breaker_open gauge)
  - State pushed to AdmissionController (gateway/admission_control.py)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerStatus:
    name: str
    state: BreakerState
    reason: str
    opened_at: float | None
    closed_at: float | None


class GPUPressureBreaker:
    """Opens when kv_cache_utilization > GPU_KV_CACHE_PRESSURE_THRESHOLD."""

    def __init__(self, threshold: float = 0.90) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 1 (Week 1)")

    async def poll_loop(self, vllm_metrics_url: str, interval_seconds: float = 5.0) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 1 (Week 1)")

    @property
    def is_open(self) -> bool:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 1 (Week 1)")

    def status(self) -> CircuitBreakerStatus:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 1 (Week 1)")


class LatencyBreaker:
    """Opens when P99 TTFT exceeds SLO threshold."""

    def __init__(self, slo_ms: float) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 2 (Week 1)")

    def record_ttft(self, ttft_ms: float) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 2 (Week 1)")

    @property
    def is_open(self) -> bool:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 2 (Week 1)")

    def status(self) -> CircuitBreakerStatus:
        raise NotImplementedError("Implement per CLAUDE.md Section 17 Failure Mode 2 (Week 1)")
