"""
HTTP client for the vLLM OpenAI-compatible inference API.

Per CLAUDE.md Sections 6 and 8:
- POST http://vllm:8080/v1/chat/completions (OpenAI-compatible)
- Explicit timeout (default 60s; inference can be slow for reasoning models)
- Propagates W3C traceparent header to vLLM for distributed tracing
- Phase 9: streaming response for TTFT measurement (non-streaming in Phase 4)
- Phase 9: LogitProcessor registration via server-side plugin

The VLLMClient is responsible ONLY for HTTP transport.
It does NOT make policy, budget, or routing decisions.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# CLAUDE.md Section 7.3 — the vLLM endpoint
_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_MODELS_PATH = "/v1/models"
_HEALTH_PATH = "/health"


@dataclass
class VLLMRequest:
    """Resolved vLLM API call specification — all budget decisions already made."""
    model: str
    messages: list[dict]
    max_tokens: int
    extra_body: dict                # Reserved for LogitProcessor config (Phase 9)
    stream: bool = False
    temperature: float = 0.0
    traceparent: Optional[str] = None
    request_id: Optional[str] = None


@dataclass
class VLLMResponse:
    """Parsed vLLM API response."""
    content: str
    model_version: str
    reasoning_tokens_used: int   # Phase 9: extract from LogitProcessor state
    output_tokens: int
    ttft_ms: float               # Phase 9: real TTFT from streaming; for now = total
    total_latency_ms: float
    finish_reason: str
    raw_response: Optional[dict] = None


class VLLMClient:
    """
    Async HTTP client for vLLM's OpenAI-compatible API.

    Lifecycle:
      await client.start()    # Open httpx session at gateway startup
      await client.complete() # Per-request inference call
      await client.close()    # Clean shutdown
    """

    def __init__(self, base_url: str, timeout_seconds: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Open the persistent httpx session. Called once at gateway startup."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=5.0),
            follow_redirects=False,
        )
        log.info("VLLMClient started: base_url=%s timeout=%.1fs", self._base_url, self._timeout)

    async def close(self) -> None:
        """Close the httpx session. Called at gateway shutdown."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            log.info("VLLMClient closed")

    async def complete(self, request: VLLMRequest) -> VLLMResponse:
        """
        Execute a single inference call.

        Per CLAUDE.md Section 6 Step 11.
        Raises httpx.HTTPStatusError on 4xx/5xx.
        Raises httpx.TimeoutException on timeout.
        """
        if self._client is None:
            raise RuntimeError(
                "VLLMClient not started — call await client.start() before use"
            )

        payload: dict = {
            "model": request.model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,   # Phase 4: non-streaming; Phase 9 adds streaming
        }
        # Merge extra_body (e.g. LogitProcessor config) without overriding core fields
        for k, v in request.extra_body.items():
            if k not in payload:
                payload[k] = v

        headers: dict[str, str] = {}
        if request.traceparent:
            headers["traceparent"] = request.traceparent
        if request.request_id:
            headers["X-Request-ID"] = request.request_id

        t_start = time.perf_counter()
        try:
            resp = await self._client.post(
                _CHAT_COMPLETIONS_PATH,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            log.error(
                "vLLM request timed out after %.1fs for request_id=%s: %s",
                self._timeout, request.request_id, exc,
            )
            raise
        except httpx.HTTPStatusError as exc:
            log.error(
                "vLLM returned HTTP %d for request_id=%s: %s",
                exc.response.status_code, request.request_id, exc,
            )
            raise

        total_latency_ms = (time.perf_counter() - t_start) * 1000.0

        data: dict = resp.json()
        return _parse_response(request, data, total_latency_ms)

    async def health_check(self) -> bool:
        """
        Lightweight connectivity check against vLLM health endpoint.
        Returns True if reachable and healthy, False otherwise.
        """
        if self._client is None:
            return False
        try:
            resp = await self._client.get(_HEALTH_PATH, timeout=httpx.Timeout(5.0))
            return resp.status_code == 200
        except Exception:
            return False


def _parse_response(
    request: VLLMRequest,
    data: dict,
    total_latency_ms: float,
) -> VLLMResponse:
    """
    Parse a raw vLLM chat completions response into VLLMResponse.

    Note on reasoning_tokens_used: In Phase 4 without an active LogitProcessor,
    the vLLM response does not separate reasoning vs. output tokens.
    Phase 9 will extract this from the LogitProcessor state via custom response fields.
    """
    choices = data.get("choices", [])
    if not choices:
        return VLLMResponse(
            content="",
            model_version=data.get("model", request.model),
            reasoning_tokens_used=0,
            output_tokens=0,
            ttft_ms=total_latency_ms,
            total_latency_ms=total_latency_ms,
            finish_reason="unknown",
            raw_response=data,
        )

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""
    finish_reason = choice.get("finish_reason", "stop")

    usage = data.get("usage", {})
    output_tokens = usage.get("completion_tokens", 0)

    # Some vLLM builds with DeepSeek expose reasoning content separately
    reasoning_tokens_used = 0
    if "reasoning_content" in message:
        reasoning_content: str = message["reasoning_content"] or ""
        # Rough estimate: 4 chars per token
        reasoning_tokens_used = len(reasoning_content) // 4

    return VLLMResponse(
        content=content,
        model_version=data.get("model", request.model),
        reasoning_tokens_used=reasoning_tokens_used,
        output_tokens=output_tokens,
        ttft_ms=total_latency_ms,  # Phase 9: real TTFT from streaming
        total_latency_ms=total_latency_ms,
        finish_reason=finish_reason,
        raw_response=data,
    )
