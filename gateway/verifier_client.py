"""
Async HTTP client for the InferaCordon verifier microservice (Port 8002).

Per CLAUDE.md Section 15.4 — verifier unavailability semantics:
  "The platform does not block response delivery when the verifier is unreachable."
  On timeout or any error → return UNVERIFIABLE (NOT INCORRECT).
  UNVERIFIABLE does NOT trigger escalation (CLAUDE.md Section 16).

Timeout: 10 seconds. CLAUDE.md does not specify a verifier timeout; 10s accounts
for HumanEval's 2s sandboxed subprocess plus network overhead.
(Per CLAUDE.md Section 32 — architectural assumption, recorded here.)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# Architectural assumption per CLAUDE.md Section 32 (not specified in Architecture Plan).
# 10s accounts for HumanEval's 2s sandboxed subprocess plus network latency.
_VERIFIER_TIMEOUT_S = 10.0


class VerificationResult(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNVERIFIABLE = "unverifiable"


@dataclass
class VerifierResponse:
    result: VerificationResult
    verifier_type: str
    reason: str
    predicted: str = ""
    expected: str = ""
    latency_ms: float = 0.0
    verifier_version: str = "verifier_v1"


class VerifierClient:
    """
    Async HTTP client for the verifier service.
    One instance per gateway process; reused across requests.
    Lazy httpx.AsyncClient — no event loop required at __init__.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = _VERIFIER_TIMEOUT_S,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_s),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def verify(
        self,
        *,
        response: str,
        verifier_type: str,
        ground_truth: Optional[str] = None,
        test_cases: Optional[str] = None,
        entry_point: Optional[str] = None,
        schema: Optional[dict] = None,
        request_id: Optional[str] = None,
        traceparent: Optional[str] = None,
    ) -> VerifierResponse:
        """
        Call POST /verify on the verifier service.

        Returns UNVERIFIABLE on any timeout or network/HTTP error.
        Per CLAUDE.md §15.4: never blocks response delivery.
        """
        headers: dict[str, str] = {}
        if traceparent:
            headers["traceparent"] = traceparent
        if request_id:
            headers["X-Request-ID"] = request_id

        payload: dict = {"response": response, "verifier_type": verifier_type}
        if ground_truth is not None:
            payload["ground_truth"] = ground_truth
        if test_cases is not None:
            payload["test_cases"] = test_cases
        if entry_point is not None:
            payload["entry_point"] = entry_point
        if schema is not None:
            payload["schema"] = schema

        t0 = time.perf_counter()
        try:
            client = self._get_client()
            resp = await client.post("/verify", json=payload, headers=headers)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            resp.raise_for_status()
            return _parse_verify_response(resp.json(), latency_ms)

        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            log.warning(
                "Verifier TIMEOUT request_id=%s verifier_type=%s — UNVERIFIABLE",
                request_id, verifier_type,
            )
            return _unverifiable("verifier_timeout", verifier_type, latency_ms)

        except httpx.HTTPStatusError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            log.error(
                "Verifier HTTP %s request_id=%s — UNVERIFIABLE",
                exc.response.status_code, request_id,
            )
            return _unverifiable(
                f"verifier_http_{exc.response.status_code}", verifier_type, latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            log.error(
                "Verifier error request_id=%s: %s — UNVERIFIABLE",
                request_id, exc,
            )
            return _unverifiable("verifier_error", verifier_type, latency_ms)


# ── Response parsers ──────────────────────────────────────────────────────────

def _parse_verify_response(data: dict, latency_ms: float) -> VerifierResponse:
    passed = bool(data.get("passed", False))
    vtype = str(data.get("verifier_type", "unknown"))
    reason = str(data.get("reason", "unknown"))

    if passed:
        result = VerificationResult.CORRECT
    elif "unverifiable" in reason:
        result = VerificationResult.UNVERIFIABLE
    else:
        result = VerificationResult.INCORRECT

    return VerifierResponse(
        result=result,
        verifier_type=vtype,
        reason=reason,
        predicted=str(data.get("predicted", "")),
        expected=str(data.get("expected", "")),
        latency_ms=latency_ms,
    )


def _unverifiable(reason: str, verifier_type: str, latency_ms: float) -> VerifierResponse:
    return VerifierResponse(
        result=VerificationResult.UNVERIFIABLE,
        verifier_type=verifier_type,
        reason=reason,
        latency_ms=latency_ms,
    )
