"""
Asynchronous evaluation worker — background thread pool for non-blocking eval.

Per CLAUDE.md §5, §20, §22:
  - GPT-4o-mini LLM-as-judge for non-verifiable responses
  - SQLite persistence for job state; results feed Grafana quality panel
  - Thread pool (max 2 workers); fire-and-forget from request path
  - Job state machine: PENDING → RUNNING → COMPLETED | FAILED

Privacy:
  prompt and response are in-memory only during the judge call.
  SQLite stores SHA-256 hashes only — never raw prompt or response text.
  Per CLAUDE.md §19: store_reasoning_trace=false; no raw content in eval DB.

File: async_eval_worker.py (Part IX authoritative name over eval_worker.py)
"""
from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

_DB_PATH_DEFAULT = os.environ.get("EVAL_SQLITE_PATH", "data/eval.db")

_CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eval_jobs (
    job_id          TEXT PRIMARY KEY,
    request_id      TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    domain          TEXT NOT NULL,
    budget_class    TEXT NOT NULL,
    verification_result TEXT,
    policy_version  INTEGER NOT NULL,
    prompt_sha256   TEXT NOT NULL,
    response_sha256 TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    score           REAL,
    reasoning       TEXT,
    judge_model     TEXT,
    judge_latency_ms REAL,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_request  ON eval_jobs (request_id);
CREATE INDEX IF NOT EXISTS idx_eval_status   ON eval_jobs (status);
CREATE INDEX IF NOT EXISTS idx_eval_tenant   ON eval_jobs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_eval_created  ON eval_jobs (created_at);
"""


@dataclass
class EvalTask:
    request_id: str
    tenant_id: str
    domain: str
    prompt: str            # NOT stored in SQLite; in-memory only for judge call
    response: str          # NOT stored in SQLite; in-memory only for judge call
    budget_class: str
    verification_result: Optional[str]
    policy_version: int


class AsyncEvalWorker:
    """
    Fire-and-forget quality evaluator using thread pool + SQLite persistence.

    Thread safety: all SQLite writes are serialized by _db_lock.
    The ThreadPoolExecutor is started at __init__ and drained at shutdown().
    """

    def __init__(
        self,
        db_path: str = _DB_PATH_DEFAULT,
        max_workers: int = 2,
    ) -> None:
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="ic-eval",
        )
        self._db_lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._setup_db()
        log.info("AsyncEvalWorker started: db=%s max_workers=%d", db_path, max_workers)

    def _setup_db(self) -> None:
        pathlib.Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: connection shared across worker threads, guarded by _db_lock
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,   # autocommit; each statement is its own transaction
        )
        self._conn.executescript(_CREATE_SCHEMA_SQL)
        log.debug("Eval SQLite schema ready at %s", self._db_path)

    def submit(self, task: EvalTask) -> None:
        """
        Enqueue an eval task. Returns immediately — never blocks the request path.

        Writes a PENDING job to SQLite, then submits to the thread pool.
        If the SQLite write fails, the task is silently dropped (best-effort).
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        prompt_hash = hashlib.sha256(task.prompt.encode()).hexdigest()
        response_hash = hashlib.sha256(task.response.encode()).hexdigest()

        try:
            with self._db_lock:
                self._conn.execute(  # type: ignore[union-attr]
                    """
                    INSERT INTO eval_jobs
                        (job_id, request_id, tenant_id, domain, budget_class,
                         verification_result, policy_version,
                         prompt_sha256, response_sha256,
                         status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (
                        job_id, task.request_id, task.tenant_id, task.domain,
                        task.budget_class, task.verification_result, task.policy_version,
                        prompt_hash, response_hash, now,
                    ),
                )
        except Exception as exc:
            log.warning(
                "Eval job DB insert failed for request_id=%s: %s", task.request_id, exc
            )
            return  # drop the task; do not submit to thread pool

        self._executor.submit(self._run_eval, job_id, task)

    def _run_eval(self, job_id: str, task: EvalTask) -> None:
        """Synchronous eval logic executed in thread pool worker."""
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._db_lock:
                self._conn.execute(  # type: ignore[union-attr]
                    "UPDATE eval_jobs SET status='RUNNING', started_at=? WHERE job_id=?",
                    (started_at, job_id),
                )
        except Exception as exc:
            log.warning("Failed to mark job %s RUNNING: %s", job_id, exc)

        score: Optional[float] = None
        reasoning: Optional[str] = None
        judge_model: Optional[str] = None
        judge_latency_ms: Optional[float] = None
        error: Optional[str] = None
        status = "FAILED"

        try:
            from evaluation.llm_judge import LLMJudge

            judge = LLMJudge.from_env()
            if judge is None:
                error = "OPENAI_API_KEY_ABSENT"
                status = "FAILED"
            else:
                result = judge.score(task.prompt, task.response, task.domain)
                judge_model = result.model_used
                judge_latency_ms = result.latency_ms

                if result.is_valid:
                    score = result.score
                    reasoning = result.reasoning
                    status = "COMPLETED"
                    # Update Prometheus quality histogram (best-effort)
                    try:
                        from telemetry.prometheus_metrics import ic_quality_score_histogram
                        ic_quality_score_histogram.labels(
                            tenant_id=task.tenant_id,
                            domain=task.domain,
                        ).observe(result.score)
                    except Exception:
                        pass
                else:
                    error = f"judge_score_invalid:{result.score}"
                    status = "FAILED"

        except Exception as exc:
            error = str(exc)[:500]
            status = "FAILED"
            log.warning(
                "Eval worker exception job_id=%s request_id=%s: %s",
                job_id, task.request_id, exc,
            )

        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._db_lock:
                self._conn.execute(  # type: ignore[union-attr]
                    """
                    UPDATE eval_jobs
                    SET status=?, score=?, reasoning=?,
                        judge_model=?, judge_latency_ms=?,
                        completed_at=?, error=?
                    WHERE job_id=?
                    """,
                    (
                        status, score, reasoning,
                        judge_model, judge_latency_ms,
                        completed_at, error,
                        job_id,
                    ),
                )
        except Exception as exc:
            log.warning("Failed to finalize job %s: %s", job_id, exc)

        log.debug(
            "Eval job complete: job_id=%s request_id=%s status=%s score=%s latency=%.1fms",
            job_id, task.request_id, status, score, judge_latency_ms or 0.0,
        )

    async def shutdown(self) -> None:
        """
        Drain pending eval tasks and shut down the thread pool gracefully.
        Runs the blocking shutdown in a thread to avoid blocking the event loop.
        """
        import asyncio

        log.info("AsyncEvalWorker shutting down — draining pending tasks")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._executor.shutdown(wait=True, cancel_futures=False),
        )
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        log.info("AsyncEvalWorker shutdown complete")
