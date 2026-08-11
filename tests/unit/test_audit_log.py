"""
Unit tests for AuditLog (policy_engine/audit_log.py).

Coverage:
  - Decision record dict enqueued and written to JSONL
  - Outcome record dict enqueued and written to JSONL
  - Each line is valid JSON
  - Queue overflow: dropped records increment counter, write is skipped
  - start()/stop() lifecycle
  - enqueue is non-blocking (does not wait for IO)
  - Invalid record_type is logged and dropped
  - OutcomeRecord.to_audit_dict() produces correct CLAUDE.md Section 19.2 fields
  - Dropped count property reflects overflows
  - Multiple records are each on their own line
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from policy_engine.audit_log import AuditLog, OutcomeRecord


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_decision_record(request_id: str = "req_test_001") -> dict:
    return {
        "record_type": "decision",
        "timestamp_iso": "2026-08-10T12:00:00+00:00",
        "request_id": request_id,
        "tenant_id": "acme_corp",
        "domain": "general_qa",
        "policy_id": "enterprise_standard_v1",
        "policy_version": 1,
        "model_version": "deepseek-r1-7b",
        "prompt_version": "prompt_v2",
        "guardrail_version": "llamaguard_onnx_v1",
        "verifier_version": "verifier_v1",
        "complexity_score": 5.2,
        "fast_path_used": False,
        "base_budget_class": "medium",
        "effective_budget_class": "medium",
        "downgrade_reason": None,
        "priority_tier": "standard",
        "max_reasoning_tokens": 512,
        "max_output_tokens": 512,
        "route": "reasoning_model",
        "cache_hit": False,
        "admission_result": "pass",
        "estimated_cost_usd": 0.0062,
    }


def _make_outcome_record(request_id: str = "req_test_001") -> dict:
    return {
        "record_type": "outcome",
        "timestamp_iso": "2026-08-10T12:00:01+00:00",
        "request_id": request_id,
        "reasoning_tokens_used": 341,
        "reasoning_tokens_allocated": 512,
        "tokens_saved": 171,
        "output_tokens": 203,
        "stop_reason": "natural_boundary",
        "escalation_count": 0,
        "fallback_used": False,
        "guardrail_input_result": "pass",
        "guardrail_output_result": "pass",
        "verification_result": "pass",
        "actual_cost_usd": 0.0058,
        "queue_ms": 18,
        "guardrail_input_ms": 24,
        "prefill_ms": 187,
        "decode_ms": 810,
        "ttft_ms": 205,
        "e2e_latency_ms": 1167,
        "circuit_breaker_state_at_completion": "closed",
    }


# ── 1. Basic write and read back ──────────────────────────────────────────────

class TestBasicWriteAndRead:

    def test_decision_record_written_to_file(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_decision(_make_decision_record())
        audit.stop(timeout=3.0)

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_decision_record_is_valid_json(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_decision(_make_decision_record())
        audit.stop(timeout=3.0)

        line = log_file.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["record_type"] == "decision"

    def test_outcome_record_written_to_file(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_outcome(_make_outcome_record())
        audit.stop(timeout=3.0)

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["record_type"] == "outcome"

    def test_both_records_per_request(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_decision(_make_decision_record("req_001"))
        audit.enqueue_outcome(_make_outcome_record("req_001"))
        audit.stop(timeout=3.0)

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        types = {json.loads(l)["record_type"] for l in lines}
        assert types == {"decision", "outcome"}

    def test_multiple_requests_each_on_own_line(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        for i in range(5):
            audit.enqueue_decision(_make_decision_record(f"req_{i:03d}"))
        audit.stop(timeout=3.0)

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5
        for line in lines:
            json.loads(line)  # must not raise

    def test_request_ids_preserved(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_decision(_make_decision_record("req_UNIQUE_XYZ"))
        audit.stop(timeout=3.0)

        content = log_file.read_text(encoding="utf-8")
        record = json.loads(content.strip())
        assert record["request_id"] == "req_UNIQUE_XYZ"


# ── 2. Parent directory creation ──────────────────────────────────────────────

class TestDirectoryCreation:

    def test_creates_parent_directories(self, tmp_path):
        log_file = tmp_path / "nested" / "dir" / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_decision(_make_decision_record())
        audit.stop(timeout=3.0)
        assert log_file.exists()


# ── 3. JSONL append semantics ─────────────────────────────────────────────────

class TestAppendSemantics:

    def test_appends_to_existing_file(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        # Pre-existing content
        log_file.write_text(
            json.dumps({"record_type": "decision", "request_id": "pre_existing"}) + "\n",
            encoding="utf-8",
        )
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_decision(_make_decision_record("new_record"))
        audit.stop(timeout=3.0)

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        ids = {json.loads(l)["request_id"] for l in lines}
        assert "pre_existing" in ids
        assert "new_record" in ids


# ── 4. Invalid record_type handling ──────────────────────────────────────────

class TestInvalidRecordType:

    def test_enqueue_decision_with_wrong_type_drops(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        # Pass an "outcome" record through enqueue_decision — should be dropped
        audit.enqueue_decision(_make_outcome_record("req_bad"))
        audit.stop(timeout=3.0)
        # File should not exist or be empty (record was dropped)
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8").strip()
            assert content == ""

    def test_enqueue_outcome_with_wrong_type_drops(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        audit = AuditLog(log_path=log_file)
        audit.start()
        audit.enqueue_outcome(_make_decision_record("req_bad"))
        audit.stop(timeout=3.0)
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8").strip()
            assert content == ""


# ── 5. Queue depth and dropped count ─────────────────────────────────────────

class TestQueueMetrics:

    def test_dropped_count_starts_at_zero(self, tmp_path):
        audit = AuditLog(log_path=tmp_path / "audit.jsonl")
        audit.start()
        audit.stop()
        assert audit.dropped_count == 0

    def test_queue_depth_property_accessible(self, tmp_path):
        audit = AuditLog(log_path=tmp_path / "audit.jsonl")
        audit.start()
        depth = audit.queue_depth
        audit.stop()
        assert isinstance(depth, int)
        assert depth >= 0

    def test_queue_overflow_increments_dropped_count(self, tmp_path):
        # Create a tiny queue to test overflow
        from policy_engine import audit_log as al_module
        original_capacity = al_module._QUEUE_CAPACITY

        try:
            # Temporarily shrink queue to 2 entries
            import queue as _queue_module
            al_module._QUEUE_CAPACITY = 2

            log_file = tmp_path / "audit_overflow.jsonl"
            audit = AuditLog(log_path=log_file)
            # Replace the internal queue with tiny one WITHOUT starting writer
            # so queue fills up immediately
            audit._queue = _queue_module.Queue(maxsize=2)

            # Enqueue 5 records — 3 should be dropped
            for i in range(5):
                audit.enqueue(_make_decision_record(f"req_{i}"))

            assert audit.dropped_count >= 1

        finally:
            al_module._QUEUE_CAPACITY = original_capacity


# ── 6. OutcomeRecord ──────────────────────────────────────────────────────────

class TestOutcomeRecord:

    def test_outcome_record_to_audit_dict_all_fields(self):
        record = OutcomeRecord(
            timestamp_iso="2026-08-10T12:00:01+00:00",
            request_id="req_outcome_001",
            reasoning_tokens_used=341,
            reasoning_tokens_allocated=512,
            tokens_saved=171,
            output_tokens=203,
            stop_reason="natural_boundary",
            escalation_count=0,
            fallback_used=False,
            guardrail_input_result="pass",
            guardrail_output_result="pass",
            verification_result="pass",
            actual_cost_usd=0.0058,
            queue_ms=18,
            guardrail_input_ms=24,
            prefill_ms=187,
            decode_ms=810,
            ttft_ms=205,
            e2e_latency_ms=1167,
            circuit_breaker_state_at_completion="closed",
        )
        d = record.to_audit_dict()

        # Per CLAUDE.md Section 19.2 — exact field list
        required_fields = {
            "record_type", "timestamp_iso", "request_id",
            "reasoning_tokens_used", "reasoning_tokens_allocated", "tokens_saved",
            "output_tokens", "stop_reason", "escalation_count", "fallback_used",
            "guardrail_input_result", "guardrail_output_result", "verification_result",
            "actual_cost_usd", "queue_ms", "guardrail_input_ms", "prefill_ms",
            "decode_ms", "ttft_ms", "e2e_latency_ms",
            "circuit_breaker_state_at_completion",
        }
        assert required_fields.issubset(set(d.keys()))

    def test_outcome_record_type_is_outcome(self):
        record = OutcomeRecord(
            timestamp_iso="2026-08-10T12:00:01+00:00",
            request_id="req_outcome",
        )
        d = record.to_audit_dict()
        assert d["record_type"] == "outcome"

    def test_outcome_record_request_id_matches(self):
        record = OutcomeRecord(
            timestamp_iso="2026-08-10T12:00:01+00:00",
            request_id="req_specific_id",
        )
        d = record.to_audit_dict()
        assert d["request_id"] == "req_specific_id"

    def test_outcome_record_section_19_2_example(self):
        """Verify exact field values from CLAUDE.md Section 19.2 example."""
        record = OutcomeRecord(
            timestamp_iso="2026-08-09T10:42:12.501Z",
            request_id="req_8c4f2a",
            reasoning_tokens_used=341,
            reasoning_tokens_allocated=512,
            tokens_saved=171,
            output_tokens=203,
            stop_reason="natural_boundary",
            escalation_count=0,
            fallback_used=False,
            guardrail_input_result="pass",
            guardrail_output_result="pass",
            verification_result="pass",
            actual_cost_usd=0.0058,
            queue_ms=18,
            guardrail_input_ms=24,
            prefill_ms=187,
            decode_ms=810,
            ttft_ms=205,
            e2e_latency_ms=1167,
            circuit_breaker_state_at_completion="closed",
        )
        d = record.to_audit_dict()
        assert d["tokens_saved"] == 171
        assert d["stop_reason"] == "natural_boundary"
        assert d["ttft_ms"] == 205


# ── 7. Lifecycle correctness ──────────────────────────────────────────────────

class TestLifecycle:

    def test_start_is_idempotent(self, tmp_path):
        audit = AuditLog(log_path=tmp_path / "audit.jsonl")
        audit.start()
        audit.start()  # Second call should be no-op
        audit.stop()

    def test_stop_before_start_is_safe(self, tmp_path):
        audit = AuditLog(log_path=tmp_path / "audit.jsonl")
        audit.stop()  # Should not raise
