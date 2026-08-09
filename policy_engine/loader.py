"""
Policy loader: discovers, loads, and validates YAML policy files at startup.

Per CLAUDE.md Section 11:
- Scans POLICY_DIR for *.yaml files at process start
- Validates each file against the Pydantic schema (see validator.py)
- Builds in-memory dict keyed by (tenant_id, domain) → Policy
- Policies are immutable after load; version bump required for any change
- Startup fails with clear error if any policy is invalid (fail-fast)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class PolicyLoader:
    """Loads and indexes all YAML policies from POLICY_DIR."""

    def __init__(self, policy_dir: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 11 (Week 1)")

    def load_all(self) -> dict[tuple[str, str], Any]:
        """Return {(tenant_id, domain): validated Policy} dict. Raises on any invalid file."""
        raise NotImplementedError("Implement per CLAUDE.md Section 11 (Week 1)")

    def get(self, tenant_id: str, domain: str) -> Any:
        """Return policy for (tenant_id, domain) or raise KeyError."""
        raise NotImplementedError("Implement per CLAUDE.md Section 11 (Week 1)")
