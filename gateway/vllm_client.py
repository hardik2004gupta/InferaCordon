"""
HTTP client for the vLLM OpenAI-compatible inference API.

Per CLAUDE.md Sections 6 and 9:
- POST http://vllm:8080/v1/chat/completions (OpenAI-compatible)
- Attaches BudgetLogitProcessor via extra_body parameters (Week 1)
- Streaming response for TTFT measurement
- Captures reasoning_tokens_used from response metadata
- Propagates W3C traceparent header to vLLM
- Emits ic_vllm_request_duration_seconds metric (CLAUDE.md Section 18)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class VLLMRequest:
    model: str
    messages: list[dict]
    max_tokens: int
    extra_body: dict                # BudgetLogitProcessor config
    stream: bool = True
    temperature: float = 0.0
    traceparent: Optional[str] = None


@dataclass
class VLLMResponse:
    content: str
    model_version: str
    reasoning_tokens_used: int
    output_tokens: int
    ttft_ms: float
    total_latency_ms: float
    finish_reason: str


class VLLMClient:
    """Async HTTP client for vLLM's OpenAI-compatible API."""

    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 12 (Week 1)")

    async def complete(self, request: VLLMRequest) -> VLLMResponse:
        """Execute inference request. Streams internally, returns complete result."""
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 12 (Week 1)")
