"""
API key authentication and tenant ID resolution.

Per CLAUDE.md Section 6 (Step 1):
- Extract Bearer token from Authorization header
- Resolve token → tenant_id via in-memory dict loaded from tenants.yaml at startup
- Return 401 on missing or invalid key
- Tenant identity is established here; downstream components receive tenant_id, not the key

Key map source priority:
  1. tenants.yaml  (canonical per CLAUDE.md — "loaded from tenants.yaml at startup")
  2. TENANT_API_KEYS env var (comma-separated key:tenant pairs — development fallback)

File name: auth.py (per Part IX authoritative layout).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import yaml
from fastapi import HTTPException, Request

log = logging.getLogger(__name__)


def load_tenant_key_map(
    tenants_yaml_path: str | Path = "tenants.yaml",
) -> dict[str, str]:
    """
    Load the API key → tenant_id mapping.

    Per CLAUDE.md Section 6 Step 1:
      "The auth middleware resolves the Authorization header API key against
       an in-memory dictionary loaded from tenants.yaml at startup."

    Falls back to TENANT_API_KEYS environment variable when tenants.yaml is absent
    (development / CI convenience). Format: "key1:tenant1,key2:tenant2".

    Returns an empty dict (no tenants) rather than raising — the gateway starts
    but all requests will fail 401 until a valid key is configured.
    """
    path = Path(tenants_yaml_path)

    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.error("Failed to parse tenants.yaml: %s — all requests will 401", exc)
            return {}
        if not isinstance(raw, dict) or "api_keys" not in raw:
            log.error(
                "tenants.yaml has unexpected format (expected top-level 'api_keys' mapping). "
                "All requests will 401."
            )
            return {}
        keys = raw.get("api_keys", {})
        if not isinstance(keys, dict):
            log.error("tenants.yaml 'api_keys' must be a dict. All requests will 401.")
            return {}
        result = {str(k): str(v) for k, v in keys.items() if k and v}
        log.info("Loaded %d API keys from %s", len(result), path)
        return result

    # Fallback: TENANT_API_KEYS env var
    env_val = os.environ.get("TENANT_API_KEYS", "")
    if env_val:
        result: dict[str, str] = {}
        for pair in env_val.split(","):
            pair = pair.strip()
            if ":" in pair:
                key, tenant = pair.split(":", 1)
                result[key.strip()] = tenant.strip()
        if result:
            log.info(
                "tenants.yaml not found — loaded %d API keys from TENANT_API_KEYS env var",
                len(result),
            )
            return result

    log.warning(
        "No tenants.yaml found at %s and TENANT_API_KEYS env var is empty. "
        "All authenticated requests will receive 401.",
        path.absolute(),
    )
    return {}


async def verify_api_key(request: Request) -> str:
    """
    Dependency: Extract Bearer token → resolve tenant_id.
    Returns tenant_id for valid key. Raises 401 for missing/invalid key.
    Per CLAUDE.md Section 6 Step 1.

    Auth failures MUST NOT proceed to complexity scoring, policy resolution,
    inference, or audit decision execution (per Phase 4 Section 24).
    """
    auth_header: str = request.headers.get("Authorization", "")

    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_authorization_header", "request_id": None},
        )

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_authorization_format",
                "detail": "Authorization header must use Bearer scheme",
                "request_id": None,
            },
        )

    api_key = auth_header[len("Bearer "):]
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "empty_api_key", "request_id": None},
        )

    # Resolve tenant from app-level key map (loaded at startup)
    # Stored under app.state.gateway per the AppState contract in main.py
    tenant_key_map: dict[str, str] = request.app.state.gateway.tenant_key_map
    tenant_id: Optional[str] = tenant_key_map.get(api_key)

    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_api_key", "request_id": None},
        )

    return tenant_id
