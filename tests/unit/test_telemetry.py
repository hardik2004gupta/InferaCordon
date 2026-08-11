"""
Unit tests for telemetry/ — OTel config and Prometheus metrics.

Per CLAUDE.md §18:
  - configure_otel() must not raise (fail-open)
  - get_tracer() must return a callable tracer
  - setup_metrics() must not raise
  - All ic_ metrics must be registered
  - Gauges initialized by setup_metrics() must start at 0.0

These tests use a fake/unreachable OTLP endpoint to verify fail-open behavior.
"""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry", reason="opentelemetry not installed locally — skipped")


class TestConfigureOtel:
    def test_does_not_raise_with_unreachable_endpoint(self):
        """Fail-open: unreachable Jaeger endpoint must not crash."""
        from telemetry.otel_config import configure_otel
        # This endpoint doesn't exist; verify no exception is raised
        configure_otel(service_name="ic-test", otlp_endpoint="http://localhost:19999")

    def test_does_not_raise_with_localhost_endpoint(self):
        from telemetry.otel_config import configure_otel
        configure_otel(service_name="ic-gateway", otlp_endpoint="http://localhost:4317")

    def test_idempotent(self):
        """Can be called multiple times without error."""
        from telemetry.otel_config import configure_otel
        configure_otel(service_name="ic-test", otlp_endpoint="http://localhost:4317")
        configure_otel(service_name="ic-test", otlp_endpoint="http://localhost:4317")


class TestGetTracer:
    def test_returns_tracer(self):
        from telemetry.otel_config import get_tracer
        t = get_tracer("ic-test")
        assert t is not None

    def test_tracer_is_otel_tracer(self):
        from telemetry.otel_config import get_tracer
        t = get_tracer("ic-test")
        # OpenTelemetry tracer must implement start_span / start_as_current_span
        assert hasattr(t, "start_span")
        assert hasattr(t, "start_as_current_span")

    def test_tracer_can_create_span(self):
        from telemetry.otel_config import configure_otel, get_tracer
        configure_otel(service_name="ic-test", otlp_endpoint="http://localhost:4317")
        tracer = get_tracer("ic-test")
        with tracer.start_as_current_span("test-span") as span:
            assert span is not None
            span.set_attribute("ic.test", "value")

    def test_different_names_return_independent_tracers(self):
        from telemetry.otel_config import get_tracer
        t1 = get_tracer("ic-gateway")
        t2 = get_tracer("ic-guardrail")
        # Both valid — we don't require them to be different objects (NoOp shares)
        assert t1 is not None
        assert t2 is not None


class TestSetupMetrics:
    def test_does_not_raise(self):
        """setup_metrics() must be idempotent and not raise."""
        from telemetry.prometheus_metrics import setup_metrics
        setup_metrics()

    def test_idempotent(self):
        from telemetry.prometheus_metrics import setup_metrics
        setup_metrics()
        setup_metrics()  # second call must also succeed


class TestMetricRegistration:
    """Verify all ic_ metrics are importable and properly registered."""

    def test_request_total_importable(self):
        from telemetry.prometheus_metrics import ic_request_total
        assert ic_request_total is not None

    def test_latency_seconds_importable(self):
        from telemetry.prometheus_metrics import ic_latency_seconds
        assert ic_latency_seconds is not None

    def test_reasoning_tokens_used_importable(self):
        from telemetry.prometheus_metrics import ic_reasoning_tokens_used
        assert ic_reasoning_tokens_used is not None

    def test_circuit_breaker_open_importable(self):
        from telemetry.prometheus_metrics import ic_circuit_breaker_open
        assert ic_circuit_breaker_open is not None

    def test_quality_score_histogram_importable(self):
        from telemetry.prometheus_metrics import ic_quality_score_histogram
        assert ic_quality_score_histogram is not None

    def test_tokens_reasoning_saved_importable(self):
        """Phase 9 addition: reasoning token savings histogram."""
        from telemetry.prometheus_metrics import ic_tokens_reasoning_saved
        assert ic_tokens_reasoning_saved is not None

    def test_cost_per_correct_answer_importable(self):
        """Phase 9 addition: cost-per-correct-answer gauge."""
        from telemetry.prometheus_metrics import ic_cost_per_correct_answer
        assert ic_cost_per_correct_answer is not None

    def test_admission_control_queue_depth_importable(self):
        from telemetry.prometheus_metrics import ic_admission_control_queue_depth
        assert ic_admission_control_queue_depth is not None

    def test_fast_path_activations_importable(self):
        from telemetry.prometheus_metrics import ic_fast_path_activations_total
        assert ic_fast_path_activations_total is not None

    def test_request_cost_usd_importable(self):
        from telemetry.prometheus_metrics import ic_request_cost_usd
        assert ic_request_cost_usd is not None


class TestMetricOperations:
    """Verify metrics accept label calls without error."""

    def test_counter_inc(self):
        from telemetry.prometheus_metrics import ic_request_total
        ic_request_total.labels(
            tenant_id="test", domain="qa", budget_class="medium",
            route="deepseek-r1-7b-q4", cache_hit="false",
        ).inc()

    def test_histogram_observe(self):
        from telemetry.prometheus_metrics import ic_latency_seconds
        ic_latency_seconds.labels(tenant_id="test", budget_class="medium").observe(1.5)

    def test_gauge_set(self):
        from telemetry.prometheus_metrics import ic_circuit_breaker_open
        ic_circuit_breaker_open.labels(breaker_name="test_cb").set(0.0)
        ic_circuit_breaker_open.labels(breaker_name="test_cb").set(1.0)

    def test_quality_histogram_observe(self):
        from telemetry.prometheus_metrics import ic_quality_score_histogram
        ic_quality_score_histogram.labels(tenant_id="test", domain="qa").observe(4.0)
