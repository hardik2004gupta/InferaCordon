"""
Admission control: asyncio.Semaphore gate for reasoning-model requests.

Per CLAUDE.md Section 6 Step 9:
  "The admission controller checks the current count of active reasoning
   model requests against the configured semaphore ceiling.  For low-priority
   requests when the ceiling is reached, the request is queued with a
   configurable timeout.  For high-priority requests, the timeout is extended.
   If the queue timeout is exceeded, the gateway returns 503."

Key design decisions (CLAUDE.md Section 12 + Section 8):
  - Only reasoning-model requests (budget_class != "low") consume the semaphore.
    Low budget class routes to Qwen2.5-3B (cheap model, no GPU semaphore needed).
  - Priority tier controls the wait timeout, not the admission outcome.
    "low" priority → shortest timeout; "high" priority → longest timeout.
  - On semaphore_timeout: caller raises HTTP 503 and writes audit event.
  - Caller MUST call release() in a try/finally block after inference completes.
    AdmissionResult.acquired_semaphore signals whether release() is needed.

Observable state (Phase 9 Prometheus integration):
  - active_count: current active reasoning-model requests
  - max_concurrent: configured semaphore ceiling
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ── Priority-tier wait timeouts ───────────────────────────────────────────────
# Per CLAUDE.md: low → shorter timeout, high → extended timeout.
# Values are conservative defaults tuned for single-GPU MVP.
_TIMEOUT_BY_PRIORITY: dict[str, float] = {
    "low":      5.0,
    "standard": 10.0,
    "high":     30.0,
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AdmissionResult:
    """
    Outcome of an admission_controller.acquire() call.

    acquired_semaphore: True only when the asyncio.Semaphore was actually
    acquired.  The caller must call release() in a finally block iff this
    is True, regardless of whether inference succeeds or fails.
    """
    admitted: bool
    reason: str           # "admitted" | "semaphore_timeout" | "bypass_cheap_model"
    wait_ms: float
    priority_tier: str
    acquired_semaphore: bool


# ── Admission controller ──────────────────────────────────────────────────────

class AdmissionController:
    """
    Semaphore-backed gate for reasoning-model GPU requests.

    Only requests routed to the reasoning model (DeepSeek-R1) consume a slot.
    Low budget-class requests (Qwen2.5-3B, cheap model) are passed through
    immediately per CLAUDE.md Section 6 Step 9 intent and Section 8.

    Priority tier from BudgetDecision.priority_tier controls queue timeout:
      low      → 5 s
      standard → 10 s
      high     → 30 s
    """

    def __init__(
        self,
        max_concurrent_reasoning: int = 10,
        *,
        timeout_by_priority: Optional[dict[str, float]] = None,
    ) -> None:
        self._max_concurrent = max_concurrent_reasoning
        self._semaphore = asyncio.Semaphore(max_concurrent_reasoning)
        self._timeouts = timeout_by_priority or dict(_TIMEOUT_BY_PRIORITY)
        self._active_count = 0

    async def acquire(
        self,
        budget_class: str,
        priority_tier: str,
    ) -> AdmissionResult:
        """
        Try to acquire an admission slot for a reasoning-model request.

        Low budget class (cheap model) is unconditionally admitted without
        consuming the semaphore — only GPU-resident reasoning requests count.

        Returns AdmissionResult with admitted=False on timeout; caller converts
        this to a 503 response and writes an admission-rejected audit event.
        """
        t0 = time.perf_counter()

        if budget_class == "low":
            return AdmissionResult(
                admitted=True,
                reason="bypass_cheap_model",
                wait_ms=0.0,
                priority_tier=priority_tier,
                acquired_semaphore=False,
            )

        timeout_s = self._timeouts.get(priority_tier, self._timeouts["standard"])

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            wait_ms = (time.perf_counter() - t0) * 1000.0
            log.warning(
                "AdmissionController: semaphore timeout after %.1f ms "
                "(priority=%s budget=%s active=%d/%d)",
                wait_ms, priority_tier, budget_class,
                self._active_count, self._max_concurrent,
            )
            return AdmissionResult(
                admitted=False,
                reason="semaphore_timeout",
                wait_ms=wait_ms,
                priority_tier=priority_tier,
                acquired_semaphore=False,
            )

        self._active_count += 1
        wait_ms = (time.perf_counter() - t0) * 1000.0
        log.debug(
            "AdmissionController: admitted priority=%s budget=%s "
            "wait_ms=%.1f active=%d/%d",
            priority_tier, budget_class, wait_ms,
            self._active_count, self._max_concurrent,
        )
        return AdmissionResult(
            admitted=True,
            reason="admitted",
            wait_ms=wait_ms,
            priority_tier=priority_tier,
            acquired_semaphore=True,
        )

    def release(self) -> None:
        """
        Release a previously acquired semaphore slot.

        MUST be called in a finally block after inference completes.
        Only call when AdmissionResult.acquired_semaphore is True.
        """
        self._active_count -= 1
        self._semaphore.release()

    # ── Observable state ──────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        """Current number of active reasoning-model requests holding a slot."""
        return self._active_count

    @property
    def max_concurrent(self) -> int:
        """Configured semaphore ceiling."""
        return self._max_concurrent

    def update_circuit_breaker_state(self, gpu_open: bool, latency_open: bool) -> None:
        """
        Receive circuit breaker state updates from vllm_adapter.
        Phase 7 will use this to dynamically tighten timeouts when GPU pressure
        or latency circuit breakers are open.  Currently a no-op placeholder —
        fleet-pressure downgrade is handled at the budget-class level via
        assign_budget_class().
        """
        log.debug(
            "AdmissionController CB state: gpu_open=%s latency_open=%s",
            gpu_open, latency_open,
        )
