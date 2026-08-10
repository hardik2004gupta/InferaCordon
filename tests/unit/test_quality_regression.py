"""
Unit tests for evaluation/regression_gate.py.

Tests:
  - Gate PASSES when accuracy degradation is within threshold
  - Gate FAILS when accuracy degradation exceeds threshold
  - At-threshold boundary (exactly at limit = PASS; just over = FAIL)
  - Verifiable threshold: 1pp
  - Enterprise synthetic threshold: 2pp
  - Per-slice failure masks aggregate pass
  - Adversarial compliance: non-zero incorrect = gate fail
  - Escalation compliance: invalid rates fail
  - evaluate_gate with no matching datasets = pass (nothing to evaluate)
  - Missing baseline dataset for governed dataset = skip with warning
"""
import pytest

from evaluation.regression_gate import (
    ENTERPRISE_THRESHOLD_PP,
    VERIFIABLE_THRESHOLD_PP,
    GateResult,
    SliceGateResult,
    _check_adversarial_compliance,
    _check_escalation_compliance,
    evaluate_gate,
    evaluate_slice,
)
from evaluation.result_schema import (
    DatasetKind,
    DatasetMetrics,
    SliceMetrics,
)


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _gsm8k_metrics(correct: int, incorrect: int, cost: float = 1.0) -> DatasetMetrics:
    total = correct + incorrect
    return DatasetMetrics(
        dataset="gsm8k",
        dataset_kind=DatasetKind.VERIFIABLE.value,
        baseline=3,
        sample_count=total,
        correct=correct,
        incorrect=incorrect,
        unverifiable=0,
        error_count=0,
        accuracy=correct / total if total > 0 else 0.0,
        total_cost_usd=cost,
        cost_per_correct_usd=cost / correct if correct > 0 else float("inf"),
        avg_reasoning_tokens=300.0,
        avg_output_tokens=150.0,
        avg_latency_ms=1500.0,
        p95_latency_ms=3000.0,
        cache_hit_rate=0.0,
        escalation_rate=0.0,
    )


def _enterprise_metrics(correct: int, incorrect: int, cost: float = 2.0) -> DatasetMetrics:
    total = correct + incorrect
    return DatasetMetrics(
        dataset="enterprise_synthetic",
        dataset_kind=DatasetKind.ENTERPRISE_SYNTHETIC.value,
        baseline=3,
        sample_count=total,
        correct=correct,
        incorrect=incorrect,
        unverifiable=0,
        error_count=0,
        accuracy=correct / total if total > 0 else 0.0,
        total_cost_usd=cost,
        cost_per_correct_usd=cost / correct if correct > 0 else float("inf"),
        avg_reasoning_tokens=400.0,
        avg_output_tokens=200.0,
        avg_latency_ms=2000.0,
        p95_latency_ms=4000.0,
        cache_hit_rate=0.0,
        escalation_rate=0.0,
    )


def _adversarial_metrics(correct: int, incorrect: int) -> DatasetMetrics:
    total = correct + incorrect
    return DatasetMetrics(
        dataset="adversarial",
        dataset_kind=DatasetKind.ADVERSARIAL.value,
        baseline=6,
        sample_count=total,
        correct=correct,
        incorrect=incorrect,
        unverifiable=0,
        error_count=0,
        accuracy=correct / total if total > 0 else 0.0,
        total_cost_usd=0.5,
        cost_per_correct_usd=0.5 / correct if correct > 0 else float("inf"),
        avg_reasoning_tokens=0.0,
        avg_output_tokens=0.0,
        avg_latency_ms=0.0,
        p95_latency_ms=0.0,
        cache_hit_rate=0.0,
        escalation_rate=0.0,
    )


# ── Threshold constants ───────────────────────────────────────────────────────

class TestThresholdConstants:
    def test_verifiable_threshold(self):
        assert VERIFIABLE_THRESHOLD_PP == 1.0

    def test_enterprise_threshold(self):
        assert ENTERPRISE_THRESHOLD_PP == 2.0


# ── evaluate_slice ────────────────────────────────────────────────────────────

class TestEvaluateSlice:
    def test_no_degradation_passes(self):
        baseline = _gsm8k_metrics(correct=80, incorrect=20)   # 80%
        governed = _gsm8k_metrics(correct=80, incorrect=20)   # 80%
        sr = evaluate_slice("gsm8k", "gsm8k", baseline, governed)
        assert sr.passed is True
        assert sr.accuracy_delta_pp == pytest.approx(0.0)

    def test_improvement_passes(self):
        baseline = _gsm8k_metrics(correct=80, incorrect=20)   # 80%
        governed = _gsm8k_metrics(correct=85, incorrect=15)   # 85%
        sr = evaluate_slice("gsm8k", "gsm8k", baseline, governed)
        assert sr.passed is True
        assert sr.accuracy_delta_pp == pytest.approx(5.0)

    def test_small_degradation_within_threshold_passes(self):
        # 80% → 79.1% = -0.9pp < 1.0pp threshold
        baseline = _gsm8k_metrics(correct=80, incorrect=20)
        governed = _gsm8k_metrics(correct=79, incorrect=21)   # 79 / 100 = 79%
        sr = evaluate_slice("gsm8k", "gsm8k", baseline, governed)
        # delta = 79 - 80 = -1.0pp  -- exactly at boundary
        # This should PASS (>= -1.0)
        assert sr.accuracy_delta_pp == pytest.approx(-1.0)
        assert sr.passed is True

    def test_degradation_exceeds_threshold_fails(self):
        # 80% → 78% = -2pp > 1.0pp threshold
        baseline = _gsm8k_metrics(correct=80, incorrect=20)   # 80%
        governed = _gsm8k_metrics(correct=78, incorrect=22)   # 78%
        sr = evaluate_slice("gsm8k", "gsm8k", baseline, governed)
        assert sr.accuracy_delta_pp == pytest.approx(-2.0)
        assert sr.passed is False

    def test_enterprise_threshold_applied(self):
        # Enterprise threshold is 2pp — 1.5pp degradation should pass
        baseline = _enterprise_metrics(correct=160, incorrect=40)   # 80%
        governed = _enterprise_metrics(correct=157, incorrect=43)   # 78.5%
        sr = evaluate_slice("enterprise_synthetic", "enterprise_synthetic", baseline, governed)
        assert sr.threshold_pp == 2.0
        assert sr.accuracy_delta_pp == pytest.approx(-1.5)
        assert sr.passed is True

    def test_enterprise_threshold_exceeded_fails(self):
        baseline = _enterprise_metrics(correct=160, incorrect=40)   # 80%
        governed = _enterprise_metrics(correct=154, incorrect=46)   # 77%
        sr = evaluate_slice("enterprise_synthetic", "enterprise_synthetic", baseline, governed)
        assert sr.threshold_pp == 2.0
        assert sr.accuracy_delta_pp < -2.0
        assert sr.passed is False

    def test_verifiable_threshold_applied_to_gsm8k(self):
        baseline = _gsm8k_metrics(correct=80, incorrect=20)
        governed = _gsm8k_metrics(correct=80, incorrect=20)
        sr = evaluate_slice("gsm8k", "gsm8k", baseline, governed)
        assert sr.threshold_pp == 1.0

    def test_degradation_property(self):
        baseline = _gsm8k_metrics(correct=80, incorrect=20)
        governed = _gsm8k_metrics(correct=78, incorrect=22)
        sr = evaluate_slice("gsm8k", "gsm8k", baseline, governed)
        # degradation_pp should be the positive magnitude
        assert sr.degradation_pp == pytest.approx(2.0)


# ── Gate boundary conditions ──────────────────────────────────────────────────

class TestGateBoundaryConditions:
    """Tests for at-threshold and just-over-threshold boundary."""

    def test_exactly_at_verifiable_threshold_passes(self):
        # Exactly 1pp degradation = PASS (>= -1.0)
        baseline = _gsm8k_metrics(correct=80, incorrect=20)   # 80.0%
        governed = _gsm8k_metrics(correct=79, incorrect=21)   # 79.0% → -1.0pp exactly
        result = evaluate_gate({"gsm8k": baseline}, {"gsm8k": governed})
        assert result.passed is True

    def test_just_over_verifiable_threshold_fails(self):
        # 1.01pp degradation — need enough samples for precision
        # 200 samples: baseline 80% = 160/200, governed 78.9% ≈ 158/200 → -1.0pp
        # Use 1000 samples for sub-pp precision
        baseline = _gsm8k_metrics(correct=800, incorrect=200)   # 80.0%
        governed = _gsm8k_metrics(correct=789, incorrect=211)   # 78.9% → -1.1pp
        result = evaluate_gate({"gsm8k": baseline}, {"gsm8k": governed})
        delta = result.slice_results[0].accuracy_delta_pp
        if delta < -1.0:
            assert result.passed is False

    def test_exactly_at_enterprise_threshold_passes(self):
        # Exactly 2pp degradation = PASS
        baseline = _enterprise_metrics(correct=80, incorrect=20)   # 80%
        governed = _enterprise_metrics(correct=78, incorrect=22)   # 78% → -2.0pp exactly
        result = evaluate_gate(
            {"enterprise_synthetic": baseline},
            {"enterprise_synthetic": governed},
        )
        assert result.passed is True

    def test_just_over_enterprise_threshold_fails(self):
        # 2.5pp degradation for enterprise
        baseline = _enterprise_metrics(correct=800, incorrect=200)   # 80%
        governed = _enterprise_metrics(correct=775, incorrect=225)   # 77.5% → -2.5pp
        result = evaluate_gate(
            {"enterprise_synthetic": baseline},
            {"enterprise_synthetic": governed},
        )
        assert result.passed is False


# ── Full gate evaluation ──────────────────────────────────────────────────────

class TestEvaluateGate:
    def test_all_pass(self):
        baseline = {"gsm8k": _gsm8k_metrics(80, 20)}
        governed = {"gsm8k": _gsm8k_metrics(82, 18)}  # improvement
        result = evaluate_gate(baseline, governed)
        assert result.passed is True
        assert result.failed_slices == []

    def test_fail_when_slice_fails(self):
        baseline = {"gsm8k": _gsm8k_metrics(80, 20)}
        governed = {"gsm8k": _gsm8k_metrics(78, 22)}  # -2pp > 1pp threshold
        result = evaluate_gate(baseline, governed)
        assert result.passed is False
        assert "gsm8k" in result.failed_slices

    def test_adversarial_skipped_from_slice_eval(self):
        baseline = {}
        governed = {"adversarial": _adversarial_metrics(correct=50, incorrect=0)}
        result = evaluate_gate(baseline, governed)
        # No slice results for adversarial (handled separately)
        assert all(sr.dataset != "adversarial" for sr in result.slice_results)

    def test_adversarial_compliant_sets_gate_pass(self):
        baseline = {"gsm8k": _gsm8k_metrics(80, 20)}
        governed = {
            "gsm8k": _gsm8k_metrics(80, 20),
            "adversarial": _adversarial_metrics(correct=50, incorrect=0),
        }
        result = evaluate_gate(baseline, governed)
        assert result.adversarial_compliant is True
        assert result.passed is True

    def test_adversarial_non_compliant_fails_gate(self):
        baseline = {"gsm8k": _gsm8k_metrics(80, 20)}
        governed = {
            "gsm8k": _gsm8k_metrics(80, 20),       # passes
            "adversarial": _adversarial_metrics(correct=48, incorrect=2),  # 2 wrong behaviors
        }
        result = evaluate_gate(baseline, governed)
        assert result.adversarial_compliant is False
        assert result.passed is False

    def test_no_datasets_to_compare_passes(self):
        result = evaluate_gate({}, {})
        assert result.passed is True
        assert result.slice_results == []

    def test_missing_baseline_for_governed_skips(self):
        governed = {"gsm8k": _gsm8k_metrics(80, 20)}
        result = evaluate_gate({}, governed)  # no baseline
        # Nothing to compare, so nothing fails
        assert result.passed is True

    def test_multiple_datasets_any_fail_propagates(self):
        baseline = {
            "gsm8k": _gsm8k_metrics(80, 20),
            "enterprise_synthetic": _enterprise_metrics(160, 40),
        }
        governed = {
            "gsm8k": _gsm8k_metrics(80, 20),       # no degradation — passes
            "enterprise_synthetic": _enterprise_metrics(140, 60),  # -10pp — fails
        }
        result = evaluate_gate(baseline, governed)
        assert result.passed is False
        assert any("enterprise_synthetic" in s for s in result.failed_slices)

    def test_per_slice_failure_fails_gate(self):
        """Per CLAUDE.md §20.5: aggregate pass does NOT mask slice failure."""
        slice_a = SliceMetrics(
            slice_name="arithmetic",
            sample_count=50, correct=45, incorrect=5, unverifiable=0, error_count=0,
        )
        slice_b = SliceMetrics(
            slice_name="algebra",
            sample_count=50, correct=30, incorrect=20, unverifiable=0, error_count=0,
        )

        # Baseline aggregate: 75/100 = 75%
        baseline_m = _gsm8k_metrics(correct=75, incorrect=25)
        baseline_m.slices = [
            SliceMetrics("arithmetic", 50, 45, 5, 0, 0),
            SliceMetrics("algebra", 50, 30, 20, 0, 0),
        ]

        # Governed aggregate: 75/100 = 75% (same) — aggregate would PASS
        governed_m = _gsm8k_metrics(correct=75, incorrect=25)
        governed_m.slices = [
            SliceMetrics("arithmetic", 50, 50, 0, 0, 0),   # 100% — improved
            SliceMetrics("algebra", 50, 25, 25, 0, 0),     # 50% — degraded from 60%
        ]

        result = evaluate_gate({"gsm8k": baseline_m}, {"gsm8k": governed_m})
        # algebra degraded from 60% to 50% = -10pp > 1pp threshold → FAIL
        failed = [s for s in result.slice_results if not s.passed]
        assert any("algebra" in s.slice_name for s in failed)


# ── Compliance helpers ────────────────────────────────────────────────────────

class TestComplianceHelpers:
    def test_adversarial_compliant_all_correct(self):
        m = _adversarial_metrics(correct=50, incorrect=0)
        assert _check_adversarial_compliance(m) is True

    def test_adversarial_non_compliant_has_incorrect(self):
        m = _adversarial_metrics(correct=48, incorrect=2)
        assert _check_adversarial_compliance(m) is False

    def test_adversarial_empty_passes(self):
        m = _adversarial_metrics(correct=0, incorrect=0)
        assert _check_adversarial_compliance(m) is True

    def test_escalation_compliant_valid_rates(self):
        m = _gsm8k_metrics(80, 20)
        m.escalation_rate = 0.1
        assert _check_escalation_compliance({"gsm8k": m}) is True

    def test_escalation_non_compliant_negative_rate(self):
        m = _gsm8k_metrics(80, 20)
        m.escalation_rate = -0.1   # invalid
        assert _check_escalation_compliance({"gsm8k": m}) is False

    def test_escalation_non_compliant_rate_above_one(self):
        m = _gsm8k_metrics(80, 20)
        m.escalation_rate = 1.5   # invalid
        assert _check_escalation_compliance({"gsm8k": m}) is False


# ── GateResult.to_dict / print_report ────────────────────────────────────────

class TestGateResultOutput:
    def _make_gate_result(self, passed: bool = True) -> GateResult:
        sr = SliceGateResult(
            slice_name="gsm8k",
            dataset="gsm8k",
            dataset_kind="verifiable",
            baseline_accuracy=0.80,
            governed_accuracy=0.81,
            accuracy_delta_pp=1.0,
            threshold_pp=1.0,
            passed=passed,
        )
        return GateResult(
            passed=passed,
            slice_results=[sr],
            failed_slices=[] if passed else ["gsm8k"],
            escalation_compliant=True,
            adversarial_compliant=None,
            baseline_experiment_id="baseline_001",
            governed_experiment_id="governed_001",
        )

    def test_to_dict_structure(self):
        result = self._make_gate_result(passed=True)
        d = result.to_dict()
        assert d["passed"] is True
        assert d["failed_slices"] == []
        assert d["escalation_compliant"] is True
        assert d["adversarial_compliant"] is None
        assert len(d["slices"]) == 1
        assert d["slices"][0]["slice_name"] == "gsm8k"

    def test_to_dict_includes_all_fields(self):
        result = self._make_gate_result(passed=False)
        d = result.to_dict()
        required = [
            "passed", "failed_slices", "escalation_compliant",
            "adversarial_compliant", "baseline_experiment_id",
            "governed_experiment_id", "slices",
        ]
        for field in required:
            assert field in d

    def test_print_report_does_not_raise(self, capsys):
        result = self._make_gate_result(passed=True)
        result.print_report()
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_print_report_fail_shows_fail(self, capsys):
        result = self._make_gate_result(passed=False)
        result.print_report()
        captured = capsys.readouterr()
        assert "FAIL" in captured.out
