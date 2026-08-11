"""
Unit tests for gateway/semantic_cache.py.

Coverage:
- CacheEntry: expiry logic, metadata dict
- CacheLookupResult: defaults
- SemanticCache disabled path (faiss not installed — always active in dev)
- SemanticCache enabled path with mocked FAISS + sentence-transformers
- Tenant/domain isolation: hit rejected when tenant/domain mismatch
- TTL: expired entries return miss
- Similarity threshold: strict > (not >=) per CLAUDE.md Section 13.3
- PII residual check (_has_residual_pii helper from main.py)
- Background threads: start on enable, stop() sets _stop event
- invalidate(): removes correct entries

All tests must pass regardless of whether faiss-cpu is installed.
Enabled-path tests are skipped when faiss is not available.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import gateway.semantic_cache as sc_module
from gateway.semantic_cache import (
    CacheEntry,
    CacheLookupResult,
    SemanticCache,
    _FAISS_AVAILABLE,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def _make_entry(
    *,
    tenant_id: str = "acme_corp",
    domain: str = "general_qa",
    vid: int = 0,
    ttl_seconds: int = 3600,
    expired: bool = False,
) -> CacheEntry:
    now = time.time()
    expires_at = (now - 1.0) if expired else (now + ttl_seconds)
    return CacheEntry(
        vector_id=vid,
        response="The answer is 42.",
        tenant_id=tenant_id,
        domain=domain,
        created_at=now,
        expires_at=expires_at,
    )


# ── CacheEntry ─────────────────────────────────────────────────────────────────

class TestCacheEntry:
    def test_not_expired_when_future(self):
        entry = _make_entry(ttl_seconds=3600)
        assert not entry.is_expired()

    def test_expired_when_past(self):
        entry = _make_entry(expired=True)
        assert entry.is_expired()

    def test_is_expired_uses_provided_now(self):
        entry = _make_entry(ttl_seconds=10)
        far_future = time.time() + 86400
        assert entry.is_expired(now=far_future)

    def test_not_expired_uses_provided_now(self):
        entry = _make_entry(expired=True)
        # Use a "now" from the past so the entry appears valid
        past = time.time() - 86400
        assert not entry.is_expired(now=past)

    def test_to_metadata_dict_has_required_keys(self):
        entry = _make_entry()
        meta = entry.to_metadata_dict()
        for key in ("tenant_id", "domain", "created_at", "expires_at"):
            assert key in meta

    def test_to_metadata_dict_tenant_id(self):
        entry = _make_entry(tenant_id="demo_tenant")
        assert entry.to_metadata_dict()["tenant_id"] == "demo_tenant"

    def test_to_metadata_dict_domain(self):
        entry = _make_entry(domain="code")
        assert entry.to_metadata_dict()["domain"] == "code"

    def test_to_metadata_dict_no_raw_response(self):
        # Response text must not leak into the metadata dict (PII hygiene)
        entry = _make_entry()
        meta = entry.to_metadata_dict()
        assert "response" not in meta


# ── CacheLookupResult ──────────────────────────────────────────────────────────

class TestCacheLookupResult:
    def test_default_miss(self):
        r = CacheLookupResult(hit=False)
        assert r.hit is False
        assert r.response is None
        assert r.similarity is None
        assert r.metadata is None

    def test_hit_fields(self):
        r = CacheLookupResult(
            hit=True,
            response="cached response",
            similarity=0.95,
            metadata={"tenant_id": "acme_corp"},
        )
        assert r.hit is True
        assert r.response == "cached response"
        assert r.similarity == pytest.approx(0.95)


# ── SemanticCache — disabled path (no faiss) ──────────────────────────────────

class TestSemanticCacheDisabled:
    """
    These tests exercise the fail-safe disabled path, which is always active
    in the development environment because faiss-cpu is not installed.
    """

    @pytest.fixture
    def disabled_cache(self, tmp_path):
        # When faiss is not installed, SemanticCache.__init__ sets _enabled=False
        cache = SemanticCache(persist_path=str(tmp_path / "cache"))
        yield cache
        cache.stop()

    def test_enabled_is_false_when_faiss_missing(self, disabled_cache):
        if _FAISS_AVAILABLE:
            pytest.skip("faiss is installed — testing enabled path elsewhere")
        assert disabled_cache.enabled is False

    def test_lookup_returns_miss(self, disabled_cache):
        result = _run(disabled_cache.lookup(
            tenant_id="acme_corp",
            domain="general_qa",
            prompt="What is 2+2?",
            similarity_threshold=0.92,
            ttl_seconds=3600,
        ))
        assert result.hit is False

    def test_store_is_noop(self, disabled_cache):
        # Must not raise
        _run(disabled_cache.store(
            tenant_id="acme_corp",
            domain="general_qa",
            prompt="What is 2+2?",
            response="4",
            metadata={},
            ttl_seconds=3600,
        ))

    def test_lookup_returns_correct_type(self, disabled_cache):
        result = _run(disabled_cache.lookup(
            tenant_id="acme_corp",
            domain="general_qa",
            prompt="Hello",
            similarity_threshold=0.92,
            ttl_seconds=3600,
        ))
        assert isinstance(result, CacheLookupResult)

    def test_lookup_hit_is_false(self, disabled_cache):
        result = _run(disabled_cache.lookup(
            tenant_id="x",
            domain="y",
            prompt="z",
            similarity_threshold=0.0,  # even with 0 threshold
            ttl_seconds=3600,
        ))
        assert result.hit is False

    def test_invalidate_returns_zero(self, disabled_cache):
        count = disabled_cache.invalidate("acme_corp", "general_qa")
        assert count == 0

    def test_stop_does_not_raise(self, disabled_cache):
        disabled_cache.stop()  # safe to call twice

    def test_store_then_lookup_returns_miss(self, disabled_cache):
        _run(disabled_cache.store(
            tenant_id="t", domain="d", prompt="p", response="r",
            metadata={}, ttl_seconds=3600,
        ))
        result = _run(disabled_cache.lookup(
            tenant_id="t", domain="d", prompt="p",
            similarity_threshold=0.0, ttl_seconds=3600,
        ))
        assert result.hit is False


# ── SemanticCache — enabled path (mocked FAISS) ───────────────────────────────

@pytest.fixture
def _mock_faiss_module():
    """A fully mocked faiss module for use in enabled-path tests."""
    mock = MagicMock()
    mock.IndexFlatIP.return_value = MagicMock()
    idx = MagicMock()
    idx.ntotal = 0
    mock.IndexIDMap2.return_value = idx
    return mock, idx


@pytest.fixture
def _mock_st_class():
    """A mock SentenceTransformer class that returns unit embeddings."""
    model_instance = MagicMock()
    model_instance.encode.return_value = np.ones((1, 384), dtype=np.float32) / (384 ** 0.5)
    cls = MagicMock(return_value=model_instance)
    return cls, model_instance


@pytest.mark.skipif(not _FAISS_AVAILABLE, reason="faiss not installed — skipping enabled path tests")
class TestSemanticCacheEnabled:
    """
    Enabled-path tests: only run when faiss-cpu is installed.
    In CI/production with faiss-cpu, these must all pass.
    In dev, they are skipped cleanly.
    """

    @pytest.fixture
    def enabled_cache(self, tmp_path, _mock_faiss_module, _mock_st_class):
        mock_faiss, mock_index = _mock_faiss_module
        mock_st_cls, mock_model = _mock_st_class
        with (
            patch.object(sc_module, "_FAISS_AVAILABLE", True),
            patch.object(sc_module, "_SBERT_AVAILABLE", True),
            patch.object(sc_module, "_faiss_lib", mock_faiss),
            patch.object(sc_module, "_SentenceTransformer", mock_st_cls),
        ):
            cache = SemanticCache(persist_path=str(tmp_path / "cache"))
            cache._mock_index = mock_index
            yield cache
            cache.stop()

    def test_enabled_is_true(self, enabled_cache):
        assert enabled_cache.enabled is True

    def test_background_threads_started(self, enabled_cache):
        assert enabled_cache._persist_thread.is_alive()
        assert enabled_cache._sweep_thread.is_alive()

    def test_stop_signals_threads(self, enabled_cache):
        enabled_cache.stop()
        assert enabled_cache._stop.is_set()

    def test_lookup_empty_index_returns_miss(self, enabled_cache):
        enabled_cache._mock_index.ntotal = 0
        result = _run(enabled_cache.lookup(
            tenant_id="acme_corp", domain="general_qa",
            prompt="Hello", similarity_threshold=0.92, ttl_seconds=3600,
        ))
        assert result.hit is False

    def test_store_calls_index_add(self, enabled_cache):
        _run(enabled_cache.store(
            tenant_id="acme_corp", domain="general_qa",
            prompt="Hello", response="Hi", metadata={}, ttl_seconds=3600,
        ))
        enabled_cache._mock_index.add_with_ids.assert_called_once()

    def test_store_adds_to_metadata(self, enabled_cache):
        _run(enabled_cache.store(
            tenant_id="acme_corp", domain="general_qa",
            prompt="Hello", response="Hi", metadata={}, ttl_seconds=3600,
        ))
        assert len(enabled_cache._metadata) == 1

    def test_store_increments_next_id(self, enabled_cache):
        before = enabled_cache._next_id
        _run(enabled_cache.store(
            tenant_id="t", domain="d", prompt="p", response="r",
            metadata={}, ttl_seconds=3600,
        ))
        assert enabled_cache._next_id == before + 1


# ── SemanticCache — internal logic (no faiss required) ────────────────────────

class TestSemanticCacheInternalLogic:
    """
    Tests for internal logic that doesn't depend on faiss being available.
    These test the _lookup_sync / _store_sync / _sweep methods by directly
    constructing a fake-enabled cache and injecting test metadata.
    """

    @pytest.fixture
    def cache_with_injected_state(self, tmp_path, _mock_faiss_module, _mock_st_class):
        """Build cache with full mocks, bypassing FAISS_AVAILABLE guard."""
        mock_faiss, mock_index = _mock_faiss_module
        mock_st_cls, mock_model = _mock_st_class

        with (
            patch.object(sc_module, "_FAISS_AVAILABLE", True),
            patch.object(sc_module, "_SBERT_AVAILABLE", True),
            patch.object(sc_module, "_faiss_lib", mock_faiss),
            patch.object(sc_module, "_SentenceTransformer", mock_st_cls),
        ):
            cache = SemanticCache(persist_path=str(tmp_path / "cache"))
        cache.stop()  # stop background threads immediately
        cache._mock_faiss = mock_faiss
        cache._mock_index = mock_index
        cache._mock_model = mock_model
        yield cache

    def _inject_entry(self, cache, *, tenant_id="acme_corp", domain="general_qa",
                      vid=0, expired=False, similarity=0.99) -> None:
        """Inject a metadata entry and configure the FAISS mock to return it."""
        entry = _make_entry(tenant_id=tenant_id, domain=domain, vid=vid, expired=expired)
        cache._metadata[vid] = entry
        # Configure mock index to return this entry on search
        ids_arr = np.array([[vid]], dtype=np.int64)
        dist_arr = np.array([[similarity]], dtype=np.float32)
        cache._index.ntotal = 1
        cache._index.search.return_value = (dist_arr, ids_arr)

    def test_lookup_hit_above_threshold(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, similarity=0.99)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.hit is True

    def test_lookup_miss_at_threshold(self, cache_with_injected_state):
        """
        Per CLAUDE.md §13.3: 'exceeds' → strict > threshold, not >=.
        Use float64 in mock to avoid float32 rounding (0.92f32 ≈ 0.920000017)
        which would be strictly > 0.92f64, masking the at-equality check.
        """
        cache = cache_with_injected_state
        cache._metadata[0] = _make_entry()
        cache._index.ntotal = 1
        cache._index.search.return_value = (
            np.array([[0.92]], dtype=np.float64),   # exact float64 equality with threshold
            np.array([[0]], dtype=np.int64),
        )
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.hit is False

    def test_lookup_miss_below_threshold(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, similarity=0.91)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.hit is False

    def test_lookup_miss_wrong_tenant(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, tenant_id="other_corp", similarity=0.99)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.hit is False

    def test_lookup_miss_wrong_domain(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, domain="code", similarity=0.99)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.hit is False

    def test_lookup_miss_expired_entry(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, expired=True, similarity=0.99)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.hit is False

    def test_lookup_hit_returns_response(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, similarity=0.95)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.response == "The answer is 42."

    def test_lookup_hit_returns_similarity(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, similarity=0.95)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.similarity == pytest.approx(0.95)

    def test_lookup_hit_returns_metadata(self, cache_with_injected_state):
        cache = cache_with_injected_state
        self._inject_entry(cache, similarity=0.95)
        result = cache._lookup_sync("acme_corp", "general_qa", "prompt", 0.92)
        assert result.metadata is not None
        assert result.metadata["tenant_id"] == "acme_corp"

    def test_sweep_removes_expired_entries(self, cache_with_injected_state):
        cache = cache_with_injected_state
        # Inject two entries: one expired, one valid
        entry_expired = _make_entry(vid=0, expired=True)
        entry_valid = _make_entry(vid=1, expired=False)
        cache._metadata[0] = entry_expired
        cache._metadata[1] = entry_valid
        cache._index.ntotal = 2

        cache._sweep()

        assert 0 not in cache._metadata
        assert 1 in cache._metadata
        cache._index.remove_ids.assert_called_once()

    def test_sweep_noop_when_no_expired(self, cache_with_injected_state):
        cache = cache_with_injected_state
        cache._metadata[0] = _make_entry(vid=0, expired=False)
        cache._index.ntotal = 1
        cache._sweep()
        cache._index.remove_ids.assert_not_called()

    def test_invalidate_removes_matching(self, cache_with_injected_state):
        cache = cache_with_injected_state
        cache._metadata[0] = _make_entry(tenant_id="acme_corp", domain="general_qa", vid=0)
        cache._metadata[1] = _make_entry(tenant_id="demo_tenant", domain="code", vid=1)
        cache._index.ntotal = 2

        removed = cache.invalidate("acme_corp", "general_qa")

        assert removed == 1
        assert 0 not in cache._metadata
        assert 1 in cache._metadata

    def test_invalidate_no_match_returns_zero(self, cache_with_injected_state):
        cache = cache_with_injected_state
        cache._metadata[0] = _make_entry(tenant_id="other", domain="other", vid=0)
        removed = cache.invalidate("acme_corp", "general_qa")
        assert removed == 0


# ── _has_residual_pii (from main.py — tested here because it guards cache usage) ──

class TestHasResidualPii:
    """
    Per CLAUDE.md Section 13.6: cache skipped when post-redaction prompt
    still contains detectable PII (indicates a Presidio miss).
    """

    def _check(self, text: str) -> bool:
        from gateway.main import _has_residual_pii
        return _has_residual_pii(text)

    def test_email_detected(self):
        assert self._check("Please email user@example.com for details.") is True

    def test_ssn_detected(self):
        assert self._check("SSN is 123-45-6789") is True

    def test_credit_card_detected(self):
        assert self._check("Card: 1234-5678-9012-3456") is True

    def test_clean_prompt_no_pii(self):
        assert self._check("What is the capital of France?") is False

    def test_redacted_placeholder_not_pii(self):
        assert self._check("User <EMAIL_ADDRESS> sent a message.") is False

    def test_phone_not_flagged(self):
        # Phone excluded to reduce false positives
        assert self._check("Call 555-123-4567 for help.") is False

    def test_empty_string(self):
        assert self._check("") is False

    def test_code_with_numbers_not_pii(self):
        assert self._check("result = array[0:10] * factor_12345") is False

    def test_multiple_pii_triggers(self):
        # Multiple PII types in same string
        assert self._check("SSN: 123-45-6789 and email: a@b.com") is True
