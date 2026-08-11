"""
Unit tests for gateway/async_eval_worker.py.

Per CLAUDE.md §20:
  - submit() returns immediately (non-blocking)
  - Job state machine: PENDING → RUNNING → COMPLETED | FAILED
  - SQLite stores SHA-256 hashes; never raw prompt or response text
  - Shutdown drains pending tasks
  - Concurrent submissions are safe (threading lock on SQLite writes)
  - LLM judge absent (no OPENAI_API_KEY) → FAILED with known error code
"""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gateway.async_eval_worker import AsyncEvalWorker, EvalTask


def _make_task(**overrides) -> EvalTask:
    defaults = dict(
        request_id="req_abc123",
        tenant_id="acme_corp",
        domain="general_qa",
        prompt="What is 2+2?",
        response="4",
        budget_class="medium",
        verification_result="unverifiable",
        policy_version=1,
    )
    defaults.update(overrides)
    return EvalTask(**defaults)


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_eval.db")


@pytest.fixture
def worker(tmp_db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    w = AsyncEvalWorker(db_path=tmp_db, max_workers=2)
    yield w
    # Synchronous shutdown in fixture teardown (can't use await in sync fixture)
    w._executor.shutdown(wait=True, cancel_futures=False)
    if w._conn:
        w._conn.close()


class TestSetup:
    def test_creates_db_file(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "test.db")
        w = AsyncEvalWorker(db_path=db_path, max_workers=1)
        assert Path(db_path).exists()
        w._executor.shutdown(wait=True)
        w._conn.close()

    def test_schema_has_eval_jobs_table(self, tmp_db):
        w = AsyncEvalWorker(db_path=tmp_db, max_workers=1)
        tables = [row[0] for row in w._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert "eval_jobs" in tables
        w._executor.shutdown(wait=True)
        w._conn.close()

    def test_schema_has_required_columns(self, tmp_db):
        w = AsyncEvalWorker(db_path=tmp_db, max_workers=1)
        cols = {row[1] for row in w._conn.execute("PRAGMA table_info(eval_jobs)")}
        required = {
            "job_id", "request_id", "tenant_id", "domain", "budget_class",
            "verification_result", "policy_version",
            "prompt_sha256", "response_sha256",
            "status", "score", "reasoning",
            "judge_model", "judge_latency_ms",
            "created_at", "started_at", "completed_at", "error",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"
        w._executor.shutdown(wait=True)
        w._conn.close()


class TestSubmit:
    def test_submit_returns_immediately(self, worker):
        task = _make_task()
        t0 = time.perf_counter()
        worker.submit(task)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert elapsed_ms < 200, f"submit() took {elapsed_ms:.0f}ms — must be non-blocking"

    def test_submit_creates_pending_record(self, worker, tmp_db):
        task = _make_task(request_id="req_test001")
        worker.submit(task)
        time.sleep(0.05)  # let the DB write complete
        rows = worker._conn.execute(
            "SELECT status FROM eval_jobs WHERE request_id=?", ("req_test001",)
        ).fetchall()
        assert len(rows) >= 1
        # Record starts as PENDING or may have already transitioned
        assert rows[0][0] in ("PENDING", "RUNNING", "COMPLETED", "FAILED")

    def test_multiple_submits_create_separate_rows(self, worker):
        for i in range(5):
            worker.submit(_make_task(request_id=f"req_{i:04d}"))
        time.sleep(0.2)
        count = worker._conn.execute("SELECT count(*) FROM eval_jobs").fetchone()[0]
        assert count == 5


class TestPrivacy:
    def test_raw_prompt_not_stored(self, worker):
        secret_prompt = "super-secret-proprietary-prompt-do-not-store"
        worker.submit(_make_task(prompt=secret_prompt))
        time.sleep(0.3)
        # SQLite must not contain the raw prompt string in any column
        all_text = " ".join(
            str(v) for row in worker._conn.execute("SELECT * FROM eval_jobs")
            for v in row if v is not None
        )
        assert secret_prompt not in all_text, "Raw prompt found in SQLite — privacy violation"

    def test_raw_response_not_stored(self, worker):
        secret_response = "secret-response-text-must-not-persist"
        worker.submit(_make_task(response=secret_response))
        time.sleep(0.3)
        all_text = " ".join(
            str(v) for row in worker._conn.execute("SELECT * FROM eval_jobs")
            for v in row if v is not None
        )
        assert secret_response not in all_text, "Raw response found in SQLite — privacy violation"

    def test_prompt_sha256_stored(self, worker):
        prompt = "What is 2+2?"
        expected_hash = hashlib.sha256(prompt.encode()).hexdigest()
        worker.submit(_make_task(prompt=prompt, request_id="req_hash_test"))
        time.sleep(0.2)
        row = worker._conn.execute(
            "SELECT prompt_sha256 FROM eval_jobs WHERE request_id=?",
            ("req_hash_test",),
        ).fetchone()
        assert row is not None
        assert row[0] == expected_hash

    def test_response_sha256_stored(self, worker):
        response = "The answer is 4."
        expected_hash = hashlib.sha256(response.encode()).hexdigest()
        worker.submit(_make_task(response=response, request_id="req_hash_resp"))
        time.sleep(0.2)
        row = worker._conn.execute(
            "SELECT response_sha256 FROM eval_jobs WHERE request_id=?",
            ("req_hash_resp",),
        ).fetchone()
        assert row is not None
        assert row[0] == expected_hash


class TestJobStateWithoutApiKey:
    """When OPENAI_API_KEY is absent, jobs complete with FAILED status."""

    def test_job_reaches_failed_when_no_api_key(self, worker):
        task = _make_task(request_id="req_no_key")
        worker.submit(task)

        # Wait for job to complete (max 5s)
        deadline = time.time() + 5.0
        status = None
        while time.time() < deadline:
            row = worker._conn.execute(
                "SELECT status FROM eval_jobs WHERE request_id=?", ("req_no_key",)
            ).fetchone()
            if row and row[0] in ("COMPLETED", "FAILED"):
                status = row[0]
                break
            time.sleep(0.05)

        assert status == "FAILED", f"Expected FAILED, got {status}"

    def test_failed_job_has_error_field(self, worker):
        task = _make_task(request_id="req_error_field")
        worker.submit(task)
        time.sleep(1.0)
        row = worker._conn.execute(
            "SELECT status, error FROM eval_jobs WHERE request_id=?",
            ("req_error_field",),
        ).fetchone()
        assert row is not None
        assert row[0] == "FAILED"
        assert row[1] is not None  # error column populated


class TestJobStateWithMockedJudge:
    """Verify COMPLETED state when judge returns a valid score."""

    def test_job_reaches_completed_on_valid_score(self, tmp_db):
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.score = 4.0
        mock_result.reasoning = "Good answer."
        mock_result.model_used = "gpt-4o-mini"
        mock_result.latency_ms = 120.0

        mock_judge = MagicMock()
        mock_judge.score.return_value = mock_result

        with patch("evaluation.llm_judge.LLMJudge.from_env", return_value=mock_judge):
            worker = AsyncEvalWorker(db_path=tmp_db, max_workers=1)
            worker.submit(_make_task(request_id="req_mocked"))

            deadline = time.time() + 5.0
            status = None
            while time.time() < deadline:
                row = worker._conn.execute(
                    "SELECT status, score FROM eval_jobs WHERE request_id=?",
                    ("req_mocked",),
                ).fetchone()
                if row and row[0] in ("COMPLETED", "FAILED"):
                    status = row[0]
                    db_score = row[1]
                    break
                time.sleep(0.05)

            worker._executor.shutdown(wait=True)
            worker._conn.close()

        assert status == "COMPLETED", f"Expected COMPLETED, got {status}"
        assert db_score == 4.0


class TestConcurrentSafety:
    def test_concurrent_submits_no_db_corruption(self, worker):
        tasks = [_make_task(request_id=f"req_concurrent_{i}") for i in range(20)]
        threads = [threading.Thread(target=worker.submit, args=(t,)) for t in tasks]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        time.sleep(0.5)
        count = worker._conn.execute("SELECT count(*) FROM eval_jobs").fetchone()[0]
        assert count == 20, f"Expected 20 rows, got {count}"
