# CLAUDE.md — InferaCordon Engineering Contract
## Phase 0 Artifact — Permanent Architecture Authority

> This file is the **permanent engineering contract** for InferaCordon.
> Every implementation phase must obey it.
> No architectural deviation may occur without following the Architecture Deviation Protocol (Section 28).
> No benchmark result may be manually written into README — all numbers come from `evaluation/benchmark_harness.py`.

---

## 1. Project Identity

**Project Name:** InferaCordon

**One-Sentence Definition:** InferaCordon is a governed AI inference control plane that makes reasoning compute schedulable, policy-bounded, cost-attributed, and quality-guaranteed — sitting between client applications and model serving infrastructure, making per-request decisions about budget, routing, stopping, verification, and escalation under explicit SLOs.

**Primary Problem:** Reasoning models generate internal chain-of-thought tokens before producing any visible output. These tokens are billed in full, consume context window, dominate inference latency, and are completely invisible to every standard monitoring, cost attribution, and governance tool in the LLMOps ecosystem. Platform teams have no control surface for this spend.

**Three Simultaneous Production Failure Modes:**
- **Overthinking:** A model spends 1,800 thinking tokens on a query requiring 200. No mechanism exists to recognize this and stop earlier.
- **Underthinking:** A complex query hits a conservative global ceiling. The model produces a shallow answer. No error is raised.
- **Budget Blindness:** No per-request allocation, no tenant-level cost attribution, no SLO-aware routing, no audit trail recording what was spent and why.

**Control-Plane Framing:** Reasoning tokens should be treated as a managed compute resource — exactly like CPU time or memory bandwidth. InferaCordon builds the control plane that allocates, governs, and attributes reasoning compute the same way CPU schedulers, memory allocators, and network rate limiters govern their respective resources.

**Four Pillars (all must be demonstrable in the five-minute demo):**
1. **Guardrails** — PII redaction, injection detection, safety classification at input AND output
2. **Governance** — Versioned YAML policies, immutable audit trail, every decision recorded with its governing policy version
3. **Cost Optimization** — Semantic cache, budget-class routing, verification-triggered escalation, cost per correct answer as primary metric
4. **Inference Optimization** — Native vLLM LogitProcessor that enforces per-request reasoning token budgets without invasive PyTorch hooks

**Intended MVP Scope:** One engineer. Fourteen weeks. One GPU node. Six containers. `docker compose up`.

---

## 2. Authoritative Source Documents

```
PRIMARY ARCHITECTURE SOURCE:
  InferaCordon Detailed Architecture Plan.pdf
  Authority over: architecture, system topology, component boundaries, repository
  structure, technology choices, service boundaries, API contracts, request lifecycle,
  data flow, implementation details, configuration, infrastructure,
  implementation constraints, failure handling, observability, testing expectations,
  implementation roadmap.

SECONDARY PRODUCT/MVP SOURCE:
  InferaCordon MVP Documentation.pdf
  Authority over: product intent, functional behavior, UX requirements, frontend
  requirements, evaluation framework, benchmark methodology, demo requirements,
  failure-mode behavior (supplementary), governance requirements,
  portfolio/documentation requirements.
```

**Source Hierarchy:** The Architecture Plan governs all architectural and implementation decisions. The MVP Documentation supplements — it may add product context and behavioral detail, but it cannot override the Architecture Plan on any architectural question.

**Conflict Resolution Rule:**
1. Architecture Plan wins for architecture and implementation.
2. MVP Documentation may supplement where it does not contradict.
3. All detected conflicts are recorded in Section 31 (Source Document Conflicts) of this file.
4. No silent conflict reconciliation. No invented resolutions.

---

## 3. Non-Negotiable Architecture Constraints

These are hard boundaries from the Architecture Plan. They govern every architectural decision.

| Constraint | Statement | Source |
|------------|-----------|--------|
| **One engineer** | Nothing in the architecture requires more than one engineer. | Architecture Plan — Governing Constraints |
| **Fourteen weeks** | The entire MVP must be built, tested, and demonstrated in 14 weeks. | Architecture Plan — Governing Constraints |
| **One GPU node** | All GPU workload runs on a single node. No multi-node GPU assumption. | Architecture Plan — Governing Constraints |
| **One reasoning model** | DeepSeek-R1-7B-Q4. No other reasoning model. | Architecture Plan — Governing Constraints |
| **One cheap model** | Qwen2.5-3B-Instruct. No other cheap model. | Architecture Plan — Governing Constraints |
| **Single vLLM instance** | Both models served via one vLLM instance using multi-model routing. | Architecture Plan — Component 5 |
| **No validation-free production** | No component enters production without a passing validation test. The LogitProcessor is validated in Week 1. | Architecture Plan — Governing Constraints |
| **No hand-written metrics** | No claim appears in the README that is not produced by a benchmark script. Every number is measured. None estimated or projected. | Architecture Plan — Governing Constraints |
| **All four pillars demonstrable** | Guardrails, Governance, Cost Optimization, and Inference Optimization each need at least one concrete, visible, interactive demonstration in the frontend. | Architecture Plan — Governing Constraints |
| **Six containers** | The system runs as six Docker containers launched by `docker compose up`. (See Section 31 for intra-document ambiguity on Jaeger.) | Architecture Plan — System Topology |
| **No separate Redis** | The gateway hosts the in-process FAISS semantic cache. No Redis. | Architecture Plan — System Topology |
| **No separate Celery** | The async evaluation worker runs as a background thread pool inside the gateway process. No Celery. | Architecture Plan — System Topology |
| **No separate frontend server** | React frontend static files are served by the FastAPI gateway. No separate frontend container. | Architecture Plan — System Topology |
| **Gateway owns control flow** | The gateway never delegates control flow to another component — it calls services, receives results, and makes decisions. | Architecture Plan — Component 1 |
| **Guardrail is CPU-only** | The guardrail service runs on CPU only. It never touches the GPU. It never calls vLLM. | Architecture Plan — Component 6 |
| **Verifier is CPU-only** | The verifier service runs on CPU only. It wraps official evaluation harnesses — it never implements verification logic from scratch. | Architecture Plan — Component 7 |
| **FAISS is in-process** | The semantic cache uses an in-process FAISS flat index inside the gateway. No external FAISS server. | Architecture Plan — Component 4 |
| **Policy engine is in-process** | The policy engine is a Python library imported directly by the gateway — not a service. | Architecture Plan — Component 2 |
| **4-bit quantization required** | Both models must be quantized to 4-bit (GPTQ or AWQ) to fit on one A100 80GB GPU with sufficient KV-cache headroom. | Architecture Plan — Component 5 |

**Principle governing every decision (from the Architecture Plan preamble):**
> If a component cannot be built, tested, and demonstrated to work correctly within its allocated phase, it does not belong in the MVP.

---

## 4. System Topology

```
╔══════════════════════════════════════════════════════════════════╗
║                        SINGLE GPU NODE                          ║
║                                                                  ║
║  ┌─────────────────────┐  ┌─────────────────┐  ┌─────────────┐ ║
║  │  FastAPI Gateway    │  │  vLLM Server    │  │  Guardrail  │ ║
║  │  + React Frontend   │  │  (GPU)          │  │  Service    │ ║
║  │  + FAISS (in-proc)  │  │  Port 8080      │  │  (CPU only) │ ║
║  │  + Eval ThreadPool  │  │                 │  │  Port 8001  │ ║
║  │  Port 8000          │  │                 │  │             │ ║
║  └─────────────────────┘  └─────────────────┘  └─────────────┘ ║
║           │                        │                    │        ║
║           │  HTTP                  │  OpenAI-compat     │  HTTP  ║
║           └──────────────┬─────────┘                    │        ║
║                          │                              │        ║
║  ┌──────────────────┐   │    ┌────────────────┐         │        ║
║  │  Verifier        │   │    │  Prometheus    │         │        ║
║  │  Service         │   │    │  Port 9090     │         │        ║
║  │  (CPU only)      │   │    └────────────────┘         │        ║
║  │  Port 8002       │   │           │                   │        ║
║  └──────────────────┘   │    ┌──────────────┐           │        ║
║           │              │    │  Grafana     │           │        ║
║           │              │    │  Port 3000   │           │        ║
║           │              │    └──────────────┘           │        ║
║  ┌──────────────────┐   │    ┌──────────────┐           │        ║
║  │  Jaeger          │   │    │  FAISS       │           │        ║
║  │  Port 16686      │   │    │  (in-process)│           │        ║
║  └──────────────────┘   │    └──────────────┘           │        ║
║                          │                               │        ║
╚══════════════════════════╪═══════════════════════════════╪═══════╝
                           │                               │
                    CLIENT APPLICATIONS
              (Web App · CLI · Internal Services · API)
```

**Container responsibilities:**
- **FastAPI Gateway (Port 8000):** Complete request lifecycle, React static files, in-process FAISS cache, background eval thread pool
- **vLLM Server (Port 8080):** GPU inference for both DeepSeek-R1-7B-Q4 and Qwen2.5-3B-Instruct; LogitProcessor registration; Prometheus metrics
- **Guardrail Service (Port 8001):** CPU-only ONNX injection and safety classifiers
- **Verifier Service (Port 8002):** CPU-only official evaluation harness wrappers
- **Prometheus (Port 9090):** Metrics scraping from all services
- **Grafana (Port 3000):** Unified dashboard (pre-configured JSON in repository)
- **Jaeger (Port 16686):** OpenTelemetry trace collection via OTLP (see Section 31 for "six vs seven containers" ambiguity)
- **FAISS:** In-process inside gateway — not a container

All containers started by: `docker compose up`
No separate Redis. No separate Celery. No separate frontend server.

---

## 5. Component Responsibility Matrix

| Component | Responsibility | Must NOT Own | Runtime | Key Dependencies |
|-----------|----------------|--------------|---------|-----------------|
| **FastAPI Gateway** | Complete request lifecycle: auth → rate limit → trace → pipeline → policy → budget → cache → admission → guardrail → inference → verify → escalate → respond → audit | GPU inference, guardrail classification, verification logic, policy storage | Python process, Port 8000 | vLLM, Guardrail Service, Verifier Service, Policy Engine (in-proc), FAISS (in-proc) |
| **Policy Engine** | Load/validate YAML policies at startup; resolve tenant+domain policy at request time; compute budget allocations; write audit records | HTTP serving, inference, guardrail logic, rate limiting | Python library, imported in-process by gateway | Pydantic, tenants.yaml |
| **vLLM Server** | Serve DeepSeek-R1-7B-Q4 and Qwen2.5-3B-Instruct; enforce per-request token budgets via LogitProcessor; expose Prometheus metrics | Policy decisions, routing decisions, guardrail checking, audit writing | GPU container, Port 8080 | GPU hardware, models on Docker volume |
| **LogitProcessor** | Per-request: count reasoning tokens, detect natural </think> delimiter, force delimiter at budget ceiling, log entropy | Cross-request state, policy lookup, network calls | In-process within vLLM, per-request instance | vLLM SamplingParams, model tokenizer constants |
| **Circuit Breakers** | Monitor GPU KV-cache pressure and P99 TTFT latency; open/close; signal gateway to downgrade budget class | Inference, policy decisions, audit writing | Python thread, in-process within vLLM_adapter | vLLM Prometheus endpoint |
| **Guardrail Service** | PII detection (Presidio), injection classification (ONNX DeBERTa), safety classification (ONNX Llama Guard) | GPU access, vLLM calls, policy decisions, inference | CPU container, Port 8001 | ONNX Runtime, model volumes |
| **Verifier Service** | Verification via official harnesses: GSM8K regex, MATH-500 SymPy, HumanEval subprocess, JSON schema | Guardrail logic, policy logic, inference | CPU container, Port 8002 | sympy, jsonschema, subprocess sandbox |
| **Semantic Cache (FAISS)** | Embed prompts, compare cosine similarity, return cached response on hit, store on miss | Policy decisions, budget assignment, guardrail logic | In-process inside gateway | all-MiniLM-L6-v2, FAISS IndexFlatIP |
| **Complexity Scorer** | Heuristic scoring 0.0–10.0 from prompt text in <3ms; no ML inference | Policy lookup, network calls, model inference | In-process, synchronous | None (pure computation) |
| **Eval Worker** | Background LLM-as-judge scoring for non-verifiable responses; SQLite writes; Prometheus quality metric updates | Request serving, response delivery, circuit breaking | Background thread pool inside gateway | GPT-4o-mini API, SQLite |
| **Prometheus** | Scrape metrics from all services; expose query API to Grafana and frontend | Business logic | Container, Port 9090 | All service /metrics endpoints |
| **Grafana** | Pre-configured unified dashboard; five panels (Cost, Quality, Reliability, Performance, Governance) | Data transformation, routing | Container, Port 3000 | Prometheus |
| **Jaeger** | Receive OTLP traces; provide trace inspection UI | Metric aggregation, alerting | Container, Port 16686 | OpenTelemetry OTLP exporter |
| **React Frontend** | Five-page SPA served as static files by gateway; Playground, Dashboard, Policy Manager, Audit Log Explorer, System Health | Backend logic, state management beyond UI | Static files served by gateway at root | Gateway API, Prometheus API |
| **Audit Log** | Append-only JSONL file; two records per request (decision + outcome); persisted to Docker volume | Query serving (served by gateway /audit/records) | File on Docker volume | None |
| **SQLite** | Evaluation results from LLM judge; quality metrics fed to Grafana | Audit governance records, operational logs | File inside gateway container | None |

---

## 6. Gateway Contract

### 6.1 Responsibility Boundary

The gateway owns the complete request lifecycle from client receipt to client response. It is the **only** component that talks directly to the client. Every other component is called by the gateway. The gateway never delegates control flow — it calls services, receives results, and makes decisions.

### 6.2 Internal Module Structure (from Architecture Plan Component 1)

```
gateway/
├── main.py              ← FastAPI app, lifespan, route registration
├── middleware/
│   ├── auth.py          ← API key → tenant ID resolution
│   ├── rate_limiter.py  ← Token bucket, in-memory, per-tenant
│   └── trace_injector.py ← UUID request ID, W3C traceparent
├── pipeline/
│   ├── orchestrator.py  ← Pre-inference pipeline, 50ms deadline
│   ├── complexity_scorer.py ← Heuristic scorer, <3ms
│   ├── pii_redactor.py  ← Presidio wrapper
│   └── context_engine.py ← Static prompt template selection
├── routing/
│   ├── budget_controller.py ← Budget class assignment
│   ├── model_router.py  ← Cheap vs reasoning route selection
│   ├── admission_control.py ← Semaphore, queue depth
│   └── semantic_cache.py ← FAISS index, sentence-transformers
├── clients/
│   ├── vllm_client.py   ← OpenAI-compatible HTTP client
│   ├── guardrail_client.py ← HTTP client for guardrail service
│   └── verifier_client.py ← HTTP client for verifier service
├── escalation/
│   └── escalation_handler.py ← Retry at higher budget class
├── evaluation/
│   └── eval_worker.py   ← Background thread pool, SQLite writes
└── static/              ← Built React frontend
```

> NOTE: The Part IX repository structure shows a flatter layout for gateway/. See Section 31 (Source Document Conflicts) for this intra-document discrepancy.

### 6.3 Complete Request Processing Sequence

All 16 steps must be implemented in this exact order. Reordering requires an Architecture Deviation Protocol entry.

**Step 1 — Authentication (sync, <1ms)**
The auth middleware resolves the `Authorization` header API key against an in-memory dictionary loaded from `tenants.yaml` at startup. Unknown keys return 401 immediately. The resolved tenant ID is attached to the request state object and propagates to every subsequent step.

**Step 2 — Rate Limiting (sync, <1ms)**
The rate limiter checks two token buckets for the tenant: requests per minute and tokens per hour. Both buckets refill continuously using the token bucket algorithm. If either bucket is empty, the gateway returns 429:
```json
{
  "error": "rate_limit_exceeded",
  "limit_type": "requests_per_minute",
  "retry_after_seconds": 14,
  "tenant_id": "acme_corp",
  "policy_version": "enterprise_standard_v1"
}
```

**Step 3 — Trace Context Injection (sync, <1ms)**
A UUID request ID is generated. A W3C `traceparent` header is constructed from this ID and attached to the request state. All downstream log statements, span creations, and audit records reference this ID. A request that fails at any point produces a complete audit trail back to this origin.

**Step 4 — Pre-Inference Pipeline (sync, 50ms deadline)**
The pipeline orchestrator starts a deadline timer and runs three operations sequentially (each feeds the next):
1. Complexity scoring runs first — produces score used by policy for SLO class selection
2. Policy lookup
3. PII redaction runs last — modifies the prompt text that all subsequent components see

If cumulative time reaches 48ms before all three complete, the orchestrator cancels remaining operations and sets the **fast-path flag**. The request proceeds with default medium budget class and complexity score -1.

**Step 5 — Policy Lookup (sync, <1ms)**
The policy engine returns the versioned policy document for the tenant and domain. This is an in-memory dictionary lookup. The policy document contains all parameters for remaining steps: budget profiles, guardrail configuration, rate limits, cost ceilings, latency SLOs, escalation settings, and version identifiers.

**Step 6 — Budget Class Assignment (sync, <1ms)**
The budget controller maps complexity score to a budget class using the policy's budget profiles. It also assigns a priority tier by evaluating: complexity (reasoning demand), risk (configured in policy per domain), and scheduling pressure (current fleet queue depth). Priority tier governs scheduling preference under load, not answer quality budget.

**Step 7 — Decision Record Write (async, non-blocking)**
The policy engine writes the pre-inference decision record to the audit log. This write is **non-blocking** — the request does not wait. The record is queued to a background write thread. If the write queue is full (bounded at 1,000 entries), the write is dropped with a counter increment. Lost audit records are logged as a warning metric but do not block serving.

**Step 8 — Semantic Cache Lookup (sync, <5ms)**
The FAISS index is queried with the redacted prompt embedding. If cosine similarity exceeds the policy threshold, the cached response is returned immediately. The cache hit is recorded in the outcome record. No guardrail, no inference, no verification on a cache hit.

**Step 9 — Admission Control (sync, <1ms)**
The admission controller checks the current count of active reasoning model requests against the configured semaphore ceiling. For low-priority requests when the ceiling is reached, the request is queued with a configurable timeout. For high-priority requests, the timeout is extended. If the queue timeout is exceeded, the gateway returns 503.

**Step 10 — Guardrail Input Check (sync, network call)**
The gateway calls the guardrail service `/guardrail/input` endpoint with the redacted prompt and the tenant's guardrail configuration. The call has a **200ms timeout**. If the call times out, the gateway applies a conservative block and returns 503. If the call succeeds, the result is attached to the request state.

**Step 11 — Inference (sync, network call)**
The gateway calls the vLLM server's OpenAI-compatible endpoint with the request parameters including the budget class token ceiling and the registered LogitProcessor identifier. The call streams the response. The gateway buffers the stream and detects the stop reason from the completion metadata.

**Step 12 — Guardrail Output Check (sync or async based on policy)**
For high-risk policy domains: output check is synchronous — response is not delivered until safety check completes. For standard domains: output check runs asynchronously after response delivery and the result is written to the outcome record.

**Step 13 — Verification (sync, network call)**
If the policy requires verification for the assigned budget class, the gateway calls the verifier service with the response and the expected format or ground truth. A failed verification triggers escalation.

**Step 14 — Escalation (sync, conditional)**
If verification fails and the current budget class is not already at maximum, the gateway increments the escalation counter and repeats steps 9–13 at the next higher budget class. **Maximum one retry in the MVP.** All retry costs are attributed to the original request. If the retry also fails verification, the gateway returns the response with a `confidence_level: "low"` field added to the response body.

**Step 15 — Response Delivery**
The response is delivered to the client. Immediately after delivery, the outcome record is queued to the audit log write thread and the evaluation task is queued to the background evaluation worker.

**Step 16 — Async Evaluation (background, post-response)**
The evaluation worker thread picks up the task, calls the LLM-as-judge API (GPT-4o-mini) for non-verifiable responses, writes the result to SQLite, and updates the Prometheus quality metrics. This never blocks the response path.

---

## 7. API Contracts

### 7.1 POST /v1/infer
**Purpose:** Primary inference endpoint. Authenticated. Used by all client applications.

**Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "prompt": "string",
  "tenant_id": "string",          // redundant with API key; for audit
  "domain": "string",             // maps to policy selection
  "response_schema": "object",    // optional; triggers JSON verification
  "budget_override": "string",    // optional; "low"|"med"|"high"|"crit"
  "stream": "boolean"             // optional; default false
}
```

**Response Body:**
```json
{
  "response": "string",
  "request_id": "string",
  "budget_class": "string",
  "reasoning_tokens_used": "integer",
  "reasoning_tokens_allocated": "integer",
  "stop_reason": "string",
  "verification_result": "string",
  "escalation_count": "integer",
  "estimated_cost_usd": "float",
  "confidence_level": "string",    // "high"|"low"
  "latency_ms": "integer"
}
```

**Error responses:**
- 401: Unknown API key
- 429: Rate limit exceeded (structured body with retry_after_seconds)
- 503: Admission control timeout, guardrail timeout, or fallback model unavailable

### 7.2 GET /v1/health
**Purpose:** Health check. Used by Docker Compose health checks and System Health page.

### 7.3 GET /metrics
**Purpose:** Prometheus scrape endpoint. Exposes all `ic_` prefixed custom metrics plus vLLM native metrics.

### 7.4 GET /audit/records
**Purpose:** Audit log query endpoint. Used by the Audit Log Explorer frontend page.

### 7.5 GET /admin/policies
**Purpose:** Policy inspection endpoint. Used by the Policy Manager frontend page. Admin only.

### 7.6 POST /admin/inject-failure
**Purpose:** Demo mode only. Triggers a defined failure behavior for a single request. Visible only when `DEMO_MODE=true` environment variable is set. Used by the Failure Injection Panel.

---

## 8. Model Serving Contract

| Property | Value |
|----------|-------|
| Reasoning model | DeepSeek-R1-7B-Q4 |
| Cheap model | Qwen2.5-3B-Instruct |
| Serving infrastructure | Single vLLM instance, multi-model routing |
| Quantization | 4-bit (GPTQ or AWQ — tested in Week 1, best format committed) |
| GPU requirement | Single A100 80GB (or equivalent with sufficient KV-cache) |
| API compatibility | OpenAI-compatible HTTP API |
| Model selection | Gateway selects by passing model name in API call's model field |
| Raw prompt policy | vLLM never receives raw prompts — only redacted, policy-validated prompts from the gateway |
| Prometheus | vLLM native Prometheus endpoint consumed directly without renaming |

**Future implementation must not casually substitute models or serving infrastructure.** Any substitution requires the Architecture Deviation Protocol.

The gateway selects the model by budget class:
- `low` budget class → Qwen2.5-3B-Instruct (cheap route; `max_reasoning_tokens: 0`)
- `medium`, `high`, `critical` budget classes → DeepSeek-R1-7B-Q4 (reasoning route)

---

## 9. LogitProcessor Contract

> **The LogitProcessor is the single most important technical component in the system. It is validated before any other component is built. Its design is fixed without ambiguity.**

### 9.1 Purpose and Position
The LogitProcessor enforces per-request reasoning token budgets natively within vLLM's generation loop — without invasive PyTorch hooks, CUDA Graph disruption, or hidden-state extraction. It executes inside the vLLM generation step, running on every token generation.

### 9.2 Registration
The LogitProcessor is a Python class implementing vLLM's `LogitsProcessor` interface. It is instantiated per-request and passed to vLLM via the `SamplingParams.logits_processors` list. Each request gets its own `BudgetLogitProcessor` instance, which carries its own state. There is **no shared mutable state** between request instances.

### 9.3 State Per Instance
```python
@dataclass
class BudgetLogitProcessor:
    request_id: str
    max_reasoning_tokens: int
    end_of_thinking_token_id: int   # Model-specific; found in Week 1
    reasoning_complete: bool = False
    reasoning_token_count: int = 0
    entropy_log: list[float] = field(default_factory=list)
```

### 9.4 Per-Step Behavior (complete specification)
```python
def __call__(
    self,
    input_ids: torch.Tensor,
    scores: torch.Tensor
) -> torch.Tensor:

    if self.reasoning_complete:
        # Already transitioned to answer phase; no intervention
        return scores

    self.reasoning_token_count += 1

    # Log entropy for telemetry (monitoring only, not control)
    probs = torch.softmax(scores, dim=-1)
    top_k_probs = torch.topk(probs, k=20).values
    entropy = -torch.sum(
        top_k_probs * torch.log(top_k_probs + 1e-9)
    ).item()
    self.entropy_log.append(entropy)

    # Check if model emitted delimiter naturally
    last_token = input_ids[-1].item()
    if last_token == self.end_of_thinking_token_id:
        self.reasoning_complete = True
        return scores

    # Enforce budget ceiling
    if self.reasoning_token_count >= self.max_reasoning_tokens:
        # Force the end-of-thinking delimiter token
        scores[:] = -float('inf')
        scores[self.end_of_thinking_token_id] = 100.0
        self.reasoning_complete = True

    return scores
```

### 9.5 End-of-Thinking Token Identification
DeepSeek-R1-7B uses a specific token for `</think>`. The exact token ID is determined during Week 1:
```python
tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
end_token_id = tokenizer.convert_tokens_to_ids("</think>")
```
This token ID is stored as a constant in `vllm_adapter/constants.py` and imported by the LogitProcessor.

### 9.6 Validation Gate (Week 1 — Hard Gate)
Fifty diverse queries are run with forced delimiter injection at five different token positions: 25%, 50%, 75%, 100% of budget, and natural completion. For each, the response is scored for coherence and completeness using the LLM judge. If the coherence rate at any forced position falls below **85%**, the implementation falls back to hard `max_tokens` truncation.

**If this fallback is triggered:** The project does not proceed to Phase 2 with an unvalidated stopping mechanism. The fallback is documented as the implemented approach and the LogitProcessor is not used.

### 9.7 Entropy Telemetry
The entropy log accumulated per request is stored in the request's outcome metadata and written to the OpenTelemetry trace as a sampled array (every 10th value to limit trace size). This feeds `notebooks/entropy_signal_analysis.ipynb` that runs offline during Phase 5 to determine whether entropy-based adaptive early stopping is worth implementing as a future extension.

### 9.8 Concurrent Request Safety
Per-request state is cleaned up on request completion or abort. The processor handles concurrent requests correctly because each request carries its own counter and threshold keyed by request ID. Concurrent access to the counter dictionary is protected by a threading lock.

> **The LogitProcessor is an architecture-critical component and must be validated before dependent optimization layers are considered complete.**

---

## 10. Complexity Scoring Contract

### 10.1 Purpose
Produces a float complexity score from 0.0 to 10.0 from a text prompt in under 3ms on CPU. No ML model inference on the critical path. No network call. No external dependency.

### 10.2 Five Feature Groups

**Feature Group 1: Constraint Keyword Density**
Vocabulary partitioned into three tiers by cognitive weight:
- Tier 3 (weight 1.5 each): prove, derive, demonstrate that, show that, verify that, find all, for all, if and only if, necessary and sufficient
- Tier 2 (weight 1.0 each): compare, contrast, analyze, evaluate, explain why, step by step, what are the implications, both, unless, however, except when
- Tier 1 (weight 0.5 each): describe, summarize, list, what is, who, when, where
Score contribution: sum of (term count × tier weight), normalized to 0–3.

**Feature Group 2: Structural Signals**
- Question mark count (0 = 0, 3+ = 1.0), normalized
- Sentence count (0 = 0, 10+ = 1.0), normalized
- Bullet point or numbered list item count, normalized
- Explicit multi-step instruction pattern (regex: "first ... then ... finally" or "step 1", "step 2" etc.) as binary 0 or 1
Score contribution: weighted sum, normalized to 0–2.

**Feature Group 3: Technical Domain Signals**
- Code block presence (markdown triple backtick or four-space indent): binary 1.0
- Mathematical notation presence (LaTeX dollar signs, Greek letters, equation patterns): binary 1.0
- Formal logic notation (∀, ∃, →, ↔): binary 1.5
- JSON or XML structure present in prompt: binary 0.5
Score contribution: sum, capped at 2.0.

**Feature Group 4: Length Signal**
- Prompt token count estimated by character count divided by 4 (fast approximation)
- Short (<50 tokens): 0, Medium (50–200 tokens): 0.5, Long (200–500 tokens): 1.0, Very long (>500 tokens): 1.5
Score contribution: 0–1.5.

**Feature Group 5: Output Format Complexity**
- Request for structured output (JSON, table, numbered list, code): 0.5
- Request for multiple sections or headers: 0.5
- Request for a specific format with constraints: 1.0
Score contribution: 0–1.5.

### 10.3 Final Score Computation
```python
raw_score = (
    constraint_score    # 0-3.0
    + structural_score  # 0-2.0
    + domain_score      # 0-2.0
    + length_score      # 0-1.5
    + format_score      # 0-1.5
)
# raw_score range: 0-10
final_score = min(10.0, max(0.0, raw_score))
```

### 10.4 Calibration
During Week 1, natural completion token counts are collected for all benchmark queries. The feature weights are adjusted using a simple linear regression to minimize the mean absolute error between the scorer's budget class prediction and the budget class that would have been optimal given the observed token counts. This calibration is done **once, offline**, and the resulting weights are committed to the codebase.

### 10.5 Mapping to Budget Classes
From the policy schema:
- `complexity_score <= low_max (3.5)` → `low` class
- `complexity_score <= medium_max (6.5)` → `medium` class
- `complexity_score <= high_max (8.5)` → `high` class
- `complexity_score > 8.5` → `critical` class

### 10.6 Failure/Timeout Behavior
If the complexity scorer exceeds 5ms (detected by the pipeline deadline timer at 48ms), the orchestrator cancels remaining operations and sets the fast-path flag. The request proceeds with default medium budget class and complexity score -1.

---

## 11. Policy Engine Contract

### 11.1 Nature
The policy engine is a **Python library**, not a service. It is imported directly by the gateway and runs in-process.

### 11.2 Responsibilities
- Load and validate policies at startup
- Resolve the correct policy for a tenant and domain at request time
- Compute budget allocations
- Write audit records

### 11.3 Startup Validation
The policy loader calls `PolicyDocument.model_validate(yaml_data)` for each file at startup. Validation failure raises a startup exception with a field-level error message. **The gateway does not start with an invalid policy file.**

### 11.4 Policy Immutability and Versioning
Each policy file carries a monotonically increasing version integer. A loaded policy is never mutated in memory. When a new version is deployed, it is a new file with a new version number. The old version remains on disk for audit reference. **A policy update requires a gateway restart.**

### 11.5 Complete Policy Schema (canonical example: acme_corp_general_qa_v1.yaml)
```yaml
policy_id: enterprise_standard_v1
tenant: acme_corp
domain: general_qa
schema_version: 1

# — Budget Profiles ————————————————————————————————————
budget_profiles:
  low:
    model: qwen25-3b
    max_reasoning_tokens: 0          # No thinking; cheap model
    max_output_tokens: 256
    verification: none
    context_template: direct

  medium:
    model: deepseek-r1-7b
    max_reasoning_tokens: 512
    max_output_tokens: 512
    verification: verifiable_only
    context_template: step_by_step

  high:
    model: deepseek-r1-7b
    max_reasoning_tokens: 1024
    max_output_tokens: 1024
    verification: required
    context_template: verify_steps

  critical:
    model: deepseek-r1-7b
    max_reasoning_tokens: 2048
    max_output_tokens: 1024
    verification: required
    context_template: verify_steps

# — Complexity Thresholds ——————————————————————————————
complexity_thresholds:
  low_max: 3.5
  medium_max: 6.5
  high_max: 8.5
  # > 8.5 → critical

# — Guardrails ——————————————————————————————————————————
guardrails:
  pii_redaction: standard          # always; presidio
  injection_check: conditional     # only on tool_use domain
  safety_check: conditional        # only on policy-flagged domains
  output_safety: async             # "sync" for high-risk domains

# — Rate Limits ——————————————————————————————————————————
limits:
  requests_per_minute: 60
  tokens_per_hour: 500000
  max_cost_per_request_usd: 0.05
  max_prompt_tokens: 4096

# — SLOs ————————————————————————————————————————————————
slo:
  p95_latency_ms: 4000
  quality_floor_score: 3.5         # LLM judge score floor (1-5)
  quality_regression_pp: 1.0       # Max accuracy drop vs. baseline

# — Cache ————————————————————————————————————————————————
cache:
  enabled: true
  similarity_threshold: 0.92
  ttl_seconds: 3600

# — Escalation ————————————————————————————————————————————
escalation:
  enabled: true
  max_retries: 1
  on_exhaustion: return_low_confidence

# — Versions ——————————————————————————————————————————————
# Every component version that governs this policy is recorded.
# A quality regression is traceable to an exact version change.
versions:
  policy: 1
  system_prompt: prompt_v2
  complexity_scorer: scorer_v1
  guardrail_model: llamaguard_onnx_v1
  injection_model: deberta_inject_v1
  verifier: verifier_v1

# — Data Handling ————————————————————————————————————————
trace_retention_days: 30
store_reasoning_trace: false       # Never store raw chain-of-thought
```

---

## 12. Budget Controller Contract

### 12.1 Complete Budget Controller Logic (canonical specification)
```python
def assign_budget_class(
    complexity_score: float,
    policy: PolicyDocument,
    fleet_state: FleetState
) -> BudgetDecision:

    # Map complexity score to base class using policy thresholds
    if complexity_score <= policy.complexity_thresholds.low_max:
        base_class = "low"
    elif complexity_score <= policy.complexity_thresholds.medium_max:
        base_class = "medium"
    elif complexity_score <= policy.complexity_thresholds.high_max:
        base_class = "high"
    else:
        base_class = "critical"

    # Apply fleet pressure downgrade for non-critical requests
    # Priority is scheduling preference; it does not reduce quality budget
    if fleet_state.latency_cb_open and base_class != "critical":
        effective_class = downgrade_one(base_class)
        downgrade_reason = "latency_circuit_breaker"
    elif fleet_state.gpu_pressure_cb_open and base_class == "low":
        effective_class = "low"  # already cheap route; no change
        downgrade_reason = None
    else:
        effective_class = base_class
        downgrade_reason = None

    profile = policy.budget_profiles[effective_class]

    return BudgetDecision(
        base_class=base_class,
        effective_class=effective_class,
        downgrade_reason=downgrade_reason,
        model=profile.model,
        max_reasoning_tokens=profile.max_reasoning_tokens,
        max_output_tokens=profile.max_output_tokens,
        verification=profile.verification,
        context_template=profile.context_template,
    )
```

### 12.2 Conceptual Distinctions (do not merge these concepts)
| Concept | Definition |
|---------|------------|
| **Quality budget** | The reasoning token ceiling assigned by budget class — governs answer quality |
| **Scheduling priority** | Preference for queue position under load — does not change quality budget |
| **Cost ceiling** | Max USD per request from policy `limits.max_cost_per_request_usd` |
| **Latency SLO** | P95 latency target from policy `slo.p95_latency_ms` |

### 12.3 Four Budget Classes

| Class | Model | max_reasoning_tokens | max_output_tokens | Verification |
|-------|-------|---------------------|-------------------|--------------|
| low | Qwen2.5-3B-Instruct | 0 | 256 | none |
| medium | DeepSeek-R1-7B-Q4 | 512 | 512 | verifiable_only |
| high | DeepSeek-R1-7B-Q4 | 1024 | 1024 | required |
| critical | DeepSeek-R1-7B-Q4 | 2048 | 1024 | required |

---

## 13. Semantic Cache Contract

The semantic cache **avoids inference entirely** for requests with high semantic similarity to recent queries.

### 13.1 Implementation
- **Index:** FAISS `IndexFlatIP` (inner product similarity) — in-process, no external service
- **Embedding model:** `all-MiniLM-L6-v2` (22MB, CPU) — loaded at gateway startup, held in memory
- **Embedding time:** approximately 15ms on CPU per request
- **Similarity metric:** Cosine similarity (inner product on normalized vectors)
- **Default threshold:** 0.92 (configurable per policy via `cache.similarity_threshold`)

### 13.2 Cache Entry Structure
Each entry contains: response text, original request metadata, timestamp, and expiry timestamp computed from the policy TTL.

### 13.3 Cache Hit Path
If inner product similarity exceeds the policy threshold → return cached response immediately. No guardrail check. No inference. No verification. Record the cache hit in the outcome record.

### 13.4 Cache Miss Path
Proceed with full inference pipeline. After response delivery, store the new entry in the FAISS index and the Python dictionary.

### 13.5 Expiry and Persistence
- A background thread sweeps expired entries every **60 seconds** and removes them from both the FAISS index and the dictionary.
- The FAISS index is persisted to a file on a Docker volume every **5 minutes**. Gateway restart restores the index from the persisted file, preserving cache state across restarts.
- TTL is configured per policy (`cache.ttl_seconds: 3600` in the example).

### 13.6 Safety Restrictions
- The cache is **never used** when `policy.cache.enabled = false`.
- The cache is **never used** for requests that contain PII in the post-redaction prompt (logged as a warning; PII in prompts after redaction indicates a Presidio miss and should be investigated).
- High-risk policy domains set `cache.enabled: false` where content freshness or uniqueness is critical.

### 13.7 Telemetry
Cache hit rate, miss rate, and TTL expiration rate are tracked as labeled Prometheus counters. Labels include tenant ID and domain, enabling per-tenant cache effectiveness analysis on the Governance dashboard panel.

**No Redis. The semantic cache is in-process FAISS only.**

---

## 14. Guardrail Contract

### 14.1 Service Boundary
A separate FastAPI container running **exclusively on CPU**. Never touches the GPU. Never calls vLLM. Port 8001.

### 14.2 Container Isolation Rationale
Three reasons:
1. Guardrail models must not compete with inference models for GPU VRAM
2. A crashed guardrail container produces a defined conservative-block behavior in the gateway; a crashed vLLM container produces an inference outage — different failure modes
3. Independent Prometheus metrics for separate monitoring and capacity planning

### 14.3 Input Guardrails

**PII Redaction (always, in gateway, not guardrail service):**
- Implemented via Microsoft Presidio wrapper (`gateway/pipeline/pii_redactor.py`)
- Runs in the pre-inference pipeline before any downstream component sees the prompt text

**Injection Classifier:**
- Model: DeBERTa-v3-small fine-tuned for prompt injection detection, exported to ONNX with int8 quantization
- Input: prompt text up to 512 tokens
- Output: float risk score 0.0 to 1.0
- Inference time: approximately 30–50ms on CPU

**Safety Classifier (input):**
- Model: Llama Guard 3-1B variant exported to ONNX
- Input: prompt text
- Output: category label (safe/unsafe) and confidence score
- Inference time: approximately 80–120ms on CPU

### 14.4 Input Decision Logic
```python
# Injection decision
if injection_score > injection_threshold:
    result = "flag"
    action = augment_system_prompt
    # NOT block — false positive risk too high for enterprise workloads

# Safety decision
if safety_confidence > safety_threshold AND category != "safe":
    result = "block"
    action = return_structured_refusal
else:
    result = "pass"
```

### 14.5 Output Guardrail

**Safety Classifier (output):**
- Same Llama Guard 3-1B model
- Input: final answer text
- Decision:
  ```python
  if safety_confidence > safety_threshold AND category != "safe":
      result = "block"
      action = return_structured_refusal
  else:
      result = "pass"
  ```

### 14.6 Service Interface

**POST /guardrail/input**
```json
Request:
{
  "text": "string",              // redacted prompt
  "run_injection_check": "boolean",  // from policy
  "run_safety_check": "boolean",     // from policy
  "injection_threshold": "float",    // from policy
  "safety_threshold": "float"        // from policy
}

Response:
{
  "result": "pass" | "flag" | "block",
  "injection_score": "float",
  "safety_category": "string",
  "safety_confidence": "float",
  "latency_ms": "integer"
}
```

**POST /guardrail/output**
```json
Request:
{
  "text": "string",              // final answer text
  "run_safety_check": "boolean",
  "safety_threshold": "float"
}

Response:
{
  "result": "pass" | "block",
  "safety_category": "string",
  "safety_confidence": "float",
  "latency_ms": "integer"
}
```

**GET /health**
**GET /metrics**

### 14.7 Timeout Behavior
- Gateway sets a **200ms HTTP timeout** on all guardrail service calls
- **Input timeout** → conservative block: request is not processed, 503 returned to client, audit event logged
- **Output timeout** → non-blocking pass: response is delivered, check failure is logged as an audit event
- This asymmetry reflects the risk difference: it is safer to block an unverified input than to hold a completed response waiting for a check that may never complete.

### 14.8 Model Loading
Both ONNX models are loaded at container startup and held in memory for the process lifetime. The container fails startup if the volume mount is absent or the models cannot be parsed by ONNX Runtime.

---

## 15. Verifier Contract

### 15.1 Service Boundary
A separate FastAPI container running exclusively on CPU. Port 8002. Wraps official evaluation harnesses — **never implements verification logic from scratch**.

### 15.2 Service Interface

**POST /verify**
```json
Request:
{
  "response": "string",
  "verifier_type": "gsm8k" | "math" | "humaneval" | "json_schema" | "none",
  "ground_truth": "string",    // for gsm8k, math
  "test_cases": "string",      // for humaneval
  "entry_point": "string",     // for humaneval
  "schema": "object"           // for json_schema
}

Response:
{
  "passed": "boolean",
  "verifier_type": "string",
  "reason": "string",
  "predicted": "string",
  "expected": "string",
  "latency_ms": "integer"
}
```

**GET /health**
**GET /metrics**

### 15.3 Verification Implementations

**GSM8K Verifier:**
```python
def verify_gsm8k(response: str, ground_truth: str) -> VerificationResult:
    # Extract final number appearing after common answer-indication phrases
    pattern = r"(?:answer is|=|equals|result is|total is)?\s*([-\d,]+\.?\d*)\s*$"
    matches = re.findall(r"[-\d,]+\.?\d*", response)
    if not matches:
        return VerificationResult(passed=False, reason="no_number_found")
    predicted = float(matches[-1].replace(",", ""))
    expected = float(ground_truth.replace(",", ""))
    passed = abs(predicted - expected) < 1e-6
    return VerificationResult(
        passed=passed,
        predicted=str(predicted),
        expected=str(expected),
        reason="exact_match" if passed else "numeric_mismatch"
    )
```

**MATH-500 Verifier:**
- Extracts content within `\boxed{}` if present
- Attempts exact string match after normalization
- Falls back to SymPy symbolic equivalence: `sympy.simplify(expr_predicted - expr_expected) == 0`
- Returns `parse_failed` if SymPy cannot parse

**HumanEval Verifier:**
- Runs in a sandboxed subprocess with resource limits
- CPU time limit: 2 seconds
- Memory limit: 256MB
- No network access (via `os.setuid` to restricted user)
- Filesystem writes restricted to `/tmp`
- Uses `subprocess.run(["python", "-u", tmpfile], capture_output=True, timeout=2.0)`

**JSON Schema Verifier:**
- Uses Python's `jsonschema` library
- `json.loads(response)` → `jsonschema.validate(data, schema)`
- Returns `invalid_json` or `schema_violation` with error message on failure

### 15.4 Verifier Unavailability
Gateway handles with non-blocking default: return the response, mark verification as pending in the trace, log the verifier unavailability event. The platform does not block response delivery when the verifier is unreachable.

---

## 16. Escalation Contract

### 16.1 Flow
```
Initial request
→ Budget class assignment (e.g., medium)
→ Inference at medium (512 reasoning tokens)
→ Verification call
→ Verification FAILS
→ Policy-controlled escalation check (policy.escalation.enabled = true)
→ Escalation counter < max_retries (1 in MVP)
→ Increment escalation counter
→ Repeat from admission control at next higher budget class (high: 1024 tokens)
→ Inference at high
→ Verification PASSES → deliver response
OR
→ Verification FAILS again → max_retries exhausted
→ Return response with confidence_level: "low" added to response body
→ policy.escalation.on_exhaustion = "return_low_confidence"
```

### 16.2 Constraints
- **Maximum one retry in the MVP** (`escalation.max_retries: 1`)
- All retry costs (inference tokens, guardrail time, verifier time) are attributed to the **original request**
- Escalation count is recorded in both the outcome record and the response body
- The trace shows both inference spans with a clear escalation span between them
- The Playground UI shows both attempts in the trace waterfall with a distinct gap

### 16.3 Stop Reason Semantics
- `natural_boundary` — model reached `</think>` before budget ceiling
- `budget_exhausted` — LogitProcessor forced delimiter at budget ceiling
- `cache_hit` — response served from FAISS cache
- `fast_path_default` — pipeline deadline exceeded, default budget class used

---

## 17. Reliability Contract — Failure Mode Catalog

Ten failure modes. All defined before implementation begins. All implemented with explicit handlers. All testable via the Failure Injection Panel. All with observable behavior in frontend and audit log.

| # | Failure | Detection Mechanism | System Response | HTTP Effect | Trace Effect | Audit Effect | UI Effect |
|---|---------|---------------------|-----------------|-------------|--------------|--------------|-----------|
| 1 | Complexity scorer timeout (>5ms) | Deadline timer | Fast-path: assign medium budget class, score logged as -1 | None — request continues | Yellow "Fast Path" badge on Playground trace | fast_path_used: true in decision record | Yellow "Fast Path" badge on trace |
| 2 | LogitProcessor exception | Exception handler in processor | Disable adaptive stopping for this request; run to hard budget cap; log error span | None — request continues | Amber span; stop_reason = budget_exhausted | fallback_used: true in outcome | Amber span in trace waterfall |
| 3 | GPU utilization > 90% | Prometheus scrape every 5s (vllm:gpu_cache_usage_perc) | Open GPU pressure circuit breaker; reroute low-priority requests to cheap model | None — affects routing | Circuit breaker state change event in trace | CB state in audit records | Red circuit breaker indicator on Health page |
| 4 | P99 TTFT SLO breach | Prometheus histogram (P99 TTFT > SLO for 3 consecutive 30s windows) | Open latency circuit breaker; all new requests assigned one budget class lower | None — affects routing | CB state change event | CB state in audit records | Amber latency alert on Reliability tab |
| 5 | Input guardrail service timeout | Gateway HTTP client timeout (200ms) | Conservative block; 503 to client; audit event logged | 503 | Rose span in trace | Guardrail timeout event in Governance tab | Rose span in trace; error state in Playground |
| 6 | Output safety classification: unsafe | Safety classifier result | Structured refusal to client; audit event with reference ID | Structured refusal (200 with refusal body) | Rose span in trace | Audit event with reference ID | Rose response card in Playground; event in Audit Log |
| 7 | Policy engine cache miss (tenant unknown) | Key lookup miss | Load default policy; log audit event; serve request | None — uses default | Amber "Default Policy" badge in trace | Default policy use event | Amber "Default Policy" badge in trace |
| 8 | Rate limit exhausted | Token bucket empty | 429 to client with Retry-After; audit event | 429 | Error span | Rate limit event | Error state in Playground with countdown timer |
| 9 | Trace/metrics backend unavailable | OTLP export error | Buffer telemetry locally up to configured limit; retry; never block serving | None — transparent to client | None (buffered locally) | None | Warning indicator on Health page; no client-visible impact |
| 10 | Fallback model (cheap model) unavailable | Health check failure | 503 to client with retry window; audit event; alert | 503 | Error span | Fallback unavailability event | Error state in Playground; alert on Health page |

### Circuit Breaker Specifications

**GPU Pressure Circuit Breaker:**
- State: CLOSED | OPEN
- Metric: `vllm:gpu_cache_usage_perc` (scraped from vLLM Prometheus)
- Open condition: `gpu_cache_usage_perc > 90.0%` for **2 consecutive scrapes**
- Close condition: `gpu_cache_usage_perc < 80.0%` for **3 consecutive scrapes**
- Scrape interval: 5 seconds
- Effect when OPEN: Low-priority requests (`priority_tier == "low"`) are rerouted to cheap model regardless of budget class. High and standard priority requests are unaffected.

**Latency Circuit Breaker:**
- State: CLOSED | OPEN
- Metric: P99 TTFT from vLLM Prometheus histogram
- Open condition: P99 TTFT > `policy.slo.p95_latency_ms` for **3 consecutive evaluation windows** (window = 30 seconds)
- Close condition: P99 TTFT < `policy.slo.p95_latency_ms * 0.85` for **2 consecutive windows**
- Effect when OPEN: All new requests assigned one budget class lower. "low" class requests are rejected with 503 + retry guidance.

Both circuit breaker state transitions are emitted as OpenTelemetry span events and as Prometheus gauge changes. The frontend System Health page polls the gauge metrics every 10 seconds.

---

## 18. Observability Contract

### 18.1 OpenTelemetry Trace Schema
Every request produces one trace. The complete schema is defined in `telemetry/trace_schema.py` as a dataclass imported by all components. This guarantees consistency — no component invents its own field names.

```python
@dataclass
class RequestTrace:
    # Identity
    request_id: str
    trace_id: str
    tenant_id: str
    domain: str

    # Governance
    policy_id: str
    policy_version: int
    model_version: str
    prompt_version: str
    guardrail_version: str
    verifier_version: str
    complexity_scorer_version: str

    # Decision
    complexity_score: float
    fast_path_used: bool
    base_budget_class: str
    effective_budget_class: str
    downgrade_reason: Optional[str]
    priority_tier: str
    max_reasoning_tokens: int
    route: str
    cache_hit: bool
    admission_decision: str

    # Execution
    reasoning_tokens_used: int
    output_tokens: int
    tokens_saved: int
    stop_reason: str        # natural_boundary | budget_exhausted | cache_hit | fast_path_default
    escalation_count: int
    fallback_used: bool

    # Guardrails
    guardrail_input_result: str
    guardrail_input_ms: int
    guardrail_injection_score: float
    guardrail_output_result: str
    guardrail_output_ms: int

    # Verification
    verification_result: str
    verification_type: str
    verification_ms: int

    # Latency breakdown
    queue_ms: int
    prefill_ms: int
    decode_ms: int
    ttft_ms: int
    e2e_latency_ms: int

    # Cost
    estimated_cost_usd: float
    actual_cost_usd: float

    # Circuit breakers
    gpu_cb_state: str
    latency_cb_state: str

    # Entropy telemetry (sampled)
    entropy_samples: list[float]
```

### 18.2 Prometheus Metric Catalog
All custom metrics use the `ic_` prefix (InferaCordon). vLLM native metrics are consumed directly without renaming.

**Cost metrics:**
```
ic_request_cost_usd{tenant, budget_class, route}           histogram
ic_tokens_reasoning_used{tenant, budget_class}             histogram
ic_tokens_reasoning_saved{tenant, budget_class}            histogram
ic_cost_per_correct_answer{tenant, task_class}             gauge (updated by eval worker)
ic_cache_hits_total{tenant}                                counter
ic_cache_misses_total{tenant}                              counter
```

**Quality metrics (from eval worker):**
```
ic_verification_pass_rate{tenant, budget_class, verifier_type}  gauge
ic_llm_judge_score_avg{tenant, domain}                          gauge
ic_escalation_rate{tenant, budget_class}                        gauge
```

**Reliability metrics:**
```
ic_circuit_breaker_state{type}                     gauge (0=closed, 1=open)
ic_admission_control_queue_depth                   gauge
ic_admission_control_rejections_total{tenant}      counter
ic_guardrail_timeout_total{direction}              counter
ic_rate_limit_hits_total{tenant, limit_type}       counter
```

**Performance metrics:**
```
ic_fast_path_activations_total                     counter
ic_audit_write_queue_depth                         gauge
ic_audit_records_dropped_total                     counter
```

### 18.3 Observability Component Roles

| System | Role | Port |
|--------|------|------|
| OpenTelemetry | Trace instrumentation; W3C traceparent propagation | (library) |
| Jaeger | Trace collection via OTLP; trace inspection UI | 16686 |
| Prometheus | Metrics scraping and storage | 9090 |
| Grafana | Unified dashboard (5 panels: Cost, Quality, Reliability, Performance, Governance) | 3000 |
| SQLite | LLM-as-judge evaluation results (not traces, not audit) | (file) |
| Audit Log | Append-only JSONL governance records (not operational logs, not traces) | (file on volume) |

### 18.4 Critical Distinctions (do not merge these)
- **Audit records** — governance artifact; append-only JSONL; decision + outcome per request; never contains raw prompt text; persisted to Docker volume
- **Operational logs** — standard stderr/stdout logs from each service
- **Telemetry traces** — OpenTelemetry spans; exported to Jaeger via OTLP
- **Benchmark/evaluation records** — LLM judge scores; stored in SQLite; feed Grafana quality panel

### 18.5 Telemetry Buffering
When the OTLP backend is unavailable: buffer telemetry locally up to a configured limit, retry, never block serving. This is Failure Mode #9.

---

## 19. Audit/Governance Contract

Two records per request. Written to separate append-only JSONL files. Never overwritten. Never deleted within the retention window. Never store raw prompt or response text by default — only derived signals, counts, and outcomes.

### 19.1 Decision Record (written before inference begins)
```json
{
  "record_type": "decision",
  "timestamp_iso": "2026-08-09T10:42:11.334Z",
  "request_id": "req_8c4f2a",
  "tenant_id": "acme_corp",
  "domain": "general_qa",
  "policy_id": "enterprise_standard_v1",
  "policy_version": 1,
  "model_version": "deepseek-r1-7b-q4",
  "prompt_version": "prompt_v2",
  "guardrail_version": "llamaguard_onnx_v1",
  "verifier_version": "verifier_v1",
  "complexity_score": 6.4,
  "fast_path_used": false,
  "base_budget_class": "medium",
  "effective_budget_class": "medium",
  "downgrade_reason": null,
  "priority_tier": "standard",
  "max_reasoning_tokens": 512,
  "max_output_tokens": 512,
  "route": "reasoning_model",
  "cache_hit": false,
  "admission_result": "pass",
  "estimated_cost_usd": 0.0062
}
```

### 19.2 Outcome Record (written after response delivery)
```json
{
  "record_type": "outcome",
  "timestamp_iso": "2026-08-09T10:42:12.501Z",
  "request_id": "req_8c4f2a",
  "reasoning_tokens_used": 341,
  "reasoning_tokens_allocated": 512,
  "tokens_saved": 171,
  "output_tokens": 203,
  "stop_reason": "natural_boundary",
  "escalation_count": 0,
  "fallback_used": false,
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
  "circuit_breaker_state_at_completion": "closed"
}
```

### 19.3 Audit Behavioral Rules
- The decision record exists even if inference subsequently fails — it is the pre-inference governance artifact
- The outcome record references the decision record by `request_id`
- Both records are queued to a background write thread (write queue bounded at 1,000 entries)
- If the write queue is full, the write is dropped with a counter increment (logged as warning metric)
- Persisted to a Docker volume; survives container restarts
- Served via `GET /audit/records` by the gateway for the Audit Log Explorer

---

## 20. Evaluation Contract

### 20.1 Primary Metric
**Cost per correct answer.** This is the only metric that simultaneously reflects inference cost, controller overhead, verification overhead, and answer quality.

```
C_online = (model inference cost
          + guardrail service cost
          + verification cost
          + serving overhead)
          / number of answers meeting quality threshold

C_total = C_online
        + async evaluation cost
        + telemetry and storage cost
```

Both metrics are computed and reported separately. Async evaluation cost is not charged to the online serving metric because it does not block the response path.

### 20.2 Six Baselines (evaluated in this order before any optimization is enabled)

| Baseline | Description |
|----------|-------------|
| 1 | Natural completion with no budget control, no routing, no stopping |
| 2 | Fixed low budget (25th percentile of natural completion token usage) |
| 3 | Fixed medium budget (50th percentile) |
| 4 | Policy-selected budget class with no adaptive stopping and no escalation |
| 5 | Policy-selected budget class with escalation but no LogitProcessor stopping |
| 6 | Full InferaCordon with routing, LogitProcessor stopping, escalation, circuit breakers, and semantic cache |

The adaptive system must improve upon the fixed medium budget baseline (Baseline 3) to justify its existence.

### 20.3 Datasets

| Dataset | Size | Verification | Notes |
|---------|------|--------------|-------|
| GSM8K | 100 examples | Exact-match numerical | Ground truth available. No LLM judge. |
| MATH-500 | 100 examples | Normalized symbolic (SymPy fallback) | Ground truth available. No LLM judge. |
| HumanEval | 50 examples | Sandboxed test runner, Pass@1 | No LLM judge. |
| Enterprise Synthetic | 200 examples | LLM judge (one quality signal), 10% human-reviewed to calibrate judge bias | Covers: summarization, structured JSON extraction, multi-constraint reasoning, long-context analysis, ambiguous instruction handling, unanswerable question handling, schema compliance |
| Adversarial | 50 examples | Correct system behavior (block/log/escalate/fallback), not answer quality | Prompt injection attempts, PII in prompts, pathological long inputs, schema violation attempts, requests designed to trigger each of the ten failure modes |

### 20.4 Ablation Study
The ablation study is the portfolio's strongest analytical artifact. It isolates the contribution of each component.

| Layer | Metric Measured |
|-------|----------------|
| Natural completion (no control) | C_online baseline |
| Fixed medium budget | Δ tokens, Δ quality |
| Policy routing only (no stopping) | Δ cost per correct answer |
| Policy routing + complexity scoring | Δ cost per correct answer |
| Policy routing + stopping (LogitProcessor) | Δ cost per correct answer |
| Above + verification escalation | Δ cost per correct answer |
| Above + semantic cache | Δ cost per correct answer |
| Full InferaCordon | Final Δ cost per correct answer |

Each layer's contribution is reported as the marginal improvement it adds over the previous layer. **Components that do not improve the primary metric are documented honestly.** A disciplined negative result is stronger portfolio evidence than an undifferentiated positive result.

### 20.5 Quality Regression Gate
The regression gate enforces a non-inferiority constraint. Any configuration change that causes:
- Accuracy to fall more than **1 percentage point** on verifiable tasks (GSM8K, MATH-500, HumanEval)
- Accuracy to fall more than **2 percentage points** on the enterprise synthetic set

...fails the gate and blocks deployment. The gate evaluates **per-slice accuracy across task categories**, not only aggregate averages.

### 20.6 Portfolio Targets (targets, NOT achieved results — never publish until measured)

| Metric | Target |
|--------|--------|
| Cost per correct answer improvement | ≥15% versus fixed medium budget baseline |
| Reasoning token reduction | 15–30% versus natural completion |
| Verifiable task accuracy regression | No more than 1 percentage point versus natural completion |
| P95 latency | No worse than natural completion; target 10% improvement |
| Controller overhead | 5% or less of end-to-end request latency |
| Policy violation rate | Zero in all tested scenarios |
| Trace completeness | 99% or higher across all requests |
| Fallback success rate | 99% or higher under fault injection across all ten failure modes |

**IMPORTANT:** Targets are targets. They are NOT implementation results. Never put target numbers into README as achieved results. README metrics come from `evaluation/benchmark_harness.py` and `evaluation/update_readme_metrics.py`.

---

## 21. Load Testing Contract

**Required RPS levels:** 10, 50, and 100 RPS

**Tool:** Locust (`load_testing/locustfile.py` with `load_testing/workload_profiles.py`)

**Hardware configuration requirement:** Document exactly the hardware configuration (GPU model, CPU, RAM) alongside all reported load test results. Do not claim scalability beyond measured results.

**Metrics to capture:** Latency (P50, P95, P99), throughput, error rate, GPU utilization, KV-cache utilization, queue depth

**Capacity profiling:** Document the capacity profile — at what RPS does latency SLO break? At what RPS does GPU KV-cache saturate?

---

## 22. Frontend Contract

### 22.1 Design Language
- **Visual theme:** Dark theme. Premium internal tooling aesthetic.
- **Base background:** `#0D1117` (deep charcoal-black)
- **Surface cards:** `#161B22` (slate)
- **Border color:** `#21262D` (subtle)
- **Primary accent:** `#6366F1` (deep indigo)
- **Secondary accent:** `#818CF8` (softer indigo)
- **Text primary:** `#F0F6FC`
- **Text secondary:** `#8B949E`
- **Status emerald:** `#10B981` (healthy, pass, closed)
- **Status amber:** `#F59E0B` (warning, degraded, escalated)
- **Status rose:** `#EF4444` (error, blocked, open)
- **Typography:** Inter for all UI text (weights 400, 500, 600). JetBrains Mono for all metric values, token counts, cost figures, latency readings, version identifiers, JSON data, and trace span labels.
- **Spatial system:** 8px base grid. Card border-radius 8px. Card border 1px solid `#21262D`. Card shadow `0 1px 3px rgba(0,0,0,0.4)`. Focused/active element glow `0 4px 16px rgba(99,102,241,0.15)`. Sidebar width 240px. Content area full remaining width. Transitions 150ms ease-out.
- **Navigation:** Left sidebar with InferaCordon wordmark at top, five navigation items with icons and labels. Small status indicator at the bottom showing health state of all backend services (green when all operational, amber when any degraded, red when any down).

### 22.2 Page 1: Inference Playground
**Purpose:** Primary interactive surface for live demos. Split horizontally: left panel 60% (request interface and response), right panel 40% (live trace).

**Left panel — Request interface:** Prompt textarea with soft indigo focus ring, token count estimate in JetBrains Mono. Below textarea: tenant selector dropdown, domain selector. Settings row: manual budget class override toggle (off by default, tooltip: "let the platform decide"), verification toggle, estimated cost ceiling derived from current policy.

**Left panel — Stage progress:** On submission, compact animated stage tracker showing: Complexity Scoring → Policy Lookup → Guardrail Check → Inference → Verification → Response. Completed stages show actual measured latency in JetBrains Mono in accent color. Active stage shows pulse animation. Failed stages show in rose.

**Left panel — Response area:** Final answer in formatted markdown. Below: metrics strip showing seven values in a row: Budget Class used (colored pill: emerald=low, indigo=medium, amber=high, rose=critical), Reasoning Tokens (used/allocated), Stop Reason, Verification Result, Escalation Count, Total Cost USD, End-to-End Latency ms. All numeric values in JetBrains Mono.

**Right panel — Trace waterfall:** Horizontal span bars on a timeline as pipeline stages complete. Span colors by component: indigo=gateway, slate=policy engine, cyan=complexity scorer, emerald=successful guardrail, amber=flagged guardrail, rose=circuit breaker open, violet=inference, teal=verifier. Each span shows label and duration. Hovering reveals tooltip with full attribute set. Escalation event shows as distinct gap and repeat of inference+verifier spans.

**Right panel — Raw trace:** Collapsible panel below the waterfall shows complete JSON trace record in syntax-highlighted code viewer.

### 22.3 Page 2: Observability Dashboard
**Purpose:** Five tab panels pulling live data from Prometheus API and SQLite evaluation database. Rendered with Recharts. This page means the portfolio demo does not require Grafana to be open.

**Cost tab:** Time-series line chart of cost per request by budget class over the last hour. Large-format metric card showing current cost per correct answer in JetBrains Mono with delta versus natural completion baseline in colored badge (green=improvement, red=regression). Donut chart of cache hit rate. Horizontal bar chart of token savings per request by budget class.

**Quality tab:** Stacked bar chart of verification pass/fail/escalation rates by task class. Line chart of rolling LLM judge score average over 24 hours with policy-configured quality floor as dashed reference line. Table of last 20 evaluation results.

**Reliability tab:** Three large colored state indicators (GPU Pressure CB, Latency CB, Admission Control) with time since last state transition and current metric value. Sparkline of P95 end-to-end latency over 30 minutes. Gauge of current queue depth versus admission control ceiling. Table of last 10 circuit breaker state transition events.

**Performance tab:** GPU utilization as live gauge updating every 5 seconds. KV-cache utilization as second live gauge. Line chart of decode throughput in tokens/second over the last hour. Histogram of TTFT distribution with P50, P95, P99 markers. Fast-path circuit breaker activation rate as small metric card.

**Governance tab:** Table showing active policy version for each registered tenant with timestamp of last policy change and link to policy diff view. Chronological event log of governance events from the last hour: budget class overrides, guardrail blocks, fast-path activations, circuit breaker transitions, rate limit hits, admission control rejections. Bar chart of budget class distribution across today's total traffic.

### 22.4 Page 3: Policy Manager
**Purpose:** Read-only view of all loaded policies. Governance is only credible when humans can read the policies governing the system.

Each policy rendered as a structured card with four collapsible sections: Budget Profiles (model, token ceilings, verification requirement), Guardrail Configuration, Rate Limits and Cost Ceilings, Version Identifiers.

Version diff panel: Structural changes between current and previous version as two-column diff (additions in emerald, removals in rose).

Policy validation panel: Raw YAML input in code editor with syntax highlighting. Real-time validation against the Pydantic schema — shows success summary or structured error list with field names, expected types, and violation descriptions. **This panel is for inspection and testing — it does not deploy policies.**

### 22.5 Page 4: Audit Log Explorer
**Purpose:** Full-featured explorer for the audit log JSONL file. The compliance showcase.

Table columns: timestamp, tenant ID, request ID, budget class (colored pill), route, stop reason, reasoning tokens used/allocated, verification result, escalation count, estimated cost. All timestamp and cost values in JetBrains Mono.

Filter bar: Dropdowns for tenant, budget class, stop reason, verification result, escalation count, plus date range picker. Search field filters by request ID or prompt hash prefix.

Selecting a row expands an inline detail panel: complete decision record JSON, complete outcome record JSON, linked trace ID with click-through to Jaeger trace view, linked evaluation result from SQLite if available, policy version that governed the request with link to Policy Manager view for that version.

### 22.6 Page 5: System Health
**Purpose:** Live status page for all components. Updated every 10 seconds.

Five component cards: Gateway, vLLM Serving Layer, Guardrail Service, Verifier Service, Evaluation Worker. Each card: large status indicator (Operational=emerald, Degraded=amber, Down=rose), component version, current request rate, error rate over last 5 minutes, P95 latency, last three alerts.

Circuit breaker state: Dedicated indicator pair (GPU Pressure, Latency) with current metric values and timestamp of last state transition.

**Failure Injection Panel:** Visible only when `DEMO_MODE=true` environment variable is set. Ten buttons, one per defined failure mode. Each button sends a test request to `POST /admin/inject-failure` that triggers the defined failure behavior for a single request and streams the result — including the system's response — back to the UI in real time.

**Do not create fake data.** All metrics come from Prometheus or the gateway API. If a service is unreachable, show the Down status, not simulated data.

---

## 23. Demo Contract

The five-minute live demo must be recorded in Weeks 13–14. It must demonstrate all four pillars with concrete, visible, interactive behavior.

### Demo Flow

**Segment 1: Overthinking Suppression (~1 min)**
- Trigger: Send a simple factual query in Playground (e.g., "What is the capital of France?")
- Expected backend: Complexity score 1.8 → low budget class → Qwen2.5-3B → 0 reasoning tokens
- Send same category query type with budget override: medium → DeepSeek-R1-7B → LogitProcessor shows budget ceiling being approached; stop_reason: natural_boundary with tokens_saved visible
- Expected trace: Inference span shows reasoning token progress in real time
- Expected UI: Metrics strip shows Reasoning Tokens (used/allocated), Stop Reason, budget class colored pill

**Segment 2: Underthinking Prevention / Escalation (~1 min)**
- Trigger: Send a complex multi-constraint reasoning query requiring JSON output matching a provided schema
- Expected backend: Complexity score → medium class → inference → JSON schema verifier FAILS → escalation triggered → high class → inference → verifier PASSES
- Expected trace: Two inference spans with escalation gap visible in waterfall; escalation_count: 1 in metrics strip; confidence_level: high in response
- Expected audit: Decision record + outcome record with escalation_count: 1

**Segment 3: Governance (Policy Manager + Audit Log) (~1 min)**
- Trigger: Navigate to Policy Manager
- Expected UI: Show versioned policy for acme_corp with all budget profiles, complexity thresholds, version identifiers
- Navigate to Audit Log Explorer
- Show audit records from previous two demo requests with decision + outcome records, linked trace IDs, policy versions
- Expected outcome: Demonstrate "why did the platform make this decision at this time" is answerable from the audit log

**Segment 4: Circuit Breaker Activation (~1 min)**
- Trigger: Use Failure Injection Panel (DEMO_MODE=true) to trigger GPU pressure failure (Failure Mode #3)
- Expected backend: GPU pressure circuit breaker opens; low-priority requests rerouted to cheap model
- Expected trace: Circuit breaker state change event visible
- Expected UI: System Health page shows red circuit breaker indicator; Reliability tab shows state transition in table

**Segment 5: Audit Log Inspection + Cost Summary (~1 min)**
- Trigger: Navigate to Observability Dashboard → Cost tab
- Expected UI: Cost per correct answer metric card showing delta versus natural completion baseline; cache hit rate donut; token savings bar chart
- All values populated from benchmark harness — no hand-written numbers

---

## 24. Repository Structure

Extracted from Part IX of the Architecture Plan. This is authoritative. Do not rename directories, move responsibilities, or create alternative layouts.

```
inferacordon/
├── docker-compose.yml                  ← One command: docker compose up
├── .env.example
├── README.md                           ← Auto-updated with measured metrics
├── architecture.md
│
├── gateway/
│   ├── main.py
│   ├── auth.py
│   ├── rate_limiter.py
│   ├── trace_context.py
│   ├── pre_inference_pipeline.py
│   ├── complexity_scorer.py
│   ├── semantic_cache.py
│   ├── context_engine.py
│   ├── admission_control.py
│   └── async_eval_worker.py
│
├── policy_engine/
│   ├── loader.py
│   ├── validator.py
│   ├── budget_controller.py
│   ├── audit_log.py
│   └── policies/
│       ├── acme_corp_general_qa_v1.yaml
│       └── demo_tenant_v1.yaml
│
├── vllm_adapter/
│   ├── logit_processor.py
│   ├── circuit_breakers.py
│   └── serving_config.py
│
├── guardrail_service/
│   ├── main.py
│   ├── injection_classifier.py
│   ├── safety_classifier.py
│   └── models/
│
├── verifier_service/
│   ├── main.py
│   ├── gsm8k_verifier.py
│   ├── math_verifier.py
│   ├── humaneval_runner.py
│   └── schema_verifier.py
│
├── telemetry/
│   ├── otel_config.py
│   ├── prometheus_metrics.py
│   └── trace_schema.py
│
├── evaluation/
│   ├── benchmark_harness.py
│   ├── ablation_runner.py
│   ├── regression_gate.py
│   ├── llm_judge.py
│   └── update_readme_metrics.py
│
├── load_testing/
│   ├── locustfile.py
│   └── workload_profiles.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── failure_injection/
│
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── Playground.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── PolicyManager.jsx
│   │   │   ├── AuditLog.jsx
│   │   │   └── SystemHealth.jsx
│   │   ├── components/
│   │   │   ├── TraceWaterfall.jsx
│   │   │   ├── MetricsStrip.jsx
│   │   │   ├── CircuitBreakerIndicator.jsx
│   │   │   ├── PolicyCard.jsx
│   │   │   └── FailureInjectionPanel.jsx
│   │   └── lib/
│   │       ├── api.js
│   │       └── prometheus.js
│   └── dist/
│
├── dashboards/
│   └── grafana/
│       └── inferacordon_unified.json
│
└── notebooks/
    └── entropy_signal_analysis.ipynb
```

> **NOTE:** The Component 1 "Internal Module Structure" section of the Architecture Plan shows a nested gateway layout with subdirectories (`middleware/`, `pipeline/`, `routing/`, `clients/`, `escalation/`, `evaluation/`). The Part IX "Repository Structure" section shows a flat gateway layout. See Section 31 (Source Document Conflicts) for full documentation of this intra-document discrepancy. Future implementation must resolve this before creating the gateway files.

---

## 25. Technology Rules

| Area | Required Technology | Forbidden or Unspecified Alternatives |
|------|---------------------|--------------------------------------|
| Gateway framework | FastAPI (Python) | Flask, Django, Express — not specified |
| Inference server | vLLM (single instance, multi-model) | TGI, LMDeploy, separate instances per model |
| Reasoning model | DeepSeek-R1-7B-Q4 | Any other reasoning model |
| Cheap model | Qwen2.5-3B-Instruct | Any other cheap model |
| Quantization | 4-bit GPTQ or AWQ (tested in Week 1) | 8-bit or full precision (insufficient VRAM) |
| Semantic cache index | FAISS IndexFlatIP (in-process) | External FAISS server, Redis, Milvus |
| Semantic embeddings | all-MiniLM-L6-v2 (22MB) | Other embedding models (deviation requires documentation) |
| PII redaction | Microsoft Presidio | Other PII tools |
| Guardrail models | ONNX Runtime (DeBERTa int8 + Llama Guard 3-1B) | GPU-based guardrail models |
| Policy format | YAML + Pydantic validation | JSON-only, database-backed policies |
| Observability traces | OpenTelemetry + W3C traceparent + Jaeger (OTLP) | Zipkin, proprietary tracing |
| Metrics | Prometheus (ic_ prefix convention) | StatsD, DataDog agent |
| Dashboard | Grafana (pre-configured JSON committed to repository) | Custom dashboard services |
| Evaluation storage | SQLite (LLM judge results only) | PostgreSQL, MySQL |
| Audit log format | Append-only JSONL file on Docker volume | Database-backed audit, mutable logs |
| Async eval | Background thread pool in gateway | Celery, Redis queue, separate worker container |
| Task queue for eval | None (thread pool) | Redis, Celery — explicitly excluded |
| MATH verification | SymPy | Custom symbolic computation |
| HumanEval execution | Sandboxed subprocess | Direct exec, no resource limits |
| Frontend framework | React (SPA, served as static files by gateway) | Vue, Angular, separate server |
| Frontend charts | Recharts | D3.js, Chart.js (deviation requires documentation) |
| Container orchestration | Docker Compose | Kubernetes, Nomad |
| LLM-as-judge | GPT-4o-mini (from MVP Documentation) | Other judge models (deviation requires documentation) |

---

## 26. Testing Philosophy

### 26.1 Test Categories

| Category | Location | Purpose |
|----------|----------|---------|
| Unit tests | `tests/unit/` | Individual function correctness; LogitProcessor logic; complexity scorer feature groups; policy validation; verifier parsers |
| Integration tests | `tests/integration/` | Gateway request lifecycle; guardrail service calls; verifier service calls; audit log writes; cache hit/miss paths |
| Failure injection tests | `tests/failure_injection/` | All ten failure modes; each produces documented system response and correct audit log event |
| Benchmark tests | `evaluation/benchmark_harness.py` | All six baselines across all five datasets |
| Ablation tests | `evaluation/ablation_runner.py` | Seven-layer ablation sequence |
| Regression gate | `evaluation/regression_gate.py` | Per-slice accuracy gating; blocks deployment on regression |
| Load tests | `load_testing/locustfile.py` | 10, 50, 100 RPS with documented hardware configuration |
| Frontend E2E | `tests/` (to be determined) | Five pages; Failure Injection Panel behavior; demo flow |

### 26.2 Validation Gates by Component

| Component | Validation Gate |
|-----------|----------------|
| LogitProcessor | 50 queries × 5 forced positions; coherence rate ≥85% at every forced position |
| Guardrail Service | Tested before touching production traffic |
| Each failure mode | Tested via failure injection before demo recording |
| README metrics | Produced by `update_readme_metrics.py` after each benchmark run |

> **No component is considered complete merely because it runs. It must satisfy its documented validation requirements.**

---

## 27. Benchmark Integrity Rules

1. **Never fabricate metrics.** If a benchmark has not run, the metric does not exist.
2. **Never manually invent benchmark numbers.** All README numbers come from `evaluation/update_readme_metrics.py`.
3. **Never claim optimization without comparison.** Every improvement claim cites the specific baseline it outperforms.
4. **Never hide negative ablation results.** A component that does not improve the primary metric is documented as a non-contributor, not omitted.
5. **Never use aggregate quality alone** when the architecture requires per-slice evaluation (it does).
6. **README metrics must come from benchmark scripts.** The README lead statement template uses `[X]%`, `[Y]%`, `[Z]%`, `[W]%`, `[C]%` placeholders that are filled by `update_readme_metrics.py`.
7. **Clearly distinguish target metrics from achieved metrics.** Section 20.6 contains targets. Achieved metrics appear only after measurement.
8. **Record hardware and configuration alongside results.** Every benchmark report includes GPU model, CPU, RAM, vLLM version, quantization format, and active policy version.

---

## 28. Architecture Deviation Protocol

This section is mandatory. If any future Claude Code session believes a documented architecture decision should change:

**DO NOT silently change it.**

Instead, follow this protocol:

1. **Identify** the specific Architecture Plan requirement that is blocked or incompatible (cite section and page reference).
2. **Explain** precisely why the documented approach cannot be implemented as specified (technical blocker, missing dependency, version incompatibility).
3. **Propose** the smallest possible deviation that preserves the intent of the original design.
4. **Record** the proposed deviation, the original requirement, and the rationale.
5. **Stop** and wait for explicit approval before permanently changing the architecture.

**For normal implementation difficulties:** prefer implementing the documented fallback rather than redesigning the architecture. The LogitProcessor fallback (hard max_tokens truncation) is an example of a documented fallback that should be implemented if the validation gate fails.

---

## 29. Implementation Phase Rules

Future Claude Code sessions will receive phase-specific prompts. For every future phase:

1. **Read `CLAUDE.md`** before doing anything else.
2. **Inspect the existing repository** to understand what has already been implemented.
3. **Inspect relevant source documents** if clarification is needed.
4. **Implement only the requested phase.** Do not implement components from future phases.
5. **Preserve all previous contracts.** Do not refactor earlier phases unless explicitly instructed.
6. **Run tests** after implementation.
7. **Run relevant validation** gates (see Section 26).
8. **Report failures honestly.** Do not paper over failing tests.
9. **Do not jump ahead** into unrelated phases.
10. **Do not refactor** unrelated architecture.

### Implementation Roadmap Reference

| Weeks | Phase | Key Deliverables |
|-------|-------|-----------------|
| 1–2 | Baseline and Core Validation | vLLM up with both models; LogitProcessor validated; six baselines on GSM8K/MATH-500/HumanEval; skeleton gateway; complexity scorer calibrated |
| 3–4 | Policy Engine and Budget Controller | YAML policy engine; audit log; rate limiter; admission control; fast-path circuit breaker; semantic cache; static prompt rewriting; baseline eval with policy routing |
| 5–6 | Guardrails and Verifier | Guardrail service container; PII redaction; output guardrail; verifier service container; verification-triggered escalation; ablation through escalation layer |
| 7–8 | Reliability Layer | GPU + latency circuit breakers; all ten failure mode handlers; fault injection tests; telemetry buffering; load tests at 10/50/100 RPS |
| 9–10 | Complete Observability | Full OTel trace schema; Jaeger; Grafana unified dashboard; async eval worker; SQLite; LLM judge; full benchmark suite |
| 11–12 | Frontend | Five-page React app; all API integrations; Prometheus queries; Failure Injection Panel; end-to-end demo scenario testing |
| 13–14 | Portfolio Packaging | Technical design document; five-minute demo video; repository packaging; architecture diagrams; portfolio case study; final benchmark run via `update_readme_metrics.py` |

---

## 30. Definition of Done

A **component** is complete only when:
- [ ] Implementation exists
- [ ] Documented API contract is respected (exact field names, error codes, response schema)
- [ ] Tests exist (unit and/or integration as appropriate)
- [ ] Tests pass
- [ ] Required validation gate passes (see Section 26)
- [ ] Observability exists where specified (Prometheus metrics, OTel spans)
- [ ] Audit behavior exists where specified (decision/outcome records)
- [ ] All ten failure modes handled where component is involved
- [ ] No undocumented architectural deviation exists

The **complete MVP** is finished only when:
- [ ] All four pillars are demonstrable in the five-minute live demo
- [ ] All six baselines are evaluated and reported
- [ ] Full ablation sequence is run and reported
- [ ] Quality regression gate passes
- [ ] Load tests at 10, 50, 100 RPS are completed with documented hardware
- [ ] All ten failure modes are tested via failure injection
- [ ] `update_readme_metrics.py` has run and populated README with measured results
- [ ] No hand-written metric appears in README

---

## 31. Source Document Conflicts

### CONFLICT 1: Gateway directory layout (intra-document, within Architecture Plan)

**Architecture Plan Component 1 "Internal Module Structure"** shows a nested gateway directory:
```
gateway/
├── middleware/  (auth.py, rate_limiter.py, trace_injector.py)
├── pipeline/   (orchestrator.py, complexity_scorer.py, pii_redactor.py, context_engine.py)
├── routing/    (budget_controller.py, model_router.py, admission_control.py, semantic_cache.py)
├── clients/    (vllm_client.py, guardrail_client.py, verifier_client.py)
├── escalation/ (escalation_handler.py)
└── evaluation/ (eval_worker.py)
```

**Architecture Plan Part IX "Repository Structure"** shows a flat gateway directory:
```
gateway/
├── main.py
├── auth.py
├── rate_limiter.py
├── trace_context.py          (vs trace_injector.py above)
├── pre_inference_pipeline.py (vs orchestrator.py above)
├── complexity_scorer.py
├── semantic_cache.py
├── context_engine.py
├── admission_control.py
└── async_eval_worker.py      (vs eval_worker.py above)
```

**File name discrepancies:**
- `trace_injector.py` (Component 1) vs `trace_context.py` (Part IX)
- `orchestrator.py` (Component 1) vs `pre_inference_pipeline.py` (Part IX)
- `eval_worker.py` (Component 1) vs `async_eval_worker.py` (Part IX)
- Part IX does not include `pii_redactor.py`, `model_router.py`, `vllm_client.py`, `guardrail_client.py`, `verifier_client.py`, `escalation_handler.py`

### PHASE 1 RESOLUTION — CONFLICT 1 (Gateway Directory Layout)

**Resolved in Phase 1.** Decision recorded here as part of the permanent contract.

**Selected structure:** FLAT layout (no subdirectories within `gateway/`), using Part IX filenames where names conflict.

**Rationale:**
1. Part IX is the explicit "Repository Structure" section. It governs the filesystem layout.
2. The Component 1 nested structure describes logical module boundaries and responsibilities, not the mandatory filesystem layout.
3. Part IX's abbreviated listing omits files that represent essential documented functionality (pii_redactor.py, model_router.py, vllm_client.py, guardrail_client.py, verifier_client.py, escalation_handler.py). These files are included in the flat gateway/ directory because their responsibilities are explicitly documented in the Architecture Plan.
4. Where filenames differ between the two representations, Part IX filenames are used: `trace_context.py` (not `trace_injector.py`), `pre_inference_pipeline.py` (not `orchestrator.py`), `async_eval_worker.py` (not `eval_worker.py`).
5. `budget_controller.py` lives in `policy_engine/` (as per Part IX), not in `gateway/routing/`. The budget controller logic is documented under the Policy Engine section of the Architecture Plan, and Part IX is unambiguous.
6. `constants.py` is added to `vllm_adapter/` because CLAUDE.md Section 9.5 explicitly requires it for the `end_of_thinking_token_id` constant.

**Final authoritative gateway/ file list (flat, no subdirectories):**
```
gateway/
├── __init__.py
├── main.py               ← FastAPI app, lifespan, route registration
├── auth.py               ← API key → tenant ID resolution
├── rate_limiter.py       ← Token bucket, in-memory, per-tenant
├── trace_context.py      ← UUID request ID, W3C traceparent
├── pre_inference_pipeline.py ← Pipeline orchestrator, 50ms deadline
├── complexity_scorer.py  ← Heuristic scorer, <3ms
├── pii_redactor.py       ← Presidio wrapper
├── context_engine.py     ← Static prompt template selection
├── semantic_cache.py     ← FAISS index, sentence-transformers
├── admission_control.py  ← Semaphore, queue depth
├── model_router.py       ← Cheap vs reasoning route selection
├── vllm_client.py        ← OpenAI-compatible HTTP client
├── guardrail_client.py   ← HTTP client for guardrail service
├── verifier_client.py    ← HTTP client for verifier service
├── escalation_handler.py ← Retry at higher budget class
├── async_eval_worker.py  ← Background thread pool, SQLite writes
└── static/               ← Built React frontend (populated by frontend build)
```

This resolution is now permanent. The gateway/ directory has no subdirectories. The module boundaries from Component 1 are preserved conceptually but implemented as flat files.

### CONFLICT 2: "Six containers" statement vs. topology diagram

The Architecture Plan states "Six containers. All started by docker compose up." The explicit six are: FastAPI Gateway, vLLM Server, Guardrail Service, Verifier Service, Prometheus, Grafana.

However, Jaeger is described as Port 16686 and "receives OpenTelemetry traces via OTLP" — implying it is also a container. If Jaeger is the 7th container, the "six" statement is incorrect within the Architecture Plan itself.

**Resolution:** FAISS is in-process (confirmed by "No separate" language). Jaeger is almost certainly the 7th container managed by docker-compose. The "six" statement likely predates the explicit addition of Jaeger. **Future implementation should include Jaeger as a 7th container in docker-compose.yml.** This is an intra-document ambiguity, not a cross-document conflict.

### No cross-document conflicts detected between the Architecture Plan and the MVP Documentation.

---

## 32. Architectural Assumptions

The following are assumptions not explicitly defined in either PDF. They are listed to prevent future confusion between "documented requirement" and "implementation assumption."

| Assumption | Basis | Risk |
|------------|-------|------|
| Python version | Not specified in either PDF | Implementation must choose; Python 3.11+ recommended for vLLM compatibility |
| Specific FastAPI version | Not specified | No risk if latest stable used |
| React version | Not specified | No risk if latest stable used |
| Docker Compose version | Not specified (v2 syntax assumed from `docker compose up` not `docker-compose up`) | Confirm syntax before implementation |
| tenants.yaml format | Referenced ("loaded from tenants.yaml at startup") but schema not defined | Implementation must define schema consistent with policy YAML conventions |
| GPT-4o-mini API authentication | LLM judge uses GPT-4o-mini (from MVP Documentation); API key management not specified | Implementation must add to .env.example |
| Budget controller `FleetState` schema | Referenced in pseudocode but not formally defined | Implementation must define, consistent with circuit breaker state signals |
| FAISS index file name on Docker volume | Not specified | Implementation must define; must be consistent across restarts |
| SQLite database filename | Not specified | Implementation must define |
| Audit JSONL file path on Docker volume | Not specified | Implementation must define |
| `budget_controller.py` placement | Architecture Plan Component 1 places it in `gateway/routing/`; Part IX places it in `policy_engine/` | Must be resolved — the budget controller logic is documented in the policy engine section but may live in either location |

---

## 33. Phase 0 Completion Attestation

**Files inspected:**
- `InferaCordon Detailed Architecture Plan.pdf` (all 20 pages)
- `InferaCordon MVP Documentation.pdf` (all 19 pages)

**CLAUDE.md:** Created at repository root.

**No application implementation has been started.**

No FastAPI code, no vLLM integration, no LogitProcessor, no policy engine, no guardrails, no verifier, no semantic cache, no admission control, no circuit breakers, no telemetry, no benchmark implementation, and no frontend have been created. Those belong to later implementation phases.

---

*This file is the permanent engineering contract. Every subsequent implementation phase must obey it. Deviations require the Architecture Deviation Protocol (Section 28).*
