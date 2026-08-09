"""
Asynchronous evaluation worker — background thread pool for non-blocking eval.

Per CLAUDE.md Sections 20 and 22 (Failure Injection Panel):
- Runs GPT-4o-mini LLM-as-judge for non-verifiable responses (Week 10+)
- Writes evaluation results to local SQLite (not blocking main request path)
- Feeds Dashboard quality metrics (ic_quality_score_histogram)
- Worker pool size configurable via env (default 2 threads)
- Evaluation triggered after response delivery (fire-and-forget per request)

File name: async_eval_worker.py (per Part IX — authoritative over eval_worker.py from Component 1)
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional


@dataclass
class EvalTask:
    request_id: str
    tenant_id: str
    domain: str
    prompt: str           # NOT stored in audit log; only used for in-memory eval
    response: str
    budget_class: str
    verification_result: Optional[str]
    policy_version: int


class AsyncEvalWorker:
    """Fire-and-forget quality evaluator using thread pool."""

    def __init__(self, max_workers: int = 2) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 10)")

    def submit(self, task: EvalTask) -> None:
        """Enqueue eval task. Returns immediately — never blocks request path."""
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 10)")

    def _run_eval(self, task: EvalTask) -> None:
        """Synchronous eval logic executed in thread pool."""
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 10)")

    async def shutdown(self) -> None:
        """Drain queue and shut down worker pool gracefully."""
        raise NotImplementedError("Implement per CLAUDE.md Section 20 (Week 10)")
