"""
Unit tests for the end-of-thinking token discovery mechanism (CLAUDE.md Section 9.5).

Tests validate:
  - Discovery with a mock tokenizer succeeds
  - Sentinel value (-1) handling
  - assert_valid() raises on unvalidated result
  - Multi-token encoding is rejected
  - Import failure is handled gracefully
  - Module-level constants have correct types
"""
import pytest
from unittest.mock import MagicMock, patch

from vllm_adapter.constants import (
    TokenDiscoveryResult,
    discover_eot_token_id,
    _UNDISCOVERED_SENTINEL,
    DEEPSEEK_HF_MODEL_ID,
    DEEPSEEK_R1_EOT_TOKEN_ID,
    DEEPSEEK_R1_EOT_VALIDATED,
    BUDGET_CLASS_REASONING_TOKENS,
)


# ── 1. Module-level constant types and values ─────────────────────────────────

class TestModuleLevelConstants:

    def test_sentinel_is_negative_one(self):
        assert _UNDISCOVERED_SENTINEL == -1

    def test_eot_token_id_is_int(self):
        assert isinstance(DEEPSEEK_R1_EOT_TOKEN_ID, int)

    def test_eot_validated_is_bool(self):
        assert isinstance(DEEPSEEK_R1_EOT_VALIDATED, bool)

    def test_budget_class_tokens_all_non_negative(self):
        for cls, tokens in BUDGET_CLASS_REASONING_TOKENS.items():
            assert tokens >= 0, f"Budget class {cls} has negative token count"

    def test_low_budget_has_zero_reasoning_tokens(self):
        assert BUDGET_CLASS_REASONING_TOKENS["low"] == 0

    def test_budget_classes_ordered(self):
        toks = BUDGET_CLASS_REASONING_TOKENS
        assert toks["low"] < toks["medium"] < toks["high"] <= toks["critical"]

    def test_not_cached_means_unvalidated(self):
        # In this test environment, DeepSeek tokenizer is not cached.
        # This is expected and documented — not a bug.
        # The token ID must be -1 (sentinel) when not discovered.
        if not DEEPSEEK_R1_EOT_VALIDATED:
            assert DEEPSEEK_R1_EOT_TOKEN_ID == _UNDISCOVERED_SENTINEL


# ── 2. Discovery with mock tokenizer ─────────────────────────────────────────

class TestDiscoveryWithMock:

    def _make_mock_tokenizer(self, token_id: int, unk_id: int = 0):
        tok = MagicMock()
        tok.unk_token_id = unk_id
        tok.convert_tokens_to_ids.return_value = token_id
        tok.encode.return_value = [token_id]
        return tok

    def test_successful_discovery(self):
        mock_tok = self._make_mock_tokenizer(token_id=151648)

        with patch("vllm_adapter.constants.AutoTokenizer", create=True) as mock_class:
            mock_class.from_pretrained.return_value = mock_tok
            result = discover_eot_token_id("some/model", "</think>")

        assert result.validated is True
        assert result.token_id == 151648
        assert result.error is None

    def test_discovery_uses_local_files_only(self):
        mock_tok = self._make_mock_tokenizer(token_id=42)

        with patch("vllm_adapter.constants.AutoTokenizer", create=True) as mock_class:
            mock_class.from_pretrained.return_value = mock_tok
            discover_eot_token_id("some/model", "</think>")
            call_kwargs = mock_class.from_pretrained.call_args[1]
            assert call_kwargs.get("local_files_only") is True

    def test_fallback_to_encode_when_convert_returns_unk(self):
        mock_tok = MagicMock()
        mock_tok.unk_token_id = 0
        mock_tok.convert_tokens_to_ids.return_value = 0  # same as unk_token_id → fallback
        mock_tok.encode.return_value = [99999]

        with patch("vllm_adapter.constants.AutoTokenizer", create=True) as mock_class:
            mock_class.from_pretrained.return_value = mock_tok
            result = discover_eot_token_id("some/model", "</think>")

        assert result.token_id == 99999
        assert result.validated is True

    def test_multi_token_encoding_returns_unvalidated(self):
        mock_tok = MagicMock()
        mock_tok.unk_token_id = 0
        mock_tok.convert_tokens_to_ids.return_value = 0   # triggers encode fallback
        mock_tok.encode.return_value = [1, 2, 3]           # multi-token — invalid

        with patch("vllm_adapter.constants.AutoTokenizer", create=True) as mock_class:
            mock_class.from_pretrained.return_value = mock_tok
            result = discover_eot_token_id("some/model", "</think>")

        assert result.validated is False
        assert result.token_id == _UNDISCOVERED_SENTINEL
        assert "multiple token IDs" in result.error


# ── 3. Import failure handling ────────────────────────────────────────────────

class TestImportFailure:

    def test_import_error_returns_unvalidated(self):
        with patch("vllm_adapter.constants.AutoTokenizer", None, create=True):
            result = discover_eot_token_id("some/model", "</think>")

        assert result.validated is False
        assert result.token_id == _UNDISCOVERED_SENTINEL

    def test_model_not_cached_returns_unvalidated(self):
        with patch("vllm_adapter.constants.AutoTokenizer", create=True) as mock_class:
            mock_class.from_pretrained.side_effect = OSError("model not found locally")
            result = discover_eot_token_id("some/model-not-cached", "</think>")

        assert result.validated is False
        assert result.token_id == _UNDISCOVERED_SENTINEL
        assert result.error is not None


# ── 4. assert_valid() ─────────────────────────────────────────────────────────

class TestAssertValid:

    def test_raises_when_not_validated(self):
        result = TokenDiscoveryResult(
            model_id="test/model",
            token_string="</think>",
            token_id=_UNDISCOVERED_SENTINEL,
            validated=False,
            error="model not cached",
        )
        with pytest.raises(ValueError, match="not been discovered"):
            result.assert_valid()

    def test_raises_when_sentinel_even_if_validated_flag_true(self):
        # Defensive: token_id sentinel with validated=True is an impossible state
        # but we guard against it anyway.
        result = TokenDiscoveryResult(
            model_id="test/model",
            token_string="</think>",
            token_id=_UNDISCOVERED_SENTINEL,
            validated=True,    # Contradiction
            error=None,
        )
        with pytest.raises(ValueError):
            result.assert_valid()

    def test_does_not_raise_when_valid(self):
        result = TokenDiscoveryResult(
            model_id="test/model",
            token_string="</think>",
            token_id=151648,
            validated=True,
            error=None,
        )
        result.assert_valid()  # Should not raise


# ── 5. TokenDiscoveryResult fields ────────────────────────────────────────────

class TestTokenDiscoveryResultFields:

    def test_all_fields_set(self):
        r = TokenDiscoveryResult(
            model_id="a/b",
            token_string="</think>",
            token_id=100,
            validated=True,
            error=None,
        )
        assert r.model_id == "a/b"
        assert r.token_string == "</think>"
        assert r.token_id == 100
        assert r.validated is True
        assert r.error is None
