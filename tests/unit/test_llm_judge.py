"""
Unit tests for evaluation/llm_judge.py.

Per CLAUDE.md §20:
  - LLM judge uses GPT-4o-mini (gpt-4o-mini)
  - Score range: 1.0–5.0 Likert scale
  - from_env() returns None when OPENAI_API_KEY is absent
  - Failed / invalid responses return score=-1.0 (JudgeResult.is_valid == False)
  - Privacy: API key is never logged; raw prompt/response not stored

All tests mock the OpenAI API — no real API calls in CI.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from evaluation.llm_judge import JudgeResult, LLMJudge, _JUDGE_MODEL


# ── JudgeResult ───────────────────────────────────────────────────────────────

class TestJudgeResult:
    def test_is_valid_in_range(self):
        for score in (1.0, 2.5, 3.0, 4.0, 5.0):
            r = JudgeResult(score=score, reasoning="ok", model_used=_JUDGE_MODEL, latency_ms=100.0)
            assert r.is_valid, f"Expected is_valid=True for score={score}"

    def test_is_valid_out_of_range(self):
        for score in (-1.0, 0.0, 0.9, 5.1, 99.0):
            r = JudgeResult(score=score, reasoning="fail", model_used=_JUDGE_MODEL, latency_ms=100.0)
            assert not r.is_valid, f"Expected is_valid=False for score={score}"

    def test_failed_result_not_valid(self):
        r = LLMJudge._failed_result(latency_ms=50.0)
        assert not r.is_valid
        assert r.score == -1.0

    def test_failed_result_model_name(self):
        r = LLMJudge._failed_result(latency_ms=50.0)
        assert r.model_used == _JUDGE_MODEL

    def test_failed_result_reasoning(self):
        r = LLMJudge._failed_result(latency_ms=50.0)
        assert r.reasoning == "evaluation_failed"


# ── LLMJudge.from_env ─────────────────────────────────────────────────────────

class TestFromEnv:
    def test_returns_none_when_key_absent(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        judge = LLMJudge.from_env()
        assert judge is None

    def test_returns_none_when_key_empty(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "")
        judge = LLMJudge.from_env()
        assert judge is None

    def test_returns_none_when_key_whitespace(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        judge = LLMJudge.from_env()
        assert judge is None

    def test_returns_judge_when_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        judge = LLMJudge.from_env()
        assert judge is not None
        assert isinstance(judge, LLMJudge)


# ── LLMJudge constructor ──────────────────────────────────────────────────────

class TestConstructor:
    def test_raises_on_empty_key(self):
        with pytest.raises(ValueError, match="openai_api_key"):
            LLMJudge(openai_api_key="")

    def test_accepts_valid_key(self):
        judge = LLMJudge(openai_api_key="sk-fake-test")
        assert judge is not None

    def test_key_not_exposed_in_repr(self):
        judge = LLMJudge(openai_api_key="sk-secret-key")
        assert "sk-secret-key" not in repr(judge)


# ── score() — mocked API ──────────────────────────────────────────────────────

def _fake_urlopen(payload_bytes: bytes, score: int = 4):
    """Return a mock urlopen context manager that yields a fake API response."""
    fake_response_content = json.dumps({
        "choices": [{
            "message": {
                "content": json.dumps({"score": score, "reasoning": "Correct and clear."})
            }
        }]
    })

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=fake_response_content.encode("utf-8"))
    return mock_resp


class TestScore:
    def test_returns_valid_result_on_success(self):
        judge = LLMJudge(openai_api_key="sk-fake")
        with patch("urllib.request.urlopen", return_value=_fake_urlopen(b"", score=4)):
            result = judge.score(
                prompt="What is 2+2?",
                response="4",
                domain="math",
            )
        assert result.is_valid
        assert result.score == 4.0
        assert result.model_used == _JUDGE_MODEL
        assert result.latency_ms >= 0.0

    def test_returns_failed_result_on_network_error(self):
        import urllib.error
        judge = LLMJudge(openai_api_key="sk-fake")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            result = judge.score(
                prompt="What is 2+2?",
                response="4",
                domain="math",
            )
        assert not result.is_valid
        assert result.score == -1.0

    def test_returns_failed_result_on_http_error(self):
        import urllib.error
        judge = LLMJudge(openai_api_key="sk-fake")
        exc = urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs=None,  # type: ignore
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=exc):
            result = judge.score(
                prompt="What is 2+2?",
                response="4",
                domain="math",
            )
        assert not result.is_valid

    def test_returns_failed_result_on_invalid_json(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=b"not-json")
        judge = LLMJudge(openai_api_key="sk-fake")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = judge.score(prompt="Q?", response="A.", domain="general")
        assert not result.is_valid

    def test_out_of_range_score_returns_failed(self):
        fake = json.dumps({
            "choices": [{"message": {"content": json.dumps({"score": 99, "reasoning": "high"})}}]
        })
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=fake.encode())
        judge = LLMJudge(openai_api_key="sk-fake")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = judge.score(prompt="Q?", response="A.", domain="general")
        assert not result.is_valid

    def test_prompt_truncated_to_api(self):
        """Long prompts are truncated before the API call (cost control)."""
        judge = LLMJudge(openai_api_key="sk-fake")
        long_prompt = "a" * 10_000
        captured_payloads: list[bytes] = []

        def fake_urlopen(req, timeout=None):
            captured_payloads.append(req.data)
            return _fake_urlopen(req.data, score=3)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            judge.score(prompt=long_prompt, response="Answer.", domain="test")

        assert captured_payloads, "No API call captured"
        payload = json.loads(captured_payloads[0])
        user_content = payload["messages"][1]["content"]
        assert len(user_content) < len(long_prompt), "Long prompt must be truncated"

    def test_api_key_not_in_log_output(self, caplog):
        import logging
        judge = LLMJudge(openai_api_key="sk-super-secret-key")
        import urllib.error
        exc = urllib.error.URLError("connection refused")
        with patch("urllib.request.urlopen", side_effect=exc):
            with caplog.at_level(logging.DEBUG, logger="evaluation.llm_judge"):
                judge.score(prompt="Q?", response="A.", domain="test")
        for record in caplog.records:
            assert "sk-super-secret-key" not in record.getMessage(), (
                "API key leaked in logs"
            )

    def test_all_scores_in_range_are_valid(self):
        for score in (1, 2, 3, 4, 5):
            judge = LLMJudge(openai_api_key="sk-fake")
            with patch("urllib.request.urlopen", return_value=_fake_urlopen(b"", score=score)):
                result = judge.score(prompt="Q?", response="A.", domain="test")
            assert result.is_valid, f"Score {score} should be valid"
            assert result.score == float(score)
