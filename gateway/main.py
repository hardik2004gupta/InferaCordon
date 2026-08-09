"""
FastAPI application entry point for InferaCordon gateway.

Responsibilities (per CLAUDE.md Section 6 — 16-step request processing):
- Expose POST /v1/infer (primary endpoint, CLAUDE.md Section 7)
- Serve React SPA static files from /app/static (no separate frontend server)
- Register middleware: auth, rate limiting, OpenTelemetry instrumentation
- Lifespan: initialize FAISS semantic cache, load policy engine, warm circuit breakers
- Mount Prometheus /metrics endpoint
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Stubs — implemented in later weeks
# from gateway.auth import verify_api_key
# from gateway.rate_limiter import RateLimiter
# from gateway.trace_context import attach_trace_context
# from gateway.pre_inference_pipeline import PreInferencePipeline
# from gateway.semantic_cache import SemanticCache
# from telemetry.prometheus_metrics import setup_metrics
# from telemetry.otel_config import configure_otel


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Week 1: initialize semantic cache (FAISS), policy engine, circuit breakers
    raise NotImplementedError("Implement lifespan startup per CLAUDE.md Section 13/12/6")
    yield
    # Week 1: flush FAISS index to disk, close audit log
    raise NotImplementedError("Implement lifespan shutdown per CLAUDE.md Section 13")


app = FastAPI(
    title="InferaCordon Gateway",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/v1/infer")
async def infer(request: Any) -> Any:
    """
    Primary inference endpoint — 16-step pipeline per CLAUDE.md Section 6.
    Full request/response schema in CLAUDE.md Section 7.
    """
    raise NotImplementedError("Implement per CLAUDE.md Section 6 (Week 1)")


@app.get("/v1/health")
async def health() -> dict:
    raise NotImplementedError("Implement per CLAUDE.md Section 7")


@app.get("/v1/policy/{tenant_id}/{domain}")
async def get_policy(tenant_id: str, domain: str) -> Any:
    raise NotImplementedError("Implement per CLAUDE.md Section 7")


@app.get("/v1/cache/stats")
async def cache_stats() -> Any:
    raise NotImplementedError("Implement per CLAUDE.md Section 7")


@app.post("/v1/cache/invalidate")
async def cache_invalidate() -> Any:
    raise NotImplementedError("Implement per CLAUDE.md Section 7")


@app.get("/v1/circuit-breakers")
async def circuit_breaker_status() -> Any:
    raise NotImplementedError("Implement per CLAUDE.md Section 7")


# Serve React SPA — built frontend at /app/static (no separate frontend server)
# Mounted last so API routes take precedence
app.mount("/", StaticFiles(directory="/app/static", html=True), name="spa")
