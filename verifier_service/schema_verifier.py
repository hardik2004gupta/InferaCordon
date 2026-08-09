"""
JSON Schema verifier: structural validation for structured output tasks.

Per CLAUDE.md Section 15:
- Parse response as JSON
- Validate against JSON Schema provided in request body
- Result: correct (valid JSON, schema passes) / incorrect (schema fails) / unverifiable (not JSON)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SchemaResult:
    result: str           # "correct" | "incorrect" | "unverifiable"
    validation_errors: list[str]
    latency_ms: float


class SchemaVerifier:
    def verify(self, response: str, schema: dict) -> SchemaResult:
        raise NotImplementedError("Implement per CLAUDE.md Section 15 (Week 3)")
