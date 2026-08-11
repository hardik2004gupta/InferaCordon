"""
Append-only JSONL audit log writer.

Per CLAUDE.md Section 19:
- Two records per request: decision (before inference) + outcome (after delivery)
- Append-only: never modify or delete existing records
- Storage: local filesystem JSONL file (path configurable)
- NEVER store raw prompts or responses — only derived signals, counts, outcomes
- Non-blocking: writes are queued to a bounded background write thread (not asyncio)
  Per CLAUDE.md Section 7 Step 7: "write is queued to a background write thread"
  Per CLAUDE.md Section 3: "No Celery" — threading.Queue + background thread only
- Queue capacity: 1,000 entries (CLAUDE.md Section 7 Step 7)
- Queue full → write is dropped, counter incremented (logged as warning metric)
- Persisted to Docker volume; survives container restarts

Thread model: background threading.Thread drains a threading.Queue.
The gateway enqueues records with non-blocking put_nowait(). This matches
"The request does not wait" and "write queue bounded at 1,000 entries."
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_QUEUE_CAPACITY = 1_000      # CLAUDE.md Section 7 Step 7: bounded at 1,000 entries
_SENTINEL = object()         # Signal background thread to stop


# ── Outcome record ─────────────────────────────────────────────────────────────

class OutcomeRecord:
    """
    Post-inference governance record.

    Per CLAUDE.md Section 19.2.
    Written after response delivery (Step 15) by the gateway.
    References the decision record by request_id.
    """

    __slots__ = (
        "record_type", "timestamp_iso", "request_id",
        "reasoning_tokens_used", "reasoning_tokens_allocated", "tokens_saved",
        "output_tokens", "stop_reason", "escalation_count", "fallback_used",
        "guardrail_input_result", "guardrail_output_result",
        "verification_result", "actual_cost_usd",
        "queue_ms", "guardrail_input_ms", "prefill_ms", "decode_ms",
        "ttft_ms", "e2e_latency_ms", "circuit_breaker_state_at_completion",
    )

    def __init__(
        self,
        *,
        timestamp_iso: str,
        request_id: str,
        reasoning_tokens_used: int = 0,
        reasoning_tokens_allocated: int = 0,
        tokens_saved: int = 0,
        output_tokens: int = 0,
        stop_reason: str = "unknown",
        escalation_count: int = 0,
        fallback_used: bool = False,
        guardrail_input_result: str = "unknown",
        guardrail_output_result: str = "unknown",
        verification_result: str = "unknown",
        actual_cost_usd: float = 0.0,
        queue_ms: int = 0,
        guardrail_input_ms: int = 0,
        prefill_ms: int = 0,
        decode_ms: int = 0,
        ttft_ms: int = 0,
        e2e_latency_ms: int = 0,
        circuit_breaker_state_at_completion: str = "closed",
    ) -> None:
        self.record_type = "outcome"
        self.timestamp_iso = timestamp_iso
        self.request_id = request_id
        self.reasoning_tokens_used = reasoning_tokens_used
        self.reasoning_tokens_allocated = reasoning_tokens_allocated
        self.tokens_saved = tokens_saved
        self.output_tokens = output_tokens
        self.stop_reason = stop_reason
        self.escalation_count = escalation_count
        self.fallback_used = fallback_used
        self.guardrail_input_result = guardrail_input_result
        self.guardrail_output_result = guardrail_output_result
        self.verification_result = verification_result
        self.actual_cost_usd = actual_cost_usd
        self.queue_ms = queue_ms
        self.guardrail_input_ms = guardrail_input_ms
        self.prefill_ms = prefill_ms
        self.decode_ms = decode_ms
        self.ttft_ms = ttft_ms
        self.e2e_latency_ms = e2e_latency_ms
        self.circuit_breaker_state_at_completion = circuit_breaker_state_at_completion

    def to_audit_dict(self) -> dict:
        """Serialize to the exact audit JSONL format from CLAUDE.md Section 19.2."""
        return {
            "record_type": self.record_type,
            "timestamp_iso": self.timestamp_iso,
            "request_id": self.request_id,
            "reasoning_tokens_used": self.reasoning_tokens_used,
            "reasoning_tokens_allocated": self.reasoning_tokens_allocated,
            "tokens_saved": self.tokens_saved,
            "output_tokens": self.output_tokens,
            "stop_reason": self.stop_reason,
            "escalation_count": self.escalation_count,
            "fallback_used": self.fallback_used,
            "guardrail_input_result": self.guardrail_input_result,
            "guardrail_output_result": self.guardrail_output_result,
            "verification_result": self.verification_result,
            "actual_cost_usd": self.actual_cost_usd,
            "queue_ms": self.queue_ms,
            "guardrail_input_ms": self.guardrail_input_ms,
            "prefill_ms": self.prefill_ms,
            "decode_ms": self.decode_ms,
            "ttft_ms": self.ttft_ms,
            "e2e_latency_ms": self.e2e_latency_ms,
            "circuit_breaker_state_at_completion": self.circuit_breaker_state_at_completion,
        }


# ── Audit log ──────────────────────────────────────────────────────────────────

class AuditLog:
    """
    Append-only JSONL audit log.

    Per CLAUDE.md Section 19. Non-blocking queue-based writer.
    Each write enqueues a record; the background writer thread drains the queue
    and appends records to the JSONL file.

    Usage:
        audit = AuditLog(log_path="data/audit.jsonl")
        audit.start()                          # Start background writer thread
        audit.enqueue(record.to_audit_dict())  # Non-blocking enqueue
        audit.stop(timeout=5.0)               # Graceful shutdown
    """

    def __init__(self, log_path: str | Path) -> None:
        self._log_path = Path(log_path)
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_CAPACITY)
        self._dropped_count: int = 0
        self._dropped_lock = threading.Lock()
        self._writer_thread: Optional[threading.Thread] = None
        self._started = False

    def start(self) -> None:
        """Start the background writer thread. Call once at gateway startup."""
        if self._started:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="audit-log-writer",
            daemon=True,
        )
        self._writer_thread.start()
        self._started = True
        log.info("AuditLog started: path=%s", self._log_path)

    def enqueue(self, record: dict[str, Any]) -> None:
        """
        Non-blocking enqueue of an audit record.

        Per CLAUDE.md Section 7 Step 7:
        "If the write queue is full (bounded at 1,000 entries), the write is dropped
        with a counter increment. Lost audit records are logged as a warning metric
        but do not block serving."
        """
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            with self._dropped_lock:
                self._dropped_count += 1
            log.warning(
                "Audit write queue full (capacity=%d). Record dropped. "
                "Total dropped this session: %d. request_id=%s",
                _QUEUE_CAPACITY,
                self._dropped_count,
                record.get("request_id", "unknown"),
            )

    def enqueue_decision(self, record: dict[str, Any]) -> None:
        """Enqueue a decision record dict. Validates record_type."""
        if record.get("record_type") != "decision":
            log.error(
                "enqueue_decision called with non-decision record (record_type=%r). Dropping.",
                record.get("record_type"),
            )
            return
        self.enqueue(record)

    def enqueue_outcome(self, record: dict[str, Any]) -> None:
        """Enqueue an outcome record dict. Validates record_type."""
        if record.get("record_type") != "outcome":
            log.error(
                "enqueue_outcome called with non-outcome record (record_type=%r). Dropping.",
                record.get("record_type"),
            )
            return
        self.enqueue(record)

    def stop(self, timeout: float = 5.0) -> None:
        """
        Graceful shutdown. Enqueue sentinel, wait for writer thread to drain.
        Call at gateway shutdown.
        """
        if not self._started:
            return
        try:
            self._queue.put(_SENTINEL, timeout=timeout)
        except queue.Full:
            log.warning("Audit queue full during shutdown; writer may not drain cleanly.")
        if self._writer_thread:
            self._writer_thread.join(timeout=timeout)
        self._started = False
        log.info(
            "AuditLog stopped. Records dropped this session: %d",
            self._dropped_count,
        )

    @property
    def dropped_count(self) -> int:
        """Total audit records dropped due to queue overflow this session."""
        with self._dropped_lock:
            return self._dropped_count

    @property
    def queue_depth(self) -> int:
        """Current audit write queue depth (for Prometheus ic_audit_write_queue_depth)."""
        return self._queue.qsize()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _writer_loop(self) -> None:
        """Background thread: drains queue, appends each record to JSONL file."""
        while True:
            try:
                item = self._queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue

            if item is _SENTINEL:
                break

            self._append_sync(item)
            self._queue.task_done()

    def _append_sync(self, record: dict[str, Any]) -> None:
        """
        Synchronous JSONL append. Called only from the background writer thread.
        Errors are logged; they never propagate to the request path.
        """
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:
            log.error(
                "Audit write failed for request_id=%s: %s",
                record.get("request_id", "unknown"),
                exc,
                exc_info=True,
            )
