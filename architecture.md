# InferaCordon Architecture Summary

Concise companion to [CLAUDE.md](CLAUDE.md) (the authoritative engineering contract).

## Seven-Container Topology

```
                    ┌─────────────────────────────────────────────────┐
                    │                    ic-net                        │
  Client ──HTTPS──► │  Gateway :8000 ──► vLLM :8080                  │
                    │      │      └────► Guardrail :8001              │
                    │      │      └────► Verifier :8002               │
                    │      │                                          │
                    │  Prometheus :9090 ◄── (all services /metrics)  │
                    │  Grafana :3000 ──────► Prometheus              │
                    │  Jaeger :16686 ◄─────── OTLP :4317 (all svcs) │
                    └─────────────────────────────────────────────────┘
```

## Request Processing (16 Steps, CLAUDE.md Section 6)

1. Auth → 2. Rate Limit → 3. Trace Context → 4. Cache Lookup →
5. Guardrail (input) → 6. PII Redact → 7. Complexity Score →
8. Policy Load → 9. Budget Assign → 10. Admission Control →
11. Context Engine → 12. Route → 13. vLLM Inference →
14. Verify → 15. Audit (outcome) → 16. Cache Store

Pre-inference deadline: 50ms (Steps 1-10).

## Budget Classes (CLAUDE.md Section 12)

| Class | Model | Reasoning Tokens | Verification |
|-------|-------|-----------------|--------------|
| low | Qwen2.5-3B | 0 | none |
| medium | DeepSeek-R1-7B | 512 | verifiable_only |
| high | DeepSeek-R1-7B | 1024 | required |
| critical | DeepSeek-R1-7B | 2048 | required |

## Key Design Decisions

- **BudgetLogitProcessor**: In-vLLM token-level budget enforcer (CLAUDE.md Section 9)
- **Semantic Cache**: FAISS IndexFlatIP in-process (not a service) — threshold 0.92 cosine similarity
- **Policy Engine**: Python library loaded at startup, immutable in-memory dict
- **Circuit Breakers**: GPU pressure (>90% KV-cache) + Latency P99 TTFT
- **Audit Log**: Append-only JSONL, no raw prompts/responses stored
- **Frontend**: React SPA served as static files by FastAPI gateway (no separate server)

See CLAUDE.md for all contracts, schemas, and implementation specifications.
