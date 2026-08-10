"""
Guardrail microservice — FastAPI wrapper around ONNX classifiers.

Per CLAUDE.md Section 14:
- POST /guardrail/input   — injection + safety check on redacted input prompt
- POST /guardrail/output  — safety check on model output text
- GET  /health            — liveness probe
- GET  /readiness         — readiness probe (classifiers loaded)
- CPU-only; never calls vLLM; never touches GPU (CLAUDE.md Section 3)
- Gateway enforces 200ms timeout; service targets <150ms end-to-end
- Decision logic per CLAUDE.md Section 14.4:
    injection_score > threshold → "flag" (NOT block — false positive risk)
    safety confidence > threshold AND category != "safe" → "block"
    Combined priority: block > flag > pass
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from guardrail_service.injection_classifier import InjectionClassifier, InjectionResult
from guardrail_service.safety_classifier import SafetyClassifier, SafetyResult

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

INJECTION_MODEL_PATH = os.environ.get(
    "INJECTION_MODEL_PATH",
    "/app/models/deberta_inject_v1.onnx",
)
SAFETY_MODEL_PATH = os.environ.get(
    "SAFETY_MODEL_PATH",
    "/app/models/llamaguard_onnx_v1.onnx",
)


# ── Service state ─────────────────────────────────────────────────────────────

@dataclass
class ServiceState:
    injection_classifier: InjectionClassifier
    safety_classifier: SafetyClassifier


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Guardrail service starting — loading classifiers")

    injection_clf = InjectionClassifier(model_path=INJECTION_MODEL_PATH)
    safety_clf = SafetyClassifier(model_path=SAFETY_MODEL_PATH)

    app.state.guardrail = ServiceState(
        injection_classifier=injection_clf,
        safety_classifier=safety_clf,
    )

    log.info(
        "Guardrail service ready — injection=%s safety=%s",
        injection_clf.model_version,
        safety_clf.model_version,
    )
    yield
    log.info("Guardrail service shut down")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="InferaCordon Guardrail Service",
    description=(
        "CPU-only injection and safety classification. "
        "Per CLAUDE.md Section 14. Port 8001."
    ),
    version="0.5.0",
    lifespan=lifespan,
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class InputCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=32768)
    run_injection_check: bool = True
    run_safety_check: bool = True
    injection_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    safety_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class InputCheckResponse(BaseModel):
    result: str                       # "pass" | "flag" | "block"
    injection_score: float
    safety_category: str
    safety_confidence: float
    injection_model_version: str
    safety_model_version: str
    latency_ms: int


class OutputCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=65536)
    run_safety_check: bool = True
    safety_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class OutputCheckResponse(BaseModel):
    result: str               # "pass" | "block"
    safety_category: str
    safety_confidence: float
    safety_model_version: str
    latency_ms: int


# ── Decision logic ────────────────────────────────────────────────────────────

def _combine_input_result(
    injection: InjectionResult | None,
    safety: SafetyResult | None,
    injection_threshold: float,
    safety_threshold: float,
) -> str:
    """
    Per CLAUDE.md Section 14.4:
      - Injection over threshold → "flag" (augment prompt, do NOT block)
      - Safety unsafe over threshold → "block"
      - Priority: block > flag > pass
    """
    decision = "pass"

    if injection is not None and injection.injection_probability > injection_threshold:
        decision = "flag"

    if (
        safety is not None
        and not safety.is_safe
        and safety.confidence > safety_threshold
    ):
        decision = "block"  # overrides flag

    return decision


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_state(request: Request) -> ServiceState:
    return request.app.state.guardrail


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/guardrail/input", response_model=InputCheckResponse)
async def check_input(body: InputCheckRequest, request: Request) -> InputCheckResponse:
    """
    Input guardrail: injection detection + safety classification on a redacted prompt.
    Per CLAUDE.md Section 14.6 API contract.
    """
    t0 = time.perf_counter()
    state = _get_state(request)

    injection: InjectionResult | None = None
    safety: SafetyResult | None = None

    if body.run_injection_check:
        injection = state.injection_classifier.classify(body.text)
    if body.run_safety_check:
        safety = state.safety_classifier.classify(body.text)

    combined = _combine_input_result(
        injection=injection,
        safety=safety,
        injection_threshold=body.injection_threshold,
        safety_threshold=body.safety_threshold,
    )

    return InputCheckResponse(
        result=combined,
        injection_score=injection.injection_probability if injection else 0.0,
        safety_category=safety.category if safety else "safe",
        safety_confidence=safety.confidence if safety else 0.0,
        injection_model_version=injection.model_version if injection else "skipped",
        safety_model_version=safety.model_version if safety else "skipped",
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


@app.post("/guardrail/output", response_model=OutputCheckResponse)
async def check_output(body: OutputCheckRequest, request: Request) -> OutputCheckResponse:
    """
    Output safety check on model response text.
    Per CLAUDE.md Section 14.5 and 14.6.
    """
    t0 = time.perf_counter()
    state = _get_state(request)

    safety: SafetyResult | None = None

    if body.run_safety_check:
        safety = state.safety_classifier.classify(body.text)

    if safety is not None and not safety.is_safe and safety.confidence > body.safety_threshold:
        result = "block"
    else:
        result = "pass"

    return OutputCheckResponse(
        result=result,
        safety_category=safety.category if safety else "safe",
        safety_confidence=safety.confidence if safety else 0.0,
        safety_model_version=safety.model_version if safety else "skipped",
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


@app.get("/health")
async def health() -> dict:
    """Liveness probe. Returns 200 if the process is alive."""
    return {"status": "ok", "service": "guardrail"}


@app.get("/readiness")
async def readiness(request: Request) -> dict:
    """Readiness probe — classifiers loaded and operational."""
    try:
        state = _get_state(request)
        return {
            "ready": True,
            "injection_model": state.injection_classifier.model_version,
            "safety_model": state.safety_classifier.model_version,
        }
    except AttributeError:
        return {"ready": False, "reason": "classifiers not initialized"}
