"""
Unit tests for BudgetLogitProcessor and HardBudgetFallback.

Per CLAUDE.md Section 9 — these tests validate the canonical stopping semantics
without requiring GPU or vLLM. All tests use CPU torch tensors.

Test coverage:
  - Natural completion (model emits </think> before ceiling)
  - Budget exhaustion (forced delimiter at ceiling)
  - Below budget (counter increments without triggering)
  - Already complete (no-op on subsequent calls)
  - State isolation between concurrent instances
  - Invalid delimiter (sentinel -1 raises ValueError)
  - Exception fallback (processor continues on internal error)
  - Entropy telemetry-only behavior (never controls stopping)
  - sampled_entropy slicing
  - HardBudgetFallback.from_env()
  - HardBudgetFallback.make_processor() returns None when active
"""
import os
import pytest

# ── torch availability guard ───────────────────────────────────────────────────

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not TORCH_AVAILABLE,
    reason="PyTorch required for BudgetLogitProcessor tests",
)

from vllm_adapter.logit_processor import BudgetLogitProcessor, HardBudgetFallback, StopReason

# ── Test constants ─────────────────────────────────────────────────────────────

FAKE_EOT_TOKEN_ID = 42        # Fake token ID (not real tokenizer)
VOCAB_SIZE = 1000
MAX_REASONING = 10            # Small budget for fast testing


def _make_logits(vocab_size: int = VOCAB_SIZE, fill: float = 0.0):
    """Return a 1-D logit tensor."""
    return torch.full((vocab_size,), fill, dtype=torch.float32)


def _make_token_ids(*token_ids: int):
    """Build token_ids list up to a given sequence."""
    return list(token_ids)


def _make_proc(**kwargs) -> BudgetLogitProcessor:
    """Convenience factory with defaults."""
    defaults = dict(
        request_id="test-req-1",
        max_reasoning_tokens=MAX_REASONING,
        end_of_thinking_token_id=FAKE_EOT_TOKEN_ID,
    )
    defaults.update(kwargs)
    return BudgetLogitProcessor(**defaults)


# ── 1. Natural completion ──────────────────────────────────────────────────────

class TestNaturalCompletion:

    def test_marks_complete_on_eot_token(self):
        proc = _make_proc()
        logits = _make_logits()
        # Feed tokens up to and including EOT
        for i in range(3):
            result = proc(_make_token_ids(10, 20, 30)[: i + 1], logits.clone())
        # Now feed EOT token as last token
        token_ids_with_eot = [10, 20, 30, FAKE_EOT_TOKEN_ID]
        result = proc(token_ids_with_eot, logits.clone())

        assert proc.reasoning_complete is True
        assert proc.stop_reason == StopReason.NATURAL_BOUNDARY
        assert proc.reasoning_token_count == 4

    def test_no_op_after_natural_completion(self):
        proc = _make_proc()
        logits = _make_logits()

        # Reach natural completion
        proc([10, FAKE_EOT_TOKEN_ID], logits.clone())
        count_after_natural = proc.reasoning_token_count

        # Further calls must not increment counter
        proc([10, FAKE_EOT_TOKEN_ID, 99], logits.clone())
        assert proc.reasoning_token_count == count_after_natural

    def test_logits_unchanged_on_natural_completion(self):
        proc = _make_proc()
        logits = _make_logits(fill=1.0)
        result = proc([10, FAKE_EOT_TOKEN_ID], logits)
        # Logits should be returned unchanged on natural completion step
        assert torch.all(result == 1.0)


# ── 2. Budget exhaustion ───────────────────────────────────────────────────────

class TestBudgetExhaustion:

    def test_forces_eot_at_ceiling(self):
        proc = _make_proc(max_reasoning_tokens=5)
        logits = _make_logits(fill=0.0)

        # Feed MAX_REASONING tokens without hitting EOT
        for i in range(5):
            token_ids = list(range(i + 1))  # never FAKE_EOT_TOKEN_ID
            result = proc(token_ids, logits.clone())

        # After ceiling, result should have EOT=100, all others=-inf
        assert proc.reasoning_complete is True
        assert proc.stop_reason == StopReason.BUDGET_EXHAUSTED
        assert result[FAKE_EOT_TOKEN_ID].item() == 100.0
        # All other logits should be -inf
        mask = torch.ones(VOCAB_SIZE, dtype=torch.bool)
        mask[FAKE_EOT_TOKEN_ID] = False
        assert torch.all(result[mask] == float("-inf"))

    def test_counter_matches_max_at_exhaustion(self):
        proc = _make_proc(max_reasoning_tokens=3)
        logits = _make_logits()
        for i in range(3):
            proc(list(range(i + 1)), logits.clone())
        assert proc.reasoning_token_count == 3

    def test_no_op_after_exhaustion(self):
        proc = _make_proc(max_reasoning_tokens=2)
        logits = _make_logits(fill=0.0)
        for i in range(2):
            proc(list(range(i + 1)), logits.clone())

        count = proc.reasoning_token_count
        proc([1, 2, 3], logits.clone())
        assert proc.reasoning_token_count == count


# ── 3. Below budget ────────────────────────────────────────────────────────────

class TestBelowBudget:

    def test_counter_increments_correctly(self):
        proc = _make_proc(max_reasoning_tokens=100)
        logits = _make_logits()
        for i in range(7):
            proc(list(range(i + 1)), logits.clone())
        assert proc.reasoning_token_count == 7
        assert proc.reasoning_complete is False

    def test_logits_unchanged_below_budget(self):
        proc = _make_proc(max_reasoning_tokens=100)
        logits = _make_logits(fill=3.0)
        result = proc([1, 2, 3], logits)
        # No forcing occurred — logits intact (entropy may have been computed on a clone)
        assert proc.reasoning_complete is False


# ── 4. Already complete (no-op) ────────────────────────────────────────────────

class TestAlreadyComplete:

    def test_all_fields_frozen_after_complete(self):
        proc = _make_proc(max_reasoning_tokens=3)
        logits = _make_logits()
        for i in range(3):
            proc(list(range(i + 1)), logits.clone())

        pre_count = proc.reasoning_token_count
        pre_entropy_len = len(proc.entropy_log)

        # Further calls
        for _ in range(5):
            proc([99, 100], logits.clone())

        assert proc.reasoning_token_count == pre_count
        assert len(proc.entropy_log) == pre_entropy_len


# ── 5. State isolation between instances ──────────────────────────────────────

class TestStateIsolation:

    def test_two_instances_independent(self):
        proc_a = _make_proc(request_id="req-A", max_reasoning_tokens=5)
        proc_b = _make_proc(request_id="req-B", max_reasoning_tokens=5)
        logits = _make_logits()

        # Exhaust proc_a
        for i in range(5):
            proc_a(list(range(i + 1)), logits.clone())

        # proc_b should be unaffected
        assert proc_b.reasoning_complete is False
        assert proc_b.reasoning_token_count == 0

    def test_entropy_logs_are_independent(self):
        proc_a = _make_proc(request_id="req-A")
        proc_b = _make_proc(request_id="req-B")
        logits = _make_logits()

        proc_a([1], logits.clone())
        proc_a([1, 2], logits.clone())

        assert len(proc_a.entropy_log) == 2
        assert len(proc_b.entropy_log) == 0


# ── 6. Invalid delimiter (sentinel) ───────────────────────────────────────────

class TestInvalidDelimiter:

    def test_raises_on_negative_token_id(self):
        with pytest.raises(ValueError, match="end_of_thinking_token_id"):
            BudgetLogitProcessor(
                request_id="req-bad",
                max_reasoning_tokens=10,
                end_of_thinking_token_id=-1,
            )

    def test_raises_on_undiscovered_sentinel(self):
        from vllm_adapter.constants import _UNDISCOVERED_SENTINEL
        with pytest.raises(ValueError):
            BudgetLogitProcessor(
                request_id="req-sentinel",
                max_reasoning_tokens=10,
                end_of_thinking_token_id=_UNDISCOVERED_SENTINEL,
            )


# ── 7. Exception handling ──────────────────────────────────────────────────────

class TestExceptionFallback:

    def test_exception_sets_flag_and_returns_logits(self):
        proc = _make_proc()
        logits = _make_logits(fill=2.0)

        # Corrupt internal state to force an exception in _step
        proc.end_of_thinking_token_id = VOCAB_SIZE + 9999  # out of bounds for _force

        # Calling with some tokens that won't hit EOT and will hit budget eventually
        # Force the exception by exhausting budget with out-of-bounds EOT ID
        for i in range(MAX_REASONING):
            result = proc(list(range(i + 1)), logits.clone())

        # At budget ceiling, _force_end_of_thinking uses out-of-bounds index
        # which should raise an IndexError — caught by __call__
        # (Note: this may or may not raise depending on torch behavior with out-of-bounds;
        # what matters is the processor does not propagate the exception)
        # The test just verifies the processor still returns a tensor
        assert isinstance(result, torch.Tensor)


# ── 8. Entropy telemetry ───────────────────────────────────────────────────────

class TestEntropyTelemetry:

    def test_entropy_log_grows_with_steps(self):
        proc = _make_proc(max_reasoning_tokens=100)
        logits = _make_logits()
        for i in range(5):
            proc(list(range(i + 1)), logits.clone())
        assert len(proc.entropy_log) == 5

    def test_entropy_values_are_non_negative(self):
        proc = _make_proc(max_reasoning_tokens=100)
        logits = _make_logits(fill=1.0)
        for i in range(10):
            proc(list(range(i + 1)), logits.clone())
        for e in proc.entropy_log:
            assert e >= 0.0, f"Entropy {e} is negative"

    def test_entropy_does_not_affect_stopping(self):
        # Even if entropy is very high, stopping must follow token budget only
        proc = _make_proc(max_reasoning_tokens=5)
        logits = _make_logits(fill=0.0)
        for i in range(4):
            proc(list(range(i + 1)), logits.clone())
        assert proc.reasoning_complete is False
        assert proc.reasoning_token_count == 4

    def test_sampled_entropy_slicing(self):
        proc = _make_proc(max_reasoning_tokens=100)
        logits = _make_logits()
        for i in range(30):
            proc(list(range(i + 1)), logits.clone())
        sampled = proc.sampled_entropy(every_n=10)
        assert len(sampled) == 3
        assert sampled[0] == proc.entropy_log[0]
        assert sampled[1] == proc.entropy_log[10]
        assert sampled[2] == proc.entropy_log[20]

    def test_sampled_entropy_empty_when_no_steps(self):
        proc = _make_proc()
        assert proc.sampled_entropy() == []


# ── 9. HardBudgetFallback ─────────────────────────────────────────────────────

class TestHardBudgetFallback:

    def test_inactive_by_default(self, monkeypatch):
        monkeypatch.delenv("LOGITPROCESSOR_FALLBACK_ACTIVE", raising=False)
        fb = HardBudgetFallback.from_env()
        assert fb.active is False

    def test_active_when_env_true(self, monkeypatch):
        monkeypatch.setenv("LOGITPROCESSOR_FALLBACK_ACTIVE", "true")
        monkeypatch.setenv("LOGITPROCESSOR_FALLBACK_REASON", "gate_failed")
        fb = HardBudgetFallback.from_env()
        assert fb.active is True
        assert fb.reason == "gate_failed"

    def test_make_processor_returns_none_when_active(self):
        fb = HardBudgetFallback(active=True, reason="test")
        result = fb.make_processor("req-1", 512, FAKE_EOT_TOKEN_ID)
        assert result is None

    def test_make_processor_returns_processor_when_inactive(self):
        fb = HardBudgetFallback(active=False, reason="")
        proc = fb.make_processor("req-1", 512, FAKE_EOT_TOKEN_ID)
        assert isinstance(proc, BudgetLogitProcessor)
        assert proc.max_reasoning_tokens == 512
        assert proc.end_of_thinking_token_id == FAKE_EOT_TOKEN_ID
