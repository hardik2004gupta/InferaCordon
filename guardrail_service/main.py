"""
Guardrail microservice — FastAPI wrapper around ONNX safety classifiers.

Per CLAUDE.md Section 14:
- POST /v1/check       — input guardrail check (injection + safety)
- POST /v1/check-output — async output safety check
- GET  /health         — liveness probe
- Hard timeout enforced at gateway (200ms); service itself is fast
- ONNX inference: LlamaGuard ONNX (safety) + DeBERTa ONNX (injection)
- Asymmetric failure: input check timeout → BLOCK; output check timeout → PASS
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(title="InferaCordon Guardrail Service", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")


@app.post("/v1/check")
async def check_input(body: Any) -> Any:
    """Input guardrail: injection check + safety check."""
    raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")


@app.post("/v1/check-output")
async def check_output(body: Any) -> Any:
    """Output safety check (async, called after inference)."""
    raise NotImplementedError("Implement per CLAUDE.md Section 14 (Week 2)")
