"""
API key authentication and tenant ID resolution.

Per CLAUDE.md Section 6 (Step 1):
- Extract Bearer token from Authorization header
- Resolve token → tenant_id via TENANT_API_KEYS env variable (key:tenant pairs)
- Return 401 on missing or invalid key
- Attach tenant_id to request state for downstream use
"""
from __future__ import annotations

from fastapi import Request, HTTPException


async def verify_api_key(request: Request) -> str:
    """Return tenant_id for a valid Bearer token, raise 401 otherwise."""
    raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 1 (Week 1)")


def load_tenant_key_map() -> dict[str, str]:
    """Parse TENANT_API_KEYS env var into {api_key: tenant_id} dict."""
    raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 1 (Week 1)")
