"""
Unit tests for gateway/pii_redactor.py.

Tests cover:
- RedactionResult dataclass
- level="none" is a no-op
- Email, phone, SSN, credit card, IP address detection (regex path)
- Multiple entities in one text
- Entity count accuracy
- Audit privacy: redacted_text does not contain raw PII values
- Backend version reporting
- Strict vs standard level (regex path treats them identically)
- PIIRedactor instantiation does not raise when Presidio absent

All tests use the regex fallback path (Presidio not installed in dev).
"""
from __future__ import annotations

import re

import pytest

from gateway.pii_redactor import PIIRedactor, RedactionResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def redactor() -> PIIRedactor:
    return PIIRedactor()


# ── RedactionResult ────────────────────────────────────────────────────────────

class TestRedactionResult:
    def test_instantiation(self):
        r = RedactionResult(redacted_text="hello")
        assert r.redacted_text == "hello"
        assert r.entities_found == []
        assert r.redaction_applied is False
        assert r.entity_count == 0
        assert r.latency_ms == 0.0

    def test_backend_version_set(self):
        r = RedactionResult(redacted_text="x")
        # Must be a non-empty string — either presidio_v2 or regex_v1
        assert isinstance(r.backend_version, str)
        assert len(r.backend_version) > 0


# ── PIIRedactor instantiation ─────────────────────────────────────────────────

class TestPIIRedactorInit:
    def test_instantiates_without_error(self):
        r = PIIRedactor()
        assert r is not None

    def test_instantiates_with_level(self):
        r = PIIRedactor(level="strict")
        assert r is not None

    def test_backend_version_is_string(self, redactor):
        from gateway.pii_redactor import _BACKEND_VERSION
        assert isinstance(_BACKEND_VERSION, str)
        assert _BACKEND_VERSION in ("presidio_v2", "regex_v1")


# ── level="none" no-op ────────────────────────────────────────────────────────

class TestNoneLevel:
    def test_none_level_returns_unchanged_text(self, redactor):
        text = "My email is user@example.com and SSN is 123-45-6789"
        result = redactor.redact(text, policy_level="none")
        assert result.redacted_text == text

    def test_none_level_no_redaction_applied(self, redactor):
        result = redactor.redact("user@example.com", policy_level="none")
        assert result.redaction_applied is False

    def test_none_level_zero_entities(self, redactor):
        result = redactor.redact("user@example.com", policy_level="none")
        assert result.entity_count == 0
        assert result.entities_found == []


# ── Email redaction ────────────────────────────────────────────────────────────

class TestEmailRedaction:
    def test_standard_email_redacted(self, redactor):
        result = redactor.redact("Contact me at user@example.com please.", "standard")
        assert "user@example.com" not in result.redacted_text

    def test_email_placeholder_present(self, redactor):
        result = redactor.redact("Email: hello@domain.org", "standard")
        assert "<EMAIL_ADDRESS>" in result.redacted_text or "EMAIL" in result.redacted_text

    def test_email_entity_detected(self, redactor):
        result = redactor.redact("test@test.com", "standard")
        assert "EMAIL_ADDRESS" in result.entities_found
        assert result.redaction_applied is True

    def test_email_with_plus_sign(self, redactor):
        result = redactor.redact("Send to user+tag@example.co.uk", "standard")
        assert "user+tag@example.co.uk" not in result.redacted_text

    def test_multiple_emails(self, redactor):
        result = redactor.redact("From a@b.com to c@d.org", "standard")
        assert "a@b.com" not in result.redacted_text
        assert "c@d.org" not in result.redacted_text


# ── Phone number redaction ────────────────────────────────────────────────────

class TestPhoneRedaction:
    def test_us_phone_dashes(self, redactor):
        result = redactor.redact("Call 555-867-5309 for details.", "standard")
        assert "867-5309" not in result.redacted_text

    def test_us_phone_dots(self, redactor):
        result = redactor.redact("Phone: 555.867.5309", "standard")
        assert "867.5309" not in result.redacted_text

    def test_phone_entity_detected(self, redactor):
        result = redactor.redact("Call 555-867-5309", "standard")
        assert "PHONE_NUMBER" in result.entities_found


# ── SSN redaction ─────────────────────────────────────────────────────────────

class TestSSNRedaction:
    def test_ssn_with_dashes_redacted(self, redactor):
        result = redactor.redact("SSN: 123-45-6789", "standard")
        assert "123-45-6789" not in result.redacted_text

    def test_ssn_entity_detected(self, redactor):
        result = redactor.redact("My SSN is 987-65-4321.", "standard")
        assert "US_SSN" in result.entities_found

    def test_ssn_with_spaces_redacted(self, redactor):
        result = redactor.redact("SSN 123 45 6789", "standard")
        assert "123 45 6789" not in result.redacted_text


# ── Credit card redaction ─────────────────────────────────────────────────────

class TestCreditCardRedaction:
    def test_card_with_dashes(self, redactor):
        result = redactor.redact("Card: 4111-1111-1111-1111", "standard")
        assert "4111-1111-1111-1111" not in result.redacted_text

    def test_card_with_spaces(self, redactor):
        result = redactor.redact("Card 4111 1111 1111 1111", "standard")
        assert "4111 1111 1111 1111" not in result.redacted_text

    def test_card_entity_detected(self, redactor):
        result = redactor.redact("CC: 4111-1111-1111-1111", "standard")
        assert "CREDIT_CARD" in result.entities_found


# ── IP address redaction ──────────────────────────────────────────────────────

class TestIPRedaction:
    def test_ipv4_redacted(self, redactor):
        result = redactor.redact("Server at 192.168.1.100 is down.", "standard")
        assert "192.168.1.100" not in result.redacted_text

    def test_ip_entity_detected(self, redactor):
        result = redactor.redact("IP: 10.0.0.1", "standard")
        assert "IP_ADDRESS" in result.entities_found

    def test_public_ip_redacted(self, redactor):
        result = redactor.redact("External IP: 203.0.113.42", "standard")
        assert "203.0.113.42" not in result.redacted_text


# ── Multi-entity prompts ──────────────────────────────────────────────────────

class TestMultiEntityRedaction:
    def test_email_and_phone_in_same_text(self, redactor):
        text = "Email user@example.com, phone 555-123-4567"
        result = redactor.redact(text, "standard")
        assert "user@example.com" not in result.redacted_text
        assert "555-123-4567" not in result.redacted_text
        assert result.entity_count >= 2

    def test_all_five_types_in_one_text(self, redactor):
        text = (
            "Email: user@example.com, "
            "Phone: 555-867-5309, "
            "SSN: 123-45-6789, "
            "Card: 4111-1111-1111-1111, "
            "IP: 192.168.0.1"
        )
        result = redactor.redact(text, "standard")
        assert "user@example.com" not in result.redacted_text
        assert "123-45-6789" not in result.redacted_text
        assert "4111-1111-1111-1111" not in result.redacted_text
        assert "192.168.0.1" not in result.redacted_text
        assert result.redaction_applied is True

    def test_entity_count_incremented_per_match(self, redactor):
        text = "a@b.com and c@d.com"
        result = redactor.redact(text, "standard")
        assert result.entity_count >= 2


# ── Audit privacy ─────────────────────────────────────────────────────────────

class TestAuditPrivacy:
    def test_entities_found_contains_type_not_value(self, redactor):
        """entities_found must list entity types, not the raw PII values."""
        result = redactor.redact("Email: secret@example.com", "standard")
        for entity in result.entities_found:
            # Entity names are uppercase type identifiers, not email strings
            assert "@" not in entity
            assert entity == entity.upper() or entity.startswith("<")

    def test_redacted_text_does_not_expose_raw_ssn(self, redactor):
        raw_ssn = "987-65-4321"
        result = redactor.redact(f"My SSN is {raw_ssn}", "standard")
        assert raw_ssn not in result.redacted_text

    def test_redacted_text_does_not_expose_card_number(self, redactor):
        card = "4111-1111-1111-1111"
        result = redactor.redact(f"My card: {card}", "standard")
        assert card not in result.redacted_text


# ── Non-PII text ──────────────────────────────────────────────────────────────

class TestCleanText:
    def test_benign_text_unchanged(self, redactor):
        text = "What is the capital of France?"
        result = redactor.redact(text, "standard")
        assert result.redacted_text == text
        assert result.redaction_applied is False

    def test_code_snippet_not_falsely_flagged(self, redactor):
        text = "def hello(): return 42"
        result = redactor.redact(text, "standard")
        # Should not incorrectly identify code as PII
        assert result.entity_count == 0

    def test_latency_tracked(self, redactor):
        result = redactor.redact("test", "standard")
        assert result.latency_ms >= 0.0


# ── Strict vs standard ────────────────────────────────────────────────────────

class TestStrictLevel:
    def test_strict_level_accepts_without_error(self, redactor):
        result = redactor.redact("Call 555-867-5309", "strict")
        assert isinstance(result, RedactionResult)

    def test_strict_detects_same_entities_as_standard_on_regex_path(self, redactor):
        from gateway.pii_redactor import _PRESIDIO_AVAILABLE
        if _PRESIDIO_AVAILABLE:
            pytest.skip("Presidio installed — strict adds PERSON/LOCATION, not tested here")
        text = "Email: x@y.com, SSN: 123-45-6789"
        standard = redactor.redact(text, "standard")
        strict = redactor.redact(text, "strict")
        # On regex path, strict and standard handle same entity types
        assert standard.entities_found == strict.entities_found
