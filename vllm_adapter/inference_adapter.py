"""
Inference adapter — typed request/response structures and vLLM HTTP bridge.

This module translates InferaCordon's internal inference request (budget class,
reasoning token ceiling, LogitProcessor) into the vLLM OpenAI-compatible API
format, and translates the response back into typed InferenceResult objects.

Boundary: This adapter knows about LogitProcessors and vLLM SamplingParams.
It does NOT know about: policy decisions, budget assignment, complexity scoring,
guardrails, verification, admission control, or audit records.
Those belong to the gateway orchestration layer.

Per CLAUDE.md Sections 8, 9, and 12.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any, List, Optional

log = logging.getLogger(__name__)

# ── Request / Response types ──────────────────────────────────────────────────

@dataclasses.dataclass
class InferenceRequest:
    """
    Fully resolved inference request — all budget decisions already made.
    Created by the gateway after policy lookup and budget assignment.
    """
    request_id: str
    model_name: str                 # "deepseek-r1-7b" or "qwen25-3b"
    messages: List[dict]            # OpenAI message format: [{"role": ..., "content": ...}]
    max_reasoning_tokens: int       # 0 for cheap model (no thinking)
    max_output_tokens: int
    budget_class: str               # "low" | "medium" | "high" | "critical"
    use_logit_processor: bool = True   # False when HardBudgetFallback is active
    temperature: float = 0.0          # Deterministic by default
    stream: bool = False

    @classmethod
    def from_prompt(
        cls,
        request_id: str,
        prompt: str,
        model_name: str,
        budget_class: str,
        max_reasoning_tokens: int,
        max_output_tokens: int,
        system_prompt: str = "",
    ) -> "InferenceRequest":
        """Convenience constructor from a plain prompt string."""
        messages: List[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return cls(
            request_id=request_id,
            model_name=model_name,
            messages=messages,
            max_reasoning_tokens=max_reasoning_tokens,
            max_output_tokens=max_output_tokens,
            budget_class=budget_class,
        )


@dataclasses.dataclass
class InferenceResult:
    """
    Typed result of a vLLM inference call. Consumed by the gateway pipeline.
    Per CLAUDE.md Section 14 (Inference Response Contract).
    """
    request_id: str
    model_name: str
    content: str                        # Final answer text
    reasoning_tokens_used: int          # Tokens in the <think>...</think> span
    reasoning_tokens_allocated: int     # max_reasoning_tokens that was configured
    output_tokens: int                  # Tokens in the answer span
    stop_reason: str                    # StopReason constant
    ttft_ms: float                      # Time to first token
    total_latency_ms: float
    logit_processor_used: bool
    entropy_log: List[float]            # From BudgetLogitProcessor.entropy_log
    exception_occurred: bool = False
    raw_response: Optional[dict] = None  # Full vLLM API response for debugging


@dataclasses.dataclass
class VLLMCallSpec:
    """
    The resolved vLLM API call payload (before HTTP serialization).
    Built by InferenceAdapter.build_call_spec().
    """
    model: str
    messages: List[dict]
    max_tokens: int              # max_output_tokens (reasoning handled by LogitProcessor)
    temperature: float
    stream: bool
    extra_body: dict             # vLLM-specific: logits_processors config
    logit_processor: Optional[Any]  # BudgetLogitProcessor instance or None


# ── Inference Adapter ────────────────────────────────────────────────────────

class InferenceAdapter:
    """
    Translates InferenceRequest → VLLMCallSpec and InferenceResult.

    Does NOT make HTTP calls (that is the gateway's vllm_client.py responsibility).
    Responsible for: SamplingParams construction, LogitProcessor instantiation,
    budget enforcement strategy selection.
    """

    def __init__(
        self,
        vllm_base_url: str,
        hard_budget_fallback: "HardBudgetFallback",  # noqa: F821
    ) -> None:
        self.vllm_base_url = vllm_base_url
        self.hard_budget_fallback = hard_budget_fallback

    def build_call_spec(self, request: InferenceRequest) -> VLLMCallSpec:
        """
        Build the complete vLLM call specification for a resolved InferenceRequest.
        Selects between BudgetLogitProcessor and HardBudgetFallback.
        """
        from vllm_adapter.constants import DEEPSEEK_R1_EOT_TOKEN_ID, DEEPSEEK_R1_EOT_VALIDATED
        from vllm_adapter.logit_processor import BudgetLogitProcessor, HardBudgetFallback, StopReason

        logit_processor = None
        use_lp = False
        extra_body: dict = {}

        if request.max_reasoning_tokens > 0 and request.use_logit_processor:
            if not DEEPSEEK_R1_EOT_VALIDATED:
                log.warning(
                    "EOT token not validated — falling back to hard budget for request %s",
                    request.request_id,
                )
            elif not self.hard_budget_fallback.active:
                logit_processor = BudgetLogitProcessor(
                    request_id=request.request_id,
                    max_reasoning_tokens=request.max_reasoning_tokens,
                    end_of_thinking_token_id=DEEPSEEK_R1_EOT_TOKEN_ID,
                )
                use_lp = True
                # vLLM accepts logits_processors as a list in extra_body
                # The actual processor is passed through the SamplingParams mechanism
                # when vLLM is called directly (not via HTTP). For HTTP API, the
                # processor must be registered via a server-side plugin. This is
                # the Week 1 integration task: validate the registration mechanism.
                extra_body["logits_processors"] = []  # Populated by vllm_client.py

        # For hard-budget fallback, max_tokens includes reasoning + output
        if not use_lp and request.max_reasoning_tokens > 0:
            hard_max = request.max_reasoning_tokens + request.max_output_tokens
        else:
            hard_max = request.max_output_tokens

        return VLLMCallSpec(
            model=request.model_name,
            messages=request.messages,
            max_tokens=hard_max,
            temperature=request.temperature,
            stream=request.stream,
            extra_body=extra_body,
            logit_processor=logit_processor,
        )

    def build_result(
        self,
        request: InferenceRequest,
        raw_response: dict,
        logit_processor: Optional[Any],
        ttft_ms: float,
        total_latency_ms: float,
    ) -> InferenceResult:
        """
        Parse a raw vLLM API response into a typed InferenceResult.
        Extracts reasoning token counts from the response metadata.
        """
        from vllm_adapter.logit_processor import StopReason

        choice = raw_response.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "unknown")

        usage = raw_response.get("usage", {})
        total_tokens = usage.get("completion_tokens", 0)

        # Extract reasoning token count from BudgetLogitProcessor state
        reasoning_tokens = 0
        entropy_log: List[float] = []
        stop_reason = finish_reason
        exception_occurred = False

        if logit_processor is not None:
            reasoning_tokens = logit_processor.reasoning_token_count
            entropy_log = list(logit_processor.entropy_log)
            stop_reason = logit_processor.stop_reason or finish_reason
            exception_occurred = logit_processor.exception_occurred
        elif request.max_reasoning_tokens > 0:
            # HardBudgetFallback was active — estimate reasoning from total
            stop_reason = StopReason.HARD_TRUNCATION

        output_tokens = max(0, total_tokens - reasoning_tokens)

        return InferenceResult(
            request_id=request.request_id,
            model_name=request.model_name,
            content=content,
            reasoning_tokens_used=reasoning_tokens,
            reasoning_tokens_allocated=request.max_reasoning_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            logit_processor_used=logit_processor is not None,
            entropy_log=entropy_log,
            exception_occurred=exception_occurred,
            raw_response=raw_response,
        )


# ── Re-export HardBudgetFallback for gateway convenience ─────────────────────
from vllm_adapter.logit_processor import HardBudgetFallback  # noqa: E402
