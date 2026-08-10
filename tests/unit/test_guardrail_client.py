"""
Unit tests for gateway/guardrail_client.py.

Tests cover:
- GuardrailDecision enum values (including FLAG)
- GuardrailResult dataclass defaults
- check_input success: pass, flag, block
- check_input timeout → BLOCK (conservative fail-closed)
- check_input HTTP error → DEGRADED
- check_input network error → DEGRADED
- check_output success: pass, block
- check_output timeout → DEGRADED (non-blocking fail-open)
- check_output network error → DEGRADED
- close() is idempotent

All HTTP calls are mocked via httpx mock transport — no real network I/O.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gateway.guardrail_client import (
    GuardrailClient,
    GuardrailDecision,
    GuardrailResult,
    _GUARDRAIL_TIMEOUT_S,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_client() -> GuardrailClient:
    return GuardrailClient(base_url="http://guardrail:8001")


class _MockResponse:
    def __init__(self, body: dict, status_code: int = 200):
        self._body = body
        self.status_code = status_code

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self,
            )


def _input_pass_response() -> dict:
    return {
        "result": "pass",
        "injection_score": 0.1,
        "safety_category": "safe",
        "safety_confidence": 0.98,
        "injection_model_version": "heuristic_inject_v1",
        "safety_model_version": "heuristic_safety_v1",
        "latency_ms": 5,
    }


def _input_flag_response() -> dict:
    return {
        "result": "flag",
        "injection_score": 0.85,
        "safety_category": "safe",
        "safety_confidence": 0.98,
        "injection_model_version": "heuristic_inject_v1",
        "safety_model_version": "heuristic_safety_v1",
        "latency_ms": 8,
    }


def _input_block_response() -> dict:
    return {
        "result": "block",
        "injection_score": 0.3,
        "safety_category": "VIOLENCE",
        "safety_confidence": 0.95,
        "injection_model_version": "heuristic_inject_v1",
        "safety_model_version": "heuristic_safety_v1",
        "latency_ms": 12,
    }


def _output_pass_response() -> dict:
    return {
        "result": "pass",
        "safety_category": "safe",
        "safety_confidence": 0.98,
        "safety_model_version": "heuristic_safety_v1",
        "latency_ms": 6,
    }


def _output_block_response() -> dict:
    return {
        "result": "block",
        "safety_category": "VIOLENCE",
        "safety_confidence": 0.95,
        "safety_model_version": "heuristic_safety_v1",
        "latency_ms": 7,
    }


def _run(coro):
    return asyncio.run(coro)


# ── GuardrailDecision ─────────────────────────────────────────────────────────

class TestGuardrailDecision:
    def test_pass_value(self):
        assert GuardrailDecision.PASS == "pass"

    def test_flag_value(self):
        assert GuardrailDecision.FLAG == "flag"

    def test_block_value(self):
        assert GuardrailDecision.BLOCK == "block"

    def test_degraded_value(self):
        assert GuardrailDecision.DEGRADED == "degraded"

    def test_all_four_values_distinct(self):
        values = {d.value for d in GuardrailDecision}
        assert len(values) == 4


# ── GuardrailResult ───────────────────────────────────────────────────────────

class TestGuardrailResult:
    def test_defaults(self):
        r = GuardrailResult(decision=GuardrailDecision.PASS, reasons=[])
        assert r.injection_score == 0.0
        assert r.safety_category == "safe"
        assert r.safety_confidence == 0.0
        assert r.latency_ms == 0.0
        assert r.model_versions == {}

    def test_full_fields(self):
        r = GuardrailResult(
            decision=GuardrailDecision.BLOCK,
            reasons=["safety_block"],
            injection_score=0.2,
            safety_category="VIOLENCE",
            safety_confidence=0.95,
            latency_ms=12.5,
            model_versions={"injection": "v1", "safety": "v1"},
        )
        assert r.decision == GuardrailDecision.BLOCK
        assert r.safety_category == "VIOLENCE"


# ── check_input — success paths ───────────────────────────────────────────────

class TestCheckInputSuccess:
    def _mock_post(self, response_data: dict):
        """Context: patch httpx.AsyncClient.post."""
        async def _run_with_mock():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=_MockResponse(response_data))
            client._client = mock_http
            return await client.check_input(
                text="test prompt",
                run_injection_check=True,
                run_safety_check=True,
                injection_threshold=0.7,
                safety_threshold=0.8,
                request_id="req_test",
                traceparent="00-abc-def-01",
            )
        return _run(_run_with_mock())

    def test_pass_result(self):
        result = self._mock_post(_input_pass_response())
        assert result.decision == GuardrailDecision.PASS

    def test_flag_result(self):
        result = self._mock_post(_input_flag_response())
        assert result.decision == GuardrailDecision.FLAG

    def test_block_result(self):
        result = self._mock_post(_input_block_response())
        assert result.decision == GuardrailDecision.BLOCK

    def test_injection_score_parsed(self):
        result = self._mock_post(_input_flag_response())
        assert result.injection_score == pytest.approx(0.85)

    def test_safety_category_parsed(self):
        result = self._mock_post(_input_block_response())
        assert result.safety_category == "VIOLENCE"

    def test_safety_confidence_parsed(self):
        result = self._mock_post(_input_block_response())
        assert result.safety_confidence == pytest.approx(0.95)

    def test_latency_positive(self):
        result = self._mock_post(_input_pass_response())
        assert result.latency_ms >= 0.0

    def test_model_versions_parsed(self):
        result = self._mock_post(_input_pass_response())
        assert "injection" in result.model_versions or "safety" in result.model_versions


# ── check_input — failure paths ───────────────────────────────────────────────

class TestCheckInputFailures:
    def test_timeout_returns_block(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.check_input(
                text="hello",
                run_injection_check=True,
                run_safety_check=True,
                injection_threshold=0.7,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.BLOCK
        assert "guardrail_input_timeout" in result.reasons

    def test_http_error_returns_degraded(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=_MockResponse({}, status_code=503))
            client._client = mock_http
            return await client.check_input(
                text="hello",
                run_injection_check=True,
                run_safety_check=True,
                injection_threshold=0.7,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.DEGRADED

    def test_connect_error_returns_degraded(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            client._client = mock_http
            return await client.check_input(
                text="hello",
                run_injection_check=True,
                run_safety_check=True,
                injection_threshold=0.7,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.DEGRADED

    def test_timeout_decision_not_pass(self):
        # CRITICAL: input timeout must never return PASS
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.check_input(
                text="hello",
                run_injection_check=True,
                run_safety_check=True,
                injection_threshold=0.7,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision != GuardrailDecision.PASS


# ── check_output — success paths ──────────────────────────────────────────────

class TestCheckOutputSuccess:
    def _mock_output(self, response_data: dict) -> GuardrailResult:
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=_MockResponse(response_data))
            client._client = mock_http
            return await client.check_output(
                text="model output text",
                run_safety_check=True,
                safety_threshold=0.8,
                request_id="req_out",
            )
        return _run(run())

    def test_pass_result(self):
        result = self._mock_output(_output_pass_response())
        assert result.decision == GuardrailDecision.PASS

    def test_block_result(self):
        result = self._mock_output(_output_block_response())
        assert result.decision == GuardrailDecision.BLOCK

    def test_safety_category_parsed(self):
        result = self._mock_output(_output_block_response())
        assert result.safety_category == "VIOLENCE"


# ── check_output — failure paths ──────────────────────────────────────────────

class TestCheckOutputFailures:
    def test_timeout_returns_degraded(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.check_output(
                text="output text",
                run_safety_check=True,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.DEGRADED
        assert "guardrail_output_timeout" in result.reasons

    def test_connect_error_returns_degraded(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            client._client = mock_http
            return await client.check_output(
                text="output text",
                run_safety_check=True,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.DEGRADED

    def test_output_timeout_is_not_block(self):
        # CRITICAL: output timeout must NOT be BLOCK (non-blocking pass per CLAUDE.md)
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.check_output(
                text="output text",
                run_safety_check=True,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision != GuardrailDecision.BLOCK


# ── Asymmetric timeout semantics (the critical CLAUDE.md invariant) ───────────

class TestAsymmetricTimeout:
    """
    Per CLAUDE.md Section 14.7:
    Input timeout  → BLOCK (conservative fail-closed)
    Output timeout → DEGRADED (non-blocking fail-open)
    """

    def test_input_timeout_is_block_not_degraded(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.check_input(
                text="hello",
                run_injection_check=True,
                run_safety_check=True,
                injection_threshold=0.7,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.BLOCK

    def test_output_timeout_is_degraded_not_block(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.check_output(
                text="output",
                run_safety_check=True,
                safety_threshold=0.8,
            )
        result = _run(run())
        assert result.decision == GuardrailDecision.DEGRADED


# ── close() ───────────────────────────────────────────────────────────────────

class TestClose:
    def test_close_on_unopened_client_does_not_raise(self):
        async def run():
            client = _make_client()
            await client.close()  # _client is None — should be no-op
        _run(run())

    def test_close_twice_does_not_raise(self):
        async def run():
            client = _make_client()
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            client._client = mock_http
            await client.close()
            await client.close()  # second close should be no-op (client is None)
        _run(run())
