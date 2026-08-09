"""
Shared pytest fixtures for all InferaCordon test suites.

Per CLAUDE.md Section 17 (Ten Failure Modes) — all failure modes must be testable.
See tests/failure_injection/ for the Failure Injection Panel test cases.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def sample_policy():
    """Returns a validated Policy object from acme_corp_general_qa_v1.yaml."""
    raise NotImplementedError("Implement with Week 1 policy_engine.loader (Week 1)")


@pytest.fixture
def low_complexity_prompt():
    return "What is the capital of France?"


@pytest.fixture
def high_complexity_prompt():
    return "Prove that the square root of 2 is irrational using proof by contradiction, then verify with a numerical example accurate to 10 decimal places."
