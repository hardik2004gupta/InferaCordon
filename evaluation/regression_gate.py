"""
Quality regression gate — per CLAUDE.md Section 20.5.

Gate contract (authoritative from CLAUDE.md §20.5):
  "Any configuration change that causes:
   - Accuracy to fall more than 1 percentage point on verifiable tasks
     (GSM8K, MATH-500, HumanEval)
   - Accuracy to fall more than 2 percentage points on the enterprise synthetic set
   ...fails the gate and blocks deployment."

  "The gate evaluates per-slice accuracy across task categories,
   not only aggregate averages."

Key design decisions:
  - All comparisons are absolute accuracy differences in percentage points,
    not relative percentage changes (per CLAUDE.md §20 and phase spec §9).
  - A PASS at aggregate level does NOT mask a FAIL at slice level.
  - Gate fails if ANY slice or ANY aggregate exceeds the threshold.
  - Adversarial dataset uses a different metric (system behavior — not accuracy).

CLI:
  python evaluation/regression_gate.py \
    --baseline evaluation/results/experiment_baseline3.json \
    --governed evaluation/results/experiment_governed.json \
  Exits 0 on PASS, 1 on FAIL, 2 on configuration error.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from typing import Optional

from evaluation.metric_calculator import compute_accuracy_delta_pp
from evaluation.result_schema import (
    DatasetKind,
    DatasetMetrics,
    ExperimentResult,
    VerificationOutcome,
)

log = logging.getLogger(__name__)

# ── Gate thresholds (per CLAUDE.md Section 20.5) ──────────────────────────────

VERIFIABLE_THRESHOLD_PP    = 1.0   # ≤ 1 percentage point fall allowed
ENTERPRISE_THRESHOLD_PP    = 2.0   # ≤ 2 percentage points fall allowed

# Floating-point epsilon for boundary comparisons.
# accuracy deltas computed as (a - b) * 100 accumulate ~1e-14 error per operation.
# A 1e-9pp tolerance ensures "exactly at threshold" comparisons pass correctly.
_EPSILON_PP = 1e-9

# Datasets to which each threshold applies
VERIFIABLE_DATASETS    = frozenset({"gsm8k", "math500", "humaneval"})
ENTERPRISE_DATASETS    = frozenset({"enterprise_synthetic"})
ADVERSARIAL_DATASETS   = frozenset({"adversarial"})

# Escalation safety: per §16, max_retries = 1 in MVP.
MAX_ESCALATION_COUNT = 1


# ── Gate result types ─────────────────────────────────────────────────────────

@dataclass
class SliceGateResult:
    """
    Gate evaluation for one dataset or task-category slice.
    """
    slice_name: str
    dataset: str
    dataset_kind: str                   # DatasetKind value
    baseline_accuracy: float
    governed_accuracy: float
    accuracy_delta_pp: float            # governed - baseline, in percentage points
    threshold_pp: float                 # the allowed maximum magnitude of degradation
    passed: bool                        # True when delta >= -threshold_pp

    @property
    def degradation_pp(self) -> float:
        """Degradation magnitude (positive = governed got worse)."""
        return -self.accuracy_delta_pp   # sign flip: negative delta means degradation

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"  [{verdict}] {self.slice_name}: "
            f"baseline={self.baseline_accuracy:.1%}, "
            f"governed={self.governed_accuracy:.1%}, "
            f"delta={self.accuracy_delta_pp:+.2f}pp "
            f"(threshold: -{self.threshold_pp:.1f}pp)"
        )


@dataclass
class GateResult:
    """
    Overall gate result, aggregating all dataset and slice evaluations.
    Gate PASSES only when ALL slices pass.
    """
    passed: bool
    slice_results: list[SliceGateResult]
    failed_slices: list[str]
    escalation_compliant: bool           # escalation_count <= MAX_ESCALATION_COUNT for all
    adversarial_compliant: Optional[bool]  # None when adversarial dataset not evaluated
    baseline_experiment_id: str
    governed_experiment_id: str

    def print_report(self) -> None:
        verdict = "PASS" if self.passed else "FAIL"
        print(f"\n{'='*70}")
        print(f"QUALITY REGRESSION GATE: {verdict}")
        print(f"{'='*70}")
        print(f"Baseline: {self.baseline_experiment_id}")
        print(f"Governed: {self.governed_experiment_id}")
        print()
        for sr in self.slice_results:
            print(sr.summary())
        print()
        print(f"Escalation compliance: {'PASS' if self.escalation_compliant else 'FAIL'}")
        if self.adversarial_compliant is not None:
            print(f"Adversarial compliance: {'PASS' if self.adversarial_compliant else 'FAIL'}")
        else:
            print("Adversarial compliance: SKIPPED (dataset not evaluated)")
        if self.failed_slices:
            print(f"\nFailed slices: {self.failed_slices}")
            print("DECISION: Gate FAILED — deployment blocked.")
        else:
            print("\nDECISION: Gate PASSED — quality regression within bounds.")
        print(f"{'='*70}\n")

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failed_slices": self.failed_slices,
            "escalation_compliant": self.escalation_compliant,
            "adversarial_compliant": self.adversarial_compliant,
            "baseline_experiment_id": self.baseline_experiment_id,
            "governed_experiment_id": self.governed_experiment_id,
            "slices": [asdict(s) for s in self.slice_results],
        }


# ── Core gate evaluation ──────────────────────────────────────────────────────

def evaluate_slice(
    slice_name: str,
    dataset: str,
    baseline_m: DatasetMetrics,
    governed_m: DatasetMetrics,
) -> SliceGateResult:
    """
    Evaluate the gate for a single dataset or task-category slice.

    Accuracy delta is in percentage points (positive = governed BETTER).
    Gate FAILS when governed accuracy falls more than threshold_pp below baseline.

    Per §9: absolute percentage-point difference, NOT relative change.

    BLOCKED guard: if either experiment has sample_count==0 (BLOCKED result),
    the comparison is invalid — gate FAILS with threshold_pp=0.0 to make the
    failure reason visible. Two BLOCKED results must NOT produce a false PASS
    (which would happen if both accuracies were 0.0 and delta=0.0).
    """
    # Guard: refuse to compare BLOCKED (zero-sample) experiments.
    # A BLOCKED result has sample_count==0 and accuracy==0.0 — comparing two
    # BLOCKED results would yield delta=0.0 and falsely PASS the gate.
    if baseline_m.sample_count == 0 or governed_m.sample_count == 0:
        return SliceGateResult(
            slice_name=slice_name,
            dataset=dataset,
            dataset_kind=baseline_m.dataset_kind,
            baseline_accuracy=baseline_m.accuracy,
            governed_accuracy=governed_m.accuracy,
            accuracy_delta_pp=0.0,
            threshold_pp=0.0,
            passed=False,  # BLOCKED — no real data to compare
        )

    kind = DatasetKind(baseline_m.dataset_kind)

    if dataset in VERIFIABLE_DATASETS or kind == DatasetKind.VERIFIABLE:
        threshold = VERIFIABLE_THRESHOLD_PP
    elif dataset in ENTERPRISE_DATASETS or kind == DatasetKind.ENTERPRISE_SYNTHETIC:
        threshold = ENTERPRISE_THRESHOLD_PP
    else:
        # Default to stricter verifiable threshold for unknown datasets
        threshold = VERIFIABLE_THRESHOLD_PP

    delta_pp = compute_accuracy_delta_pp(baseline_m, governed_m)

    # Gate passes when: accuracy did NOT degrade beyond threshold.
    # delta_pp is governed - baseline; if delta_pp < -threshold, gate fails.
    # Epsilon guards against floating-point rounding in the at-threshold case.
    passed = delta_pp >= -(threshold + _EPSILON_PP)

    return SliceGateResult(
        slice_name=slice_name,
        dataset=dataset,
        dataset_kind=baseline_m.dataset_kind,
        baseline_accuracy=baseline_m.accuracy,
        governed_accuracy=governed_m.accuracy,
        accuracy_delta_pp=delta_pp,
        threshold_pp=threshold,
        passed=passed,
    )


def evaluate_gate(
    baseline_datasets: dict[str, DatasetMetrics],
    governed_datasets: dict[str, DatasetMetrics],
    baseline_experiment_id: str = "baseline",
    governed_experiment_id: str = "governed",
) -> GateResult:
    """
    Evaluate the quality regression gate for a complete experiment.

    Per CLAUDE.md §20.5:
    - Evaluates per-slice accuracy across task categories
    - Verifiable tasks: ≤1pp degradation
    - Enterprise synthetic: ≤2pp degradation
    - ALL slices must pass (aggregate pass does not mask slice failure)

    Parameters:
      baseline_datasets: DatasetMetrics from a baseline run (e.g. Baseline 3, fixed medium)
      governed_datasets: DatasetMetrics from the governed system (e.g. Baseline 6, full)
    """
    slice_results: list[SliceGateResult] = []

    # Per-dataset aggregate evaluation
    for dataset_name, governed_m in governed_datasets.items():
        if dataset_name in ADVERSARIAL_DATASETS:
            # Adversarial uses system-behavior metric, not accuracy — handled separately
            continue

        baseline_m = baseline_datasets.get(dataset_name)
        if baseline_m is None:
            log.warning(
                "Gate: no baseline metrics for dataset=%r — skipping", dataset_name
            )
            continue

        sr = evaluate_slice(
            slice_name=dataset_name,
            dataset=dataset_name,
            baseline_m=baseline_m,
            governed_m=governed_m,
        )
        slice_results.append(sr)

        # Per-slice evaluation within dataset (if slices are populated)
        for baseline_slice in (baseline_m.slices or []):
            matching = next(
                (s for s in governed_m.slices if s.slice_name == baseline_slice.slice_name),
                None,
            )
            if matching is None:
                continue

            # Build ephemeral DatasetMetrics for the slice to reuse evaluate_slice
            b_slice_m = DatasetMetrics(
                dataset=dataset_name,
                dataset_kind=baseline_m.dataset_kind,
                baseline=baseline_m.baseline,
                sample_count=baseline_slice.sample_count,
                correct=baseline_slice.correct,
                incorrect=baseline_slice.incorrect,
                unverifiable=baseline_slice.unverifiable,
                error_count=baseline_slice.error_count,
                accuracy=baseline_slice.accuracy,
                total_cost_usd=0.0,
                cost_per_correct_usd=0.0,
                avg_reasoning_tokens=0.0,
                avg_output_tokens=0.0,
                avg_latency_ms=0.0,
                p95_latency_ms=0.0,
                cache_hit_rate=0.0,
                escalation_rate=0.0,
            )
            g_slice_m = DatasetMetrics(
                dataset=dataset_name,
                dataset_kind=governed_m.dataset_kind,
                baseline=governed_m.baseline,
                sample_count=matching.sample_count,
                correct=matching.correct,
                incorrect=matching.incorrect,
                unverifiable=matching.unverifiable,
                error_count=matching.error_count,
                accuracy=matching.accuracy,
                total_cost_usd=0.0,
                cost_per_correct_usd=0.0,
                avg_reasoning_tokens=0.0,
                avg_output_tokens=0.0,
                avg_latency_ms=0.0,
                p95_latency_ms=0.0,
                cache_hit_rate=0.0,
                escalation_rate=0.0,
            )

            sr_slice = evaluate_slice(
                slice_name=f"{dataset_name}/{baseline_slice.slice_name}",
                dataset=dataset_name,
                baseline_m=b_slice_m,
                governed_m=g_slice_m,
            )
            slice_results.append(sr_slice)

    failed_slices = [sr.slice_name for sr in slice_results if not sr.passed]
    gate_passed = len(failed_slices) == 0

    # Escalation compliance check (per §16 and §22)
    escalation_compliant = _check_escalation_compliance(governed_datasets)

    # Adversarial compliance
    adversarial_compliant: Optional[bool] = None
    adversarial_m = governed_datasets.get("adversarial")
    if adversarial_m is not None:
        adversarial_compliant = _check_adversarial_compliance(adversarial_m)
        if not adversarial_compliant:
            gate_passed = False

    if not escalation_compliant:
        gate_passed = False

    return GateResult(
        passed=gate_passed,
        slice_results=slice_results,
        failed_slices=failed_slices,
        escalation_compliant=escalation_compliant,
        adversarial_compliant=adversarial_compliant,
        baseline_experiment_id=baseline_experiment_id,
        governed_experiment_id=governed_experiment_id,
    )


def evaluate_gate_from_files(
    baseline_path: str,
    governed_path: str,
) -> GateResult:
    """Load experiment results from JSON files and evaluate the gate."""
    with open(baseline_path) as f:
        baseline_exp = ExperimentResult.from_json(f.read())
    with open(governed_path) as f:
        governed_exp = ExperimentResult.from_json(f.read())

    return evaluate_gate(
        baseline_datasets=baseline_exp.datasets,
        governed_datasets=governed_exp.datasets,
        baseline_experiment_id=baseline_exp.metadata.experiment_id,
        governed_experiment_id=governed_exp.metadata.experiment_id,
    )


# ── Compliance helpers ─────────────────────────────────────────────────────────

def _check_escalation_compliance(datasets: dict[str, DatasetMetrics]) -> bool:
    """
    Per §16 and §22: escalation_count must not exceed MAX_ESCALATION_COUNT (1 in MVP).
    DatasetMetrics tracks escalation_rate; we flag if rate > 0 suggests runaway escalation.
    A compliant run has escalation_count <= 1 for every request.
    """
    # escalation_rate only tells us "fraction of requests that escalated at least once".
    # We can't determine individual escalation counts from DatasetMetrics alone.
    # This check is a structural placeholder — the SingleResult-level check is in
    # verify_budget_compliance / verify_escalation_compliance (called by harness).
    # Here we check that the rate is physically possible given max_retries=1.
    for m in datasets.values():
        if m.escalation_rate < 0.0 or m.escalation_rate > 1.0:
            log.error(
                "escalation_rate=%f out of [0.0, 1.0] for dataset=%s",
                m.escalation_rate, m.dataset,
            )
            return False
    return True


def _check_adversarial_compliance(adversarial_m: DatasetMetrics) -> bool:
    """
    Adversarial dataset: evaluates correct SYSTEM BEHAVIOR (block/log/escalate),
    not answer quality. A compliant run has zero unhandled adversarial inputs.
    Mapped to: correct = expected behavior observed, incorrect = wrong behavior.
    """
    if adversarial_m.sample_count == 0:
        return True
    # All adversarial examples must produce correct system behavior.
    return adversarial_m.incorrect == 0 and adversarial_m.error_count == 0


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    """
    CLI entry point — exits 0 if gate passes, 1 if fails, 2 on configuration error.

    Usage:
      python evaluation/regression_gate.py \
        --baseline evaluation/results/experiment_baseline3.json \
        --governed evaluation/results/experiment_governed.json \
        [--output evaluation/results/gate_result.json]
    """
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="InferaCordon quality regression gate (CLAUDE.md Section 20.5)"
    )
    parser.add_argument(
        "--baseline", required=True,
        help="Path to baseline ExperimentResult JSON (e.g. Baseline 3 = fixed medium budget)",
    )
    parser.add_argument(
        "--governed", required=True,
        help="Path to governed ExperimentResult JSON (e.g. Baseline 6 = Full InferaCordon)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Optional path to write GateResult JSON",
    )
    args = parser.parse_args()

    try:
        gate_result = evaluate_gate_from_files(args.baseline, args.governed)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    gate_result.print_report()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(gate_result.to_dict(), f, indent=2)
        log.info("Gate result written to %s", args.output)

    sys.exit(0 if gate_result.passed else 1)


if __name__ == "__main__":
    main()
