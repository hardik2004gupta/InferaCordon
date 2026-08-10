"""
Unit tests for gateway/auth.py.

Tests cover:
- load_tenant_key_map: YAML loading, env fallback, malformed YAML, missing file
- verify_api_key: Bearer extraction, tenant resolution, 401 cases

Per Phase 4 Section 24 — auth boundary must be hard: invalid keys must NOT
proceed to downstream processing.
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from gateway.auth import load_tenant_key_map, verify_api_key


# ── load_tenant_key_map ─────────────────────────────────────────────────────────

class TestLoadTenantKeyMap:
    def test_loads_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            api_keys:
              ic-key-test: test_tenant
              ic-key-demo: demo_tenant
        """))
        result = load_tenant_key_map(str(yaml_file))
        assert result == {
            "ic-key-test": "test_tenant",
            "ic-key-demo": "demo_tenant",
        }

    def test_returns_empty_dict_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TENANT_API_KEYS", raising=False)
        result = load_tenant_key_map(str(tmp_path / "nonexistent.yaml"))
        assert result == {}

    def test_returns_empty_dict_on_malformed_yaml(self, tmp_path):
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text(":::not valid yaml:::")
        result = load_tenant_key_map(str(yaml_file))
        assert result == {}

    def test_returns_empty_dict_when_api_keys_missing(self, tmp_path):
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text("some_other_key: value\n")
        result = load_tenant_key_map(str(yaml_file))
        assert result == {}

    def test_returns_empty_dict_when_api_keys_not_a_dict(self, tmp_path):
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text("api_keys:\n  - item1\n  - item2\n")
        result = load_tenant_key_map(str(yaml_file))
        assert result == {}

    def test_env_fallback_when_yaml_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TENANT_API_KEYS", "key1:tenant_a,key2:tenant_b")
        result = load_tenant_key_map(str(tmp_path / "nonexistent.yaml"))
        assert result == {"key1": "tenant_a", "key2": "tenant_b"}

    def test_env_fallback_ignores_malformed_pairs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TENANT_API_KEYS", "good-key:tenant_a,bad_pair,another:tenant_b")
        result = load_tenant_key_map(str(tmp_path / "nonexistent.yaml"))
        assert "good-key" in result
        assert "another" in result
        # "bad_pair" has no colon — skipped
        assert "bad_pair" not in result

    def test_yaml_takes_priority_over_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TENANT_API_KEYS", "env-key:env_tenant")
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text("api_keys:\n  yaml-key: yaml_tenant\n")
        result = load_tenant_key_map(str(yaml_file))
        # YAML exists → env var should NOT be consulted
        assert "yaml-key" in result
        assert "env-key" not in result

    def test_skips_blank_keys_or_values(self, tmp_path):
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text("api_keys:\n  good-key: tenant_a\n  '': blank_tenant\n")
        result = load_tenant_key_map(str(yaml_file))
        # blank key should be filtered
        assert "good-key" in result
        assert "" not in result

    def test_keys_are_strings(self, tmp_path):
        yaml_file = tmp_path / "tenants.yaml"
        yaml_file.write_text("api_keys:\n  123: numeric_key_tenant\n")
        result = load_tenant_key_map(str(yaml_file))
        assert "123" in result


# ── verify_api_key ──────────────────────────────────────────────────────────────

class _MockGatewayState:
    def __init__(self, tenant_key_map):
        self.tenant_key_map = tenant_key_map


class _MockAppState:
    def __init__(self, tenant_key_map):
        self.gateway = _MockGatewayState(tenant_key_map)


class _MockRequest:
    def __init__(self, auth_header: str, tenant_key_map: dict):
        self.headers = {"Authorization": auth_header}
        self.app = type("App", (), {"state": _MockAppState(tenant_key_map)})()


async def _call_verify(auth_header: str, key_map: dict) -> str:
    """Helper: invoke verify_api_key and return tenant_id on success."""
    import httpx
    from starlette.requests import Request
    from starlette.testclient import TestClient
    from fastapi import FastAPI, Depends
    from fastapi.responses import JSONResponse

    # Use a minimal FastAPI app to test the dependency correctly
    app = FastAPI()
    app.state.gateway = _MockGatewayState(key_map)

    @app.get("/test")
    async def endpoint(tenant_id: str = Depends(verify_api_key)):
        return {"tenant_id": tenant_id}

    client = TestClient(app, raise_server_exceptions=False)
    headers = {}
    if auth_header is not None:
        headers["Authorization"] = auth_header
    resp = client.get("/test", headers=headers)
    return resp


class TestVerifyApiKey:
    def test_valid_key_returns_tenant_id(self):
        resp = _call_verify_sync("Bearer ic-key-test", {"ic-key-test": "acme_corp"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "acme_corp"

    def test_missing_authorization_header_returns_401(self):
        resp = _call_verify_sync(None, {"ic-key-test": "acme_corp"})
        assert resp.status_code == 401

    def test_wrong_scheme_returns_401(self):
        resp = _call_verify_sync("Token ic-key-test", {"ic-key-test": "acme_corp"})
        assert resp.status_code == 401

    def test_empty_key_returns_401(self):
        resp = _call_verify_sync("Bearer ", {"ic-key-test": "acme_corp"})
        assert resp.status_code == 401

    def test_unknown_key_returns_401(self):
        resp = _call_verify_sync("Bearer unknown-key", {"ic-key-test": "acme_corp"})
        assert resp.status_code == 401

    def test_empty_key_map_returns_401(self):
        resp = _call_verify_sync("Bearer ic-key-test", {})
        assert resp.status_code == 401

    def test_error_body_contains_error_field(self):
        resp = _call_verify_sync("Bearer bad-key", {"ic-key-test": "acme_corp"})
        assert resp.status_code == 401
        data = resp.json()
        assert "error" in data.get("detail", data)


def _call_verify_sync(auth_header, key_map):
    """Synchronous wrapper using TestClient."""
    from fastapi import FastAPI, Depends
    from starlette.testclient import TestClient

    app = FastAPI()
    app.state.gateway = _MockGatewayState(key_map)

    @app.get("/test")
    async def endpoint(tenant_id: str = Depends(verify_api_key)):
        return {"tenant_id": tenant_id}

    client = TestClient(app, raise_server_exceptions=False)
    headers = {}
    if auth_header is not None:
        headers["Authorization"] = auth_header
    return client.get("/test", headers=headers)
