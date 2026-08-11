"""
Unit tests for gateway/vllm_client.py.

Tests cover:
- VLLMRequest: dataclass fields
- VLLMResponse: dataclass fields
- VLLMClient.complete: success path, HTTP error, timeout, no-start guard
- _parse_response: content extraction, finish_reason, usage tokens
- VLLMClient.health_check: success and failure paths

All vLLM HTTP calls are mocked via httpx transport — no real network I/O.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gateway.vllm_client import VLLMClient, VLLMRequest, VLLMResponse, _parse_response


# ── VLLMRequest / VLLMResponse dataclasses ─────────────────────────────────────

class TestVLLMRequest:
    def test_required_fields(self):
        req = VLLMRequest(
            model="deepseek-r1-7b",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=512,
            extra_body={},
        )
        assert req.model == "deepseek-r1-7b"
        assert req.max_tokens == 512
        assert req.stream is False
        assert req.temperature == 0.0

    def test_optional_fields_default_to_none(self):
        req = VLLMRequest(
            model="m",
            messages=[],
            max_tokens=100,
            extra_body={},
        )
        assert req.traceparent is None
        assert req.request_id is None


class TestVLLMResponse:
    def test_fields(self):
        resp = VLLMResponse(
            content="The answer is 42.",
            model_version="deepseek-r1-7b",
            reasoning_tokens_used=200,
            output_tokens=50,
            ttft_ms=100.0,
            total_latency_ms=500.0,
            finish_reason="stop",
        )
        assert resp.content == "The answer is 42."
        assert resp.reasoning_tokens_used == 200
        assert resp.raw_response is None


# ── _parse_response ─────────────────────────────────────────────────────────────

def _make_request() -> VLLMRequest:
    return VLLMRequest(
        model="deepseek-r1-7b",
        messages=[{"role": "user", "content": "Test"}],
        max_tokens=512,
        extra_body={},
    )


class TestParseResponse:
    def test_parses_content(self):
        data = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "model": "deepseek-r1-7b",
            "usage": {"completion_tokens": 10, "prompt_tokens": 5},
        }
        result = _parse_response(_make_request(), data, 300.0)
        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert result.output_tokens == 10

    def test_empty_choices_returns_empty_content(self):
        data = {"choices": [], "model": "deepseek-r1-7b", "usage": {}}
        result = _parse_response(_make_request(), data, 100.0)
        assert result.content == ""
        assert result.finish_reason == "unknown"

    def test_reasoning_content_estimated(self):
        data = {
            "choices": [{
                "message": {
                    "content": "Final answer",
                    "reasoning_content": "A" * 400,  # ~100 tokens at 4 chars/token
                },
                "finish_reason": "stop",
            }],
            "model": "deepseek-r1-7b",
            "usage": {"completion_tokens": 120},
        }
        result = _parse_response(_make_request(), data, 200.0)
        assert result.reasoning_tokens_used == 100  # 400 // 4

    def test_total_latency_stored(self):
        data = {
            "choices": [{"message": {"content": "x"}, "finish_reason": "length"}],
            "model": "m",
            "usage": {"completion_tokens": 5},
        }
        result = _parse_response(_make_request(), data, 987.654)
        assert result.total_latency_ms == pytest.approx(987.654)

    def test_model_version_from_response(self):
        data = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "model": "deepseek-r1-7b-q4",
            "usage": {},
        }
        result = _parse_response(_make_request(), data, 100.0)
        assert result.model_version == "deepseek-r1-7b-q4"

    def test_model_falls_back_to_request_model(self):
        data = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "usage": {},
        }
        result = _parse_response(_make_request(), data, 100.0)
        assert result.model_version == "deepseek-r1-7b"


# ── VLLMClient ──────────────────────────────────────────────────────────────────

def _make_vllm_client() -> VLLMClient:
    return VLLMClient(base_url="http://vllm:8080", timeout_seconds=30.0)


def _good_response_payload() -> dict:
    return {
        "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
        "model": "deepseek-r1-7b",
        "usage": {"completion_tokens": 20, "prompt_tokens": 10},
    }


class TestVLLMClientCompleteNotStarted:
    def test_raises_when_not_started(self):
        import asyncio
        client = _make_vllm_client()
        req = VLLMRequest(model="m", messages=[], max_tokens=10, extra_body={})
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(client.complete(req))


class TestVLLMClientComplete:
    def _run_complete(self, response_data: dict) -> VLLMResponse:
        """Run VLLMClient.complete with a mocked httpx session."""
        import asyncio

        class _MockResponse:
            status_code = 200
            def json(self):
                return response_data
            def raise_for_status(self):
                pass

        async def run():
            client = _make_vllm_client()
            mock_httpx = AsyncMock()
            mock_httpx.post = AsyncMock(return_value=_MockResponse())
            client._client = mock_httpx
            req = VLLMRequest(
                model="deepseek-r1-7b",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=512,
                extra_body={},
                traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                request_id="req_abc123",
            )
            return await client.complete(req)

        return asyncio.run(run())

    def test_success_path(self):
        result = self._run_complete(_good_response_payload())
        assert result.content == "Answer"
        assert result.output_tokens == 20

    def test_traceparent_and_request_id_in_headers(self):
        import asyncio
        response_data = _good_response_payload()

        captured_headers = {}

        class _MockResponse:
            status_code = 200
            def json(self): return response_data
            def raise_for_status(self): pass

        async def run():
            client = _make_vllm_client()
            mock_httpx = AsyncMock()
            async def post_capture(*args, **kwargs):
                captured_headers.update(kwargs.get("headers", {}))
                return _MockResponse()
            mock_httpx.post = post_capture
            client._client = mock_httpx
            req = VLLMRequest(
                model="deepseek-r1-7b",
                messages=[],
                max_tokens=10,
                extra_body={},
                traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                request_id="req_test",
            )
            return await client.complete(req)

        asyncio.run(run())
        assert captured_headers.get("traceparent") is not None
        assert captured_headers.get("X-Request-ID") == "req_test"

    def test_http_error_propagates(self):
        import asyncio

        async def run():
            client = _make_vllm_client()

            class _ErrorResponse:
                status_code = 500
                def raise_for_status(self):
                    raise httpx.HTTPStatusError(
                        "Server error", request=MagicMock(), response=self
                    )

            mock_httpx = AsyncMock()
            mock_httpx.post = AsyncMock(return_value=_ErrorResponse())
            client._client = mock_httpx
            req = VLLMRequest(model="m", messages=[], max_tokens=10, extra_body={})
            await client.complete(req)

        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(run())

    def test_timeout_propagates(self):
        import asyncio

        async def run():
            client = _make_vllm_client()
            mock_httpx = AsyncMock()
            mock_httpx.post = AsyncMock(
                side_effect=httpx.TimeoutException("Timed out")
            )
            client._client = mock_httpx
            req = VLLMRequest(model="m", messages=[], max_tokens=10, extra_body={})
            await client.complete(req)

        with pytest.raises(httpx.TimeoutException):
            asyncio.run(run())


class TestVLLMClientHealthCheck:
    def test_returns_true_on_200(self):
        import asyncio

        async def run():
            client = _make_vllm_client()

            class _OkResp:
                status_code = 200

            mock_httpx = AsyncMock()
            mock_httpx.get = AsyncMock(return_value=_OkResp())
            client._client = mock_httpx
            return await client.health_check()

        assert asyncio.run(run()) is True

    def test_returns_false_on_non_200(self):
        import asyncio

        async def run():
            client = _make_vllm_client()

            class _BadResp:
                status_code = 503

            mock_httpx = AsyncMock()
            mock_httpx.get = AsyncMock(return_value=_BadResp())
            client._client = mock_httpx
            return await client.health_check()

        assert asyncio.run(run()) is False

    def test_returns_false_on_exception(self):
        import asyncio

        async def run():
            client = _make_vllm_client()
            mock_httpx = AsyncMock()
            mock_httpx.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            client._client = mock_httpx
            return await client.health_check()

        assert asyncio.run(run()) is False

    def test_returns_false_when_client_is_none(self):
        import asyncio

        async def run():
            client = _make_vllm_client()
            # Never started — _client is None
            return await client.health_check()

        assert asyncio.run(run()) is False
