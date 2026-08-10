"""
Integration tests for the evaluation pipeline end-to-end.

Scope (CPU-only, no GPU, no vLLM):
  - benchmark_harness.run_baseline returns BLOCKED when _is_gpu_available() returns False
  - BLOCKED result has correct structure (zero metrics, status="blocked", no fake data)
  - dataset loading with BLOCKED status propagates to harness result
  - metric computation + regression gate in sequence (pure CPU path)
  - ExperimentResult JSON persistence and reload
  - update_readme_metrics.py: load_results finds files, build_metrics_block with BLOCKED results
  - update_readme_metrics.py: README block insertion idempotent

All GPU-dependent paths are explicitly mocked to BLOCKED to prevent
accidental vLLM calls or network requests in the test suite.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from evaluation.benchmark_harness import (
    _make_blocked_result,
    _write_result,
    run_baseline,
)
from evaluation.metric_calculator import compute_dataset_metrics
from evaluation.regression_gate import evaluate_gate
from evaluation.result_schema import (
    DatasetKind,
    DatasetMetrics,
    EvaluationMetadata,
    ExperimentResult,
    SingleResult,
    SliceMetrics,
    VerificationOutcome,
)
from evaluation.update_readme_metrics import (
    METRICS_BEGIN,
    METRICS_END,
    build_metrics_block,
    load_results,
    update_readme,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sample_metadata(baseline: int = 3, dataset: str = "gsm8k", status: str = "complete") -> EvaluationMetadata:
    return EvaluationMetadata(
        experiment_id=f"test_exp_b{baseline}_{dataset}",
        timestamp_iso="2026-08-10T12:00:00+00:00",
        git_commit="abc1234",
        dataset_name=dataset,
        dataset_version=f"{dataset}:test:2024",
        baseline=baseline,
        model_name="deepseek-r1-7b",
        policy_version="v1",
        complexity_scorer_version="scorer_v1",
        hardware_config="GPU: Test, CPU: Test",
        random_seed=42,
        status=status,
    )


def _sample_metrics(
    dataset: str = "gsm8k",
    dataset_kind: str = DatasetKind.VERIFIABLE.value,
    baseline: int = 3,
    correct: int = 80,
    incorrect: int = 20,
) -> DatasetMetrics:
    total = correct + incorrect
    return DatasetMetrics(
        dataset=dataset,
        dataset_kind=dataset_kind,
        baseline=baseline,
        sample_count=total,
        correct=correct,
        incorrect=incorrect,
        unverifiable=0,
        error_count=0,
        accuracy=correct / total,
        total_cost_usd=2.0,
        cost_per_correct_usd=2.0 / correct,
        avg_reasoning_tokens=400.0,
        avg_output_tokens=200.0,
        avg_latency_ms=1800.0,
        p95_latency_ms=3500.0,
        cache_hit_rate=0.0,
        escalation_rate=0.05,
        slices=[],
    )


def _make_experiment(
    baseline: int,
    dataset: str,
    correct: int = 80,
    incorrect: int = 20,
    status: str = "complete",
) -> ExperimentResult:
    meta = _sample_metadata(baseline=baseline, dataset=dataset, status=status)
    if status == "blocked":
        meta.block_reason = "BLOCKED — test"
    metrics = _sample_metrics(dataset=dataset, baseline=baseline, correct=correct, incorrect=incorrect)
    return ExperimentResult(metadata=meta, datasets={dataset: metrics})


# ── Harness: BLOCKED path ─────────────────────────────────────────────────────

class TestHarnessBlockedPath:
    """All GPU paths must return BLOCKED when vLLM is unreachable."""

    def test_run_baseline_blocked_when_no_gpu(self, tmp_path):
        with patch("evaluation.benchmark_harness._is_gpu_available", return_value=False):
            result = run_baseline(3, "gsm8k", output_dir=tmp_path, seed=42)

        assert result.metadata.status == "blocked"
        assert result.metadata.block_reason is not None
        assert "BLOCKED" in result.metadata.block_reason

    def test_blocked_result_has_zero_metrics(self, tmp_path):
        with patch("evaluation.benchmark_harness._is_gpu_available", return_value=False):
            result = run_baseline(3, "gsm8k", output_dir=tmp_path, seed=42)

        m = result.datasets["gsm8k"]
        assert m.sample_count == 0
        assert m.correct == 0
        assert m.accuracy == 0.0
        import math
        assert math.isinf(m.cost_per_correct_usd)

    def test_blocked_result_is_written_to_disk(self, tmp_path):
        with patch("evaluation.benchmark_harness._is_gpu_available", return_value=False):
            run_baseline(3, "gsm8k", output_dir=tmp_path, seed=42)

        written = list(tmp_path.glob("experiment_baseline3_gsm8k_*.json"))
        assert len(written) == 1

    def test_blocked_result_json_parseable(self, tmp_path):
        with patch("evaluation.benchmark_harness._is_gpu_available", return_value=False):
            run_baseline(3, "gsm8k", output_dir=tmp_path, seed=42)

        written = list(tmp_path.glob("experiment_baseline3_gsm8k_*.json"))[0]
        loaded = ExperimentResult.from_json(written.read_text())
        assert loaded.metadata.status == "blocked"

    def test_blocked_when_dataset_unavailable(self, tmp_path):
        """Dataset load failure propagates BLOCKED before GPU check."""
        with patch("evaluation.benchmark_harness.load_dataset") as mock_load:
            from evaluation.datasets import DatasetLoadResult
            mock_load.return_value = DatasetLoadResult(
                dataset="gsm8k",
                records=[],
                status="blocked",
                block_reason="HuggingFace datasets library not installed",
                expected_count=100,
                loaded_count=0,
            )
            result = run_baseline(3, "gsm8k", output_dir=tmp_path, seed=42)

        assert result.metadata.status == "blocked"
        assert "Dataset BLOCKED" in result.metadata.block_reason


# ── make_blocked_result ───────────────────────────────────────────────────────

class TestMakeBlockedResult:
    def test_zero_sample_count(self):
        result = _make_blocked_result(
            experiment_id="test_001",
            dataset_name="gsm8k",
            baseline=3,
            block_reason="Test block",
        )
        m = result.datasets["gsm8k"]
        assert m.sample_count == 0
        assert m.correct == 0
        assert m.incorrect == 0

    def test_status_is_blocked(self):
        result = _make_blocked_result("id", "gsm8k", 3, "reason")
        assert result.metadata.status == "blocked"

    def test_experiment_id_preserved(self):
        result = _make_blocked_result("my_experiment_id", "math500", 6, "reason")
        assert result.metadata.experiment_id == "my_experiment_id"

    def test_baseline_preserved(self):
        result = _make_blocked_result("id", "gsm8k", 5, "reason")
        assert result.metadata.baseline == 5

    def test_accounting_valid_even_when_blocked(self):
        result = _make_blocked_result("id", "gsm8k", 3, "reason")
        m = result.datasets["gsm8k"]
        assert m.accounting_valid is True


# ── Metric computation + regression gate in sequence ──────────────────────────

class TestMetricsToGatePipeline:
    """Tests the CPU-only path: SingleResults → DatasetMetrics → GateResult."""

    def _make_results(self, n_correct: int, n_incorrect: int) -> list[SingleResult]:
        results = []
        for i in range(n_correct):
            results.append(SingleResult(
                example_id=f"c_{i:04d}",
                dataset="gsm8k",
                baseline=3,
                model_used="deepseek-r1-7b",
                reasoning_tokens=300,
                output_tokens=150,
                stop_reason="natural_boundary",
                verification_outcome=VerificationOutcome.CORRECT.value,
                escalation_count=0,
                cache_hit=False,
                cost_usd=0.005,
                latency_ms=1500.0,
            ))
        for i in range(n_incorrect):
            results.append(SingleResult(
                example_id=f"i_{i:04d}",
                dataset="gsm8k",
                baseline=3,
                model_used="deepseek-r1-7b",
                reasoning_tokens=400,
                output_tokens=200,
                stop_reason="budget_exhausted",
                verification_outcome=VerificationOutcome.INCORRECT.value,
                escalation_count=1,
                cache_hit=False,
                cost_usd=0.008,
                latency_ms=2500.0,
            ))
        return results

    def test_gate_passes_with_no_degradation(self):
        baseline_results = self._make_results(80, 20)
        governed_results = self._make_results(82, 18)

        baseline_m = compute_dataset_metrics(baseline_results, "gsm8k", DatasetKind.VERIFIABLE, 3)
        governed_m = compute_dataset_metrics(governed_results, "gsm8k", DatasetKind.VERIFIABLE, 6)

        gate = evaluate_gate({"gsm8k": baseline_m}, {"gsm8k": governed_m})
        assert gate.passed is True

    def test_gate_fails_with_excessive_degradation(self):
        baseline_results = self._make_results(80, 20)    # 80%
        governed_results = self._make_results(78, 22)    # 78% → -2pp > 1pp threshold

        baseline_m = compute_dataset_metrics(baseline_results, "gsm8k", DatasetKind.VERIFIABLE, 3)
        governed_m = compute_dataset_metrics(governed_results, "gsm8k", DatasetKind.VERIFIABLE, 6)

        gate = evaluate_gate({"gsm8k": baseline_m}, {"gsm8k": governed_m})
        assert gate.passed is False
        assert "gsm8k" in gate.failed_slices

    def test_sample_accounting_preserved_through_pipeline(self):
        results = self._make_results(80, 20)
        m = compute_dataset_metrics(results, "gsm8k", DatasetKind.VERIFIABLE, 3)
        assert m.accounting_valid is True
        assert m.sample_count == 100


# ── ExperimentResult JSON persistence ────────────────────────────────────────

class TestExperimentResultPersistence:
    def test_write_and_reload(self, tmp_path):
        exp = _make_experiment(baseline=3, dataset="gsm8k")
        _write_result(exp, tmp_path, 3, "gsm8k")

        files = list(tmp_path.glob("experiment_baseline3_gsm8k_*.json"))
        assert len(files) == 1

        reloaded = ExperimentResult.from_json(files[0].read_text())
        assert reloaded.metadata.baseline == 3
        assert reloaded.datasets["gsm8k"].correct == 80

    def test_slices_survive_round_trip(self, tmp_path):
        exp = _make_experiment(baseline=3, dataset="gsm8k")
        exp.datasets["gsm8k"].slices = [
            SliceMetrics("arithmetic", 50, 40, 10, 0, 0)
        ]
        _write_result(exp, tmp_path, 3, "gsm8k")

        files = list(tmp_path.glob("experiment_baseline3_gsm8k_*.json"))
        reloaded = ExperimentResult.from_json(files[0].read_text())
        slices = reloaded.datasets["gsm8k"].slices
        assert len(slices) == 1
        assert isinstance(slices[0], SliceMetrics)
        assert slices[0].slice_name == "arithmetic"
        assert slices[0].correct == 40

    def test_multiple_writes_do_not_overwrite(self, tmp_path):
        """Each write should produce a distinct filename."""
        exp1 = _make_experiment(baseline=3, dataset="gsm8k")
        exp2 = _make_experiment(baseline=3, dataset="gsm8k")
        exp2.metadata.experiment_id = "test_exp_b3_gsm8k_different"

        _write_result(exp1, tmp_path, 3, "gsm8k")
        _write_result(exp2, tmp_path, 3, "gsm8k")

        # Filenames include experiment_id suffix — two different files expected
        files = list(tmp_path.glob("experiment_baseline3_gsm8k_*.json"))
        assert len(files) == 2


# ── load_results ─────────────────────────────────────────────────────────────

class TestLoadResults:
    def test_empty_directory_returns_empty(self, tmp_path):
        loaded = load_results(tmp_path)
        assert loaded == {}

    def test_loads_single_file(self, tmp_path):
        exp = _make_experiment(baseline=3, dataset="gsm8k")
        _write_result(exp, tmp_path, 3, "gsm8k")

        loaded = load_results(tmp_path)
        assert 3 in loaded
        assert "gsm8k" in loaded[3]

    def test_loads_multiple_baselines(self, tmp_path):
        for b in [3, 6]:
            exp = _make_experiment(baseline=b, dataset="gsm8k")
            _write_result(exp, tmp_path, b, "gsm8k")

        loaded = load_results(tmp_path)
        assert 3 in loaded
        assert 6 in loaded

    def test_loads_multiple_datasets(self, tmp_path):
        for ds in ["gsm8k", "math500"]:
            exp = _make_experiment(baseline=3, dataset=ds)
            _write_result(exp, tmp_path, 3, ds)

        loaded = load_results(tmp_path)
        assert "gsm8k" in loaded[3]
        assert "math500" in loaded[3]

    def test_skips_malformed_files(self, tmp_path):
        (tmp_path / "experiment_baseline3_gsm8k_bad.json").write_text("not json")
        loaded = load_results(tmp_path)
        assert loaded == {}

    def test_keeps_most_recent_for_same_baseline_dataset(self, tmp_path):
        exp_old = _make_experiment(baseline=3, dataset="gsm8k", correct=70, incorrect=30)
        exp_old.metadata.experiment_id = "test_exp_b3_gsm8k_old"
        exp_old.metadata.timestamp_iso = "2026-08-10T10:00:00+00:00"

        exp_new = _make_experiment(baseline=3, dataset="gsm8k", correct=80, incorrect=20)
        exp_new.metadata.experiment_id = "test_exp_b3_gsm8k_new"
        exp_new.metadata.timestamp_iso = "2026-08-10T12:00:00+00:00"

        _write_result(exp_old, tmp_path, 3, "gsm8k")
        _write_result(exp_new, tmp_path, 3, "gsm8k")

        loaded = load_results(tmp_path)
        assert loaded[3]["gsm8k"].datasets["gsm8k"].correct == 80


# ── build_metrics_block ───────────────────────────────────────────────────────

class TestBuildMetricsBlock:
    def test_blocked_results_produces_not_measured_block(self):
        blocked_exp = _make_experiment(baseline=3, dataset="gsm8k", status="blocked")
        all_results = {3: {"gsm8k": blocked_exp}}
        block = build_metrics_block(all_results)
        assert "NOT YET MEASURED" in block
        assert METRICS_BEGIN in block
        assert METRICS_END in block

    def test_empty_results_produces_not_measured_block(self):
        block = build_metrics_block({})
        assert "NOT YET MEASURED" in block

    def test_complete_results_produce_metrics_table(self):
        b3 = _make_experiment(baseline=3, dataset="gsm8k", correct=80, incorrect=20)
        b6 = _make_experiment(baseline=6, dataset="gsm8k", correct=85, incorrect=15)
        all_results = {3: {"gsm8k": b3}, 6: {"gsm8k": b6}}
        block = build_metrics_block(all_results)
        assert "Benchmark Results" in block
        assert "Cost per Correct" in block
        assert "gsm8k" in block
        assert METRICS_BEGIN in block
        assert METRICS_END in block

    def test_block_begins_with_marker(self):
        block = build_metrics_block({})
        assert block.startswith(METRICS_BEGIN)

    def test_block_ends_with_marker(self):
        block = build_metrics_block({})
        assert block.rstrip().endswith(METRICS_END)

    def test_no_fabricated_numbers_in_not_measured(self):
        """NOT YET MEASURED block must not contain any percentage or dollar values."""
        block = build_metrics_block({})
        lines_with_pct = [l for l in block.split("\n") if "%" in l and "BLOCKED" not in l and ">" not in l]
        assert lines_with_pct == []


# ── update_readme ─────────────────────────────────────────────────────────────

class TestUpdateReadme:
    def _readme_with_markers(self, existing_content: str = "") -> str:
        return (
            "# InferaCordon\n\nSome intro text.\n\n"
            + METRICS_BEGIN
            + "\nOld metrics content\n"
            + METRICS_END
            + "\n\nMore text after.\n"
        )

    def test_replaces_existing_block(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(self._readme_with_markers())

        new_block = METRICS_BEGIN + "\nNew content\n" + METRICS_END
        ok = update_readme(readme, new_block)

        assert ok is True
        content = readme.read_text()
        assert "New content" in content
        assert "Old metrics content" not in content

    def test_preserves_content_before_marker(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(self._readme_with_markers())
        new_block = METRICS_BEGIN + "\nNew\n" + METRICS_END
        update_readme(readme, new_block)
        content = readme.read_text()
        assert "# InferaCordon" in content

    def test_preserves_content_after_marker(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(self._readme_with_markers())
        new_block = METRICS_BEGIN + "\nNew\n" + METRICS_END
        update_readme(readme, new_block)
        content = readme.read_text()
        assert "More text after." in content

    def test_appends_when_no_markers(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# No markers here\n")
        new_block = METRICS_BEGIN + "\nNew\n" + METRICS_END
        ok = update_readme(readme, new_block)
        assert ok is True
        content = readme.read_text()
        assert "New" in content

    def test_returns_false_when_file_missing(self, tmp_path):
        readme = tmp_path / "MISSING.md"
        ok = update_readme(readme, "content")
        assert ok is False

    def test_idempotent_double_update(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(self._readme_with_markers())
        new_block = METRICS_BEGIN + "\nFinal\n" + METRICS_END

        update_readme(readme, new_block)
        update_readme(readme, new_block)   # second call — idempotent

        content = readme.read_text()
        assert content.count(METRICS_BEGIN) == 1
        assert content.count(METRICS_END) == 1
        assert "Final" in content
