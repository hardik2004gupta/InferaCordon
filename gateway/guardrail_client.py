"""
Async HTTP client for the InferaCordon guardrail microservice (Port 8001).

Per CLAUDE.md Section 14.7 — asymmetric failure semantics:
  Input check timeout  → GuardrailDecision.BLOCK (conservative fail-closed)
  Output check timeout → GuardrailDecision.DEGRADED (non-blocking fail-open)

The gateway treats these downstream:
  BLOCK / DEGRADED on input  → 503 to client, no inference
  BLOCK on output            → structured refusal returned to client
  DEGRADED on output         → response delivered, event logged

Endpoints per CLAUDE.md Section 14.6:
  POST /guardrail/input   (text + policy booleans/thresholds)
  POST /guardrail/output  (text + safety threshold)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# 200ms hard timeout from CLAUDE.md Section 14.7
_GUARDRAIL_TIMEOUT_S = 0.200


class GuardrailDecision(str, Enum):
    PASS = "pass"
    FLAG = "flag"           # injection detected — augment system prompt, do NOT block
    BLOCK = "block"         # safety unsafe — block request/response
    DEGRADED = "degraded"   # service timeout/error — gateway applies asymmetric policy


@dataclass
class GuardrailResult:
    decision: GuardrailDecision
    reasons: list[str]
    injection_score: float = 0.0
    safety_category: str = "safe"
    safety_confidence: float = 0.0
    latency_ms: float = 0.0
    model_versions: dict[str, str] = field(default_factory=dict)


# ── Response parsers ──────────────────────────────────────────────────────────

def _parse_input_response(data: dict, latency_ms: float) -> GuardrailResult:
    raw_result = data.get("result", "pass")
    try:
        decision = GuardrailDecision(raw_result)
    except ValueError:
        log.warning("Guardrail service returned unknown result %r — treating as PASS", raw_result)
        decision = GuardrailDecision.PASS

    return GuardrailResult(
        decision=decision,
        reasons=[raw_result],
        injection_score=float(data.get("injection_score", 0.0)),
        safety_category=str(data.get("safety_category", "safe")),
        safety_confidence=float(data.get("safety_confidence", 0.0)),
        latency_ms=latency_ms,
        model_versions={
            "injection": str(data.get("injection_model_version", "unknown")),
            "safety": str(data.get("safety_model_version", "unknown")),
        },
    )


def _parse_output_response(data: dict, latency_ms: float) -> GuardrailResult:
    raw_result = data.get("result", "pass")
    try:
        decision = GuardrailDecision(raw_result)
    except ValueError:
        log.warning("Guardrail service returned unknown output result %r — treating as PASS", raw_result)
        decision = GuardrailDecision.PASS

    return GuardrailResult(
        decision=decision,
        reasons=[raw_result],
        safety_category=str(data.get("safety_category", "safe")),
        safety_confidence=float(data.get("safety_confidence", 0.0)),
        latency_ms=latency_ms,
        model_versions={
            "safety": str(data.get("safety_model_version", "unknown")),
        },
    )


# ── Block / DEGRADED sentinels ────────────────────────────────────────────────

def _input_block_result(reasons: list[str], latency_ms: float = _GUARDRAIL_TIMEOUT_S * 1000) -> GuardrailResult:
    return GuardrailResult(
        decision=GuardrailDecision.BLOCK,
        reasons=reasons,
        latency_ms=latency_ms,
    )


def _input_degraded_result(reasons: list[str], latency_ms: float = 0.0) -> GuardrailResult:
    return GuardrailResult(
        decision=GuardrailDecision.DEGRADED,
        reasons=reasons,
        latency_ms=latency_ms,
    )


def _output_degraded_result(reasons: list[str], latency_ms: float = _GUARDRAIL_TIMEOUT_S * 1000) -> GuardrailResult:
    return GuardrailResult(
        decision=GuardrailDecision.DEGRADED,
        reasons=reasons,
        latency_ms=latency_ms,
    )


# ── GuardrailClient ───────────────────────────────────────────────────────────

class GuardrailClient:
    """
    Async HTTP client for the guardrail service.
    One instance per gateway process; reuse across requests.
    Uses lazy httpx.AsyncClient creation (safe — no event loop needed at init).
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(_GUARDRAIL_TIMEOUT_S),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def check_input(
        self,
        text: str,
        run_injection_check: bool,
        run_safety_check: bool,
        injection_threshold: float,
        safety_threshold: float,
        request_id: Optional[str] = None,
        traceparent: Optional[str] = None,
    ) -> GuardrailResult:
        """
        Input guardrail check.

        On timeout  → BLOCK (conservative fail-closed per CLAUDE.md Section 14.7).
        On HTTP/net error → DEGRADED (gateway treats as BLOCK for input).
        """
        headers: dict[str, str] = {}
        if traceparent:
            headers["traceparent"] = traceparent
        if request_id:
            headers["X-Request-ID"] = request_id

        payload = {
            "text": text,
            "run_injection_check": run_injection_check,
            "run_safety_check": run_safety_check,
            "injection_threshold": injection_threshold,
            "safety_threshold": safety_threshold,
        }

        t0 = time.perf_counter()
        try:
            client = self._get_client()
            resp = await client.post("/guardrail/input", json=payload, headers=headers)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            resp.raise_for_status()
            return _parse_input_response(resp.json(), latency_ms)

        except httpx.TimeoutException:
            log.error(
                "Guardrail input TIMEOUT for request_id=%s — conservative BLOCK",
                request_id,
            )
            return _input_block_result(["guardrail_input_timeout"])

        except httpx.HTTPStatusError as exc:
            log.error(
                "Guardrail input HTTP %s for request_id=%s — DEGRADED",
                exc.response.status_code,
                request_id,
            )
            return _input_degraded_result(
                [f"guardrail_http_error_{exc.response.status_code}"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        except Exception as exc:
            log.error(
                "Guardrail input error for request_id=%s: %s — DEGRADED",
                request_id,
                exc,
            )
            return _input_degraded_result(
                ["guardrail_input_error"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

    async def check_output(
        self,
        text: str,
        run_safety_check: bool,
        safety_threshold: float,
        request_id: Optional[str] = None,
        traceparent: Optional[str] = None,
    ) -> GuardrailResult:
        """
        Output safety check.

        On timeout/error → DEGRADED (non-blocking pass per CLAUDE.md Section 14.7).
        The caller (gateway) logs the degraded state but delivers the response.
        """
        headers: dict[str, str] = {}
        if traceparent:
            headers["traceparent"] = traceparent
        if request_id:
            headers["X-Request-ID"] = request_id

        payload = {
            "text": text,
            "run_safety_check": run_safety_check,
            "safety_threshold": safety_threshold,
        }

        t0 = time.perf_counter()
        try:
            client = self._get_client()
            resp = await client.post("/guardrail/output", json=payload, headers=headers)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            resp.raise_for_status()
            return _parse_output_response(resp.json(), latency_ms)

        except httpx.TimeoutException:
            log.warning(
                "Guardrail output TIMEOUT for request_id=%s — non-blocking PASS (DEGRADED)",
                request_id,
            )
            return _output_degraded_result(["guardrail_output_timeout"])

        except Exception as exc:
            log.warning(
                "Guardrail output error for request_id=%s: %s — non-blocking PASS (DEGRADED)",
                request_id,
                exc,
            )
            return _output_degraded_result(
                ["guardrail_output_error"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
