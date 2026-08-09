# InferaCordon

Governed AI inference control plane for reasoning token management.

**Four Pillars:** Guardrails · Governance · Cost Optimization · Inference Optimization

## Quick Start

```bash
cp .env.example .env
# Edit .env — set TENANT_API_KEYS, HUGGINGFACE_TOKEN
docker compose up
```

Access:
- Gateway API: http://localhost:8000
- React SPA: http://localhost:8000 (static files served by gateway)
- Grafana: http://localhost:3000 (admin / inferacordon)
- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686

## Architecture

Seven containers (CLAUDE.md Section 4):

| Container | Port | Role |
|-----------|------|------|
| gateway | 8000 | FastAPI control plane, SPA host |
| vllm | 8080 | DeepSeek-R1-7B-Q4 + Qwen2.5-3B-Instruct |
| guardrail | 8001 | ONNX safety + injection classifiers |
| verifier | 8002 | GSM8K / MATH / HumanEval / Schema verifiers |
| prometheus | 9090 | Metrics collection (ic_ prefix) |
| grafana | 3000 | Unified dashboard |
| jaeger | 16686 | Distributed tracing (OTLP) |

See [CLAUDE.md](CLAUDE.md) for the complete engineering contract.

## Metrics

<!-- METRICS -->
*Benchmark results not yet available — run after Week 9.*
<!-- /METRICS -->
