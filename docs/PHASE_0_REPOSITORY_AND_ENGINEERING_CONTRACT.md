# Phase 0 — Repository and Engineering Contract

> **Date:** 2026-09-27
> **Purpose:** Read-only audit of the InferaCordon repository.
> **Rule:** No source code, dependencies, or configuration was modified during this phase.
> **Authority:** CLAUDE.md is the permanent engineering contract. This document records the gap between that contract and the current implementation state.

---

## 1. Project Understanding

**InferaCordon** is a governed AI inference control plane that treats reasoning tokens as a managed compute resource. It sits between client applications and model serving infrastructure, making per-request decisions about budget, routing, stopping, verification, and escalation under explicit SLOs.

**Primary problem:** Reasoning models generate internal chain-of-thought tokens that are billed in full, consume context, dominate latency, and are invisible to all standard LLMOps tooling. Three simultaneous failure modes exist in production:

1. **Overthinking** — excessive reasoning tokens on simple queries
2. **Underthinking** — conservative global ceilings produce shallow answers on complex queries
3. **Budget Blindness** — no per-request allocation, no tenant cost attribution, no SLO-aware routing

**Four pillars (all must be demonstrable in the five-minute demo):**

| Pillar | Meaning in this project |
|--------|------------------------|
| **Guardrails** | PII redaction (Presidio), injection detection (DeBERTa ONNX), safety classification (Llama Guard ONNX) at input and output |
| **Governance** | Versioned YAML policies, immutable append-only JSONL audit trail, every decision recorded with its governing policy version |
| **Cost Optimization** | FAISS semantic cache, budget-class routing, verification-triggered escalation, cost per correct answer as primary metric |
| **Inference Optimization** | Native vLLM LogitProcessor enforcing per-request reasoning token budgets at the `</think>` delimiter boundary |

**Governing constraints:** One engineer, fourteen weeks, one GPU node (A100 80GB), one reasoning model (DeepSeek-R1-7B-Q4), one cheap model (Qwen2.5-3B-Instruct), single vLLM instance, `docker compose up`.

---

## 2. Source/Document Hierarchy

### Documents discovered

| Document | Location | Authority |
|----------|----------|-----------|
| `CLAUDE.md` | Repository root (1,800+ lines) | **PRIMARY** — permanent engineering contract governing all architecture, implementation, API contracts, testing, evaluation, and frontend specifications |
| `InferaCordon Detailed Architecture Plan.pdf` | Repository root | Primary architecture source (CLAUDE.md Section 2). Governs system topology, component boundaries, technology choices, implementation roadmap |
| `InferaCordon MVP Documentation.pdf` | Repository root | Secondary product/MVP source. Governs product intent, UX requirements, evaluation framework, demo requirements |
| `architecture.md` | Repository root | Concise companion to CLAUDE.md. Contains a **different step ordering** than CLAUDE.md (see Section 19) |
| `README.md` | Repository root | Public-facing project summary. Contains benchmark targets (not results). Metrics block is a placeholder |
| `.env.example` | Repository root | Environment variable reference |
| `tenants.yaml` | Repository root | API key → tenant ID mapping |

### Hierarchy determination

1. **CLAUDE.md** is authoritative for all architectural, implementation, and API contract decisions. It explicitly states its own authority and documents conflicts between the two PDF sources.
2. **Architecture Plan PDF** is the primary architecture source referenced by CLAUDE.md.
3. **MVP Documentation PDF** supplements with product/behavioral detail but cannot override architecture decisions.
4. **architecture.md** summarizes CLAUDE.md but contains step-ordering discrepancies (see Section 19).
5. **README.md** contains portfolio-facing descriptions and target metrics (explicitly documented as targets, not results).

---

## 3. Architecture Map

### Seven-Container Topology (resolved from CLAUDE.md Section 31 Conflict 2)

| Container | Port | Runtime | Responsibility |
|-----------|------|---------|---------------|
| FastAPI Gateway (`ic-gateway`) | 8000 | CPU | Complete 16-step request lifecycle, React SPA static files, in-process FAISS cache, background eval thread pool |
| vLLM Server (`ic-vllm`) | 8080 (internal only) | GPU | DeepSeek-R1-7B-Q4 + Qwen2.5-3B-Instruct serving, LogitProcessor registration |
| Guardrail Service (`ic-guardrail`) | 8001 | CPU only | DeBERTa injection + Llama Guard safety via ONNX Runtime |
| Verifier Service (`ic-verifier`) | 8002 | CPU only | GSM8K, MATH-500, HumanEval, JSON schema verification |
| Prometheus (`ic-prometheus`) | 9090 | — | Metrics scraping from all services |
| Grafana (`ic-grafana`) | 3000 | — | Pre-configured unified dashboard |
| Jaeger (`ic-jaeger`) | 16686 | — | OpenTelemetry trace collection via OTLP |

**In-process components (not containers):**
- Policy Engine — Python library imported by gateway
- FAISS Semantic Cache — in-process IndexFlatIP inside gateway
- Eval Worker — background thread pool inside gateway
- Complexity Scorer — synchronous in-process function

### docker-compose.yml status

The `docker-compose.yml` is fully defined with all seven services, health checks, volumes, and networking. Notable details:
- vLLM port 8080 is `expose`-only (not published to host) — enforces that clients must go through the gateway
- Gateway depends on vLLM, guardrail, and verifier being healthy before starting
- Model weights use a named Docker volume (`vllm-model-cache`)
- Frontend static files mounted from `frontend/dist/` as read-only
- Policy files mounted from `policy_engine/policies/` as read-only
- Prometheus data retention: 30 days
- Jaeger uses in-memory span storage (not persistent)

---

## 4. Request Lifecycle (16 Steps per CLAUDE.md Section 6.3)

The gateway implements the following sequence. Each step's implementation status is noted.

| Step | Name | Sync/Async | Implemented? | Notes |
|------|------|-----------|-------------|-------|
| 1 | Authentication | sync | **YES** | `auth.py` — API key → tenant ID via `tenants.yaml` dict |
| 2 | Rate Limiting | sync | **CODE EXISTS, NOT WIRED** | `rate_limiter.py` exists but is never imported by `main.py` |
| 3 | Trace Context | sync | **YES** | `trace_context.py` — UUID request ID + W3C traceparent |
| 4 | Pre-Inference Pipeline | sync | **PARTIAL** | Complexity scoring implemented; pipeline orchestrator with 50ms deadline NOT implemented (scorer called directly) |
| 5 | Policy Lookup | sync | **YES** | In-process dict lookup via `PolicyRegistry.resolve()` |
| 6 | Budget Class Assignment | sync | **YES** | `budget_controller.py` — maps complexity → budget class |
| 7 | Decision Record Write | async | **YES** | Non-blocking enqueue to `AuditLog` background thread |
| 8 | Semantic Cache Lookup | sync | **YES** | FAISS IndexFlatIP, in-process. Cache hit → immediate return |
| 8.5 | PII Redaction | sync | **YES** | Presidio wrapper. Runs BEFORE cache lookup (deviation from CLAUDE.md which puts PII in Step 4) |
| 9 | Admission Control | sync | **YES** | Semaphore-based, configurable concurrency ceiling |
| 10 | Guardrail Input Check | sync | **YES** | HTTP call to guardrail service with 200ms timeout |
| 11 | Inference | sync | **YES** | vLLM OpenAI-compatible API via `InferenceAdapter` |
| 12 | Guardrail Output Check | sync/async | **YES** | Sync or async based on policy `output_safety` setting |
| 13 | Verification | sync | **PARTIAL** | Only `json_schema` verification in live gateway; GSM8K/MATH/HumanEval require ground truth not present in `InferRequest` |
| 14 | Escalation | sync | **YES** | Monotonic budget class escalation, max 1 retry, semaphore release/re-acquire |
| 15 | Response Delivery | sync | **YES** | Including Prometheus metric updates, outcome record enqueue |
| 16 | Async Evaluation | background | **YES** | `AsyncEvalWorker` — LLM-judge for non-verifiable responses |

### Step ordering discrepancy (vs CLAUDE.md)

The actual implementation order differs slightly from the CLAUDE.md specification:
- **PII redaction** runs at Step 8.5 (between decision record and cache lookup), not in Step 4 (pre-inference pipeline)
- **Complexity scoring** runs standalone at Step 4, not as part of a deadline-orchestrated pipeline
- The pre-inference pipeline orchestrator with 50ms deadline timer is NOT implemented

---

## 5. Component Responsibility Map

### Gateway (`gateway/` — 18 Python files, ~3,200 lines)

| File | Responsibility | Implementation Status |
|------|---------------|----------------------|
| `main.py` (~1,545 lines) | FastAPI app, lifespan, all endpoints, escalation loop | Complete |
| `auth.py` | API key → tenant ID resolution | Complete |
| `rate_limiter.py` | Token bucket rate limiter | **Complete but NOT WIRED into main.py** |
| `trace_context.py` | UUID + W3C traceparent generation | Complete |
| `pre_inference_pipeline.py` | Pipeline orchestrator | **Exists but the 50ms deadline timer is not used by main.py** |
| `complexity_scorer.py` | 5-feature-group heuristic scorer | Complete |
| `pii_redactor.py` | Presidio PII wrapper | Complete |
| `context_engine.py` | Static prompt template selection | Complete |
| `semantic_cache.py` | FAISS IndexFlatIP cache | Complete |
| `admission_control.py` | Semaphore-based admission | Complete |
| `model_router.py` | Budget class → model selection | **Complete but NOT WIRED** (routing done inline) |
| `vllm_client.py` | OpenAI-compatible HTTP client | Complete |
| `guardrail_client.py` | HTTP client for guardrail service | Complete |
| `verifier_client.py` | HTTP client for verifier service | Complete |
| `escalation_handler.py` | Verification-triggered escalation | Complete |
| `async_eval_worker.py` | Background LLM-judge thread pool | Complete |
| `schemas.py` | Pydantic request/response models | Complete |
| `Dockerfile` | Gateway container build | Complete |

### Policy Engine (`policy_engine/` — 4 Python files + 3 YAML policies)

| File | Responsibility | Status |
|------|---------------|--------|
| `loader.py` | YAML load + Pydantic validation at startup | Complete |
| `validator.py` | Pydantic models for policy schema | Complete |
| `budget_controller.py` | Complexity → budget class mapping; fleet pressure downgrades | Complete |
| `audit_log.py` | Append-only JSONL, background write thread | Complete |

### vLLM Adapter (`vllm_adapter/` — 5 Python files)

| File | Responsibility | Status |
|------|---------------|--------|
| `logit_processor.py` | BudgetLogitProcessor per-request budget enforcement | Complete |
| `circuit_breakers.py` | GPU pressure + latency circuit breakers | **STUB — raises NotImplementedError** |
| `constants.py` | End-of-thinking token ID | Complete |
| `serving_config.py` | vLLM server configuration builder | Complete |
| `inference_adapter.py` | Inference call spec builder + result parser | Complete |

### Guardrail Service (`guardrail_service/` — 3 Python files)

| File | Responsibility | Status |
|------|---------------|--------|
| `main.py` | FastAPI service, `/guardrail/input`, `/guardrail/output`, `/health` | Complete |
| `injection_classifier.py` | DeBERTa ONNX injection detection | Complete (falls back to keyword heuristic if ONNX unavailable) |
| `safety_classifier.py` | Llama Guard ONNX safety classification | Complete (falls back to keyword heuristic if ONNX unavailable) |

### Verifier Service (`verifier_service/` — 5 Python files)

| File | Responsibility | Status |
|------|---------------|--------|
| `main.py` | FastAPI service, `/verify`, `/health` | Complete |
| `gsm8k_verifier.py` | Exact-match numerical verification | Complete |
| `math_verifier.py` | SymPy symbolic equivalence | Complete |
| `humaneval_runner.py` | Sandboxed subprocess execution | Complete |
| `schema_verifier.py` | JSON schema validation | Complete |

### Telemetry (`telemetry/` — 3 Python files)

| File | Responsibility | Status |
|------|---------------|--------|
| `otel_config.py` | OpenTelemetry SDK configuration | Complete |
| `prometheus_metrics.py` | All `ic_` prefixed Prometheus metrics | Complete |
| `trace_schema.py` | RequestTrace dataclass | Complete |

### Evaluation (`evaluation/` — 11 Python files)

| File | Responsibility | Status |
|------|---------------|--------|
| `benchmark_harness.py` | Full benchmark runner across all baselines/datasets | Complete |
| `ablation_runner.py` | Seven-layer ablation sequence | Complete |
| `baseline_measurements.py` | Six baseline measurement runners | Complete |
| `complexity_calibration.py` | Complexity scorer weight calibration | Complete |
| `datasets.py` | Dataset loading (GSM8K, MATH-500, HumanEval, synthetic, adversarial) | Complete |
| `llm_judge.py` | GPT-4o-mini async quality scoring | Complete |
| `logit_processor_validation.py` | 50-query × 5-position validation gate | Complete |
| `metric_calculator.py` | Cost-per-correct-answer and metric computation | Complete |
| `regression_gate.py` | Per-slice accuracy gating | Complete |
| `result_schema.py` | Experiment result Pydantic schema | Complete |
| `update_readme_metrics.py` | README metrics block auto-updater | Complete |

**Benchmark results status:** Only one result file exists (`experiment_baseline3_gsm8k_4071b3c2.json`) and it is marked `"status": "blocked"` — GPU runtime unavailable. No benchmark has actually run.

---

## 6. Budget/Routing Model

### Budget Classes (from CLAUDE.md Section 12 and policy YAML)

| Class | Model | Reasoning Tokens | Output Tokens | Verification | Context Template |
|-------|-------|:----------------:|:-------------:|:------------:|:----------------:|
| `low` | Qwen2.5-3B-Instruct | 0 | 256 | none | direct |
| `medium` | DeepSeek-R1-7B-Q4 | 512 | 512 | verifiable_only | step_by_step |
| `high` | DeepSeek-R1-7B-Q4 | 1,024 | 1,024 | required | verify_steps |
| `critical` | DeepSeek-R1-7B-Q4 | 2,048 | 1,024 | required | verify_steps |

### Complexity Score → Budget Class Mapping

| Score Range | Budget Class |
|-------------|:------------:|
| 0.0 – 3.5 | low |
| 3.5 – 6.5 | medium |
| 6.5 – 8.5 | high |
| 8.5 – 10.0 | critical |

### Complexity Scorer (5 Feature Groups)

All five feature groups documented in CLAUDE.md Section 10 are implemented in `gateway/complexity_scorer.py`:
1. Constraint keyword density (tier-weighted vocabulary, 0–3.0)
2. Structural signals (question count, sentences, multi-step patterns, 0–2.0)
3. Technical domain signals (code, LaTeX, formal logic, JSON/XML, 0–2.0)
4. Length signal (token count estimate, 0–1.5)
5. Output format complexity (structured output requests, 0–1.5)

Score range: 0.0–10.0. Latency target: <3ms. No ML on critical path.

### Circuit Breakers

**IMPLEMENTATION STATUS: STUB**

Both `GPUPressureBreaker` and `LatencyBreaker` in `vllm_adapter/circuit_breakers.py` raise `NotImplementedError`. The gateway hardcodes `FleetState.nominal()` (all circuit breakers closed) and the `/v1/status` endpoint returns hardcoded `"state": "closed"` for both breakers.

**Implication for frontend:** Circuit breaker indicators will always show "CLOSED" regardless of actual system state.

### Model Routing

The routing decision is embedded in the budget controller: `low` class → Qwen2.5-3B-Instruct, all other classes → DeepSeek-R1-7B-Q4. The standalone `model_router.py` exists but is never imported by the gateway. Routing is done inline via the `InferenceAdapter.build_call_spec()` method.

### Escalation

Implemented and wired. On verification failure:
1. Check `EscalationHandler.should_escalate()` — INCORRECT result + retries < max (1) + escalation enabled
2. Release current admission semaphore
3. Compute next budget class via `escalate_budget_class()`
4. Re-acquire semaphore for escalated class
5. Run inference + verification at higher class
6. On exhaustion: return with `confidence_level: "low"`

UNVERIFIABLE results do NOT trigger escalation (correct per CLAUDE.md Section 16).

---

## 7. Guardrail Model

### Pipeline

| Check | Location | Model | Runtime | Timeout | On Failure |
|-------|----------|-------|---------|---------|------------|
| PII Redaction | Gateway in-process | Presidio | CPU | None (local) | Runs always; entities redacted before any downstream component |
| Injection Detection | Guardrail service | DeBERTa-v3-small ONNX int8 | CPU | 200ms | **Flag** (augment system prompt), NOT block |
| Safety Classification (input) | Guardrail service | Llama Guard 3-1B ONNX | CPU | 200ms | **Block** → 503 |
| Safety Classification (output) | Guardrail service | Llama Guard 3-1B ONNX | CPU | 200ms | Sync: Block → structured refusal. Async: log only |

### Timeout behavior (CLAUDE.md Section 14.7)
- **Input timeout → conservative block** (503). The gateway code implements this via the `GuardrailDecision.DEGRADED` case.
- **Output timeout → non-blocking pass** (response already delivered; failure logged).

### ONNX model fallback
Both `injection_classifier.py` and `safety_classifier.py` fall back to keyword-based heuristics when ONNX models are not available on disk. This fallback is not documented in CLAUDE.md but exists in the implementation.

---

## 8. Governance Model

### Policy Structure

Three policy files exist:
1. `acme_corp_general_qa_v1.yaml` — primary demo tenant, matches CLAUDE.md Section 11.5 exactly
2. `demo_tenant_v1.yaml` — secondary demo tenant
3. `default_policy_v1.yaml` — system fallback for unknown tenants (Failure Mode 7), more conservative

All policies validated at startup via Pydantic (`PolicyRegistry.load_from_dir()`). Gateway refuses to start with invalid policy files.

### Audit Log

- Format: append-only JSONL
- Two records per request: decision (pre-inference) + outcome (post-response)
- Background write thread with bounded queue (1,000 entries)
- Dropped writes logged as warning metrics but never block serving
- No raw prompt or response text stored (privacy rule)
- Path: configurable via `AUDIT_LOG_PATH` env var
- Served via `GET /audit/records` with filtering

### Policy Immutability

Policies are immutable in memory. Updates require gateway restart. Version numbers are monotonically increasing integers.

---

## 9. Inference Optimization Model

### BudgetLogitProcessor

Implemented in `vllm_adapter/logit_processor.py`. Matches CLAUDE.md Section 9 specification:
- Per-request instance with own state (no shared mutable state)
- Counts reasoning tokens
- Detects natural `</think>` delimiter
- Forces delimiter at budget ceiling
- Logs entropy per token for offline analysis

### End-of-Thinking Token

`vllm_adapter/constants.py` defines the token ID. The value is set to `151668` (identified from DeepSeek-R1-Distill-Qwen-7B tokenizer).

### Validation Gate

`evaluation/logit_processor_validation.py` implements the 50-query × 5-position validation gate. Status: **BLOCKED** — requires GPU runtime. No validation results exist.

### Fallback

`HardBudgetFallback` class exists for when the LogitProcessor validation fails. It uses hard `max_tokens` truncation instead of delimiter forcing.

---

## 10. Verification Model

### Verifier Types

| Type | Implementation | Ground Truth Source | Status |
|------|---------------|--------------------| ------|
| `gsm8k` | Regex numerical extraction, exact match | `ground_truth` parameter | Complete |
| `math` | `\boxed{}` extraction, SymPy symbolic equivalence | `ground_truth` parameter | Complete |
| `humaneval` | Sandboxed subprocess (2s CPU, 256MB memory) | `test_cases` + `entry_point` parameters | Complete |
| `json_schema` | `jsonschema.validate()` | `schema` parameter | Complete |

### Live Gateway Verification

In the live gateway, only `json_schema` verification runs. GSM8K/MATH/HumanEval require ground truth or test cases that are not present in the `InferRequest` schema — these run only in the evaluation harness.

### Escalation Trigger

- `"incorrect"` → triggers escalation (if enabled, retries < max)
- `"unverifiable"` → does NOT trigger escalation
- `"correct"` → no escalation
- `"skipped"` → no escalation
- Verifier unavailable → `"unverifiable"` (non-blocking per CLAUDE.md Section 15.4)

---

## 11. Observability Model

### Prometheus Metrics

All metrics use the `ic_` prefix. The following are **actually defined** in `telemetry/prometheus_metrics.py`:

| Metric | Type | Implemented | Emitted by gateway |
|--------|------|:-----------:|:------------------:|
| `ic_request_total` | Counter | Yes | Yes |
| `ic_request_cost_usd` | Histogram | Yes | Yes |
| `ic_cost_usd_total` | Counter | Yes | Yes |
| `ic_latency_seconds` | Histogram | Yes | Yes |
| `ic_ttft_seconds` | Histogram | Yes | Yes |
| `ic_reasoning_tokens_used` | Histogram | Yes | Yes |
| `ic_tokens_reasoning_saved` | Histogram | Yes | Yes |
| `ic_cache_hit_total` | Counter | Yes | Yes |
| `ic_cache_miss_total` | Counter | Yes | Yes |
| `ic_escalation_total` | Counter | Yes | Yes |
| `ic_guardrail_block_total` | Counter | Yes | Yes |
| `ic_fast_path_activations_total` | Counter | Yes | Yes |
| `ic_complexity_score_histogram` | Histogram | Yes | Yes |
| `ic_budget_ceiling_hit_total` | Counter | Yes | Partial |
| `ic_circuit_breaker_open` | Gauge | Yes | **Hardcoded to 0** |
| `ic_admission_control_queue_depth` | Gauge | Yes | Not actively updated |
| `ic_admission_rejected_total` | Counter | Yes | Not actively updated |
| `ic_rate_limit_exceeded_total` | Counter | Yes | **Never emitted** (rate limiter not wired) |
| `ic_audit_write_queue_depth` | Gauge | Yes | Not actively updated |
| `ic_quality_score_histogram` | Histogram | Yes | Updated by eval worker |

### Grafana Dashboard

`dashboards/grafana/inferacordon_unified.json` defines a comprehensive dashboard with five row panels:
1. **Cost** — Request cost by budget class, cache hit rate gauge, reasoning tokens saved
2. **Quality** — LLM judge score, verification pass rate, escalation rate
3. **Reliability** — Circuit breaker states, admission queue depth, rate limit/admission rejections
4. **Performance** — P50/P95/P99 E2E latency, TTFT by model, throughput by budget class
5. **Governance** — Budget class distribution pie chart, guardrail blocks, budget ceiling enforcement

Dashboard uses `ic_` metric names that match the `prometheus_metrics.py` definitions. Some metric names in the dashboard differ slightly from implementations (e.g., `ic_cache_hit_total` vs `ic_cache_hits_total` in CLAUDE.md).

### OpenTelemetry

`telemetry/otel_config.py` configures OpenTelemetry SDK with OTLP gRPC exporter to Jaeger. Trace spans are added to the gateway request lifecycle via `FastAPIInstrumentor`. Custom `ic.*` span attributes are set in `main.py`.

### Trace Schema

`telemetry/trace_schema.py` defines the `RequestTrace` dataclass matching CLAUDE.md Section 18.1. All fields present.

### SQLite Evaluation Store

`AsyncEvalWorker` writes LLM-judge results to SQLite at `EVAL_SQLITE_PATH`. Schema: `eval_jobs` table with columns matching the `/v1/eval-jobs` endpoint response.

---

## 12. Frontend Architecture

### Technology Stack

| Aspect | Implementation |
|--------|---------------|
| Framework | React 18.3.1 |
| Build tool | Vite 5.2.11 |
| Routing | react-router-dom 6.23.1 |
| Charts | Recharts 2.12.7 |
| Styling | CSS custom properties + inline styles (no CSS framework) |
| State | React `useState` hooks (no external state management) |
| API client | Custom fetch wrapper (`lib/api.js`) |
| Prometheus client | Custom fetch wrapper (`lib/prometheus.js`) |
| Testing | **None** (no test framework installed) |
| Type checking | **None** (no TypeScript) |

### Design System

**Critical deviation from CLAUDE.md Section 22.1:** The frontend uses a **light theme** with dark governance surfaces, not the fully dark theme specified:

| Property | CLAUDE.md Spec | Actual | Match |
|----------|:-------------:|:------:|:-----:|
| Background | `#0D1117` (dark) | `#F4F6F9` (light gray) | **NO** |
| Surface | `#161B22` (dark slate) | `#FFFFFF` (white) | **NO** |
| Border | `#21262D` | `#E2E8F0` | **NO** |
| Accent | `#6366F1` | `#4F46E5` | Close |
| Text primary | `#F0F6FC` (light) | `#0F172A` (dark) | **NO** |
| Emerald/amber/rose | Matching | Matching | Yes |
| Inter + JetBrains Mono | Yes | Yes | Yes |
| 8px grid, 240px sidebar | Yes | Yes | Yes |
| 150ms ease-out transitions | Yes | Yes | Yes |

The light-theme design is an **undocumented deviation** from the engineering contract. Dark governance surfaces (`#1A2332`) are used for data-heavy panels (trace waterfall, dashboard charts) creating a "light canvas + dark data" dual-theme.

---

## 13. Frontend Page Inventory

| Page | Route | Lines | Status | Assessment |
|------|-------|:-----:|--------|------------|
| **Playground** | `/` | 447 | Substantial | Prompt input, pipeline animation, governance result grid, trace waterfall. Missing: verification toggle, cost ceiling, markdown rendering, measured stage latencies, raw JSON trace panel |
| **Dashboard** | `/dashboard` | 251 | Partial | 5 tabs present but each is minimal — line charts for basic metrics only. Missing: gauge visualizations, donut chart, bar charts, histograms, eval results tables, governance event log |
| **Policy Manager** | `/policies` | 159 | Partial | Policy list + PolicyCard with 4 sections + JSON view. Missing: version diff panel, YAML validation panel with code editor |
| **Audit Log** | `/audit` | 264 | Substantial | 10-column table with 3 filters + pagination + detail panel. Missing: date range picker, request ID search, Jaeger trace link, eval result link, policy version link |
| **System Health** | `/health` | 204 | Substantial | 7 service cards + CB indicators + eval jobs + failure injection. Missing: per-service metrics, real health probes to non-gateway services, streaming failure results |

### Component Inventory

| Component | Lines | Status | Notes |
|-----------|:-----:|--------|-------|
| `BudgetBadge` | 39 | Complete | Correct color mapping per CLAUDE.md |
| `CircuitBreakerIndicator` | 81 | **Broken** | Prop mismatch: SystemHealth passes `gpuOpen`/`latOpen` but component expects `gpuState`/`latencyState`. Always shows "CLOSED" |
| `FailureInjectionPanel` | 124 | Complete | 10 failure modes, real API calls |
| `MetricsStrip` | 94 | **Orphaned** | Complete but not imported anywhere |
| `PolicyCard` | 142 | Complete | 4 collapsible sections matching spec |
| `StatusBadge` | 58 | Complete | 16 status states, accessible |
| `TraceWaterfall` | 161 | Partial | Span durations are **approximated** from response metadata, not from actual trace spans. Jaeger deep-link button present |

---

## 14. API Inventory

### Endpoints exposed by gateway

| Method | Route | Purpose | Frontend Consumer | Working |
|--------|-------|---------|-------------------|:-------:|
| GET | `/v1/health` | Health check | App.jsx, SystemHealth | Yes |
| GET | `/v1/readiness` | Startup readiness | **Not called by frontend** | Yes |
| GET | `/metrics` | Prometheus scrape | Prometheus server | Yes |
| POST | `/v1/infer` | Primary inference | Playground | Yes |
| GET | `/admin/policies` | Policy inspection | PolicyManager | Yes |
| GET | `/audit/records` | Audit log query | AuditLog | Yes |
| GET | `/v1/status` | System state (cache, admission, CB, demo_mode) | SystemHealth | Yes |
| GET | `/v1/eval-jobs` | Evaluation job list | SystemHealth | Yes |
| POST | `/admin/inject-failure` | Failure injection (DEMO_MODE only) | FailureInjectionPanel | **Partial** — returns description but doesn't actually inject failure |

### Endpoints NOT in frontend but documented in CLAUDE.md

| Documented Endpoint | Status |
|--------------------|--------|
| Streaming inference (`stream: true`) | Not implemented ("reserved" per schemas.py) |
| Prometheus proxy at `/prometheus` | Not implemented in gateway (frontend hits Prometheus directly at port 9090 in dev) |

### Guardrail Service endpoints

| Method | Route | Status |
|--------|-------|--------|
| POST | `/guardrail/input` | Complete |
| POST | `/guardrail/output` | Complete |
| GET | `/health` | Complete |
| GET | `/metrics` | Complete |

### Verifier Service endpoints

| Method | Route | Status |
|--------|-------|--------|
| POST | `/verify` | Complete |
| GET | `/health` | Complete |
| GET | `/metrics` | Complete |

---

## 15. Demo Contract

### Five-Segment Demo Flow (CLAUDE.md Section 23)

| Segment | Capability Required | Implementation Status |
|---------|--------------------|-----------------------|
| 1. Overthinking Suppression | Playground shows budget class selection, reasoning tokens used/allocated, stop reason | **Backend ready, frontend can demonstrate** |
| 2. Underthinking Prevention / Escalation | JSON schema verification → failure → escalation to higher budget class | **Backend ready** — escalation works. Frontend shows escalation_count. Trace waterfall shows two spans conceptually but uses approximated durations |
| 3. Governance (Policy + Audit) | Policy Manager shows versioned policies; Audit Log shows decision+outcome records | **Partially ready** — policies display correctly. Audit records display. Missing: linked trace IDs, version diff |
| 4. Circuit Breaker Activation | Failure injection triggers CB → System Health shows state change | **NOT READY** — circuit breakers are stubs. Failure injection endpoint returns description only without actual injection |
| 5. Cost Summary | Dashboard shows cost-per-correct-answer with delta vs baseline | **NOT READY** — no benchmark results exist. Cost tab has basic line chart but no cost-per-correct-answer metric card or delta |

### Failure Injection Status

The `/admin/inject-failure` endpoint accepts failure types but **does not actually inject failures**. It returns `{"failure_type": "...", "description": "...", "injected": true}` without modifying system behavior. All ten failure modes are listed but none produce real system responses.

---

## 16. Evaluation/Metrics Contract

### Benchmarks

**Status: BLOCKED** — No GPU runtime has been available. The single result file (`experiment_baseline3_gsm8k_4071b3c2.json`) contains zero samples and is marked `"status": "blocked"`.

### README Metrics

The README metrics block is a placeholder:
```
> **Benchmark results pending** — GPU infrastructure required to run `evaluation/benchmark_harness.py`.
```

Portfolio targets listed are explicitly labeled as targets, not results. This is correct per CLAUDE.md Section 27.

### Key distinction for frontend

All evaluation numbers in README and documentation are **targets**. The frontend must NEVER:
- Display targets as measured results
- Fabricate cost-per-correct-answer numbers
- Show hardcoded benchmark values as live telemetry

---

## 17. Repository Structure

```
inferacordon/
├── .claude/launch.json              ← Dev server configs (frontend + product-demo)
├── .env.example                     ← Environment variable reference
├── .gitignore                       ← Excludes .env, models, audit logs, FAISS files
├── CLAUDE.md                        ← Permanent engineering contract (~1,800 lines)
├── README.md                        ← Portfolio-facing project summary
├── architecture.md                  ← Concise architecture companion
├── InferaCordon Detailed Architecture Plan.pdf  ← Primary architecture source
├── InferaCordon MVP Documentation.pdf           ← Secondary product source
├── docker-compose.yml               ← 7-container topology
├── tenants.yaml                     ← API key → tenant mapping
│
├── gateway/                         ← FastAPI control plane (18 modules, flat)
│   ├── main.py                      ← App entry, all endpoints, request lifecycle
│   ├── schemas.py                   ← Pydantic request/response models
│   ├── auth.py                      ← Authentication middleware
│   ├── rate_limiter.py              ← Token bucket (EXISTS, NOT WIRED)
│   ├── trace_context.py             ← W3C traceparent generation
│   ├── pre_inference_pipeline.py    ← Pipeline orchestrator (deadline timer not used)
│   ├── complexity_scorer.py         ← 5-feature heuristic scorer
│   ├── pii_redactor.py              ← Presidio wrapper
│   ├── context_engine.py            ← Prompt template selection
│   ├── semantic_cache.py            ← FAISS IndexFlatIP
│   ├── admission_control.py         ← Semaphore-based admission
│   ├── model_router.py              ← Budget → model (EXISTS, NOT WIRED)
│   ├── vllm_client.py               ← OpenAI-compatible client
│   ├── guardrail_client.py          ← Guardrail HTTP client
│   ├── verifier_client.py           ← Verifier HTTP client
│   ├── escalation_handler.py        ← Budget class escalation
│   ├── async_eval_worker.py         ← Background LLM judge
│   ├── static/                      ← Built React frontend (mounted in Docker)
│   ├── Dockerfile                   
│   └── requirements.txt             
│
├── policy_engine/                   ← Python library (in-process, not a service)
│   ├── loader.py                    ← YAML + Pydantic validation
│   ├── validator.py                 ← Policy schema models
│   ├── budget_controller.py         ← Complexity → budget class
│   ├── audit_log.py                 ← JSONL audit writer
│   └── policies/                    ← Versioned YAML policies
│       ├── acme_corp_general_qa_v1.yaml
│       ├── demo_tenant_v1.yaml
│       └── default_policy_v1.yaml
│
├── vllm_adapter/                    ← vLLM integration
│   ├── logit_processor.py           ← BudgetLogitProcessor
│   ├── circuit_breakers.py          ← STUB — raises NotImplementedError
│   ├── constants.py                 ← End-of-thinking token ID (151668)
│   ├── serving_config.py            ← Server configuration builder
│   ├── inference_adapter.py         ← Call spec builder + result parser
│   └── Dockerfile                   
│
├── guardrail_service/               ← CPU-only FastAPI container
│   ├── main.py                      ← Service endpoints
│   ├── injection_classifier.py      ← DeBERTa ONNX + keyword fallback
│   ├── safety_classifier.py         ← Llama Guard ONNX + keyword fallback
│   ├── models/                      ← ONNX model directory (.gitkeep)
│   └── Dockerfile                   
│
├── verifier_service/                ← CPU-only FastAPI container
│   ├── main.py                      ← Service endpoints
│   ├── gsm8k_verifier.py            ← Numerical extraction
│   ├── math_verifier.py             ← SymPy equivalence
│   ├── humaneval_runner.py          ← Sandboxed subprocess
│   ├── schema_verifier.py           ← jsonschema validation
│   └── Dockerfile                   
│
├── telemetry/                       ← Observability infrastructure
│   ├── otel_config.py               ← OTel SDK configuration
│   ├── prometheus_metrics.py        ← All ic_ metric definitions
│   └── trace_schema.py              ← RequestTrace dataclass
│
├── evaluation/                      ← Benchmark framework
│   ├── benchmark_harness.py         ← Main runner
│   ├── ablation_runner.py           ← Ablation sequence
│   ├── baseline_measurements.py     ← Baseline runners
│   ├── complexity_calibration.py    ← Weight calibration
│   ├── datasets.py                  ← Dataset loaders
│   ├── llm_judge.py                 ← GPT-4o-mini scoring
│   ├── logit_processor_validation.py ← 50×5 validation gate
│   ├── metric_calculator.py         ← Cost/quality computation
│   ├── regression_gate.py           ← Accuracy gating
│   ├── result_schema.py             ← Result models
│   ├── update_readme_metrics.py     ← README auto-updater
│   └── results/                     ← Experiment results (BLOCKED)
│
├── load_testing/                    ← Locust test profiles
│   ├── locustfile.py                
│   └── workload_profiles.py         
│
├── frontend/                        ← React SPA source
│   ├── package.json                 ← 4 runtime deps (react, react-dom, react-router-dom, recharts)
│   ├── vite.config.js               ← Dev proxy for /v1, /admin, /audit, /metrics
│   ├── index.html                   ← Entry (Inter + JetBrains Mono fonts)
│   └── src/
│       ├── main.jsx                 ← React entry
│       ├── App.jsx                  ← Shell + router + sidebar
│       ├── index.css                ← CSS custom properties design system
│       ├── pages/                   ← 5 page components
│       ├── components/              ← 7 shared components
│       └── lib/                     ← API + Prometheus clients
│
├── config/prometheus.yml            ← Prometheus scrape config
├── dashboards/grafana/              ← Pre-configured dashboard JSON
├── notebooks/                       ← Entropy analysis notebook (BLOCKED)
├── tests/                           ← Unit + integration tests
│   ├── conftest.py                  
│   ├── unit/ (30 test files)        
│   ├── integration/ (5 test files)  
│   └── failure_injection/           ← .gitkeep only
└── media/                           ← README images and GIFs
```

---

## 18. Implementation Status Matrix

| Feature | Documented | Implemented | Tested | Frontend Exposed | Notes |
|---------|:----------:|:-----------:|:------:|:----------------:|-------|
| Authentication (API key) | Yes | Yes | Yes | Yes (sessionStorage) | |
| Rate Limiting | Yes | Code exists | Yes (unit) | No | **NOT WIRED** into gateway main.py |
| Trace Context | Yes | Yes | Yes | Partial (Jaeger link) | |
| Pre-inference Pipeline (50ms deadline) | Yes | Code exists | Unknown | No | Deadline timer not used; scorer called directly |
| Complexity Scoring | Yes | Yes | Yes | Yes (budget class shown) | |
| Policy Engine | Yes | Yes | Yes | Yes (PolicyManager) | |
| Budget Controller | Yes | Yes | Yes | Yes (budget class in response) | |
| Audit Log | Yes | Yes | Yes | Yes (AuditLog page) | |
| Semantic Cache | Yes | Yes | Yes | Yes (cache_hit in response) | |
| Admission Control | Yes | Yes | Yes | Yes (status endpoint) | |
| PII Redaction | Yes | Yes | Yes | No (transparent to frontend) | |
| Input Guardrail | Yes | Yes | Yes | Yes (block → 503) | |
| Output Guardrail | Yes | Yes | Partial | Partial | |
| vLLM Inference | Yes | Yes | Yes (mock) | Yes (response from /v1/infer) | |
| LogitProcessor | Yes | Yes | Yes (unit) | Yes (stop_reason, tokens) | Validation gate BLOCKED (needs GPU) |
| Circuit Breakers | Yes | **STUB** | No | **Broken** (hardcoded closed + prop mismatch) | `NotImplementedError` |
| Verification | Yes | Yes | Yes | Yes (verification_result) | Only json_schema in live gateway |
| Escalation | Yes | Yes | Yes | Yes (escalation_count) | |
| Async Eval (LLM Judge) | Yes | Yes | Yes | Yes (eval-jobs endpoint) | |
| Failure Injection | Yes | **STUB** | No | Yes (UI sends request) | Returns description only, no actual injection |
| Load Testing | Yes | Code exists | No | No | Locust profiles defined |
| Benchmark Harness | Yes | Yes | Partial | No | BLOCKED — needs GPU |
| Grafana Dashboard | Yes | Yes | N/A | N/A | Pre-configured JSON committed |
| Frontend (5 pages) | Yes | Partial | No | — | Light theme, missing features per section 13 |
| Streaming | Yes | No | No | No | "Reserved" in schemas.py |
| Demo Recording | Yes | No | N/A | N/A | Phase 13-14 deliverable |

---

## 19. Documentation-vs-Code Discrepancies

### D1. Request Step Ordering: architecture.md vs CLAUDE.md vs Implementation

**architecture.md** lists a 16-step sequence that differs from both CLAUDE.md Section 6.3 and the actual implementation:
- architecture.md puts Cache Lookup at step 4 (before guardrails)
- CLAUDE.md puts Cache Lookup at step 8 (after budget assignment)
- Implementation puts Cache Lookup after PII redaction and budget assignment

**Resolution needed:** architecture.md should be updated to match the actual implementation order.

### D2. Rate Limiter Not Wired

`gateway/rate_limiter.py` is fully implemented with token bucket algorithm but is never imported by `gateway/main.py`. CLAUDE.md Step 2 requires rate limiting.

**Classification:** Implementation gap.

### D3. Model Router Not Wired

`gateway/model_router.py` exists but is never imported. Model routing is done inline within `InferenceAdapter.build_call_spec()`.

**Classification:** Intentional deviation (routing abstracted into inference adapter).

### D4. Circuit Breakers Are Stubs

`vllm_adapter/circuit_breakers.py` defines class interfaces but all methods raise `NotImplementedError`. The gateway hardcodes `FleetState.nominal()`. CLAUDE.md Section 17 specifies full circuit breaker behavior.

**Classification:** Implementation gap (Phase 7-8 deliverable per roadmap).

### D5. Failure Injection Endpoint Is a Stub

`POST /admin/inject-failure` returns `{"injected": true}` but does not actually inject failures. CLAUDE.md Section 22.6 specifies that each button "triggers the defined failure behavior for a single request and streams the result."

**Classification:** Implementation gap.

### D6. Frontend Theme is Light, Not Dark

CLAUDE.md Section 22.1 specifies a dark theme with `#0D1117` base background. The implementation uses `#F4F6F9` (light gray) with dark governance surfaces.

**Classification:** Undocumented intentional deviation.

### D7. Pre-Inference Pipeline Deadline Not Implemented

CLAUDE.md Section 6.3 Step 4 specifies a 50ms deadline timer for the pre-inference pipeline. The implementation calls the complexity scorer directly without a deadline orchestrator.

**Classification:** Implementation gap — the `pre_inference_pipeline.py` file exists but its deadline logic is not used.

### D8. PII Redaction Ordering

CLAUDE.md Section 6.3 places PII redaction in Step 4 (pre-inference pipeline, before policy lookup). The implementation places it at Step 8.5 (after budget assignment, before cache lookup).

**Classification:** Intentional deviation. The implementation comment notes that PII must run before the cache sees the prompt, which is correct — but the ordering relative to policy lookup differs from spec.

### D9. README Status Badge Says "Phase 1"

The README badge shows "phase 1 — baseline & validation" but the git history shows commits through Phase 11-12 (frontend, observability, integration).

**Classification:** Documentation lag.

### D10. product-demo in launch.json But No Directory

`.claude/launch.json` references an `inferacordon-product-demo` configuration with `product-demo/` directory, which does not exist.

**Classification:** Stale configuration.

### D11. Prometheus Metric Name Discrepancies

CLAUDE.md Section 18.2 uses `ic_cache_hits_total` (plural). Implementation uses `ic_cache_hit_total` (singular). Similarly for `ic_cache_misses_total` vs `ic_cache_miss_total`.

**Classification:** Minor naming inconsistency.

### D12. `ic_cost_per_correct_answer` Metric

CLAUDE.md Section 18.2 lists `ic_cost_per_correct_answer{tenant, task_class}` as a gauge. This metric is NOT defined in `telemetry/prometheus_metrics.py` and is not emitted by the gateway.

**Classification:** Missing implementation.

### D13. CircuitBreakerIndicator Prop Mismatch

`SystemHealth.jsx` passes `gpuOpen`/`latOpen` (booleans) to `CircuitBreakerIndicator`, but the component destructures `gpuState`/`latencyState` (strings). The component always shows "CLOSED".

**Classification:** Frontend bug.

### D14. MetricsStrip Component Not Used

`MetricsStrip.jsx` is a complete component with Prometheus polling but is not imported by any page.

**Classification:** Orphaned code.

### D15. Prometheus Proxy

The frontend `lib/prometheus.js` expects `/prometheus` as the Prometheus API path in production, but the gateway does not implement a `/prometheus` proxy route. In development, it hits `http://localhost:9090` directly.

**Classification:** Missing implementation for production deployment.

---

## 20. Open Engineering Questions

1. **Should the light-theme frontend be kept or reverted to the CLAUDE.md dark theme?** This is the largest UI deviation from the engineering contract.

2. **When will circuit breakers be implemented?** They are Phase 7-8 deliverables per the roadmap but are stubs in the current code. The frontend CB display is broken regardless due to D13.

3. **Should `rate_limiter.py` be wired into `main.py`?** The code is complete and tested but not integrated.

4. **Should `model_router.py` be removed or wired?** Routing is done inline via InferenceAdapter. The standalone module may be dead code.

5. **How should the Prometheus proxy work in production?** The frontend assumes `/prometheus` proxied through the gateway, but this route doesn't exist.

6. **Should the pre-inference pipeline deadline timer be implemented?** The orchestrator exists but isn't used — the complexity scorer runs without time-bounding.

7. **What should failure injection actually do?** The endpoint stub returns a description but doesn't modify system behavior.

8. **Which step ordering is authoritative — CLAUDE.md or the implementation?** There are differences in PII redaction placement.

9. **Should guardrail/verifier keyword fallbacks be documented?** The ONNX fallback behavior is not in CLAUDE.md.

10. **How should the frontend display trace timing?** Currently approximated from response metadata. Real OTel span data is not available via any frontend-facing API.

---

## 21. Frontend Non-Negotiables

Based on the project's documented contracts and architecture:

1. **Do not fabricate telemetry.** All metric values must come from Prometheus or the gateway API. If a service is unreachable, show a "data unavailable" state, not simulated data.

2. **Do not change backend API contracts.** The frontend is a display layer. Field names, error codes, and response schemas are governed by CLAUDE.md Section 7.

3. **Do not expose undocumented backend capabilities.** If the backend doesn't implement a feature, the frontend must not fake it.

4. **Do not change governance semantics.** Budget classes, escalation logic, stop reasons, and verification results have precise meanings defined in CLAUDE.md. Do not reinterpret them into generic terminology.

5. **Do not change budget semantics.** "reasoning_tokens_used" and "reasoning_tokens_allocated" are specific technical values from the LogitProcessor. They are not "AI performance" or "thinking progress" metrics.

6. **Do not expose private reasoning traces.** Per CLAUDE.md Section 11.5: `store_reasoning_trace: false`. Raw chain-of-thought tokens must never appear in the frontend.

7. **Do not convert audit data into editable data.** The audit log is append-only (CLAUDE.md Section 19). The Audit Log Explorer is a read-only inspection tool.

8. **Do not fake failure injection.** Failure injection must produce real system responses, not UI animations disconnected from backend behavior.

9. **Do not turn benchmark targets into measured results.** Portfolio targets (CLAUDE.md Section 20.6) are NOT implementation results. The README uses `[X]%` placeholders specifically to prevent this.

10. **Do not make demo-only information appear to be live production telemetry.** The Failure Injection Panel is gated on `DEMO_MODE=true`. Demo scaffolding must remain visually distinct from production monitoring.

11. **Do not invent policy deployment functionality.** The Policy Manager is read-only. Policy updates require gateway restart (CLAUDE.md Section 11.4).

12. **Do not expose raw prompts or responses in audit views.** Per CLAUDE.md Section 19: "Never store raw prompt or response text by default — only derived signals, counts, and outcomes."

---

## 22. Rules for Subsequent Frontend Phases

1. Read CLAUDE.md before every implementation session.
2. Inspect the existing repository to understand what has changed since this audit.
3. Implement only the requested phase scope.
4. Preserve all backend contracts and existing functionality.
5. Every frontend value must trace to a documented API response field or Prometheus metric.
6. If Prometheus is unreachable, show null/unavailable state — never fabricate.
7. The five pages correspond to CLAUDE.md Section 22 subsections 22.2–22.6. Implementation must reference the specific subsection.
8. Dark theme restoration (if chosen) must use the exact hex values from CLAUDE.md Section 22.1.
9. All JetBrains Mono usage must follow the documented rule: metric values, token counts, cost figures, latency readings, version identifiers, JSON data, trace span labels.
10. Test frontend against the gateway's actual API responses, not mocked data.
11. Report missing backend capabilities honestly. Do not add frontend features that require backend changes without documenting the dependency.
12. The README status badge should reflect the actual project phase.

---

## Appendix A: Git History Summary

All implementation was committed on August 10–11, 2026 across 11 commits:

| Commit | Date | Phase Description |
|--------|------|-------------------|
| `c78916f` | 2026-08-10 | Repository foundation + vLLM inference foundation |
| `2964c0b` | 2026-08-10 | Policy engine, budget controller, policy resolution |
| `f1e381b` | 2026-08-10 | FastAPI gateway + guardrail service |
| `273c393` | 2026-08-10 | Architecture, security, and privacy audit |
| `5cde4df` | 2026-08-10 | Semantic cache, admission control, adaptive reasoning |
| `c516fba` | 2026-08-10 | Evaluation harness and benchmarking suite |
| `a83e6e9` | 2026-08-11 | Observability, async eval, LLM-as-judge |
| `3c183f4` | 2026-08-11 | Production-grade frontend control plane |
| `34a868a` | 2026-08-11 | System integration, prod provisioning, benchmarks |
| `6eabf98` | 2026-08-11 | Full system integration, release hardening |
| `b54dd58` | 2026-08-11 | Merge PR #1 |

---

## Appendix B: Codebase Size

| Area | Files | Lines |
|------|:-----:|:-----:|
| Backend Python | ~45 | ~11,600 |
| Frontend JSX/JS/CSS | ~15 | ~2,500 |
| Tests | ~35 | ~11,600 |
| Configuration (YAML, JSON, Dockerfile) | ~12 | ~600 |
| Documentation (CLAUDE.md, architecture.md, README.md) | 3 | ~2,400 |
| **Total** | ~110 | ~28,700 |

---

## Appendix C: Confirmation

**A. What was inspected:** All 110+ files in the repository, including every Python module, every frontend component, every configuration file, every policy file, every test file, and all documentation.

**B. Documents discovered:** CLAUDE.md, architecture.md, README.md, two PDF source documents, three YAML policies, tenants.yaml, .env.example, docker-compose.yml, prometheus.yml, Grafana dashboard JSON, entropy analysis notebook.

**C. Repository architecture understood:** Seven-container topology, 16-step request lifecycle, four-pillar governance model, budget class routing, escalation mechanics, audit trail, observability stack.

**D. Current frontend architecture:** React 18 SPA with Vite, react-router-dom, Recharts, CSS custom properties (light theme), inline styles, no state management library, no testing.

**E. Current frontend page status:** All five pages exist. Playground and Audit Log are substantial. Dashboard is partial. Policy Manager is partial. System Health is substantial but with broken circuit breaker display.

**F. Backend APIs relevant to frontend:** 9 endpoints identified — `/v1/infer`, `/v1/health`, `/v1/readiness`, `/v1/status`, `/v1/eval-jobs`, `/admin/policies`, `/audit/records`, `/admin/inject-failure`, `/metrics`.

**G. Major mismatches:** 15 discrepancies documented (Section 19). Most significant: rate limiter not wired, circuit breakers are stubs, failure injection is a stub, frontend uses light theme instead of dark, CB indicator has prop mismatch.

**H. Open engineering questions:** 10 questions documented (Section 20).

**I. Frontend constraints:** 12 non-negotiables documented (Section 21).

**J. Engineering contract location:** `docs/PHASE_0_REPOSITORY_AND_ENGINEERING_CONTRACT.md`

**K. Confirmation:** No source code, dependencies, or configuration was modified during this audit. The only file created was this document.
