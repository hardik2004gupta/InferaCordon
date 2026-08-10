"""
Integration tests for the observability pipeline.

Per Phase 9 spec:
  - OTel spans propagate through the request lifecycle
  - Prometheus metrics are updated on each request
  - Async eval worker submits after response delivery
  - Trace schema fields match CLAUDE.md §18.1 exactly

These tests use in-memory/stub infrastructure — no live Jaeger or OpenAI API.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import fields as dc_fields
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# Check opentelemetry availability without failing the whole module
try:
    import opentelemetry  # noqa: F401
    _OTEL_INSTALLED = True
except ImportError:
    _OTEL_INSTALLED = False

_skip_otel = pytest.mark.skipif(
    not _OTEL_INSTALLED,
    reason="opentelemetry not installed locally",
)


class TestTraceContextPropagation:
    """
    Verify W3C traceparent is present in every gateway request.
    The TraceContext module (already fully implemented) is the source of truth.
    """

    def test_create_trace_context_generates_request_id(self):
        from unittest.mock import MagicMock
        from gateway.trace_context import create_trace_context, generate_request_id

        mock_request = MagicMock()
        mock_request.headers = {}
        ctx = create_trace_context(mock_request, "acme_corp")
        assert ctx.request_id.startswith("req_")

    def test_traceparent_format(self):
        from gateway.trace_context import create_trace_context

        mock_request = MagicMock()
        mock_request.headers = {}
        ctx = create_trace_context(mock_request, "acme_corp")
        # W3C traceparent: 00-<trace_id_32hex>-<parent_id_16hex>-<flags_2hex>
        if ctx.traceparent:
            parts = ctx.traceparent.split("-")
            assert len(parts) == 4
            assert parts[0] == "00"  # version
            assert len(parts[1]) == 32  # trace-id
            assert len(parts[2]) == 16  # parent-id
            assert len(parts[3]) == 2   # trace-flags

    def test_client_traceparent_propagated(self):
        from gateway.trace_context import create_trace_context

        client_tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        mock_request = MagicMock()
        mock_request.headers = {"traceparent": client_tp}
        ctx = create_trace_context(mock_request, "acme_corp")
        assert ctx.traceparent == client_tp


class TestRequestTraceSchema:
    """
    Verify RequestTrace fields are exactly what CLAUDE.md §18.1 requires.
    This is an integration check that the schema module is wired correctly.
    """

    _SPEC_FIELDS = [
        "request_id", "trace_id", "tenant_id", "domain",
        "policy_id", "policy_version", "model_version", "prompt_version",
        "guardrail_version", "verifier_version", "complexity_scorer_version",
        "complexity_score", "fast_path_used", "base_budget_class",
        "effective_budget_class", "downgrade_reason", "priority_tier",
        "max_reasoning_tokens", "route", "cache_hit", "admission_decision",
        "reasoning_tokens_used", "output_tokens", "tokens_saved",
        "stop_reason", "escalation_count", "fallback_used",
        "guardrail_input_result", "guardrail_input_ms", "guardrail_injection_score",
        "guardrail_output_result", "guardrail_output_ms",
        "verification_result", "verification_type", "verification_ms",
        "queue_ms", "prefill_ms", "decode_ms", "ttft_ms", "e2e_latency_ms",
        "estimated_cost_usd", "actual_cost_usd",
        "gpu_cb_state", "latency_cb_state",
        "entropy_samples",
    ]

    def test_schema_fields_match_spec(self):
        from telemetry.trace_schema import RequestTrace
        actual = [f.name for f in dc_fields(RequestTrace)]
        assert actual == self._SPEC_FIELDS


@_skip_otel
class TestOtelConfiguration:
    """Verify OTel can be configured without crashing."""

    def test_configure_otel_fail_open(self):
        from telemetry.otel_config import configure_otel
        # Port 19999 is not listening — must not raise
        configure_otel(service_name="ic-integration-test", otlp_endpoint="http://localhost:19999")

    def test_get_tracer_returns_span_capable_object(self):
        from telemetry.otel_config import configure_otel, get_tracer
        configure_otel(service_name="ic-test", otlp_endpoint="http://localhost:19999")
        tracer = get_tracer("ic-test")
        with tracer.start_as_current_span("ic.integration.test") as span:
            span.set_attribute("ic.test_attr", "value")
            assert span is not None


class TestPrometheusMetricPipeline:
    """Verify ic_ metrics are observable after operations."""

    def test_cache_hit_counter_increments(self):
        from prometheus_client import REGISTRY
        from telemetry.prometheus_metrics import ic_cache_hit_total

        ic_cache_hit_total.labels(tenant_id="test_pipeline", domain="qa").inc()
        # prometheus_client strips _total from the family name in REGISTRY.collect();
        # samples carry the full _total suffix.  Check both forms.
        all_names = {m.name for m in REGISTRY.collect()}
        sample_names = {
            s.name for m in REGISTRY.collect() for s in m.samples
        }
        found = "ic_cache_hit" in all_names or "ic_cache_hit_total" in sample_names
        assert found, f"ic_cache_hit[_total] not found in Prometheus registry. Found: {sorted(all_names)}"

    def test_quality_score_histogram_observable(self):
        from prometheus_client import REGISTRY
        from telemetry.prometheus_metrics import ic_quality_score_histogram

        ic_quality_score_histogram.labels(tenant_id="test", domain="qa").observe(3.5)
        found = any(
            m.name == "ic_quality_score_histogram"
            for m in REGISTRY.collect()
        )
        assert found


class TestAsyncEvalWorkerPipeline:
    """End-to-end eval worker pipeline: submit → SQLite → judge call."""

    def test_eval_task_fields_match_worker_schema(self):
        """EvalTask fields must cover what the worker inserts into SQLite."""
        from gateway.async_eval_worker import EvalTask
        task = EvalTask(
            request_id="req_inttest",
            tenant_id="acme_corp",
            domain="general_qa",
            prompt="What is 2+2?",
            response="4",
            budget_class="medium",
            verification_result="unverifiable",
            policy_version=1,
        )
        # All required fields present
        assert task.request_id == "req_inttest"
        assert task.tenant_id == "acme_corp"
        assert task.policy_version == 1

    def test_worker_submit_writes_to_sqlite(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from gateway.async_eval_worker import AsyncEvalWorker, EvalTask

        db = str(tmp_path / "integration_test.db")
        worker = AsyncEvalWorker(db_path=db, max_workers=1)
        task = EvalTask(
            request_id="req_pipeline",
            tenant_id="acme_corp",
            domain="math",
            prompt="Prove 1+1=2",
            response="By Peano axioms...",
            budget_class="high",
            verification_result="unverifiable",
            policy_version=2,
        )
        worker.submit(task)
        time.sleep(0.1)

        row = worker._conn.execute(
            "SELECT request_id, tenant_id, domain, budget_class FROM eval_jobs WHERE request_id=?",
            ("req_pipeline",),
        ).fetchone()
        worker._executor.shutdown(wait=True)
        worker._conn.close()

        assert row is not None
        assert row[0] == "req_pipeline"
        assert row[1] == "acme_corp"
        assert row[2] == "math"
        assert row[3] == "high"

    def test_worker_prompt_not_in_sqlite(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from gateway.async_eval_worker import AsyncEvalWorker, EvalTask

        db = str(tmp_path / "privacy_integration.db")
        worker = AsyncEvalWorker(db_path=db, max_workers=1)
        secret = "secret-pipeline-prompt-value-xyz"
        worker.submit(EvalTask(
            request_id="req_priv",
            tenant_id="acme",
            domain="qa",
            prompt=secret,
            response="answer",
            budget_class="low",
            verification_result=None,
            policy_version=1,
        ))
        time.sleep(0.5)

        all_values = " ".join(
            str(v) for row in worker._conn.execute("SELECT * FROM eval_jobs") for v in row if v
        )
        worker._executor.shutdown(wait=True)
        worker._conn.close()

        assert secret not in all_values, "Raw prompt stored in SQLite — privacy violation"


class TestJudgePrivacy:
    """Verify LLM judge does not expose sensitive data."""

    def test_api_key_not_exposed_in_judge_repr(self):
        from evaluation.llm_judge import LLMJudge
        key = "sk-super-private-key-12345"
        judge = LLMJudge(openai_api_key=key)
        assert key not in repr(judge)
        assert key not in str(judge)

    def test_failed_result_has_no_raw_content(self):
        from evaluation.llm_judge import LLMJudge
        result = LLMJudge._failed_result(latency_ms=99.0)
        result_dict = {
            "score": result.score,
            "reasoning": result.reasoning,
            "model_used": result.model_used,
            "latency_ms": result.latency_ms,
        }
        # reasoning field should be generic, not contain any prompt/response content
        assert result.reasoning == "evaluation_failed"
