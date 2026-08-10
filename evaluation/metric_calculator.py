"""
Pure deterministic metric computation for InferaCordon evaluation.

Per CLAUDE.md Sections 20 and 27:
  - All computations are deterministic given the same input results.
  - No I/O. No model calls. No external services.
  - Validates sample accounting and numeric bounds.
  - Never silently drops examples.

Primary metric: cost per correct answer (CLAUDE.md Section 20.1):
  C_online = total_online_cost / correct_answers_meeting_quality_threshold
"""
from __future__ import annotations

import math
from typing import Optional

from evaluation.result_schema import (
    DatasetKind,
    DatasetMetrics,
    SingleResult,
    SliceMetrics,
    VerificationOutcome,
)


# ── Aggregation ───────────────────────────────────────────────────────────────

def compute_dataset_metrics(
    results: list[SingleResult],
    dataset_name: str,
    dataset_kind: DatasetKind,
    baseline: int,
) -> DatasetMetrics:
    """
    Compute all DatasetMetrics from a list of per-example results.

    Validates sample accounting before returning.
    Raises ValueError if accounting fails.
    """
    if not results:
        return DatasetMetrics(
            dataset=dataset_name,
            dataset_kind=dataset_kind.value,
            baseline=baseline,
            sample_count=0,
            correct=0,
            incorrect=0,
            unverifiable=0,
            error_count=0,
            accuracy=0.0,
            total_cost_usd=0.0,
            cost_per_correct_usd=float("inf"),
            avg_reasoning_tokens=0.0,
            avg_output_tokens=0.0,
            avg_latency_ms=0.0,
            p95_latency_ms=0.0,
            cache_hit_rate=0.0,
            escalation_rate=0.0,
            slices=[],
        )

    n = len(results)
    correct      = sum(1 for r in results if r.verification_outcome == VerificationOutcome.CORRECT.value)
    incorrect    = sum(1 for r in results if r.verification_outcome == VerificationOutcome.INCORRECT.value)
    unverifiable = sum(1 for r in results if r.verification_outcome == VerificationOutcome.UNVERIFIABLE.value)
    error_count  = sum(1 for r in results if r.verification_outcome == VerificationOutcome.ERROR.value)

    # Sample accounting — must reconcile exactly.
    # Per phase spec §39: if counts do not reconcile, evaluation must fail.
    accounted = correct + incorrect + unverifiable + error_count
    if accounted != n:
        raise ValueError(
            f"Sample accounting failure for {dataset_name}: "
            f"{n} total != {correct} correct + {incorrect} incorrect + "
            f"{unverifiable} unverifiable + {error_count} error = {accounted}"
        )

    verifiable_denominator = correct + incorrect
    accuracy = correct / verifiable_denominator if verifiable_denominator > 0 else 0.0

    total_cost = sum(r.cost_usd for r in results)
    cost_per_correct = total_cost / correct if correct > 0 else float("inf")

    reasoning_tokens = [r.reasoning_tokens for r in results]
    output_tokens    = [r.output_tokens for r in results]
    latencies        = [r.latency_ms for r in results]

    cache_hits = sum(1 for r in results if r.cache_hit)
    escalated  = sum(1 for r in results if r.escalation_count > 0)

    return DatasetMetrics(
        dataset=dataset_name,
        dataset_kind=dataset_kind.value,
        baseline=baseline,
        sample_count=n,
        correct=correct,
        incorrect=incorrect,
        unverifiable=unverifiable,
        error_count=error_count,
        accuracy=accuracy,
        total_cost_usd=total_cost,
        cost_per_correct_usd=cost_per_correct,
        avg_reasoning_tokens=_mean(reasoning_tokens),
        avg_output_tokens=_mean(output_tokens),
        avg_latency_ms=_mean(latencies),
        p95_latency_ms=compute_percentile(latencies, 95),
        cache_hit_rate=cache_hits / n,
        escalation_rate=escalated / n,
        slices=[],  # per-slice populated by caller after task categorization
    )


def compute_percentile(values: list[float], percentile: int) -> float:
    """
    Compute an exact percentile using linear interpolation.
    Returns 0.0 for empty lists.
    """
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    k = (percentile / 100.0) * (n - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return sorted_v[lo]
    frac = k - lo
    return sorted_v[lo] * (1 - frac) + sorted_v[hi] * frac


def compute_cost_per_correct(total_cost_usd: float, correct: int) -> float:
    """
    Primary metric per CLAUDE.md Section 20.1.
    Returns inf when correct == 0 (not a valid answer, documented honestly).
    """
    return total_cost_usd / correct if correct > 0 else float("inf")


# ── Validation ────────────────────────────────────────────────────────────────

def validate_sample_accounting(metrics: DatasetMetrics) -> list[str]:
    """
    Per §39: sample_count must equal sum of all categories.
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []
    accounted = metrics.correct + metrics.incorrect + metrics.unverifiable + metrics.error_count
    if accounted != metrics.sample_count:
        errors.append(
            f"sample_count={metrics.sample_count} != "
            f"correct({metrics.correct}) + incorrect({metrics.incorrect}) + "
            f"unverifiable({metrics.unverifiable}) + error({metrics.error_count}) = {accounted}"
        )
    return errors


def validate_metric_bounds(metrics: DatasetMetrics) -> list[str]:
    """
    Per §37: metrics must not contain NaN, inf (except cost_per_correct when correct=0),
    negative values, or accuracy outside [0.0, 1.0].
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    if math.isnan(metrics.accuracy):
        errors.append("accuracy is NaN")
    elif not 0.0 <= metrics.accuracy <= 1.0:
        errors.append(f"accuracy={metrics.accuracy} not in [0.0, 1.0]")

    if metrics.avg_reasoning_tokens < 0:
        errors.append(f"avg_reasoning_tokens={metrics.avg_reasoning_tokens} < 0")
    if metrics.avg_output_tokens < 0:
        errors.append(f"avg_output_tokens={metrics.avg_output_tokens} < 0")
    if metrics.avg_latency_ms < 0:
        errors.append(f"avg_latency_ms={metrics.avg_latency_ms} < 0")
    if metrics.p95_latency_ms < 0:
        errors.append(f"p95_latency_ms={metrics.p95_latency_ms} < 0")
    if metrics.total_cost_usd < 0:
        errors.append(f"total_cost_usd={metrics.total_cost_usd} < 0")

    # cost_per_correct == inf is valid when correct == 0
    if math.isnan(metrics.cost_per_correct_usd):
        errors.append("cost_per_correct_usd is NaN")

    if not 0.0 <= metrics.cache_hit_rate <= 1.0:
        errors.append(f"cache_hit_rate={metrics.cache_hit_rate} not in [0.0, 1.0]")
    if not 0.0 <= metrics.escalation_rate <= 1.0:
        errors.append(f"escalation_rate={metrics.escalation_rate} not in [0.0, 1.0]")

    return errors


def validate_experiment_metrics(datasets: dict[str, DatasetMetrics]) -> dict[str, list[str]]:
    """
    Run all validations on a complete experiment result.
    Returns dict of {dataset_name: [error_strings]} (empty lists = valid).
    """
    return {
        name: validate_sample_accounting(m) + validate_metric_bounds(m)
        for name, m in datasets.items()
    }


# ── Token budget verification ─────────────────────────────────────────────────

def verify_budget_compliance(results: list[SingleResult], max_budget: int) -> list[str]:
    """
    Per §22 (token-budget evaluation): actual generated tokens must not exceed
    the assigned maximum. Returns list of violation strings.

    Note: In practice reasoning_tokens + output_tokens is checked against
    max_reasoning_tokens + max_output_tokens for the assigned budget class.
    For each result the combined count must not exceed max_budget.
    """
    violations: list[str] = []
    for r in results:
        total = r.reasoning_tokens + r.output_tokens
        if total > max_budget:
            violations.append(
                f"example_id={r.example_id}: total_tokens={total} > max_budget={max_budget}"
            )
    return violations


# ── Ablation delta ────────────────────────────────────────────────────────────

def compute_accuracy_delta_pp(
    baseline_metrics: DatasetMetrics,
    governed_metrics: DatasetMetrics,
) -> float:
    """
    Accuracy delta in percentage points (positive = governed BETTER than baseline).
    Formula: (governed_accuracy - baseline_accuracy) × 100.

    Per §9: difference is in absolute percentage points, not relative %.
    """
    return (governed_metrics.accuracy - baseline_metrics.accuracy) * 100.0


def compute_cost_reduction_pct(
    baseline_metrics: DatasetMetrics,
    governed_metrics: DatasetMetrics,
) -> Optional[float]:
    """
    Cost-per-correct reduction percentage.
    Returns None when baseline cost_per_correct is inf (baseline_correct == 0).
    """
    b = baseline_metrics.cost_per_correct_usd
    g = governed_metrics.cost_per_correct_usd
    if not math.isfinite(b) or b == 0.0:
        return None
    return (b - g) / b * 100.0


# ── Private helpers ───────────────────────────────────────────────────────────

def _mean(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
