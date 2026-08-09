"""
Verifier microservice — selects and runs the appropriate verifier per domain.

Per CLAUDE.md Section 15:
- POST /v1/verify — dispatches to domain-specific verifier
- GET  /health    — liveness probe
- Verifier selection: gsm8k / math / humaneval / schema (per domain config)
- Results: correct / incorrect / unverifiable
- Called for policies where verification: required or verifiable_only
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(title="InferaCordon Verifier Service", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")


@app.post("/v1/verify")
async def verify(body: Any) -> Any:
    """Dispatch to appropriate verifier based on domain."""
    raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")
