"""
GPT-4o-mini LLM-as-judge for non-verifiable response quality scoring.

Per CLAUDE.md Sections 20 and 22:
- Used for MMLU-Pro and internal corpus (no ground-truth verifier)
- Score: 1-5 Likert scale (rubric defined in CLAUDE.md Section 20)
- Model: gpt-4o-mini (cost-effective judge per architecture decision)
- Called asynchronously from async_eval_worker.py — never on request path
- Requires OPENAI_API_KEY env variable
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JudgeResult:
    score: float        # 1.0–5.0
    reasoning: str      # Judge's brief rationale (not stored in audit log)
    model_used: str     # "gpt-4o-mini"
    latency_ms: float


class LLMJudge:
    """GPT-4o-mini quality judge. Week 10 onwards."""

    def __init__(self, openai_api_key: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 10)")

    def score(self, prompt: str, response: str, domain: str) -> JudgeResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 10)")
