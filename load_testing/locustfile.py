"""
Locust load testing for InferaCordon gateway.

Per CLAUDE.md Section 3 and workload_profiles.py:
- Tests all tenant/domain combinations from configured profiles
- Measures: RPS, P50/P95/P99 latency, error rate, cache hit rate
- Run: locust -f locustfile.py --host http://localhost:8000
"""
from __future__ import annotations

try:
    from locust import HttpUser, task, between
except ImportError:
    raise ImportError("Install locust: pip install locust")

from load_testing.workload_profiles import STANDARD_PROFILE, BURST_PROFILE


class InferaCordonUser(HttpUser):
    wait_time = between(0.1, 1.0)

    @task(3)
    def infer_standard(self) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 3 load testing requirements (Week 8)")

    @task(1)
    def infer_complex(self) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 3 load testing requirements (Week 8)")
