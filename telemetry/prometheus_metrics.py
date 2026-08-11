"""
Prometheus metric definitions for InferaCordon.

Per CLAUDE.md Section 18 — all custom metrics use ic_ prefix.
vLLM native metrics are consumed directly from vllm:8080/metrics.

Metric catalog (CLAUDE.md Section 18):
  ic_request_total            (counter)   — per tenant, domain, budget_class, route, cache_hit
  ic_latency_seconds          (histogram) — p50/p95/p99 per tenant, budget_class
  ic_ttft_seconds             (histogram) — time to first token per model
  ic_reasoning_tokens_used    (histogram) — actual reasoning tokens per request
  ic_budget_ceiling_hit_total (counter)   — BudgetLogitProcessor forced </think>
  ic_cache_hit_total          (counter)   — semantic cache hits per tenant, domain
  ic_cache_miss_total         (counter)   — semantic cache misses
  ic_cache_size_entries       (gauge)     — current FAISS index entry count
  ic_cost_usd_total           (counter)   — cumulative cost per tenant
  ic_quality_score_histogram  (histogram) — LLM judge scores
  ic_circuit_breaker_open     (gauge)     — 1.0 if open, 0.0 if closed; per breaker name
  ic_admission_rejected_total (counter)   — admission control rejections
  ic_rate_limit_exceeded_total(counter)   — rate limit exceeded per tenant
  ic_escalation_total         (counter)   — budget class escalations
  ic_guardrail_block_total    (counter)   — guardrail blocks per check_type (input/output)
  ic_complexity_score_histogram(histogram)— distribution of complexity scores
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── Request Lifecycle ──────────────────────────────────────────────────────
ic_request_total = Counter(
    "ic_request_total",
    "Total inference requests",
    ["tenant_id", "domain", "budget_class", "route", "cache_hit"],
)

ic_latency_seconds = Histogram(
    "ic_latency_seconds",
    "End-to-end request latency in seconds",
    ["tenant_id", "budget_class"],
    buckets=(0.1, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0),
)

ic_ttft_seconds = Histogram(
    "ic_ttft_seconds",
    "Time to first token in seconds",
    ["model_version"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0),
)

# ── Reasoning Budget ───────────────────────────────────────────────────────
ic_reasoning_tokens_used = Histogram(
    "ic_reasoning_tokens_used",
    "Actual reasoning tokens consumed per request",
    ["budget_class", "model_version"],
    buckets=(0, 64, 128, 256, 512, 1024, 2048),
)

ic_budget_ceiling_hit_total = Counter(
    "ic_budget_ceiling_hit_total",
    "Requests where BudgetLogitProcessor forced </think> token",
    ["budget_class"],
)

# ── Semantic Cache ─────────────────────────────────────────────────────────
ic_cache_hit_total = Counter(
    "ic_cache_hit_total",
    "Semantic cache hits",
    ["tenant_id", "domain"],
)

ic_cache_miss_total = Counter(
    "ic_cache_miss_total",
    "Semantic cache misses",
    ["tenant_id", "domain"],
)

ic_cache_size_entries = Gauge(
    "ic_cache_size_entries",
    "Current number of entries in FAISS semantic cache",
)

# ── Cost ───────────────────────────────────────────────────────────────────
ic_cost_usd_total = Counter(
    "ic_cost_usd_total",
    "Cumulative inference cost in USD",
    ["tenant_id"],
)

# ── Quality ────────────────────────────────────────────────────────────────
ic_quality_score_histogram = Histogram(
    "ic_quality_score_histogram",
    "LLM judge quality scores (1-5 scale)",
    ["tenant_id", "domain"],
    buckets=(1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0),
)

# ── Circuit Breakers ───────────────────────────────────────────────────────
ic_circuit_breaker_open = Gauge(
    "ic_circuit_breaker_open",
    "1.0 if circuit breaker is open, 0.0 if closed",
    ["breaker_name"],
)

# ── Admission + Rate Limiting ──────────────────────────────────────────────
ic_admission_rejected_total = Counter(
    "ic_admission_rejected_total",
    "Requests rejected by admission control",
    ["reason"],
)

ic_rate_limit_exceeded_total = Counter(
    "ic_rate_limit_exceeded_total",
    "Requests rejected by rate limiter",
    ["tenant_id"],
)

# ── Escalation ────────────────────────────────────────────────────────────
ic_escalation_total = Counter(
    "ic_escalation_total",
    "Budget class escalations triggered",
    ["from_class", "to_class"],
)

# ── Guardrails ────────────────────────────────────────────────────────────
ic_guardrail_block_total = Counter(
    "ic_guardrail_block_total",
    "Requests blocked by guardrail",
    ["check_type", "classifier"],  # check_type: input|output
)

# ── Complexity ────────────────────────────────────────────────────────────
ic_complexity_score_histogram = Histogram(
    "ic_complexity_score_histogram",
    "Distribution of prompt complexity scores",
    ["domain"],
    buckets=(0.5, 1.0, 2.0, 3.5, 5.0, 6.5, 8.5, 10.0),
)

# ── Missing from §18.2 — added in Phase 9 ─────────────────────────────────
ic_tokens_reasoning_saved = Histogram(
    "ic_tokens_reasoning_saved",
    "Reasoning tokens saved vs. allocated ceiling per request",
    ["tenant_id", "budget_class"],
    buckets=(0, 64, 128, 256, 512, 1024, 2048),
)

ic_cost_per_correct_answer = Gauge(
    "ic_cost_per_correct_answer",
    "Rolling cost (USD) per verified-correct answer; updated by eval worker",
    ["tenant_id", "task_class"],
)

ic_admission_control_queue_depth = Gauge(
    "ic_admission_control_queue_depth",
    "Current number of requests waiting in admission control queue",
)

ic_audit_write_queue_depth = Gauge(
    "ic_audit_write_queue_depth",
    "Current audit log write queue depth",
)

ic_audit_records_dropped_total = Counter(
    "ic_audit_records_dropped_total",
    "Audit records dropped due to full write queue",
)

ic_fast_path_activations_total = Counter(
    "ic_fast_path_activations_total",
    "Requests that triggered the 48ms pipeline deadline fast-path",
)

ic_request_cost_usd = Histogram(
    "ic_request_cost_usd",
    "Per-request inference cost in USD",
    ["tenant_id", "budget_class", "route"],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.10, 0.50),
)


def setup_metrics() -> None:
    """
    Initialize Prometheus metric state. Called once at gateway startup.

    Seeds state-bearing gauges so Grafana shows known-good defaults before
    the first real data point arrives. The ic_ metric objects are defined
    at module import time by prometheus_client; this function only sets
    initial values for gauges that represent runtime state.
    """
    # Circuit breakers start closed (0.0 = closed, 1.0 = open)
    ic_circuit_breaker_open.labels(breaker_name="gpu_pressure").set(0.0)
    ic_circuit_breaker_open.labels(breaker_name="latency").set(0.0)

    # Queue and size gauges start at zero
    ic_cache_size_entries.set(0.0)
    ic_admission_control_queue_depth.set(0.0)
    ic_audit_write_queue_depth.set(0.0)
