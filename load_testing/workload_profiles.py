"""
Workload profiles for load testing.

Profiles define tenant, domain, prompt mix, and expected budget class distribution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkloadProfile:
    name: str
    tenant_id: str
    domain: str
    rps_target: float
    prompt_mix: dict[str, float]     # {budget_class: fraction}
    expected_cache_hit_rate: float


STANDARD_PROFILE = WorkloadProfile(
    name="standard",
    tenant_id="acme_corp",
    domain="general_qa",
    rps_target=10.0,
    prompt_mix={"low": 0.4, "medium": 0.4, "high": 0.15, "critical": 0.05},
    expected_cache_hit_rate=0.30,
)

BURST_PROFILE = WorkloadProfile(
    name="burst",
    tenant_id="acme_corp",
    domain="general_qa",
    rps_target=50.0,
    prompt_mix={"low": 0.6, "medium": 0.3, "high": 0.08, "critical": 0.02},
    expected_cache_hit_rate=0.50,
)
