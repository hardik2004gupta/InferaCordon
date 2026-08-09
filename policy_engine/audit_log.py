"""
Append-only JSONL audit log writer.

Per CLAUDE.md Section 19:
- Two records per request: decision (before inference) + outcome (after delivery)
- Append-only: never modify or delete existing records
- Storage: local filesystem JSONL file (path from AUDIT_LOG_PATH env)
- NEVER store raw prompts or responses (Section 19 — only metadata)
- Thread-safe: asyncio lock around file writes
- Decision record emitted at Step 10 (admission pass)
- Outcome record emitted after response delivery (Step 16)

Decision record schema (CLAUDE.md Section 19):
  record_type, timestamp_iso, request_id, tenant_id, domain, policy_id,
  policy_version, model_version, prompt_version, guardrail_version,
  verifier_version, complexity_score, fast_path_used, base_budget_class,
  effective_budget_class, downgrade_reason, priority_tier,
  max_reasoning_tokens, max_output_tokens, route, cache_hit,
  admission_result, estimated_cost_usd

Outcome record schema (CLAUDE.md Section 19):
  record_type, timestamp_iso, request_id, tenant_id, actual_reasoning_tokens,
  actual_output_tokens, actual_cost_usd, latency_ms, ttft_ms, finish_reason,
  verification_result, quality_score, escalation_count, cache_stored,
  guardrail_output_result
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class AuditLog:
    """Append-only JSONL audit log."""

    def __init__(self, log_path: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 19 (Week 1)")

    async def write_decision(self, record: dict[str, Any]) -> None:
        """Append a decision record. Validates required fields before write."""
        raise NotImplementedError("Implement per CLAUDE.md Section 19 (Week 1)")

    async def write_outcome(self, record: dict[str, Any]) -> None:
        """Append an outcome record. Validates required fields before write."""
        raise NotImplementedError("Implement per CLAUDE.md Section 19 (Week 1)")

    async def _append(self, record: dict[str, Any]) -> None:
        """Thread-safe JSONL append (asyncio lock)."""
        raise NotImplementedError("Implement per CLAUDE.md Section 19 (Week 1)")
