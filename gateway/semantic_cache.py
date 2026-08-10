"""
In-process semantic cache backed by FAISS IndexFlatIP (IndexIDMap2 wrapper).

Per CLAUDE.md Section 13:
- Embedding model: all-MiniLM-L6-v2 (sentence-transformers, 22MB, CPU)
- Similarity metric: cosine similarity via IndexFlatIP + L2-normalised embeddings
- Hit threshold: configurable per policy (default 0.92); CLAUDE.md uses "exceeds" → strict >
- Persistence: flush to disk every 5 minutes (FAISS binary + JSON metadata)
- Sweep: remove TTL-expired entries every 60 seconds
- Tenant + domain isolation: a hit is only returned when both match
- Disabled automatically when faiss-cpu is not installed (all lookups = miss, stores = no-op)
- NOT a separate service — runs entirely in-process in the gateway

CLAUDE.md Section 13.6 safety restrictions:
  - Cache never used when policy.cache.enabled = false
  - Cache never used for requests with detectable PII in post-redaction prompt
  - High-risk domains set cache.enabled = false

CLAUDE.md Section 16.3 stop reason: "cache_hit"
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# ── Optional dependency gates ─────────────────────────────────────────────────

try:
    import faiss as _faiss_lib  # type: ignore[import]
    _FAISS_AVAILABLE = True
except ImportError:
    _faiss_lib = None
    _FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore[import]
    _SBERT_AVAILABLE = True
except ImportError:
    _SentenceTransformer = None  # type: ignore[assignment,misc]
    _SBERT_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────

_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_EMBEDDING_DIM = 384


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CacheEntry:
    """One semantic cache entry stored alongside its FAISS vector."""
    vector_id: int
    response: str
    tenant_id: str
    domain: str
    created_at: float
    expires_at: float
    response_metadata: dict = field(default_factory=dict)

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at

    def to_metadata_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass
class CacheLookupResult:
    """Result of a cache lookup. hit=False means no usable entry found."""
    hit: bool
    response: Optional[str] = None
    similarity: Optional[float] = None
    metadata: Optional[dict] = None


# ── Semantic cache ─────────────────────────────────────────────────────────────

class SemanticCache:
    """
    FAISS IndexIDMap2-backed in-process semantic cache.

    Automatically disabled when faiss-cpu or sentence-transformers is not
    installed — all lookups return CacheLookupResult(hit=False) and all
    stores are silent no-ops.  This matches the Phase 5 pattern where ONNX
    unavailability triggers a graceful heuristic fallback.

    Thread safety: a single threading.Lock protects all FAISS and metadata
    mutations.  Embedding (CPU-bound, ~15 ms) is off-loaded to a thread pool
    via asyncio.to_thread so the event loop is never blocked.
    """

    def __init__(
        self,
        persist_path: str,
        persist_interval_seconds: int = 300,
        sweep_interval_seconds: int = 60,
    ) -> None:
        self._persist_dir = Path(persist_path)
        self._persist_interval = persist_interval_seconds
        self._sweep_interval = sweep_interval_seconds
        self._index_path = self._persist_dir / "faiss.index"
        self._meta_path = self._persist_dir / "metadata.json"

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._enabled = False
        self._model = None
        self._index = None
        self._metadata: dict[int, CacheEntry] = {}
        self._next_id = 0

        if not _FAISS_AVAILABLE:
            log.warning(
                "faiss-cpu not installed — semantic cache DISABLED "
                "(pip install faiss-cpu to enable; CLAUDE.md Section 13)"
            )
            return

        if not _SBERT_AVAILABLE:
            log.warning(
                "sentence-transformers not installed — semantic cache DISABLED "
                "(pip install sentence-transformers; CLAUDE.md Section 13)"
            )
            return

        try:
            self._model = _SentenceTransformer(_EMBEDDING_MODEL)
        except Exception as exc:
            log.warning(
                "Failed to load embedding model %r: %s — cache DISABLED",
                _EMBEDDING_MODEL, exc,
            )
            return

        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            inner = _faiss_lib.IndexFlatIP(_EMBEDDING_DIM)
            self._index = _faiss_lib.IndexIDMap2(inner)
            self._load()
        except Exception as exc:
            log.warning("Failed to initialise FAISS index: %s — cache DISABLED", exc)
            return

        self._enabled = True
        log.info(
            "SemanticCache enabled — model=%s dim=%d persist=%s interval=%ds sweep=%ds",
            _EMBEDDING_MODEL, _EMBEDDING_DIM, self._persist_dir,
            persist_interval_seconds, sweep_interval_seconds,
        )

        self._persist_thread = threading.Thread(
            target=self._persist_loop, daemon=True, name="cache-persist"
        )
        self._sweep_thread = threading.Thread(
            target=self._sweep_loop, daemon=True, name="cache-sweep"
        )
        self._persist_thread.start()
        self._sweep_thread.start()

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def lookup(
        self,
        tenant_id: str,
        domain: str,
        prompt: str,
        similarity_threshold: float,
        ttl_seconds: int,
    ) -> CacheLookupResult:
        """
        Async cache lookup.  Offloads embedding to thread pool.

        Returns CacheLookupResult(hit=True) only when:
        - A stored embedding has inner-product similarity *strictly greater than*
          similarity_threshold (per CLAUDE.md Section 13.3 "exceeds")
        - The matching entry belongs to the same tenant and domain
        - The entry has not expired

        Searches up to k=10 nearest neighbours and returns the first that passes
        all three filters — handles the case where the most-similar vector belongs
        to a different tenant.
        """
        if not self._enabled:
            return CacheLookupResult(hit=False)
        try:
            return await asyncio.to_thread(
                self._lookup_sync,
                tenant_id, domain, prompt, similarity_threshold,
            )
        except Exception as exc:
            log.warning("Cache lookup failed (fail-open): %s", exc)
            return CacheLookupResult(hit=False)

    async def store(
        self,
        tenant_id: str,
        domain: str,
        prompt: str,
        response: str,
        metadata: dict,
        ttl_seconds: int,
    ) -> None:
        """
        Async cache store.  Offloads embedding to thread pool.
        Per CLAUDE.md Section 13.4: called after response delivery, never blocks serving.
        """
        if not self._enabled:
            return
        try:
            await asyncio.to_thread(
                self._store_sync,
                tenant_id, domain, prompt, response, metadata, ttl_seconds,
            )
        except Exception as exc:
            log.warning("Cache store failed (fail-open): %s", exc)

    def invalidate(self, tenant_id: str, domain: str) -> int:
        """
        Remove all cache entries for a tenant/domain.
        Returns the number of entries removed.
        """
        if not self._enabled:
            return 0
        with self._lock:
            to_remove = [
                vid for vid, entry in self._metadata.items()
                if entry.tenant_id == tenant_id and entry.domain == domain
            ]
            if not to_remove:
                return 0
            ids = np.array(to_remove, dtype=np.int64)
            self._index.remove_ids(ids)
            for vid in to_remove:
                del self._metadata[vid]
            return len(to_remove)

    def stop(self) -> None:
        """
        Signal background threads to stop and flush to disk.
        Call during gateway shutdown.
        """
        self._stop.set()
        if self._enabled:
            self._flush()

    # ── Synchronous internals (run in thread pool from async callers) ─────────

    def _embed(self, text: str) -> np.ndarray:
        """Encode text to L2-normalised float32 vector, shape (1, 384)."""
        vec = self._model.encode(
            [text], normalize_embeddings=True, show_progress_bar=False
        )
        return vec.astype(np.float32)

    def _lookup_sync(
        self,
        tenant_id: str,
        domain: str,
        prompt: str,
        similarity_threshold: float,
    ) -> CacheLookupResult:
        query = self._embed(prompt)
        with self._lock:
            if self._index.ntotal == 0:
                return CacheLookupResult(hit=False)
            k = min(10, self._index.ntotal)
            distances, indices = self._index.search(query, k)
            now = time.time()
            for i in range(k):
                idx = int(indices[0][i])
                if idx < 0:
                    break
                similarity = float(distances[0][i])
                if similarity <= similarity_threshold:
                    break
                entry = self._metadata.get(idx)
                if entry is None:
                    continue
                if entry.tenant_id != tenant_id or entry.domain != domain:
                    continue
                if entry.is_expired(now):
                    continue
                return CacheLookupResult(
                    hit=True,
                    response=entry.response,
                    similarity=similarity,
                    metadata=entry.to_metadata_dict(),
                )
        return CacheLookupResult(hit=False)

    def _store_sync(
        self,
        tenant_id: str,
        domain: str,
        prompt: str,
        response: str,
        metadata: dict,
        ttl_seconds: int,
    ) -> None:
        vec = self._embed(prompt)
        now = time.time()
        with self._lock:
            vid = self._next_id
            self._next_id += 1
            entry = CacheEntry(
                vector_id=vid,
                response=response,
                tenant_id=tenant_id,
                domain=domain,
                created_at=now,
                expires_at=now + ttl_seconds,
                response_metadata=metadata,
            )
            ids = np.array([vid], dtype=np.int64)
            self._index.add_with_ids(vec, ids)
            self._metadata[vid] = entry

    # ── Persistence ───────────────────────────────────────────────────────────

    def _flush(self) -> None:
        """Write FAISS index + JSON metadata to the persist directory."""
        if not self._enabled:
            return
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            with self._lock:
                _faiss_lib.write_index(self._index, str(self._index_path))
                serialisable = {
                    str(vid): {
                        "vector_id": e.vector_id,
                        "response": e.response,
                        "tenant_id": e.tenant_id,
                        "domain": e.domain,
                        "created_at": e.created_at,
                        "expires_at": e.expires_at,
                        "response_metadata": e.response_metadata,
                    }
                    for vid, e in self._metadata.items()
                }
                serialisable["__next_id__"] = self._next_id
                with open(self._meta_path, "w", encoding="utf-8") as f:
                    json.dump(serialisable, f)
        except Exception as exc:
            log.warning("Cache persist failed: %s", exc)

    def _load(self) -> None:
        """Restore index and metadata from disk at startup."""
        if not (self._index_path.exists() and self._meta_path.exists()):
            return
        try:
            loaded = _faiss_lib.read_index(str(self._index_path))
            with open(self._meta_path, encoding="utf-8") as f:
                raw = json.load(f)
            now = time.time()
            restored: dict[int, CacheEntry] = {}
            max_id = 0
            next_id = raw.pop("__next_id__", 0)
            for vid_str, data in raw.items():
                vid = int(vid_str)
                entry = CacheEntry(
                    vector_id=data["vector_id"],
                    response=data["response"],
                    tenant_id=data["tenant_id"],
                    domain=data["domain"],
                    created_at=data["created_at"],
                    expires_at=data["expires_at"],
                    response_metadata=data.get("response_metadata", {}),
                )
                if not entry.is_expired(now):
                    restored[vid] = entry
                    max_id = max(max_id, vid)
            self._index = loaded
            self._metadata = restored
            self._next_id = max(next_id, max_id + 1)
            log.info(
                "SemanticCache restored %d entries from %s",
                len(restored), self._persist_dir,
            )
        except Exception as exc:
            log.warning(
                "Cache restore failed (%s) — starting with empty cache", exc
            )

    # ── Background threads ────────────────────────────────────────────────────

    def _persist_loop(self) -> None:
        """Flush to disk every persist_interval_seconds."""
        while not self._stop.wait(self._persist_interval):
            self._flush()

    def _sweep_loop(self) -> None:
        """Remove TTL-expired entries every sweep_interval_seconds."""
        while not self._stop.wait(self._sweep_interval):
            self._sweep()

    def _sweep(self) -> None:
        """Remove expired entries from FAISS index and metadata dict."""
        if not self._enabled:
            return
        now = time.time()
        with self._lock:
            expired = [
                vid for vid, entry in self._metadata.items()
                if entry.is_expired(now)
            ]
            if not expired:
                return
            ids = np.array(expired, dtype=np.int64)
            self._index.remove_ids(ids)
            for vid in expired:
                del self._metadata[vid]
        log.debug("Cache sweep removed %d expired entries", len(expired))
