"""
PII redaction for the InferaCordon gateway.

Production path: Microsoft Presidio (AnalyzerEngine + AnonymizerEngine).
Dev / fallback path: regex patterns for common PII categories.

Per CLAUDE.md Section 14.3 and Section 6 Step 4:
- Runs in the pre-inference pipeline BEFORE any downstream component sees the prompt
- Redaction level configured per policy (none / standard / strict)
- Must NOT store raw PII in audit records (CLAUDE.md Section 19)
- Replaces detected entities with placeholder tokens, e.g. <EMAIL_ADDRESS>

Supported entities (both paths):
  EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, CREDIT_CARD, IP_ADDRESS
Strict-mode additions (Presidio only):
  PERSON, LOCATION, ORGANIZATION
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ── Presidio availability check (module level, import once) ──────────────────

try:
    from presidio_analyzer import AnalyzerEngine  # type: ignore[import]
    from presidio_anonymizer import AnonymizerEngine  # type: ignore[import]

    _PRESIDIO_AVAILABLE = True
except ImportError:
    _PRESIDIO_AVAILABLE = False
    log.info("PIIRedactor: presidio not installed — regex fallback active")

_BACKEND_VERSION = "presidio_v2" if _PRESIDIO_AVAILABLE else "regex_v1"

# ── Regex patterns for the fallback path ─────────────────────────────────────

_REGEX_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL_ADDRESS", re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    )),
    ("PHONE_NUMBER", re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
    )),
    ("US_SSN", re.compile(
        r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"
    )),
    ("CREDIT_CARD", re.compile(
        r"\b(?:\d{4}[-\s]){3}\d{4}\b"
    )),
    ("IP_ADDRESS", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
]

# ── Result type ───────────────────────────────────────────────────────────────


@dataclass
class RedactionResult:
    redacted_text: str
    entities_found: list[str] = field(default_factory=list)
    redaction_applied: bool = False
    entity_count: int = 0
    backend_version: str = _BACKEND_VERSION
    latency_ms: float = 0.0


# ── PIIRedactor ───────────────────────────────────────────────────────────────


class PIIRedactor:
    """
    Presidio-backed PII redactor with automatic regex fallback.
    One instance is created at gateway startup and reused for all requests.
    """

    def __init__(self, level: str = "standard") -> None:
        self._default_level = level
        self._analyzer = None
        self._anonymizer = None

        if _PRESIDIO_AVAILABLE:
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()

    def redact(self, text: str, policy_level: str = "standard") -> RedactionResult:
        """
        Redact PII from text according to the policy redaction level.

        Args:
            text: Raw prompt text (never stored after this function returns).
            policy_level: "none" | "standard" | "strict"
                - "none": no-op, return text unchanged
                - "standard": EMAIL, PHONE, SSN, CREDIT_CARD, IP; PERSON/LOCATION with Presidio
                - "strict": standard + PERSON + LOCATION + ORGANIZATION (Presidio path only)

        Returns:
            RedactionResult with redacted text and entity metadata (no raw PII in metadata).
        """
        if policy_level == "none":
            return RedactionResult(
                redacted_text=text,
                backend_version=_BACKEND_VERSION,
            )

        t0 = time.perf_counter()
        if _PRESIDIO_AVAILABLE:
            result = self._redact_presidio(text, policy_level)
        else:
            result = self._redact_regex(text, policy_level)
        result.latency_ms = (time.perf_counter() - t0) * 1000.0
        return result

    def _redact_presidio(self, text: str, policy_level: str) -> RedactionResult:
        entities = [
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "CREDIT_CARD",
            "US_SSN",
            "IP_ADDRESS",
            "PERSON",
            "LOCATION",
        ]
        if policy_level == "strict":
            entities.append("ORGANIZATION")

        results = self._analyzer.analyze(text=text, entities=entities, language="en")
        if not results:
            return RedactionResult(
                redacted_text=text,
                entities_found=[],
                redaction_applied=False,
                entity_count=0,
                backend_version="presidio_v2",
            )

        anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)
        return RedactionResult(
            redacted_text=anonymized.text,
            entities_found=sorted({r.entity_type for r in results}),
            redaction_applied=True,
            entity_count=len(results),
            backend_version="presidio_v2",
        )

    def _redact_regex(self, text: str, policy_level: str) -> RedactionResult:
        """
        Regex fallback. Handles EMAIL, PHONE, SSN, CREDIT_CARD, IP_ADDRESS.
        PERSON and LOCATION are not supported in the regex path — no NLP context.
        """
        redacted = text
        found_types: list[str] = []
        total_count = 0

        for entity_type, pattern in _REGEX_PATTERNS:
            matches = pattern.findall(redacted)
            if matches:
                found_types.append(entity_type)
                total_count += len(matches)
                redacted = pattern.sub(f"<{entity_type}>", redacted)

        return RedactionResult(
            redacted_text=redacted,
            entities_found=found_types,
            redaction_applied=bool(found_types),
            entity_count=total_count,
            backend_version="regex_v1",
        )
