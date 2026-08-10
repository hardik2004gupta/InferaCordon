"""
Unit tests for PolicyRegistry (policy_engine/loader.py).

Coverage:
  - load_from_dir: loads all valid YAMLs in policies/
  - resolve: exact match returns is_fallback=False
  - resolve: unknown tenant returns is_fallback=True + fallback_reason="unknown_tenant"
  - resolve: known tenant, unknown domain returns is_fallback=True + fallback_reason="unknown_domain"
  - resolve: no match + no default → PolicyNotFoundError
  - Fail-fast: invalid YAML raises PolicyLoadError at startup
  - Fail-fast: missing policy_dir raises PolicyLoadError
  - Fail-fast: empty policy_dir raises PolicyLoadError
  - Fail-fast: duplicate (tenant, domain) pair raises PolicyLoadError
  - Default policy: tenant="default" designated as system fallback
  - list_policies() returns all loaded policies
  - get_default() returns the default policy or None
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from policy_engine.loader import (
    PolicyLoadError,
    PolicyNotFoundError,
    PolicyRegistry,
    PolicyResolution,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

REAL_POLICIES_DIR = Path(__file__).parent.parent.parent / "policy_engine" / "policies"


def _write_yaml(directory: Path, filename: str, content: str) -> Path:
    path = directory / filename
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


VALID_POLICY_YAML = """
policy_id: test_v1
tenant: test_tenant
domain: test_domain
schema_version: 1
budget_profiles:
  low:
    model: qwen25-3b
    max_reasoning_tokens: 0
    max_output_tokens: 256
    verification: none
    context_template: direct
  medium:
    model: deepseek-r1-7b
    max_reasoning_tokens: 512
    max_output_tokens: 512
    verification: verifiable_only
    context_template: step_by_step
  high:
    model: deepseek-r1-7b
    max_reasoning_tokens: 1024
    max_output_tokens: 1024
    verification: required
    context_template: verify_steps
  critical:
    model: deepseek-r1-7b
    max_reasoning_tokens: 2048
    max_output_tokens: 1024
    verification: required
    context_template: verify_steps
complexity_thresholds:
  low_max: 3.5
  medium_max: 6.5
  high_max: 8.5
guardrails:
  pii_redaction: standard
  injection_check: conditional
  safety_check: conditional
  output_safety: async
limits:
  requests_per_minute: 60
  tokens_per_hour: 500000
  max_cost_per_request_usd: 0.05
  max_prompt_tokens: 4096
slo:
  p95_latency_ms: 4000
  quality_floor_score: 3.5
  quality_regression_pp: 1.0
cache:
  enabled: true
  similarity_threshold: 0.92
  ttl_seconds: 3600
escalation:
  enabled: true
  max_retries: 1
  on_exhaustion: return_low_confidence
versions:
  policy: 1
  system_prompt: prompt_v1
  complexity_scorer: scorer_v1
  guardrail_model: llamaguard_onnx_v1
  injection_model: deberta_inject_v1
  verifier: verifier_v1
trace_retention_days: 30
store_reasoning_trace: false
"""

DEFAULT_POLICY_YAML = VALID_POLICY_YAML.replace(
    "tenant: test_tenant", "tenant: default"
).replace(
    "domain: test_domain", "domain: general"
).replace(
    "policy_id: test_v1", "policy_id: default_v1"
)


# ── 1. Load real policy directory ─────────────────────────────────────────────

class TestLoadRealPolicies:

    def test_load_real_policies_dir(self):
        registry = PolicyRegistry.load_from_dir(REAL_POLICIES_DIR)
        assert len(registry) >= 2  # acme_corp, demo_tenant at minimum

    def test_acme_corp_resolvable(self):
        registry = PolicyRegistry.load_from_dir(REAL_POLICIES_DIR)
        result = registry.resolve("acme_corp", "general_qa")
        assert result.policy.tenant == "acme_corp"
        assert result.is_fallback is False
        assert result.fallback_reason is None

    def test_demo_tenant_resolvable(self):
        registry = PolicyRegistry.load_from_dir(REAL_POLICIES_DIR)
        result = registry.resolve("demo_tenant", "general_qa")
        assert result.policy.tenant == "demo_tenant"
        assert result.is_fallback is False

    def test_default_policy_resolvable(self):
        registry = PolicyRegistry.load_from_dir(REAL_POLICIES_DIR)
        default = registry.get_default()
        assert default is not None
        assert default.tenant == "default"

    def test_list_policies_returns_all(self):
        registry = PolicyRegistry.load_from_dir(REAL_POLICIES_DIR)
        policies = registry.list_policies()
        tenants = {p.tenant for p in policies}
        assert "acme_corp" in tenants
        assert "demo_tenant" in tenants

    def test_registry_repr_contains_count(self):
        registry = PolicyRegistry.load_from_dir(REAL_POLICIES_DIR)
        r = repr(registry)
        assert "PolicyRegistry" in r


# ── 2. Resolve: exact match ───────────────────────────────────────────────────

class TestResolveExactMatch:

    def test_exact_match_returns_policy(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("test_tenant", "test_domain")
        assert isinstance(result, PolicyResolution)
        assert result.policy.tenant == "test_tenant"

    def test_exact_match_is_not_fallback(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("test_tenant", "test_domain")
        assert result.is_fallback is False
        assert result.fallback_reason is None

    def test_exact_match_returns_correct_policy_id(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("test_tenant", "test_domain")
        assert result.policy.policy_id == "test_v1"


# ── 3. Resolve: unknown tenant (fallback) ────────────────────────────────────

class TestResolveUnknownTenant:

    def test_unknown_tenant_returns_default(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("unknown_corp", "general_qa")
        assert result.is_fallback is True
        assert result.fallback_reason == "unknown_tenant"

    def test_unknown_tenant_uses_default_policy(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("unknown_corp", "general_qa")
        assert result.policy.tenant == "default"

    def test_unknown_tenant_result_is_named_tuple(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("unknown_corp", "anything")
        assert isinstance(result, PolicyResolution)


# ── 4. Resolve: known tenant, unknown domain ──────────────────────────────────

class TestResolveUnknownDomain:

    def test_known_tenant_unknown_domain_returns_fallback(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("test_tenant", "nonexistent_domain")
        assert result.is_fallback is True
        assert result.fallback_reason == "unknown_domain"

    def test_known_tenant_unknown_domain_uses_default(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        result = registry.resolve("test_tenant", "nonexistent_domain")
        assert result.policy.tenant == "default"


# ── 5. No match and no default → PolicyNotFoundError ─────────────────────────

class TestPolicyNotFoundError:

    def test_no_match_no_default_raises(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        # No default policy file
        registry = PolicyRegistry.load_from_dir(tmp_path)
        with pytest.raises(PolicyNotFoundError) as exc_info:
            registry.resolve("unknown_corp", "unknown_domain")
        assert "unknown_corp" in str(exc_info.value)
        assert "unknown_domain" in str(exc_info.value)

    def test_policy_not_found_error_has_tenant_attr(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        with pytest.raises(PolicyNotFoundError) as exc_info:
            registry.resolve("nobody", "nowhere")
        assert exc_info.value.tenant_id == "nobody"
        assert exc_info.value.domain == "nowhere"


# ── 6. Fail-fast: invalid YAML ────────────────────────────────────────────────

class TestFailFastInvalidYAML:

    def test_invalid_yaml_syntax_raises_at_startup(self, tmp_path):
        _write_yaml(tmp_path, "bad.yaml", "this: is: not: valid: yaml: :\n  - [\n")
        with pytest.raises(PolicyLoadError):
            PolicyRegistry.load_from_dir(tmp_path)

    def test_invalid_schema_raises_at_startup(self, tmp_path):
        _write_yaml(tmp_path, "bad.yaml", VALID_POLICY_YAML.replace(
            "policy_id: test_v1", ""  # Remove required field
        ))
        with pytest.raises(PolicyLoadError):
            PolicyRegistry.load_from_dir(tmp_path)

    def test_invalid_model_name_raises_at_startup(self, tmp_path):
        _write_yaml(tmp_path, "bad.yaml", VALID_POLICY_YAML.replace(
            "model: deepseek-r1-7b", "model: gpt-4"
        ))
        with pytest.raises(PolicyLoadError):
            PolicyRegistry.load_from_dir(tmp_path)

    def test_error_message_contains_filename(self, tmp_path):
        _write_yaml(tmp_path, "broken_policy.yaml", VALID_POLICY_YAML.replace(
            "model: deepseek-r1-7b", "model: gpt-4"
        ))
        with pytest.raises(PolicyLoadError) as exc_info:
            PolicyRegistry.load_from_dir(tmp_path)
        assert "broken_policy.yaml" in str(exc_info.value)

    def test_valid_files_not_loaded_when_one_is_invalid(self, tmp_path):
        _write_yaml(tmp_path, "good.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "bad.yaml", VALID_POLICY_YAML.replace(
            "model: deepseek-r1-7b", "model: gpt-4"
        ))
        with pytest.raises(PolicyLoadError):
            PolicyRegistry.load_from_dir(tmp_path)


# ── 7. Fail-fast: directory issues ────────────────────────────────────────────

class TestFailFastDirectory:

    def test_nonexistent_dir_raises(self, tmp_path):
        with pytest.raises(PolicyLoadError) as exc_info:
            PolicyRegistry.load_from_dir(tmp_path / "does_not_exist")
        assert "does not exist" in str(exc_info.value)

    def test_empty_dir_raises(self, tmp_path):
        with pytest.raises(PolicyLoadError) as exc_info:
            PolicyRegistry.load_from_dir(tmp_path)
        assert "No *.yaml" in str(exc_info.value)

    def test_file_path_instead_of_dir_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(PolicyLoadError) as exc_info:
            PolicyRegistry.load_from_dir(f)
        assert "not a directory" in str(exc_info.value)


# ── 8. Fail-fast: duplicate (tenant, domain) ─────────────────────────────────

class TestDuplicatePolicies:

    def test_duplicate_tenant_domain_raises_at_startup(self, tmp_path):
        _write_yaml(tmp_path, "policy_a.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "policy_b.yaml", VALID_POLICY_YAML.replace(
            "policy_id: test_v1", "policy_id: test_v2"
        ))  # Same tenant+domain, different policy_id
        with pytest.raises(PolicyLoadError) as exc_info:
            PolicyRegistry.load_from_dir(tmp_path)
        assert "duplicate" in str(exc_info.value).lower()


# ── 9. Default policy management ──────────────────────────────────────────────

class TestDefaultPolicy:

    def test_get_default_returns_none_when_absent(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        assert registry.get_default() is None

    def test_get_default_returns_policy_when_present(self, tmp_path):
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        default = registry.get_default()
        assert default is not None
        assert default.tenant == "default"

    def test_default_policy_not_in_list_policies(self, tmp_path):
        # Default policy IS in list_policies() (it's a real policy with tenant="default")
        _write_yaml(tmp_path, "policy.yaml", VALID_POLICY_YAML)
        _write_yaml(tmp_path, "default.yaml", DEFAULT_POLICY_YAML)
        registry = PolicyRegistry.load_from_dir(tmp_path)
        all_policies = registry.list_policies()
        tenants = {p.tenant for p in all_policies}
        assert "default" in tenants  # default IS included in the registry
