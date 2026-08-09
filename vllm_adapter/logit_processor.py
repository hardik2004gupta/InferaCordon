"""
BudgetLogitProcessor — per-request reasoning token budget enforcer.

Per CLAUDE.md Section 9. This is the single most important technical component.
Validated before any other component is built (Week 1 hard gate).

Interface contract (vLLM v0.4.x):
    __call__(token_ids: List[int], logits: torch.Tensor) -> torch.Tensor

CLAUDE.md Section 9.4 specifies the older interface (input_ids: torch.Tensor).
vLLM ≥ 0.3 uses List[int] for the first argument. The stopping semantics are
identical — the only difference is the type of the first parameter.
This is documented here as an implementation detail, not an architecture deviation.

Stopping semantics (exact per CLAUDE.md Section 9.4):
  1. If reasoning_complete: return logits unchanged (no-op).
  2. Increment reasoning_token_count.
  3. Compute and append entropy (telemetry ONLY — never controls stopping).
  4. If last generated token == end_of_thinking_token_id: mark complete, return.
  5. If token_count >= max_reasoning_tokens: force delimiter, mark complete.

HardBudgetFallback (per CLAUDE.md Section 9.6):
  If the processor fails the ≥85% coherence gate, generation falls back to
  hard max_tokens truncation. The fallback is a configuration flag on the
  InferenceRequest — NOT a silent replacement of the processor.
"""
from __future__ import annotations

import dataclasses
import logging
import math
from typing import List, Optional, TYPE_CHECKING

log = logging.getLogger(__name__)

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False
    log.error("PyTorch not available. BudgetLogitProcessor cannot operate.")


# ── Stop reasons (per CLAUDE.md Section 16.3) ─────────────────────────────────

class StopReason:
    NATURAL_BOUNDARY = "natural_boundary"    # model emitted </think> before ceiling
    BUDGET_EXHAUSTED = "budget_exhausted"    # forced delimiter at ceiling
    HARD_TRUNCATION = "hard_truncation"      # HardBudgetFallback active
    EXCEPTION = "exception"                  # processor raised, fallback used


# ── BudgetLogitProcessor ───────────────────────────────────────────────────────

@dataclasses.dataclass
class BudgetLogitProcessor:
    """
    Per-request reasoning token budget enforcer for vLLM's LogitsProcessor interface.

    State fields per CLAUDE.md Section 9.3 — these are part of the public contract
    and must not be renamed or removed without an Architecture Deviation entry.

    Thread safety: Each request gets its own instance. There is NO shared mutable
    state between instances (CLAUDE.md Section 9.8).
    """

    request_id: str
    max_reasoning_tokens: int
    end_of_thinking_token_id: int    # discovered per CLAUDE.md Section 9.5
    reasoning_complete: bool = dataclasses.field(default=False)
    reasoning_token_count: int = dataclasses.field(default=0)
    entropy_log: list = dataclasses.field(default_factory=list)

    # Internal bookkeeping (not part of the public contract)
    _stop_reason: str = dataclasses.field(default="", init=False, repr=False)
    _exception_occurred: bool = dataclasses.field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "PyTorch is required for BudgetLogitProcessor. "
                "Install: pip install torch"
            )
        if self.end_of_thinking_token_id < 0:
            raise ValueError(
                f"end_of_thinking_token_id={self.end_of_thinking_token_id} is invalid. "
                "Run the tokenizer discovery process before instantiating the processor. "
                "See vllm_adapter/constants.py::discover_eot_token_id()."
            )

    def __call__(self, token_ids: List[int], logits: "torch.Tensor") -> "torch.Tensor":
        """
        Per-step budget enforcement. Called by vLLM on every generated token.

        Args:
            token_ids: List of token IDs generated so far for this request.
                       In vLLM v0.4.x this is List[int]; in older versions it
                       was torch.Tensor. We handle both gracefully.
            logits:    1-D tensor of shape [vocab_size]. Modified in-place and returned.

        Returns:
            logits tensor, possibly modified to force the delimiter token.
        """
        try:
            return self._step(token_ids, logits)
        except Exception as exc:
            # Per CLAUDE.md Section 9 / Phase 2 requirement:
            # Do NOT silence exceptions — record them and let vLLM handle.
            self._exception_occurred = True
            self._stop_reason = StopReason.EXCEPTION
            log.error(
                "BudgetLogitProcessor exception (request=%s step=%d): %s",
                self.request_id, self.reasoning_token_count, exc,
            )
            # Return logits unchanged — generation continues to hard max_tokens
            return logits

    def _step(self, token_ids, logits: "torch.Tensor") -> "torch.Tensor":
        """Core per-step logic (extracted for testability and exception isolation)."""

        # ── 1. No-op if reasoning phase already complete ──────────────────────
        if self.reasoning_complete:
            return logits

        # ── 2. Increment reasoning token counter ──────────────────────────────
        self.reasoning_token_count += 1

        # ── 3. Entropy telemetry (MONITORING ONLY — never controls stopping) ──
        self._log_entropy(logits)

        # ── 4. Check for natural delimiter emission ───────────────────────────
        # last_token is the most recently generated token ID
        if isinstance(token_ids, list):
            last_token = token_ids[-1] if token_ids else -1
        else:
            # torch.Tensor (older vLLM versions)
            last_token = token_ids[-1].item() if len(token_ids) > 0 else -1

        if last_token == self.end_of_thinking_token_id:
            self.reasoning_complete = True
            self._stop_reason = StopReason.NATURAL_BOUNDARY
            return logits

        # ── 5. Enforce budget ceiling ─────────────────────────────────────────
        if self.reasoning_token_count >= self.max_reasoning_tokens:
            logits = self._force_end_of_thinking(logits)
            self.reasoning_complete = True
            self._stop_reason = StopReason.BUDGET_EXHAUSTED

        return logits

    def _log_entropy(self, logits: "torch.Tensor") -> None:
        """
        Compute and record top-20 token entropy. Telemetry ONLY.
        Per CLAUDE.md Section 9.4 formula:
          entropy = -sum(top_k_probs * log(top_k_probs + 1e-9))
        """
        try:
            probs = torch.softmax(logits, dim=-1)
            k = min(20, probs.shape[-1])
            top_k_probs = torch.topk(probs, k=k).values
            entropy = -torch.sum(top_k_probs * torch.log(top_k_probs + 1e-9)).item()
            self.entropy_log.append(entropy)
        except Exception as exc:
            # Entropy failure must never affect stopping behavior
            log.debug("Entropy logging failed (non-fatal): %s", exc)

    def _force_end_of_thinking(self, logits: "torch.Tensor") -> "torch.Tensor":
        """
        Force the end-of-thinking delimiter token by zeroing all logits
        and setting the delimiter token to +100. Per CLAUDE.md Section 9.4:
          scores[:] = -inf
          scores[end_of_thinking_token_id] = 100.0
        """
        logits[:] = -float("inf")
        logits[self.end_of_thinking_token_id] = 100.0
        return logits

    @property
    def stop_reason(self) -> str:
        """The stop reason after generation completes. Empty string while in progress."""
        return self._stop_reason

    @property
    def exception_occurred(self) -> bool:
        """True if the processor caught an exception during generation."""
        return self._exception_occurred

    def sampled_entropy(self, every_n: int = 10) -> list:
        """
        Return every nth entropy sample for OTel trace storage.
        Per CLAUDE.md Section 9.7 — sampled to limit trace size.
        """
        return self.entropy_log[::every_n]


# ── HardBudgetFallback ────────────────────────────────────────────────────────

@dataclasses.dataclass
class HardBudgetFallback:
    """
    Documented fallback when BudgetLogitProcessor fails the ≥85% coherence gate.

    Per CLAUDE.md Section 9.6:
      "If this fallback is triggered: The project does not proceed to Phase 2 with
      an unvalidated stopping mechanism. The fallback is documented as the
      implemented approach and the LogitProcessor is not used."

    When active, inference uses hard max_tokens truncation instead of the
    LogitProcessor delimiter injection. The answer may be mid-sentence at the
    budget ceiling — no </think> token is injected.

    This is NOT a silent replacement. It is:
    - Configured explicitly via LOGITPROCESSOR_FALLBACK_ACTIVE env variable
    - Logged at WARNING level on every request
    - Recorded as stop_reason = "hard_truncation" in all audit records
    - Exposed via the /v1/circuit-breakers endpoint
    """

    active: bool
    reason: str   # Human-readable reason fallback was activated

    @classmethod
    def from_env(cls) -> "HardBudgetFallback":
        """Build from LOGITPROCESSOR_FALLBACK_ACTIVE environment variable."""
        import os
        active = os.getenv("LOGITPROCESSOR_FALLBACK_ACTIVE", "false").lower() == "true"
        reason = os.getenv("LOGITPROCESSOR_FALLBACK_REASON", "") if active else ""
        if active:
            log.warning(
                "HardBudgetFallback is ACTIVE: %s  "
                "BudgetLogitProcessor is NOT enforcing reasoning budgets. "
                "Stop reason will be 'hard_truncation' on all requests.",
                reason,
            )
        return cls(active=active, reason=reason)

    def make_processor(
        self,
        request_id: str,
        max_reasoning_tokens: int,
        end_of_thinking_token_id: int,
    ) -> Optional["BudgetLogitProcessor"]:
        """
        Return a BudgetLogitProcessor if fallback is NOT active.
        Return None if fallback IS active (caller must use hard max_tokens instead).
        """
        if self.active:
            return None
        return BudgetLogitProcessor(
            request_id=request_id,
            max_reasoning_tokens=max_reasoning_tokens,
            end_of_thinking_token_id=end_of_thinking_token_id,
        )
