"""
Verifier microservice — FastAPI app dispatching to domain-specific verifiers.

Per CLAUDE.md Section 15.2 — exact API contract:
  POST /verify  — dispatch to verifier_type-specific implementation
  GET  /health  — liveness probe
  GET  /readiness — readiness probe

Verifier types: gsm8k, math, humaneval, json_schema, none
Results:        correct | incorrect | unverifiable
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from verifier_service.gsm8k_verifier import GSM8KVerifier
from verifier_service.humaneval_runner import HumanEvalRunner
from verifier_service.math_verifier import MathVerifier
from verifier_service.schema_verifier import SchemaVerifier

app = FastAPI(title="InferaCordon Verifier Service", version="0.7.0")

_gsm8k = GSM8KVerifier()
_math = MathVerifier()
_humaneval = HumanEvalRunner()
_schema = SchemaVerifier()


# ── Request / Response models ─────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    """Per CLAUDE.md Section 15.2 request contract."""
    response: str
    verifier_type: str                   # "gsm8k"|"math"|"humaneval"|"json_schema"|"none"
    ground_truth: Optional[str] = None  # gsm8k, math
    test_cases: Optional[str] = None    # humaneval — JSON array or newline-separated
    entry_point: Optional[str] = None   # humaneval (not used by runner; for audit)
    schema: Optional[dict] = None       # json_schema


class VerifyResponse(BaseModel):
    """Per CLAUDE.md Section 15.2 response contract."""
    passed: bool
    verifier_type: str
    reason: str
    predicted: str = ""
    expected: str = ""
    latency_ms: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.7.0"}


@app.get("/readiness")
async def readiness() -> dict:
    return {"ready": True}


@app.post("/verify", response_model=VerifyResponse)
async def verify(body: VerifyRequest) -> VerifyResponse:
    """
    Dispatch to the appropriate verifier.
    Per CLAUDE.md Section 15.2 — verifier type determines the implementation.
    """
    vt = body.verifier_type.strip().lower()

    if vt == "none":
        return VerifyResponse(
            passed=True,
            verifier_type="none",
            reason="no_verification_required",
            latency_ms=0.0,
        )

    if vt == "gsm8k":
        r = _gsm8k.verify(body.response, body.ground_truth)
        return VerifyResponse(
            passed=r.result == "correct",
            verifier_type="gsm8k",
            reason=r.result,
            predicted=r.extracted_answer or "",
            expected=r.expected_answer or "",
            latency_ms=r.latency_ms,
        )

    if vt == "math":
        r = _math.verify(body.response, body.ground_truth)
        return VerifyResponse(
            passed=r.result == "correct",
            verifier_type="math",
            reason=r.result,
            predicted=r.parsed_response or "",
            expected=r.expected or "",
            latency_ms=r.latency_ms,
        )

    if vt == "humaneval":
        cases: list[str] = []
        if body.test_cases:
            try:
                parsed = json.loads(body.test_cases)
                cases = [parsed] if isinstance(parsed, str) else list(parsed)
            except (json.JSONDecodeError, TypeError):
                cases = [ln.strip() for ln in body.test_cases.splitlines() if ln.strip()]
        r = _humaneval.verify(body.response, cases)
        return VerifyResponse(
            passed=r.result == "correct",
            verifier_type="humaneval",
            reason=r.result,
            predicted=f"{r.test_cases_passed}/{r.test_cases_total}",
            expected=str(r.test_cases_total),
            latency_ms=r.latency_ms,
        )

    if vt == "json_schema":
        if body.schema is None:
            return VerifyResponse(
                passed=False,
                verifier_type="json_schema",
                reason="unverifiable_no_schema",
                latency_ms=0.0,
            )
        r = _schema.verify(body.response, body.schema)
        reason_detail = (
            f": {r.validation_errors[0]}" if r.validation_errors else ""
        )
        return VerifyResponse(
            passed=r.result == "correct",
            verifier_type="json_schema",
            reason=r.result + reason_detail,
            latency_ms=r.latency_ms,
        )

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unknown verifier_type: {body.verifier_type!r}. "
            "Valid values: gsm8k, math, humaneval, json_schema, none"
        ),
    )
