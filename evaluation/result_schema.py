"""
Canonical typed schema for InferaCordon evaluation results.

Per CLAUDE.md Sections 20 and 27:
  - All metrics come from reproducible evaluation scripts.
  - No hand-written metric values.
  - Schema is the authoritative contract for all evaluation code.

Two kinds of results:
  SingleResult  — one example from one evaluation run
  DatasetMetrics — aggregated metrics for one dataset in one experiment
  ExperimentResult — all datasets in one baseline run + metadata

Sample accounting invariant (must hold for every DatasetMetrics):
  sample_count == correct + incorrect + unverifiable + error_count

Numeric invariants:
  accuracy in [0.0, 1.0]
  all token counts >= 0
  all latencies >= 0
  cost_usd >= 0
  escalation_count >= 0
"""
from __future__ import annotations

import datetime
import json
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


# ── Enumerations ──────────────────────────────────────────────────────────────

class VerificationOutcome(str, Enum):
    """Outcome for a single example — matches verifier_service terminology."""
    CORRECT      = "correct"
    INCORRECT    = "incorrect"
    UNVERIFIABLE = "unverifiable"
    ERROR        = "error"          # infrastructure failure during evaluation


class DatasetKind(str, Enum):
    """
    Per CLAUDE.md Section 20.3.
    Determines which regression-gate threshold applies.
    """
    VERIFIABLE           = "verifiable"           # GSM8K, MATH-500, HumanEval
    ENTERPRISE_SYNTHETIC = "enterprise_synthetic"  # 200 examples, LLM judge
    ADVERSARIAL          = "adversarial"           # system-behavior checks


class BaselineLabel(int, Enum):
    """
    Six baselines per CLAUDE.md Section 20.2.
    Integer values match baseline_measurements.py identifiers.
    """
    NATURAL_COMPLETION = 1   # No budget, no routing, no stopping
    FIXED_LOW          = 2   # Fixed 25th-percentile budget
    FIXED_MEDIUM       = 3   # Fixed 50th-percentile budget
    POLICY_NO_STOPPING = 4   # Policy budget class, no LogitProcessor, no escalation
    POLICY_ESCALATION  = 5   # Policy budget class, escalation, no LogitProcessor
    FULL_INFERACORDON  = 6   # All components active


DATASET_REGISTRY: dict[str, DatasetKind] = {
    "gsm8k":                DatasetKind.VERIFIABLE,
    "math500":              DatasetKind.VERIFIABLE,
    "humaneval":            DatasetKind.VERIFIABLE,
    "enterprise_synthetic": DatasetKind.ENTERPRISE_SYNTHETIC,
    "adversarial":          DatasetKind.ADVERSARIAL,
}

DATASET_EXPECTED_COUNTS: dict[str, int] = {
    "gsm8k":                100,
    "math500":              100,
    "humaneval":            50,
    "enterprise_synthetic": 200,
    "adversarial":          50,
}

VERIFIABLE_DATASETS = frozenset(
    k for k, v in DATASET_REGISTRY.items() if v == DatasetKind.VERIFIABLE
)


# ── Per-example result ─────────────────────────────────────────────────────────

@dataclass
class SingleResult:
    """
    Result for one evaluation example.

    Per CLAUDE.md Sections 20 and 27:
      - prompt is NOT stored here (per governance privacy contract);
        store only derived signals and counts.
      - ground truth hash may be stored for audit; raw ground truth is not.
    """
    example_id: str
    dataset: str
    baseline: int
    model_used: str
    reasoning_tokens: int
    output_tokens: int
    stop_reason: str
    verification_outcome: str           # VerificationOutcome value
    escalation_count: int
    cache_hit: bool
    cost_usd: float
    latency_ms: float
    error: Optional[str] = None         # non-None when infrastructure fails

    def __post_init__(self) -> None:
        valid = {v.value for v in VerificationOutcome}
        if self.verification_outcome not in valid:
            raise ValueError(
                f"verification_outcome={self.verification_outcome!r} not in {valid}"
            )
        if self.reasoning_tokens < 0:
            raise ValueError("reasoning_tokens must be >= 0")
        if self.output_tokens < 0:
            raise ValueError("output_tokens must be >= 0")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")
        if self.cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")
        if self.escalation_count < 0:
            raise ValueError("escalation_count must be >= 0")


# ── Per-slice metrics (for regression gate) ───────────────────────────────────

@dataclass
class SliceMetrics:
    """
    Accuracy metrics for one task-category slice.
    Per CLAUDE.md Section 20.5: gate evaluates per-slice accuracy.
    """
    slice_name: str
    sample_count: int
    correct: int
    incorrect: int
    unverifiable: int
    error_count: int

    @property
    def accuracy(self) -> float:
        """
        Accuracy = correct / (correct + incorrect).
        Excludes unverifiable and error from denominator (per CLAUDE.md §20.5).
        If no verifiable examples, returns 0.0.
        """
        verifiable = self.correct + self.incorrect
        return self.correct / verifiable if verifiable > 0 else 0.0

    @property
    def sample_count_reconciled(self) -> bool:
        return self.sample_count == self.correct + self.incorrect + self.unverifiable + self.error_count


# ── Per-dataset aggregated metrics ────────────────────────────────────────────

@dataclass
class DatasetMetrics:
    """
    All metrics for one dataset in one baseline evaluation.

    Sample accounting invariant:
      sample_count == correct + incorrect + unverifiable + error_count
    """
    dataset: str
    dataset_kind: str                   # DatasetKind value
    baseline: int
    sample_count: int
    correct: int
    incorrect: int
    unverifiable: int
    error_count: int
    accuracy: float                     # correct / (correct + incorrect)
    total_cost_usd: float
    cost_per_correct_usd: float         # inf when correct == 0
    avg_reasoning_tokens: float
    avg_output_tokens: float
    avg_latency_ms: float
    p95_latency_ms: float
    cache_hit_rate: float               # cache_hits / sample_count
    escalation_rate: float              # requests_with_escalation / sample_count
    slices: list[SliceMetrics] = field(default_factory=list)

    @property
    def accounting_valid(self) -> bool:
        return self.sample_count == self.correct + self.incorrect + self.unverifiable + self.error_count


# ── Evaluation metadata ────────────────────────────────────────────────────────

@dataclass
class EvaluationMetadata:
    """
    Per CLAUDE.md Section 27 benchmark integrity rules.
    Every benchmark report includes hardware config, software versions, seed.
    """
    experiment_id: str                  # UUID
    timestamp_iso: str                  # ISO 8601
    git_commit: str                     # programmatically captured (never typed)
    dataset_name: str
    dataset_version: str                # e.g. "gsm8k:main:2024"
    baseline: int
    model_name: str
    policy_version: str
    complexity_scorer_version: str
    hardware_config: str                # "GPU: A100 80GB, CPU: ..., RAM: ..."
    random_seed: int
    status: str                         # "complete" | "blocked" | "partial"
    block_reason: Optional[str] = None  # non-None when status == "blocked"

    @classmethod
    def blocked(cls, dataset_name: str, reason: str) -> "EvaluationMetadata":
        return cls(
            experiment_id="BLOCKED",
            timestamp_iso=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            git_commit=_capture_git_commit(),
            dataset_name=dataset_name,
            dataset_version="BLOCKED",
            baseline=0,
            model_name="BLOCKED",
            policy_version="BLOCKED",
            complexity_scorer_version="BLOCKED",
            hardware_config="BLOCKED — GPU runtime unavailable",
            random_seed=0,
            status="blocked",
            block_reason=reason,
        )


# ── Complete experiment result ─────────────────────────────────────────────────

@dataclass
class ExperimentResult:
    """
    Complete result of one baseline evaluation across all datasets.
    Written to evaluation/results/experiment_<id>.json.
    """
    metadata: EvaluationMetadata
    datasets: dict[str, DatasetMetrics]  # dataset_name -> DatasetMetrics

    def to_dict(self) -> dict:
        return {
            "metadata": asdict(self.metadata),
            "datasets": {k: asdict(v) for k, v in self.datasets.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentResult":
        metadata = EvaluationMetadata(**data["metadata"])
        datasets = {}
        for k, v in data["datasets"].items():
            raw_slices = v.pop("slices", []) or []
            slices = [SliceMetrics(**s) for s in raw_slices]
            dm = DatasetMetrics(**v, slices=slices)
            datasets[k] = dm
        return cls(metadata=metadata, datasets=datasets)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, s: str) -> "ExperimentResult":
        return cls.from_dict(json.loads(s))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _capture_git_commit() -> str:
    """Programmatically capture current git commit hash. Never typed manually."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"
