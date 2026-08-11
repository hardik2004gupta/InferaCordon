"""
Unit tests for evaluation/metric_calculator.py.

Tests:
  - compute_dataset_metrics: aggregation correctness, sample accounting invariant
  - compute_percentile: boundary values, linear interpolation
  - compute_cost_per_correct: inf when correct==0
  - validate_sample_accounting: detects mismatch
  - validate_metric_bounds: NaN, negative values, rate out of range
  - verify_budget_compliance: detects violations
  - compute_accuracy_delta_pp: sign convention, absolute pp
  - compute_cost_reduction_pct: None when baseline correct==0
"""
import math
import pytest

from evaluation.metric_calculator import (
    compute_accuracy_delta_pp,
    compute_cost_per_correct,
    compute_cost_reduction_pct,
    compute_dataset_metrics,
    compute_percentile,
    validate_experiment_metrics,
    validate_metric_bounds,
    validate_sample_accounting,
    verify_budget_compliance,
)
from evaluation.result_schema import (
    DatasetKind,
    DatasetMetrics,
    SingleResult,
    SliceMetrics,
    VerificationOutcome,
)


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _make_result(
    example_id: str,
    outcome: str = VerificationOutcome.CORRECT.value,
    reasoning_tokens: int = 300,
    output_tokens: int = 150,
    cost_usd: float = 0.005,
    latency_ms: float = 1500.0,
    escalation_count: int = 0,
    cache_hit: bool = False,
) -> SingleResult:
    return SingleResult(
        example_id=example_id,
        dataset="gsm8k",
        baseline=3,
        model_used="deepseek-r1-7b",
        reasoning_tokens=reasoning_tokens,
        output_tokens=output_tokens,
        stop_reason="natural_boundary",
        verification_outcome=outcome,
        escalation_count=escalation_count,
        cache_hit=cache_hit,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )


def _make_dataset_metrics(
    correct: int,
    incorrect: int,
    unverifiable: int = 0,
    error_count: int = 0,
    total_cost: float = 1.0,
) -> DatasetMetrics:
    total = correct + incorrect + unverifiable + error_count
    acc = correct / (correct + incorrect) if (correct + incorrect) > 0 else 0.0
    cpc = total_cost / correct if correct > 0 else float("inf")
    return DatasetMetrics(
        dataset="gsm8k",
        dataset_kind=DatasetKind.VERIFIABLE.value,
        baseline=3,
        sample_count=total,
        correct=correct,
        incorrect=incorrect,
        unverifiable=unverifiable,
        error_count=error_count,
        accuracy=acc,
        total_cost_usd=total_cost,
        cost_per_correct_usd=cpc,
        avg_reasoning_tokens=300.0,
        avg_output_tokens=150.0,
        avg_latency_ms=1500.0,
        p95_latency_ms=3000.0,
        cache_hit_rate=0.0,
        escalation_rate=0.0,
    )


# ── compute_dataset_metrics ───────────────────────────────────────────────────

class TestComputeDatasetMetrics:
    def test_all_correct(self):
        results = [_make_result(f"ex_{i:04d}") for i in range(10)]
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.sample_count == 10
        assert m.correct == 10
        assert m.incorrect == 0
        assert m.accuracy == 1.0
        assert m.accounting_valid

    def test_mixed_outcomes(self):
        results = (
            [_make_result(f"c{i}", outcome="correct") for i in range(7)]
            + [_make_result(f"i{i}", outcome="incorrect") for i in range(2)]
            + [_make_result(f"u{i}", outcome="unverifiable") for i in range(1)]
        )
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.sample_count == 10
        assert m.correct == 7
        assert m.incorrect == 2
        assert m.unverifiable == 1
        assert m.error_count == 0
        assert m.accuracy == pytest.approx(7 / 9)
        assert m.accounting_valid

    def test_all_unverifiable(self):
        results = [_make_result(f"u{i}", outcome="unverifiable") for i in range(5)]
        m = compute_dataset_metrics(results, "enterprise_synthetic", DatasetKind.ENTERPRISE_SYNTHETIC, baseline=3)
        assert m.accuracy == 0.0
        assert m.cost_per_correct_usd == float("inf")
        assert m.accounting_valid

    def test_error_outcomes_counted(self):
        results = [_make_result("e1", outcome="error")]
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.error_count == 1
        assert m.accounting_valid

    def test_cost_per_correct_computed(self):
        results = (
            [_make_result(f"c{i}", outcome="correct", cost_usd=0.01) for i in range(5)]
            + [_make_result("i1", outcome="incorrect", cost_usd=0.01)]
        )
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.total_cost_usd == pytest.approx(0.06)
        assert m.cost_per_correct_usd == pytest.approx(0.06 / 5)

    def test_latency_percentile(self):
        latencies = [float(i * 100) for i in range(1, 101)]
        results = [_make_result(f"ex_{i}", latency_ms=latencies[i]) for i in range(100)]
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        # P95 of latencies[0..99] = latency at index 94 with linear interp
        assert m.p95_latency_ms > 0

    def test_empty_results(self):
        m = compute_dataset_metrics([], "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.sample_count == 0
        assert m.accuracy == 0.0
        assert m.accounting_valid

    def test_accounting_invariant_enforced_via_mutation(self):
        """validate_sample_accounting detects post-hoc accounting inconsistencies.

        Note: the guard INSIDE compute_dataset_metrics (which raises ValueError) is
        technically unreachable via valid SingleResult inputs, because SingleResult.
        __post_init__ enforces that verification_outcome is one of the four enum
        values — so every result is always counted in exactly one category.
        The guard is defensive programming for future enum extension.

        This test covers the guard via validate_sample_accounting (the correct
        external API for post-hoc validation) by mutating sample_count after the
        fact to simulate a corruption scenario.
        """
        results = [_make_result("ex1", outcome="correct")]
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        m.sample_count += 1  # corrupt sample_count
        errors = validate_sample_accounting(m)
        assert errors
        assert "sample_count" in errors[0]

    def test_accounting_invariant_enforced_direct(self):
        """compute_dataset_metrics raises ValueError when an unknown outcome bypasses validation.

        This test exercises the defensive guard at line 72-77 of metric_calculator.py
        directly by patching verification_outcome to an unknown string AFTER SingleResult
        creation (bypassing __post_init__ validation). Under this condition,
        none of the four outcome buckets match and accounted < n.
        """
        result = _make_result("ex1", outcome="correct")
        # Bypass __post_init__ to inject an unknown outcome string
        result.verification_outcome = "not_a_valid_outcome"  # noqa: direct attribute write

        with pytest.raises(ValueError, match="Sample accounting failure"):
            compute_dataset_metrics([result], "gsm8k", DatasetKind.VERIFIABLE, baseline=3)

    def test_cache_hit_rate(self):
        results = (
            [_make_result(f"c{i}", cache_hit=True) for i in range(3)]
            + [_make_result(f"m{i}", cache_hit=False) for i in range(7)]
        )
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.cache_hit_rate == pytest.approx(0.3)

    def test_escalation_rate(self):
        results = (
            [_make_result(f"e{i}", escalation_count=1) for i in range(4)]
            + [_make_result(f"n{i}", escalation_count=0) for i in range(6)]
        )
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, baseline=3)
        assert m.escalation_rate == pytest.approx(0.4)


# ── compute_percentile ────────────────────────────────────────────────────────

class TestComputePercentile:
    def test_single_element(self):
        assert compute_percentile([42.0], 50) == 42.0

    def test_empty_returns_zero(self):
        assert compute_percentile([], 95) == 0.0

    def test_two_elements_median(self):
        assert compute_percentile([10.0, 20.0], 50) == 15.0

    def test_p0_returns_minimum(self):
        assert compute_percentile([1.0, 5.0, 10.0], 0) == 1.0

    def test_p100_returns_maximum(self):
        assert compute_percentile([1.0, 5.0, 10.0], 100) == 10.0

    def test_p95_of_100_sorted(self):
        values = [float(i) for i in range(1, 101)]
        p95 = compute_percentile(values, 95)
        # P95 of [1..100]: k = 0.95 * 99 = 94.05 → interp between values[94]=95 and values[95]=96
        assert p95 == pytest.approx(95.05)

    def test_unsorted_input(self):
        values = [30.0, 10.0, 20.0]
        assert compute_percentile(values, 50) == 20.0


# ── compute_cost_per_correct ──────────────────────────────────────────────────

class TestComputeCostPerCorrect:
    def test_normal(self):
        assert compute_cost_per_correct(1.0, 5) == pytest.approx(0.2)

    def test_zero_correct_returns_inf(self):
        assert compute_cost_per_correct(1.0, 0) == float("inf")

    def test_zero_cost(self):
        assert compute_cost_per_correct(0.0, 10) == 0.0


# ── validate_sample_accounting ────────────────────────────────────────────────

class TestValidateSampleAccounting:
    def test_valid(self):
        m = _make_dataset_metrics(correct=80, incorrect=15, unverifiable=5)
        assert validate_sample_accounting(m) == []

    def test_detects_mismatch(self):
        m = _make_dataset_metrics(correct=80, incorrect=15, unverifiable=5)
        m.sample_count += 1
        errors = validate_sample_accounting(m)
        assert errors
        assert "sample_count" in errors[0]


# ── validate_metric_bounds ────────────────────────────────────────────────────

class TestValidateMetricBounds:
    def test_valid_metrics(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        assert validate_metric_bounds(m) == []

    def test_nan_accuracy_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.accuracy = float("nan")
        errors = validate_metric_bounds(m)
        assert any("NaN" in e or "nan" in e.lower() for e in errors)

    def test_accuracy_above_one_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.accuracy = 1.1
        errors = validate_metric_bounds(m)
        assert any("accuracy" in e for e in errors)

    def test_negative_reasoning_tokens_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.avg_reasoning_tokens = -1.0
        errors = validate_metric_bounds(m)
        assert any("reasoning" in e for e in errors)

    def test_negative_latency_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.avg_latency_ms = -1.0
        errors = validate_metric_bounds(m)
        assert any("latency" in e for e in errors)

    def test_negative_cost_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.total_cost_usd = -0.001
        errors = validate_metric_bounds(m)
        assert any("cost" in e for e in errors)

    def test_nan_cost_per_correct_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.cost_per_correct_usd = float("nan")
        errors = validate_metric_bounds(m)
        assert any("cost_per_correct" in e for e in errors)

    def test_inf_cost_per_correct_valid(self):
        m = _make_dataset_metrics(correct=0, incorrect=100)
        m.cost_per_correct_usd = float("inf")
        errors = validate_metric_bounds(m)
        assert not any("cost_per_correct" in e for e in errors)

    def test_cache_hit_rate_above_one_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.cache_hit_rate = 1.1
        errors = validate_metric_bounds(m)
        assert any("cache_hit" in e for e in errors)

    def test_escalation_rate_negative_detected(self):
        m = _make_dataset_metrics(correct=80, incorrect=20)
        m.escalation_rate = -0.1
        errors = validate_metric_bounds(m)
        assert any("escalation" in e for e in errors)


# ── verify_budget_compliance ──────────────────────────────────────────────────

class TestVerifyBudgetCompliance:
    def test_compliant(self):
        results = [_make_result("ex1", reasoning_tokens=100, output_tokens=100)]
        violations = verify_budget_compliance(results, max_budget=1000)
        assert violations == []

    def test_violation_detected(self):
        results = [_make_result("ex1", reasoning_tokens=900, output_tokens=200)]
        violations = verify_budget_compliance(results, max_budget=1000)
        assert violations
        assert "ex1" in violations[0]
        assert "1000" in violations[0]

    def test_exactly_at_limit(self):
        results = [_make_result("ex1", reasoning_tokens=500, output_tokens=500)]
        violations = verify_budget_compliance(results, max_budget=1000)
        assert violations == []


# ── compute_accuracy_delta_pp ─────────────────────────────────────────────────

class TestComputeAccuracyDeltaPP:
    def test_improvement_positive(self):
        baseline = _make_dataset_metrics(correct=80, incorrect=20)   # 80%
        governed = _make_dataset_metrics(correct=90, incorrect=10)   # 90%
        delta = compute_accuracy_delta_pp(baseline, governed)
        assert delta == pytest.approx(10.0)

    def test_degradation_negative(self):
        baseline = _make_dataset_metrics(correct=90, incorrect=10)   # 90%
        governed = _make_dataset_metrics(correct=80, incorrect=20)   # 80%
        delta = compute_accuracy_delta_pp(baseline, governed)
        assert delta == pytest.approx(-10.0)

    def test_no_change(self):
        baseline = _make_dataset_metrics(correct=80, incorrect=20)
        governed = _make_dataset_metrics(correct=80, incorrect=20)
        delta = compute_accuracy_delta_pp(baseline, governed)
        assert delta == pytest.approx(0.0)

    def test_absolute_not_relative(self):
        # 50% baseline, 51% governed → 1pp absolute (not 2% relative)
        baseline = _make_dataset_metrics(correct=50, incorrect=50)
        governed = _make_dataset_metrics(correct=51, incorrect=49)
        delta = compute_accuracy_delta_pp(baseline, governed)
        assert delta == pytest.approx(1.0)


# ── compute_cost_reduction_pct ────────────────────────────────────────────────

class TestComputeCostReductionPct:
    def test_improvement(self):
        baseline = _make_dataset_metrics(correct=10, incorrect=0, total_cost=1.0)  # $0.10/correct
        governed = _make_dataset_metrics(correct=10, incorrect=0, total_cost=0.8)  # $0.08/correct
        pct = compute_cost_reduction_pct(baseline, governed)
        assert pct is not None
        assert pct == pytest.approx(20.0)

    def test_regression(self):
        baseline = _make_dataset_metrics(correct=10, incorrect=0, total_cost=1.0)
        governed = _make_dataset_metrics(correct=10, incorrect=0, total_cost=1.2)
        pct = compute_cost_reduction_pct(baseline, governed)
        assert pct is not None
        assert pct < 0.0

    def test_returns_none_when_baseline_inf(self):
        baseline = _make_dataset_metrics(correct=0, incorrect=10, total_cost=1.0)
        governed = _make_dataset_metrics(correct=5, incorrect=5, total_cost=0.5)
        pct = compute_cost_reduction_pct(baseline, governed)
        assert pct is None

    def test_returns_none_when_baseline_zero_cost(self):
        baseline = _make_dataset_metrics(correct=10, incorrect=0, total_cost=0.0)
        governed = _make_dataset_metrics(correct=10, incorrect=0, total_cost=0.5)
        pct = compute_cost_reduction_pct(baseline, governed)
        assert pct is None
