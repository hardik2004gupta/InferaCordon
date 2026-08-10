"""
GPT-4o-mini LLM-as-judge for non-verifiable response quality scoring.

Per CLAUDE.md §20:
  Model: gpt-4o-mini
  Scale: 1–5 Likert
  Called asynchronously from async_eval_worker.py — NEVER on the request path
  Requires OPENAI_API_KEY env variable; returns blocked result when absent

Privacy:
  Only redacted prompts (already PII-stripped by Presidio) reach the API.
  Raw prompt/response are in memory only; not stored in SQLite or logs.
  The judge API key is never logged.

Security:
  Judge instructions live in the system prompt.
  Evaluated content is in the user turn only.
  Content cannot override scoring instructions.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_JUDGE_MODEL = "gpt-4o-mini"
_TIMEOUT_SECONDS = 30
_MAX_RETRIES = 2

# Scoring rubric lives in system prompt so evaluated content cannot override it.
_SYSTEM_PROMPT = """You are a response quality evaluator for an AI inference system.

Score the AI response on a 1–5 Likert scale:
  1 — Completely wrong, incoherent, or refuses to answer without reason
  2 — Partially correct but contains significant errors or omissions
  3 — Correct overall but lacks depth, precision, or clarity
  4 — Correct and clear; meets the request well
  5 — Excellent: correct, precise, clear, and appropriately concise

Return only valid JSON:
{"score": <integer 1-5>, "reasoning": "<one sentence>"}

No other text. Do not reproduce the question or response in your output.""".strip()


@dataclass
class JudgeResult:
    score: float        # 1.0–5.0 on success; -1.0 if blocked/failed
    reasoning: str      # Judge rationale (not stored in audit log)
    model_used: str     # "gpt-4o-mini"
    latency_ms: float

    @property
    def is_valid(self) -> bool:
        """True when the score is within the defined 1-5 range."""
        return 1.0 <= self.score <= 5.0


class LLMJudge:
    """
    GPT-4o-mini quality judge.
    Called from async_eval_worker thread — never on the inference request path.
    """

    def __init__(self, openai_api_key: str) -> None:
        if not openai_api_key:
            raise ValueError("openai_api_key must be non-empty")
        self._api_key = openai_api_key

    @classmethod
    def from_env(cls) -> Optional["LLMJudge"]:
        """
        Return a judge from OPENAI_API_KEY env var.
        Returns None (BLOCKED) when the key is absent or empty.
        """
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            log.warning("OPENAI_API_KEY not set — LLM judge BLOCKED (eval skipped)")
            return None
        return cls(openai_api_key=key)

    def score(self, prompt: str, response: str, domain: str) -> JudgeResult:
        """
        Score a response using GPT-4o-mini.

        prompt:   Redacted prompt (PII-safe — processed by Presidio).
        response: Model response text.
        domain:   Request domain for context.

        Returns JudgeResult; score=-1.0 if the API call fails after retries.
        """
        t0 = time.perf_counter()

        # Truncate to keep API costs low and avoid token limit errors
        prompt_excerpt = prompt[:2_000]
        response_excerpt = response[:3_000]

        user_message = (
            f"Domain: {domain}\n\n"
            f"Question:\n{prompt_excerpt}\n\n"
            f"Response to evaluate:\n{response_excerpt}"
        )

        payload = {
            "model": _JUDGE_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 128,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = self._call_api(payload)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                if result is not None:
                    return result
                # API returned unparseable JSON — treat as failure
                log.warning(
                    "LLM judge returned unparseable response on attempt %d", attempt
                )
            except Exception as exc:
                last_exc = exc
                log.debug("LLM judge attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        log.warning(
            "LLM judge failed after %d attempts: %s", _MAX_RETRIES, last_exc
        )
        return self._failed_result(latency_ms)

    def _call_api(self, payload: dict) -> Optional[JudgeResult]:
        """
        Make one HTTP POST to the OpenAI chat completions endpoint.
        Returns JudgeResult on success, None if response cannot be parsed.
        Raises RuntimeError on network or HTTP errors.
        """
        t0 = time.perf_counter()
        body_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url="https://api.openai.com/v1/chat/completions",
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                raw_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI API HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API network error: {exc.reason}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000.0

        try:
            outer = json.loads(raw_bytes.decode("utf-8"))
            content_str = outer["choices"][0]["message"]["content"]
            parsed = json.loads(content_str)
            score_raw = parsed.get("score")
            reasoning = str(parsed.get("reasoning", ""))[:500]
        except (KeyError, TypeError, json.JSONDecodeError, IndexError) as exc:
            log.warning("Failed to parse judge response: %s", exc)
            return None

        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            log.warning("Judge score not numeric: %r", score_raw)
            return None

        if not (1.0 <= score <= 5.0):
            log.warning("Judge score out of range: %s", score_raw)
            return None

        return JudgeResult(
            score=score,
            reasoning=reasoning,
            model_used=_JUDGE_MODEL,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _failed_result(latency_ms: float) -> JudgeResult:
        return JudgeResult(
            score=-1.0,
            reasoning="evaluation_failed",
            model_used=_JUDGE_MODEL,
            latency_ms=latency_ms,
        )
