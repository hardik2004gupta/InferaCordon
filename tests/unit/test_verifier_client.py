"""
Unit tests for gateway/verifier_client.py.

Coverage:
  VerificationResult enum values
  VerifierResponse fields and defaults
  VerifierClient.verify():
    — successful CORRECT response
    — successful INCORRECT response
    — successful unverifiable reason → UNVERIFIABLE result
    — TimeoutException → UNVERIFIABLE
    — HTTPStatusError → UNVERIFIABLE
    — generic Exception → UNVERIFIABLE
    — schema kwarg forwarded in payload
    — X-Request-ID and traceparent headers forwarded

All tests mock the httpx.AsyncClient to avoid real network calls.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gateway.verifier_client import (
    VerificationResult,
    VerifierClient,
    VerifierResponse,
    _parse_verify_response,
    _unverifiable,
)


def _run(coro):
    return asyncio.run(coro)


# ── VerificationResult ────────────────────────────────────────────────────────

class TestVerificationResultEnum:
    def test_correct_value(self):
        assert VerificationResult.CORRECT == "correct"

    def test_incorrect_value(self):
        assert VerificationResult.INCORRECT == "incorrect"

    def test_unverifiable_value(self):
        assert VerificationResult.UNVERIFIABLE == "unverifiable"


# ── VerifierResponse ──────────────────────────────────────────────────────────

class TestVerifierResponseDefaults:
    def test_predicted_default(self):
        r = VerifierResponse(
            result=VerificationResult.CORRECT,
            verifier_type="gsm8k",
            reason="correct",
        )
        assert r.predicted == ""

    def test_expected_default(self):
        r = VerifierResponse(
            result=VerificationResult.CORRECT,
            verifier_type="gsm8k",
            reason="correct",
        )
        assert r.expected == ""

    def test_latency_ms_default(self):
        r = VerifierResponse(
            result=VerificationResult.CORRECT,
            verifier_type="gsm8k",
            reason="correct",
        )
        assert r.latency_ms == 0.0

    def test_verifier_version_default(self):
        r = VerifierResponse(
            result=VerificationResult.CORRECT,
            verifier_type="gsm8k",
            reason="correct",
        )
        assert r.verifier_version == "verifier_v1"


# ── _parse_verify_response helper ─────────────────────────────────────────────

class TestParseVerifyResponse:
    def test_passed_true_returns_correct(self):
        r = _parse_verify_response(
            {"passed": True, "verifier_type": "gsm8k", "reason": "correct"}, 5.0
        )
        assert r.result == VerificationResult.CORRECT

    def test_passed_false_non_unverifiable_reason_returns_incorrect(self):
        r = _parse_verify_response(
            {"passed": False, "verifier_type": "gsm8k", "reason": "numeric_mismatch"}, 5.0
        )
        assert r.result == VerificationResult.INCORRECT

    def test_passed_false_unverifiable_reason_returns_unverifiable(self):
        r = _parse_verify_response(
            {"passed": False, "verifier_type": "gsm8k", "reason": "unverifiable_no_schema"}, 5.0
        )
        assert r.result == VerificationResult.UNVERIFIABLE

    def test_latency_ms_preserved(self):
        r = _parse_verify_response({"passed": True, "verifier_type": "v", "reason": "ok"}, 42.5)
        assert r.latency_ms == pytest.approx(42.5)

    def test_predicted_and_expected_extracted(self):
        r = _parse_verify_response(
            {"passed": True, "verifier_type": "gsm8k", "reason": "ok",
             "predicted": "42.0", "expected": "42.0"}, 1.0,
        )
        assert r.predicted == "42.0"
        assert r.expected == "42.0"


# ── _unverifiable helper ──────────────────────────────────────────────────────

class TestUnverifiableHelper:
    def test_result_is_unverifiable(self):
        r = _unverifiable("verifier_timeout", "gsm8k", 200.0)
        assert r.result == VerificationResult.UNVERIFIABLE

    def test_reason_set(self):
        r = _unverifiable("verifier_timeout", "gsm8k", 200.0)
        assert r.reason == "verifier_timeout"

    def test_verifier_type_set(self):
        r = _unverifiable("verifier_timeout", "json_schema", 1.0)
        assert r.verifier_type == "json_schema"


# ── VerifierClient.verify() ───────────────────────────────────────────────────

def _make_http_response(body: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestVerifierClientSuccess:
    """Happy path: verifier service responds correctly."""

    def test_correct_result_returned(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(
                return_value=_make_http_response(
                    {"passed": True, "verifier_type": "json_schema", "reason": "correct"}
                )
            )
            client._client = mock_http
            return await client.verify(
                response='{"key": "value"}',
                verifier_type="json_schema",
                schema={"type": "object"},
            )
        r = _run(run())
        assert r.result == VerificationResult.CORRECT

    def test_incorrect_result_returned(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(
                return_value=_make_http_response(
                    {"passed": False, "verifier_type": "gsm8k", "reason": "numeric_mismatch"}
                )
            )
            client._client = mock_http
            return await client.verify(response="42", verifier_type="gsm8k", ground_truth="99")
        r = _run(run())
        assert r.result == VerificationResult.INCORRECT

    def test_schema_forwarded_in_payload(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            captured_payload = {}

            async def _post(url, *, json=None, headers=None):
                captured_payload.update(json or {})
                return _make_http_response(
                    {"passed": True, "verifier_type": "json_schema", "reason": "correct"}
                )

            mock_http.post = _post
            client._client = mock_http
            schema = {"type": "object", "required": ["name"]}
            await client.verify(
                response='{"name": "x"}',
                verifier_type="json_schema",
                schema=schema,
            )
            return captured_payload

        payload = _run(run())
        assert payload.get("schema") == {"type": "object", "required": ["name"]}

    def test_request_id_forwarded_in_header(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            captured_headers = {}

            async def _post(url, *, json=None, headers=None):
                captured_headers.update(headers or {})
                return _make_http_response(
                    {"passed": True, "verifier_type": "gsm8k", "reason": "correct"}
                )

            mock_http.post = _post
            client._client = mock_http
            await client.verify(
                response="42",
                verifier_type="gsm8k",
                ground_truth="42",
                request_id="req_test_123",
            )
            return captured_headers

        headers = _run(run())
        assert headers.get("X-Request-ID") == "req_test_123"

    def test_traceparent_forwarded_in_header(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            captured_headers = {}

            async def _post(url, *, json=None, headers=None):
                captured_headers.update(headers or {})
                return _make_http_response(
                    {"passed": True, "verifier_type": "gsm8k", "reason": "correct"}
                )

            mock_http.post = _post
            client._client = mock_http
            await client.verify(
                response="42",
                verifier_type="gsm8k",
                traceparent="00-trace-span-01",
            )
            return captured_headers

        headers = _run(run())
        assert headers.get("traceparent") == "00-trace-span-01"


class TestVerifierClientFailureHandling:
    """Per CLAUDE.md §15.4 — all failures return UNVERIFIABLE, never raise."""

    def test_timeout_returns_unverifiable(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.verify(response="42", verifier_type="gsm8k")
        r = _run(run())
        assert r.result == VerificationResult.UNVERIFIABLE
        assert "timeout" in r.reason

    def test_timeout_does_not_raise(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            await client.verify(response="42", verifier_type="gsm8k")
        _run(run())  # must not raise

    def test_http_status_error_returns_unverifiable(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(
                return_value=_make_http_response({}, status_code=500)
            )
            client._client = mock_http
            return await client.verify(response="42", verifier_type="gsm8k")
        r = _run(run())
        assert r.result == VerificationResult.UNVERIFIABLE

    def test_generic_exception_returns_unverifiable(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=ConnectionRefusedError("refused"))
            client._client = mock_http
            return await client.verify(response="42", verifier_type="gsm8k")
        r = _run(run())
        assert r.result == VerificationResult.UNVERIFIABLE

    def test_unverifiable_reason_contains_source(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            client._client = mock_http
            return await client.verify(response="42", verifier_type="gsm8k")
        r = _run(run())
        assert r.reason  # non-empty

    def test_verifier_type_preserved_on_error(self):
        async def run():
            client = VerifierClient("http://verifier:8002")
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("t"))
            client._client = mock_http
            return await client.verify(response="42", verifier_type="json_schema")
        r = _run(run())
        assert r.verifier_type == "json_schema"
