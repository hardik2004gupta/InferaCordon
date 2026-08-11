"""
JSON Schema verifier: structural validation for structured output tasks.

Per CLAUDE.md Section 15.3:
  - json.loads(response) → jsonschema.validate(data, schema)
  - Returns invalid_json or schema_violation with error message on failure
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

try:
    import jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False


@dataclass
class SchemaResult:
    result: str                           # "correct" | "incorrect" | "unverifiable"
    validation_errors: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


def _extract_json_from_response(text: str) -> str:
    """
    Extract JSON content from a response that may be wrapped in markdown
    code fences or contain surrounding prose.
    """
    # Prefer explicit ```json ... ``` fence
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Any ``` ... ``` fence
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Bare JSON object or array (take the outermost match)
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


class SchemaVerifier:
    """
    Validates JSON responses against a provided JSON Schema.
    Per CLAUDE.md Section 15.3.
    """

    def verify(self, response: str, schema: dict) -> SchemaResult:
        t0 = time.perf_counter()

        if not _JSONSCHEMA_AVAILABLE:
            return SchemaResult(
                result="unverifiable",
                validation_errors=["jsonschema package not installed"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        if not schema:
            return SchemaResult(
                result="unverifiable",
                validation_errors=["no schema provided"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        json_str = _extract_json_from_response(response)

        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as exc:
            return SchemaResult(
                result="incorrect",
                validation_errors=[f"invalid_json: {exc}"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        try:
            jsonschema.validate(data, schema)
            return SchemaResult(
                result="correct",
                validation_errors=[],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except jsonschema.ValidationError as exc:
            return SchemaResult(
                result="incorrect",
                validation_errors=[f"schema_violation: {exc.message}"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except jsonschema.SchemaError as exc:
            return SchemaResult(
                result="unverifiable",
                validation_errors=[f"invalid_schema: {exc.message}"],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
