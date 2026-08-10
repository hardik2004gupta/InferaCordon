"""
Policy registry: discovers, loads, validates, and serves YAML policy files.

Per CLAUDE.md Section 11:
- Scans POLICY_DIR for *.yaml files at process start
- Validates each file against the Pydantic schema (validator.py)
- Builds an in-memory registry keyed by (tenant, domain) → Policy
- Policies are immutable after load (CLAUDE.md Section 11.4)
- Startup fails with a clear error if any policy is invalid (CLAUDE.md Section 11.3)
- A policy update requires a gateway restart (CLAUDE.md Section 11.4)

Unknown tenant/domain behavior per CLAUDE.md Section 17 (Failure Mode 7):
- Key lookup miss → return system default policy + flag it as a fallback
- Gateway logs the audit event; this registry only signals the fallback condition
- The "default" policy is the one with tenant="default" in the loaded policy set
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple, Optional

import yaml

from policy_engine.validator import Policy

log = logging.getLogger(__name__)

_DEFAULT_TENANT = "default"


# ── Resolution result ──────────────────────────────────────────────────────────

class PolicyResolution(NamedTuple):
    """Result of resolving a (tenant, domain) pair to a policy."""
    policy: Policy
    is_fallback: bool       # True when system default was used (CLAUDE.md Section 17 FM7)
    fallback_reason: Optional[str]  # "unknown_tenant" | "unknown_domain" | None


# ── Custom exceptions ──────────────────────────────────────────────────────────

class PolicyLoadError(Exception):
    """Raised at startup when a policy YAML file fails validation."""


class PolicyNotFoundError(Exception):
    """Raised when no policy and no default is available for a tenant+domain."""
    def __init__(self, tenant_id: str, domain: str) -> None:
        self.tenant_id = tenant_id
        self.domain = domain
        super().__init__(
            f"No policy found for tenant={tenant_id!r} domain={domain!r} "
            "and no system default policy is configured. "
            "Add a policy with tenant='default' to policy_dir to enable fallback."
        )


# ── Policy Registry ────────────────────────────────────────────────────────────

class PolicyRegistry:
    """
    In-process policy registry. NOT a service. NOT HTTP-accessible.

    Per CLAUDE.md Section 3: "Policy engine is in-process — Python library
    imported directly by the gateway — not a service."

    Lifecycle:
    1. Created at gateway startup via PolicyRegistry.load_from_dir()
    2. Held in memory for the process lifetime
    3. Replaced only by a full gateway restart (policy update protocol)
    """

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], Policy] = {}
        self._default: Optional[Policy] = None

    @classmethod
    def load_from_dir(cls, policy_dir: str | Path) -> "PolicyRegistry":
        """
        Load all *.yaml policy files from policy_dir.
        Raises PolicyLoadError at startup on any invalid file.

        Per CLAUDE.md Section 11.3: "The gateway does not start with an invalid policy file."
        """
        registry = cls()
        dir_path = Path(policy_dir)

        if not dir_path.exists():
            raise PolicyLoadError(
                f"Policy directory does not exist: {dir_path}. "
                "Set POLICY_DIR environment variable or create the directory."
            )
        if not dir_path.is_dir():
            raise PolicyLoadError(f"Policy path is not a directory: {dir_path}")

        yaml_files = sorted(dir_path.glob("*.yaml"))
        if not yaml_files:
            raise PolicyLoadError(
                f"No *.yaml policy files found in {dir_path}. "
                "At least one policy file is required."
            )

        loaded: list[str] = []
        errors: list[str] = []

        for yaml_file in yaml_files:
            try:
                policy = _load_and_validate(yaml_file)
                key = (policy.tenant, policy.domain)
                if key in registry._registry:
                    errors.append(
                        f"{yaml_file.name}: duplicate policy for "
                        f"tenant={policy.tenant!r} domain={policy.domain!r} "
                        f"(already loaded from another file)"
                    )
                    continue
                registry._registry[key] = policy
                loaded.append(f"{yaml_file.name} → ({policy.tenant}, {policy.domain}) v{policy.versions.policy}")
                if policy.tenant == _DEFAULT_TENANT:
                    if registry._default is not None:
                        errors.append(
                            f"{yaml_file.name}: multiple default policies found "
                            "(only one policy with tenant='default' is allowed)"
                        )
                    else:
                        registry._default = policy
                        log.info("System default policy loaded: %s", yaml_file.name)
            except Exception as exc:
                errors.append(f"{yaml_file.name}: {exc}")

        if errors:
            error_block = "\n  ".join(errors)
            raise PolicyLoadError(
                f"Policy startup validation failed — gateway cannot start:\n  {error_block}"
            )

        log.info("PolicyRegistry loaded %d policies: %s", len(loaded), loaded)
        return registry

    def resolve(self, tenant_id: str, domain: str) -> PolicyResolution:
        """
        Resolve the policy for (tenant_id, domain).

        Returns PolicyResolution:
        - is_fallback=False when an exact match exists
        - is_fallback=True when the system default is used (Failure Mode 7)

        Raises PolicyNotFoundError when no match and no default exists.
        Per CLAUDE.md Section 17 Failure Mode 7.
        """
        policy = self._registry.get((tenant_id, domain))
        if policy is not None:
            return PolicyResolution(policy=policy, is_fallback=False, fallback_reason=None)

        # Determine fallback reason for audit event
        known_tenant = any(t == tenant_id for t, _ in self._registry)
        fallback_reason = "unknown_domain" if known_tenant else "unknown_tenant"

        if self._default is not None:
            log.warning(
                "Policy engine fallback: no policy for tenant=%r domain=%r (%s). "
                "Using system default policy %r. Audit event required.",
                tenant_id, domain, fallback_reason, self._default.policy_id,
            )
            return PolicyResolution(
                policy=self._default,
                is_fallback=True,
                fallback_reason=fallback_reason,
            )

        raise PolicyNotFoundError(tenant_id, domain)

    def list_policies(self) -> list[Policy]:
        """Return all loaded policies (for admin/Policy Manager endpoint)."""
        return list(self._registry.values())

    def get_default(self) -> Optional[Policy]:
        """Return the system default policy, or None if not configured."""
        return self._default

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self) -> str:
        keys = list(self._registry.keys())
        return f"PolicyRegistry({len(keys)} policies: {keys})"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_and_validate(yaml_file: Path) -> Policy:
    """Load and Pydantic-validate a single policy YAML file."""
    try:
        raw = yaml_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyLoadError(f"Cannot read {yaml_file}: {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PolicyLoadError(f"YAML parse error in {yaml_file}: {exc}") from exc

    if not isinstance(data, dict):
        raise PolicyLoadError(
            f"{yaml_file}: top-level YAML must be a mapping (got {type(data).__name__})"
        )

    try:
        policy = Policy.model_validate(data)
    except Exception as exc:
        raise PolicyLoadError(
            f"Schema validation failed for {yaml_file}:\n{exc}"
        ) from exc

    return policy
