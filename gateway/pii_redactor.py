"""
PII redaction using Microsoft Presidio.

Per CLAUDE.md Section 6 (Step 6) and guardrails policy (pii_redaction):
- Detects and anonymizes PII before the prompt reaches the model
- Redaction level configurable per policy (none / standard / strict)
- Presidio AnalyzerEngine + AnonymizerEngine (spaCy NLP backend)
- Redaction map stored in request context for audit
- Must NOT store raw prompts in audit log (CLAUDE.md Section 19)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RedactionResult:
    redacted_text: str
    entities_found: list[str]
    redaction_applied: bool


class PIIRedactor:
    """Presidio-backed PII redactor. Loaded once at gateway startup."""

    def __init__(self, level: str = "standard") -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 6 (Week 1)")

    def redact(self, text: str, policy_level: str) -> RedactionResult:
        """Redact PII per policy level. 'none' is a no-op."""
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 6 (Week 1)")
