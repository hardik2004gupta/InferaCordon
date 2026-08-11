"""
Unit tests for gateway/admission_control.py.

Coverage:
- AdmissionResult: all fields and defaults
- AdmissionController: construction, max_concurrent, default timeouts
- acquire() — low budget class: always admitted, no semaphore consumed
- acquire() — reasoning class: semaphore acquired, active_count incremented
- acquire() — reasoning class at capacity: blocks, then times out → admitted=False
- acquire() — priority tier controls timeout duration
- release(): decrements active_count, releases semaphore
- acquired_semaphore field: False for cheap model, True for reasoning model
- Sequential acquire/release cycle: semaphore correctly recyclable
- update_circuit_breaker_state(): no-op, does not raise
- active_count / max_concurrent properties

All tests are synchronous wrappers around async logic via asyncio.run().
No external dependencies — asyncio.Semaphore is self-contained.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from gateway.admission_control import (
    AdmissionController,
    AdmissionResult,
    _TIMEOUT_BY_PRIORITY,
)

# ── Helper ─────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


# ── AdmissionResult ────────────────────────────────────────────────────────────

class TestAdmissionResultFields:
    def test_admitted_field(self):
        r = AdmissionResult(
            admitted=True, reason="admitted", wait_ms=3.0,
            priority_tier="standard", acquired_semaphore=True,
        )
        assert r.admitted is True

    def test_reason_field(self):
        r = AdmissionResult(
            admitted=False, reason="semaphore_timeout", wait_ms=10001.0,
            priority_tier="low", acquired_semaphore=False,
        )
        assert r.reason == "semaphore_timeout"

    def test_wait_ms_field(self):
        r = AdmissionResult(
            admitted=True, reason="bypass_cheap_model", wait_ms=0.0,
            priority_tier="low", acquired_semaphore=False,
        )
        assert r.wait_ms == pytest.approx(0.0)

    def test_priority_tier_field(self):
        r = AdmissionResult(
            admitted=True, reason="admitted", wait_ms=1.0,
            priority_tier="high", acquired_semaphore=True,
        )
        assert r.priority_tier == "high"

    def test_acquired_semaphore_true(self):
        r = AdmissionResult(
            admitted=True, reason="admitted", wait_ms=1.0,
            priority_tier="standard", acquired_semaphore=True,
        )
        assert r.acquired_semaphore is True

    def test_acquired_semaphore_false(self):
        r = AdmissionResult(
            admitted=True, reason="bypass_cheap_model", wait_ms=0.0,
            priority_tier="low", acquired_semaphore=False,
        )
        assert r.acquired_semaphore is False


# ── AdmissionController construction ──────────────────────────────────────────

class TestAdmissionControllerConstruction:
    def test_default_max_concurrent(self):
        ctrl = AdmissionController()
        assert ctrl.max_concurrent == 10

    def test_custom_max_concurrent(self):
        ctrl = AdmissionController(max_concurrent_reasoning=5)
        assert ctrl.max_concurrent == 5

    def test_initial_active_count_zero(self):
        ctrl = AdmissionController()
        assert ctrl.active_count == 0

    def test_default_timeouts_present(self):
        ctrl = AdmissionController()
        # All priority tiers must have a configured timeout
        for tier in ("low", "standard", "high"):
            assert tier in ctrl._timeouts

    def test_custom_timeout_overrides_default(self):
        ctrl = AdmissionController(timeout_by_priority={"low": 99.0, "standard": 99.0, "high": 99.0})
        assert ctrl._timeouts["low"] == 99.0

    def test_module_default_timeout_low_lt_standard(self):
        assert _TIMEOUT_BY_PRIORITY["low"] < _TIMEOUT_BY_PRIORITY["standard"]

    def test_module_default_timeout_standard_lt_high(self):
        assert _TIMEOUT_BY_PRIORITY["standard"] < _TIMEOUT_BY_PRIORITY["high"]


# ── acquire() — low budget class (cheap model bypass) ─────────────────────────

class TestAcquireLowBudgetClass:
    """
    Per CLAUDE.md Section 6 Step 9: only reasoning-model requests consume
    the semaphore.  Low budget class (Qwen, cheap model) is bypassed.
    """

    def test_low_budget_admitted(self):
        async def run():
            ctrl = AdmissionController(max_concurrent_reasoning=0)  # cap=0 — would block all
            result = await ctrl.acquire(budget_class="low", priority_tier="low")
            return result
        result = _run(run())
        assert result.admitted is True

    def test_low_budget_bypass_reason(self):
        result = _run(AdmissionController().acquire("low", "low"))
        assert result.reason == "bypass_cheap_model"

    def test_low_budget_no_semaphore_acquired(self):
        result = _run(AdmissionController().acquire("low", "low"))
        assert result.acquired_semaphore is False

    def test_low_budget_wait_ms_is_zero(self):
        result = _run(AdmissionController().acquire("low", "low"))
        assert result.wait_ms == pytest.approx(0.0)

    def test_low_budget_does_not_increment_active_count(self):
        async def run():
            ctrl = AdmissionController()
            await ctrl.acquire("low", "low")
            return ctrl.active_count
        assert _run(run()) == 0

    def test_low_budget_priority_tier_preserved(self):
        result = _run(AdmissionController().acquire("low", "low"))
        assert result.priority_tier == "low"


# ── acquire() — reasoning model admitted ──────────────────────────────────────

class TestAcquireReasoningAdmitted:
    """Reasoning-model requests acquire the semaphore when capacity is available."""

    def _make(self, max_concurrent=10):
        return AdmissionController(
            max_concurrent_reasoning=max_concurrent,
            timeout_by_priority={"low": 5.0, "standard": 5.0, "high": 5.0},
        )

    def test_medium_admitted(self):
        result = _run(self._make().acquire("medium", "standard"))
        assert result.admitted is True

    def test_high_admitted(self):
        result = _run(self._make().acquire("high", "standard"))
        assert result.admitted is True

    def test_critical_admitted(self):
        result = _run(self._make().acquire("critical", "high"))
        assert result.admitted is True

    def test_admitted_reason(self):
        result = _run(self._make().acquire("medium", "standard"))
        assert result.reason == "admitted"

    def test_acquired_semaphore_true(self):
        result = _run(self._make().acquire("medium", "standard"))
        assert result.acquired_semaphore is True

    def test_active_count_incremented(self):
        async def run():
            ctrl = self._make()
            await ctrl.acquire("medium", "standard")
            return ctrl.active_count
        assert _run(run()) == 1

    def test_active_count_two_after_two_acquires(self):
        async def run():
            ctrl = self._make(max_concurrent=10)
            await ctrl.acquire("medium", "standard")
            await ctrl.acquire("high", "high")
            return ctrl.active_count
        assert _run(run()) == 2

    def test_wait_ms_is_non_negative(self):
        result = _run(self._make().acquire("medium", "standard"))
        assert result.wait_ms >= 0.0

    def test_priority_tier_in_result(self):
        result = _run(self._make().acquire("medium", "standard"))
        assert result.priority_tier == "standard"


# ── acquire() — semaphore timeout ─────────────────────────────────────────────

class TestAcquireTimeout:
    """
    When the semaphore ceiling is exhausted and the queue timeout expires,
    acquire() must return admitted=False (not raise).
    """

    def _make_full_ctrl(self, timeout=0.02):
        """Controller with cap=1 and very short timeout for testing."""
        return AdmissionController(
            max_concurrent_reasoning=1,
            timeout_by_priority={"low": timeout, "standard": timeout, "high": timeout},
        )

    def test_timeout_returns_admitted_false(self):
        async def run():
            ctrl = self._make_full_ctrl()
            # Fill the one slot
            r1 = await ctrl.acquire("medium", "standard")
            assert r1.admitted
            # Second acquire must timeout
            r2 = await ctrl.acquire("medium", "standard")
            return r2
        result = _run(run())
        assert result.admitted is False

    def test_timeout_reason(self):
        async def run():
            ctrl = self._make_full_ctrl()
            await ctrl.acquire("medium", "standard")
            return await ctrl.acquire("medium", "standard")
        result = _run(run())
        assert result.reason == "semaphore_timeout"

    def test_timeout_acquired_semaphore_false(self):
        async def run():
            ctrl = self._make_full_ctrl()
            await ctrl.acquire("medium", "standard")
            return await ctrl.acquire("medium", "standard")
        result = _run(run())
        assert result.acquired_semaphore is False

    def test_timeout_does_not_raise(self):
        async def run():
            ctrl = self._make_full_ctrl()
            await ctrl.acquire("medium", "standard")
            return await ctrl.acquire("medium", "standard")
        _run(run())  # must not raise

    def test_active_count_unchanged_on_timeout(self):
        async def run():
            ctrl = self._make_full_ctrl()
            await ctrl.acquire("medium", "standard")
            r2 = await ctrl.acquire("medium", "standard")
            assert not r2.admitted
            return ctrl.active_count
        assert _run(run()) == 1

    def test_wait_ms_reflects_actual_wait(self):
        async def run():
            ctrl = self._make_full_ctrl(timeout=0.05)
            await ctrl.acquire("medium", "standard")
            return await ctrl.acquire("medium", "standard")
        result = _run(run())
        assert result.wait_ms >= 40.0  # waited at least ~50ms


# ── release() ─────────────────────────────────────────────────────────────────

class TestRelease:
    def test_release_decrements_active_count(self):
        async def run():
            ctrl = AdmissionController(
                max_concurrent_reasoning=10,
                timeout_by_priority={"low": 5.0, "standard": 5.0, "high": 5.0},
            )
            await ctrl.acquire("medium", "standard")
            assert ctrl.active_count == 1
            ctrl.release()
            return ctrl.active_count
        assert _run(run()) == 0

    def test_release_makes_slot_available(self):
        async def run():
            ctrl = AdmissionController(
                max_concurrent_reasoning=1,
                timeout_by_priority={"low": 5.0, "standard": 5.0, "high": 5.0},
            )
            r1 = await ctrl.acquire("medium", "standard")
            assert r1.admitted
            ctrl.release()
            r2 = await ctrl.acquire("medium", "standard")
            return r2
        result = _run(run())
        assert result.admitted is True

    def test_acquire_release_cycle_reusable(self):
        """Semaphore must be fully reusable across multiple request cycles."""
        async def run():
            ctrl = AdmissionController(
                max_concurrent_reasoning=2,
                timeout_by_priority={"low": 5.0, "standard": 5.0, "high": 5.0},
            )
            for _ in range(5):
                r = await ctrl.acquire("medium", "standard")
                assert r.admitted
                ctrl.release()
            return ctrl.active_count
        assert _run(run()) == 0


# ── Priority tier timeout influence ───────────────────────────────────────────

class TestPriorityTierTimeout:
    """
    Verify that different priority tiers consult different timeout values.
    We use extremely short timeouts to force a timeout and measure wait_ms.
    """

    def test_low_priority_timeout_shorter_than_high(self):
        async def run():
            low_ctrl = AdmissionController(
                max_concurrent_reasoning=1,
                timeout_by_priority={"low": 0.02, "standard": 0.05, "high": 0.10},
            )
            high_ctrl = AdmissionController(
                max_concurrent_reasoning=1,
                timeout_by_priority={"low": 0.02, "standard": 0.05, "high": 0.10},
            )

            # Fill the slot on both
            await low_ctrl.acquire("medium", "standard")
            await high_ctrl.acquire("medium", "standard")

            t_low_start = time.perf_counter()
            r_low = await low_ctrl.acquire("medium", "low")
            t_low = time.perf_counter() - t_low_start

            t_high_start = time.perf_counter()
            r_high = await high_ctrl.acquire("medium", "high")
            t_high = time.perf_counter() - t_high_start

            return r_low, r_high, t_low, t_high

        r_low, r_high, t_low, t_high = _run(run())
        assert not r_low.admitted
        assert not r_high.admitted
        # High priority waited longer than low priority (within tolerance)
        assert t_high > t_low


# ── update_circuit_breaker_state ──────────────────────────────────────────────

class TestCircuitBreakerCallback:
    def test_no_raise_on_both_open(self):
        ctrl = AdmissionController()
        ctrl.update_circuit_breaker_state(gpu_open=True, latency_open=True)  # must not raise

    def test_no_raise_on_both_closed(self):
        ctrl = AdmissionController()
        ctrl.update_circuit_breaker_state(gpu_open=False, latency_open=False)

    def test_no_raise_mixed_state(self):
        ctrl = AdmissionController()
        ctrl.update_circuit_breaker_state(gpu_open=True, latency_open=False)
        ctrl.update_circuit_breaker_state(gpu_open=False, latency_open=True)

    def test_active_count_unaffected(self):
        ctrl = AdmissionController()
        ctrl.update_circuit_breaker_state(gpu_open=True, latency_open=True)
        assert ctrl.active_count == 0

    def test_max_concurrent_unaffected(self):
        ctrl = AdmissionController(max_concurrent_reasoning=7)
        ctrl.update_circuit_breaker_state(gpu_open=True, latency_open=True)
        assert ctrl.max_concurrent == 7
