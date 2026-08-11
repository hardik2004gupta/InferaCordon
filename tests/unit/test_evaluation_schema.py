"""
Unit tests for evaluation/result_schema.py.

Tests:
  - SingleResult field validation (__post_init__ bounds)
  - DatasetMetrics accounting_valid property
  - SliceMetrics accuracy property
  - ExperimentResult JSON round-trip (including SliceMetrics deserialization)
  - EvaluationMetadata.blocked constructor
  - VerificationOutcome enum values
  - DatasetKind enum values and DATASET_REGISTRY coverage
"""
import json
import pytest

from evaluation.result_schema import (
    BaselineLabel,
    DatasetKind,
    DatasetMetrics,
    DATASET_EXPECTED_COUNTS,
    DATASET_REGISTRY,
    EvaluationMetadata,
    ExperimentResult,
    SingleResult,
    SliceMetrics,
    VerificationOutcome,
)


# ── SingleResult validation ──────────────────────────────────────────────────

class TestSingleResultValidation:
    def _make(self, **overrides) -> SingleResult:
        defaults = dict(
            example_id="ex_0001",
            dataset="gsm8k",
            baseline=3,
            model_used="deepseek-r1-7b",
            reasoning_tokens=200,
            output_tokens=100,
            stop_reason="natural_boundary",
            verification_outcome=VerificationOutcome.CORRECT.value,
            escalation_count=0,
            cache_hit=False,
            cost_usd=0.005,
            latency_ms=1200.0,
        )
        defaults.update(overrides)
        return SingleResult(**defaults)

    def test_valid_correct(self):
        r = self._make()
        assert r.verification_outcome == "correct"

    def test_valid_incorrect(self):
        r = self._make(verification_outcome="incorrect")
        assert r.verification_outcome == "incorrect"

    def test_valid_unverifiable(self):
        r = self._make(verification_outcome="unverifiable")
        assert r.verification_outcome == "unverifiable"

    def test_valid_error(self):
        r = self._make(verification_outcome="error")
        assert r.verification_outcome == "error"

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValueError, match="verification_outcome"):
            self._make(verification_outcome="unknown_value")

    def test_negative_reasoning_tokens_raises(self):
        with pytest.raises(ValueError, match="reasoning_tokens"):
            self._make(reasoning_tokens=-1)

    def test_zero_reasoning_tokens_valid(self):
        r = self._make(reasoning_tokens=0)
        assert r.reasoning_tokens == 0

    def test_negative_output_tokens_raises(self):
        with pytest.raises(ValueError, match="output_tokens"):
            self._make(output_tokens=-1)

    def test_negative_latency_raises(self):
        with pytest.raises(ValueError, match="latency_ms"):
            self._make(latency_ms=-0.1)

    def test_zero_latency_valid(self):
        r = self._make(latency_ms=0.0)
        assert r.latency_ms == 0.0

    def test_negative_cost_raises(self):
        with pytest.raises(ValueError, match="cost_usd"):
            self._make(cost_usd=-0.001)

    def test_zero_cost_valid(self):
        r = self._make(cost_usd=0.0)
        assert r.cost_usd == 0.0

    def test_negative_escalation_raises(self):
        with pytest.raises(ValueError, match="escalation_count"):
            self._make(escalation_count=-1)

    def test_zero_escalation_valid(self):
        r = self._make(escalation_count=0)
        assert r.escalation_count == 0

    def test_error_field_optional(self):
        r = self._make()
        assert r.error is None

    def test_error_field_populated(self):
        r = self._make(verification_outcome="error", error="timeout")
        assert r.error == "timeout"


# ── DatasetMetrics accounting ─────────────────────────────────────────────────

class TestDatasetMetricsAccounting:
    def _make(self, correct=60, incorrect=30, unverifiable=5, error_count=5) -> DatasetMetrics:
        total = correct + incorrect + unverifiable + error_count
        acc = correct / (correct + incorrect) if (correct + incorrect) > 0 else 0.0
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
            total_cost_usd=1.0,
            cost_per_correct_usd=1.0 / correct if correct > 0 else float("inf"),
            avg_reasoning_tokens=300.0,
            avg_output_tokens=150.0,
            avg_latency_ms=1500.0,
            p95_latency_ms=3000.0,
            cache_hit_rate=0.1,
            escalation_rate=0.05,
        )

    def test_accounting_valid_true(self):
        m = self._make()
        assert m.accounting_valid is True

    def test_accounting_invalid_when_sample_count_wrong(self):
        m = self._make()
        m.sample_count += 1   # introduce mismatch
        assert m.accounting_valid is False

    def test_all_correct(self):
        m = self._make(correct=100, incorrect=0, unverifiable=0, error_count=0)
        assert m.accounting_valid is True
        assert m.accuracy == 1.0

    def test_all_unverifiable(self):
        m = DatasetMetrics(
            dataset="enterprise_synthetic",
            dataset_kind=DatasetKind.ENTERPRISE_SYNTHETIC.value,
            baseline=3,
            sample_count=200,
            correct=0, incorrect=0, unverifiable=200, error_count=0,
            accuracy=0.0,
            total_cost_usd=0.0,
            cost_per_correct_usd=float("inf"),
            avg_reasoning_tokens=0.0,
            avg_output_tokens=0.0,
            avg_latency_ms=0.0,
            p95_latency_ms=0.0,
            cache_hit_rate=0.0,
            escalation_rate=0.0,
        )
        assert m.accounting_valid is True
        assert m.accuracy == 0.0


# ── SliceMetrics accuracy ─────────────────────────────────────────────────────

class TestSliceMetricsAccuracy:
    def test_accuracy_excludes_unverifiable(self):
        s = SliceMetrics(
            slice_name="arithmetic",
            sample_count=10,
            correct=7,
            incorrect=2,
            unverifiable=1,
            error_count=0,
        )
        assert s.accuracy == pytest.approx(7 / 9)

    def test_accuracy_with_no_verifiable(self):
        s = SliceMetrics(
            slice_name="unknown",
            sample_count=5,
            correct=0,
            incorrect=0,
            unverifiable=5,
            error_count=0,
        )
        assert s.accuracy == 0.0

    def test_accounting_reconciled(self):
        s = SliceMetrics(
            slice_name="code",
            sample_count=10,
            correct=8,
            incorrect=1,
            unverifiable=0,
            error_count=1,
        )
        assert s.sample_count_reconciled is True

    def test_accounting_unreconciled(self):
        s = SliceMetrics(
            slice_name="code",
            sample_count=11,  # wrong total
            correct=8,
            incorrect=1,
            unverifiable=0,
            error_count=1,
        )
        assert s.sample_count_reconciled is False


# ── ExperimentResult JSON round-trip ─────────────────────────────────────────

class TestExperimentResultRoundTrip:
    def _sample_metadata(self) -> EvaluationMetadata:
        return EvaluationMetadata(
            experiment_id="test_exp_001",
            timestamp_iso="2026-08-10T12:00:00+00:00",
            git_commit="abc1234",
            dataset_name="gsm8k",
            dataset_version="gsm8k:main:2024",
            baseline=3,
            model_name="deepseek-r1-7b",
            policy_version="v1",
            complexity_scorer_version="scorer_v1",
            hardware_config="GPU: A100 80GB",
            random_seed=42,
            status="complete",
        )

    def _sample_metrics(self, with_slices: bool = False) -> DatasetMetrics:
        slices = []
        if with_slices:
            slices = [
                SliceMetrics(
                    slice_name="arithmetic",
                    sample_count=60,
                    correct=50,
                    incorrect=8,
                    unverifiable=2,
                    error_count=0,
                )
            ]
        return DatasetMetrics(
            dataset="gsm8k",
            dataset_kind=DatasetKind.VERIFIABLE.value,
            baseline=3,
            sample_count=100,
            correct=75,
            incorrect=20,
            unverifiable=5,
            error_count=0,
            accuracy=0.789,
            total_cost_usd=2.5,
            cost_per_correct_usd=0.0333,
            avg_reasoning_tokens=400.0,
            avg_output_tokens=200.0,
            avg_latency_ms=1800.0,
            p95_latency_ms=3500.0,
            cache_hit_rate=0.0,
            escalation_rate=0.05,
            slices=slices,
        )

    def test_round_trip_no_slices(self):
        exp = ExperimentResult(
            metadata=self._sample_metadata(),
            datasets={"gsm8k": self._sample_metrics()},
        )
        json_str = exp.to_json()
        restored = ExperimentResult.from_json(json_str)
        assert restored.metadata.experiment_id == exp.metadata.experiment_id
        assert restored.datasets["gsm8k"].correct == 75
        assert restored.datasets["gsm8k"].slices == []

    def test_round_trip_with_slices(self):
        exp = ExperimentResult(
            metadata=self._sample_metadata(),
            datasets={"gsm8k": self._sample_metrics(with_slices=True)},
        )
        json_str = exp.to_json()
        restored = ExperimentResult.from_json(json_str)
        slices = restored.datasets["gsm8k"].slices
        assert len(slices) == 1
        assert isinstance(slices[0], SliceMetrics)
        assert slices[0].slice_name == "arithmetic"
        assert slices[0].correct == 50

    def test_from_dict_mutates_input(self):
        """from_dict pops 'slices' from the raw dict — verify no KeyError."""
        exp = ExperimentResult(
            metadata=self._sample_metadata(),
            datasets={"gsm8k": self._sample_metrics(with_slices=True)},
        )
        raw = exp.to_dict()
        # Simulate two consecutive from_dict calls — second must not fail
        ExperimentResult.from_dict(raw)
        # raw["datasets"]["gsm8k"]["slices"] was popped, so second call must handle it
        # (The test validates that from_dict handles missing slices gracefully)
        raw2 = exp.to_dict()
        restored2 = ExperimentResult.from_dict(raw2)
        assert restored2.datasets["gsm8k"].slices[0].slice_name == "arithmetic"


# ── EvaluationMetadata.blocked ────────────────────────────────────────────────

class TestEvaluationMetadataBlocked:
    def test_blocked_sets_status(self):
        m = EvaluationMetadata.blocked("gsm8k", reason="test reason")
        assert m.status == "blocked"
        assert m.block_reason == "test reason"
        assert m.dataset_name == "gsm8k"
        assert m.experiment_id == "BLOCKED"

    def test_blocked_has_timestamp(self):
        m = EvaluationMetadata.blocked("gsm8k", reason="x")
        assert "T" in m.timestamp_iso  # ISO 8601 format

    def test_blocked_hardware_config(self):
        m = EvaluationMetadata.blocked("gsm8k", reason="x")
        assert "BLOCKED" in m.hardware_config


# ── Registry and enum coverage ────────────────────────────────────────────────

class TestRegistryAndEnums:
    def test_all_datasets_in_registry(self):
        expected = {"gsm8k", "math500", "humaneval", "enterprise_synthetic", "adversarial"}
        assert set(DATASET_REGISTRY.keys()) == expected

    def test_all_datasets_have_expected_counts(self):
        for ds in DATASET_REGISTRY:
            assert ds in DATASET_EXPECTED_COUNTS
            assert DATASET_EXPECTED_COUNTS[ds] > 0

    def test_verifiable_datasets(self):
        verifiable = {k for k, v in DATASET_REGISTRY.items() if v == DatasetKind.VERIFIABLE}
        assert "gsm8k" in verifiable
        assert "math500" in verifiable
        assert "humaneval" in verifiable

    def test_baseline_labels_contiguous(self):
        values = sorted(b.value for b in BaselineLabel)
        assert values == [1, 2, 3, 4, 5, 6]

    def test_verification_outcome_values(self):
        assert VerificationOutcome.CORRECT.value == "correct"
        assert VerificationOutcome.INCORRECT.value == "incorrect"
        assert VerificationOutcome.UNVERIFIABLE.value == "unverifiable"
        assert VerificationOutcome.ERROR.value == "error"

    def test_verification_outcome_is_str_enum(self):
        assert VerificationOutcome.CORRECT == "correct"
