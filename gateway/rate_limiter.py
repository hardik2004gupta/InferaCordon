"""
Per-tenant rate limiting.

Per CLAUDE.md Section 6 (Step 2):
- Token-bucket algorithm, in-memory, per-tenant
- Limits sourced from policy (requests_per_minute, tokens_per_hour)
- Return 429 with Retry-After header on limit exceeded
- Emit ic_rate_limit_exceeded_total metric (CLAUDE.md Section 18)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill_ts: float = field(init=False)

    def __post_init__(self) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 2 (Week 1)")

    def consume(self, tokens: float = 1.0) -> bool:
        """Return True if tokens available and consumed, False if rate-limited."""
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 2 (Week 1)")


class RateLimiter:
    """In-memory per-tenant rate limiter backed by token buckets."""

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, tenant_id: str, rpm_limit: int, tph_limit: int) -> None:
        """Raise 429 HTTPException if tenant is rate-limited."""
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 2 (Week 1)")
