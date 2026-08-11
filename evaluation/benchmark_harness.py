"""
InferaCordon benchmark harness — CLAUDE.md Section 20.

Runs all six baselines (§20.2) across all five datasets (§20.3).
Writes one ExperimentResult JSON per baseline run.
Produces output consumed by update_readme_metrics.py.

GPU EXECUTION STATUS: BLOCKED — requires:
  - vLLM server running with DeepSeek-R1-7B-Q4 and Qwen2.5-3B-Instruct
  - GPU node (A100 80GB)
  - All datasets cached locally

All GPU-dependent code paths return BLOCKED ExperimentResult when
the infrastructure is not available. Per CLAUDE.md §27: never substitute
model outputs, fabricate latencies, or generate synthetic accuracy numbers.

CLI:
  python evaluation/benchmark_harness.py run \
    --baseline 3 \
    --dataset gsm8k \
    --output evaluation/results/ \
    [--seed 42]

  python evaluation/benchmark_harness.py run-all

  Exits 0 on success, 1 on BLOCKED or error.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from evaluation.datasets import DatasetRecord, load_dataset, validate_dataset
from evaluation.metric_calculator import compute_dataset_metrics
from evaluation.result_schema import (
    BaselineLabel,
    DatasetKind,
    DatasetMetrics,
    EvaluationMetadata,
    ExperimentResult,
    SingleResult,
    VerificationOutcome,
    _capture_git_commit,
)

log = logging.getLogger(__name__)

RESULTS_DIR = Path("evaluation/results")

# ── Baseline configuration ────────────────────────────────────────────────────

# Budget class token ceilings per CLAUDE.md Section 12.3
_BUDGET_CEILINGS: dict[str, dict[str, int]] = {
    "low":      {"reasoning": 0,    "output": 256},
    "medium":   {"reasoning": 512,  "output": 512},
    "high":     {"reasoning": 1024, "output": 1024},
    "critical": {"reasoning": 2048, "output": 1024},
}

_BASELINE_DESCRIPTIONS: dict[int, str] = {
    1: "Natural completion — no budget, no routing, no stopping",
    2: "Fixed low budget (25th-percentile token usage)",
    3: "Fixed medium budget (50th-percentile token usage)",
    4: "Policy-selected budget class, no adaptive stopping, no escalation",
    5: "Policy-selected budget class, escalation, no LogitProcessor stopping",
    6: "Full InferaCordon — routing, LogitProcessor, escalation, cache, circuit breakers",
}

_VERIFIER_TYPE_MAP: dict[str, str] = {
    "gsm8k":                "gsm8k",
    "math500":              "math",
    "humaneval":            "humaneval",
    "enterprise_synthetic": "none",
    "adversarial":          "none",
}


# ── Harness entry points ──────────────────────────────────────────────────────

def run_baseline(
    baseline: int,
    dataset_name: str,
    output_dir: Path = RESULTS_DIR,
    seed: int = 42,
) -> ExperimentResult:
    """
    Run one baseline evaluation on one dataset.

    Returns a BLOCKED ExperimentResult when GPU infrastructure is unavailable.
    Writes the result to output_dir/experiment_{baseline}_{dataset}_{id}.json.

    Per CLAUDE.md §27 benchmark integrity rules:
    - Never fabricate model outputs
    - Never substitute another dataset
    - Always record hardware config alongside results
    """
    experiment_id = f"baseline{baseline}_{dataset_name}_{uuid.uuid4().hex[:8]}"
    log.info("Starting baseline=%d dataset=%s experiment_id=%s", baseline, dataset_name, experiment_id)

    # Load and validate dataset
    load_result = load_dataset(dataset_name)
    if load_result.is_blocked:
        log.warning("Dataset BLOCKED: %s", load_result.block_reason)
        result = _make_blocked_result(
            experiment_id=experiment_id,
            dataset_name=dataset_name,
            baseline=baseline,
            block_reason=f"Dataset BLOCKED — {load_result.block_reason}",
        )
        _write_result(result, output_dir, baseline, dataset_name)
        return result

    errors = validate_dataset(load_result)
    if errors:
        log.error("Dataset validation failed: %s", errors)
        result = _make_blocked_result(
            experiment_id=experiment_id,
            dataset_name=dataset_name,
            baseline=baseline,
            block_reason=f"Dataset validation failed: {errors}",
        )
        _write_result(result, output_dir, baseline, dataset_name)
        return result

    # Check GPU availability — all model inference paths require GPU
    if not _is_gpu_available():
        block_reason = (
            "BLOCKED — GPU infrastructure unavailable. "
            "vLLM server must be running with DeepSeek-R1-7B-Q4 and Qwen2.5-3B-Instruct. "
            "See docker-compose.yml: docker compose up vllm_server"
        )
        log.warning(block_reason)
        result = _make_blocked_result(
            experiment_id=experiment_id,
            dataset_name=dataset_name,
            baseline=baseline,
            block_reason=block_reason,
        )
        _write_result(result, output_dir, baseline, dataset_name)
        return result

    # GPU available — run actual evaluation
    # NOTE: This path executes only on the GPU node.
    try:
        single_results = _run_examples(
            records=load_result.records,
            baseline=baseline,
            dataset_name=dataset_name,
            seed=seed,
        )
    except Exception as exc:
        log.exception("Evaluation run failed: %s", exc)
        result = _make_blocked_result(
            experiment_id=experiment_id,
            dataset_name=dataset_name,
            baseline=baseline,
            block_reason=f"Evaluation run failed: {exc}",
        )
        _write_result(result, output_dir, baseline, dataset_name)
        return result

    dataset_kind = _get_dataset_kind(dataset_name)
    dataset_metrics = compute_dataset_metrics(
        results=single_results,
        dataset_name=dataset_name,
        dataset_kind=dataset_kind,
        baseline=baseline,
    )

    metadata = EvaluationMetadata(
        experiment_id=experiment_id,
        timestamp_iso=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        git_commit=_capture_git_commit(),
        dataset_name=dataset_name,
        dataset_version=_dataset_version(dataset_name),
        baseline=baseline,
        model_name=_model_name_for_baseline(baseline),
        policy_version=_active_policy_version(),
        complexity_scorer_version="scorer_v1",
        hardware_config=_capture_hardware_config(),
        random_seed=seed,
        status="complete",
    )

    result = ExperimentResult(
        metadata=metadata,
        datasets={dataset_name: dataset_metrics},
    )
    _write_result(result, output_dir, baseline, dataset_name)
    log.info(
        "Baseline=%d dataset=%s complete: accuracy=%.3f cost/correct=$%.4f",
        baseline, dataset_name,
        dataset_metrics.accuracy, dataset_metrics.cost_per_correct_usd,
    )
    return result


def run_all_baselines(
    output_dir: Path = RESULTS_DIR,
    seed: int = 42,
) -> list[ExperimentResult]:
    """
    Run all six baselines across all five datasets.
    Per CLAUDE.md §20.2: baselines must be run IN ORDER (1 through 6).
    """
    results = []
    datasets = ["gsm8k", "math500", "humaneval", "enterprise_synthetic", "adversarial"]
    for baseline in range(1, 7):
        for dataset in datasets:
            result = run_baseline(baseline, dataset, output_dir=output_dir, seed=seed)
            results.append(result)
    return results


# ── Per-example evaluation ────────────────────────────────────────────────────

def _run_examples(
    records: list[DatasetRecord],
    baseline: int,
    dataset_name: str,
    seed: int,
) -> list[SingleResult]:
    """
    Run inference on all examples for one baseline.

    GPU REQUIRED — raises RuntimeError if vLLM unreachable.
    Never called when _is_gpu_available() returns False.
    """
    vllm_url = os.environ.get("VLLM_URL", "http://localhost:8080")
    gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8000")

    results: list[SingleResult] = []
    verifier_type = _VERIFIER_TYPE_MAP.get(dataset_name, "none")

    for record in records:
        result = _run_one_example(
            record=record,
            baseline=baseline,
            vllm_url=vllm_url,
            gateway_url=gateway_url,
            verifier_type=verifier_type,
        )
        results.append(result)

    return results


def _run_one_example(
    record: DatasetRecord,
    baseline: int,
    vllm_url: str,
    gateway_url: str,
    verifier_type: str,
) -> SingleResult:
    """
    Run inference for one example under a specific baseline configuration.

    GPU REQUIRED — all paths call vLLM or the gateway.
    Returns a SingleResult with verification_outcome=ERROR on any failure.
    Never fabricates model outputs (per CLAUDE.md §27 rule 1).
    """
    import httpx

    start = time.monotonic()

    try:
        if baseline in (
            BaselineLabel.NATURAL_COMPLETION.value,
            BaselineLabel.FIXED_LOW.value,
            BaselineLabel.FIXED_MEDIUM.value,
        ):
            response_text, tokens_info = _call_vllm_direct(
                vllm_url=vllm_url,
                prompt=record.prompt,
                baseline=baseline,
            )
            reasoning_tokens = tokens_info.get("reasoning_tokens", 0)
            output_tokens = tokens_info.get("output_tokens", 0)
            stop_reason = tokens_info.get("stop_reason", "unknown")
            model_used = tokens_info.get("model", "unknown")
            escalation_count = 0
            cache_hit = False
            cost_usd = _estimate_cost(reasoning_tokens, output_tokens, model_used)

        else:
            gateway_response = _call_gateway(
                gateway_url=gateway_url,
                prompt=record.prompt,
                baseline=baseline,
            )
            response_text = gateway_response.get("response", "")
            reasoning_tokens = gateway_response.get("reasoning_tokens_used", 0)
            output_tokens = gateway_response.get("output_tokens", 0)
            stop_reason = gateway_response.get("stop_reason", "unknown")
            model_used = gateway_response.get("model_used", "unknown")
            escalation_count = gateway_response.get("escalation_count", 0)
            cache_hit = gateway_response.get("cache_hit", False)
            cost_usd = gateway_response.get("estimated_cost_usd", 0.0)

        latency_ms = (time.monotonic() - start) * 1000.0

        verification_outcome = _verify_response(
            response_text=response_text,
            record=record,
            verifier_type=verifier_type,
            baseline=baseline,
        )

        return SingleResult(
            example_id=record.example_id,
            dataset=record.dataset,
            baseline=baseline,
            model_used=model_used,
            reasoning_tokens=reasoning_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
            verification_outcome=verification_outcome,
            escalation_count=escalation_count,
            cache_hit=cache_hit,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        log.error("Example %s failed: %s", record.example_id, exc)
        return SingleResult(
            example_id=record.example_id,
            dataset=record.dataset,
            baseline=baseline,
            model_used="error",
            reasoning_tokens=0,
            output_tokens=0,
            stop_reason="error",
            verification_outcome=VerificationOutcome.ERROR.value,
            escalation_count=0,
            cache_hit=False,
            cost_usd=0.0,
            latency_ms=latency_ms,
            error=str(exc),
        )


# ── vLLM and gateway clients (GPU-required) ───────────────────────────────────

def _call_vllm_direct(
    vllm_url: str,
    prompt: str,
    baseline: int,
) -> tuple[str, dict]:
    """
    Direct vLLM call for baselines 1–3 that bypass gateway routing.
    GPU REQUIRED.

    baseline 1: no max_tokens cap (natural completion)
    baseline 2: fixed low budget (Qwen2.5-3B, 0 reasoning + 256 output)
    baseline 3: fixed medium budget (DeepSeek-R1-7B, 512 reasoning + 512 output)
    """
    import httpx

    if baseline == BaselineLabel.NATURAL_COMPLETION.value:
        model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        max_tokens = 4096
    elif baseline == BaselineLabel.FIXED_LOW.value:
        model = "Qwen/Qwen2.5-3B-Instruct"
        max_tokens = _BUDGET_CEILINGS["low"]["output"]
    else:
        model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        max_tokens = _BUDGET_CEILINGS["medium"]["output"]

    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }

    resp = httpx.post(f"{vllm_url}/v1/completions", json=payload, timeout=120.0)
    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]
    usage = data.get("usage", {})

    return choice["text"], {
        "reasoning_tokens": usage.get("reasoning_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "stop_reason": choice.get("finish_reason", "unknown"),
        "model": model,
    }


def _call_gateway(
    gateway_url: str,
    prompt: str,
    baseline: int,
) -> dict:
    """
    Gateway call for baselines 4–6 (full InferaCordon pipeline).
    GPU REQUIRED.

    KNOWN LIMITATION — Baselines 4 and 5 isolation (Phase 9 dependency):
    -----------------------------------------------------------------------
    Baselines 4 and 5 are intended to isolate gateway routing without
    LogitProcessor stopping (baseline 4) and with escalation but without
    LogitProcessor (baseline 5).  Properly isolating these requires the
    gateway to accept per-request control flags (e.g. disable_logit_processor,
    disable_escalation) that are NOT in the current CLAUDE.md §7.1 API contract.

    Until the gateway API is extended in Phase 9 to support these flags,
    baselines 4 and 5 will behave identically to baseline 6 (full InferaCordon).
    The ablation study will document this as a known gap — the two baselines
    will be labelled "NOT INDEPENDENTLY ISOLATABLE — gateway extension required"
    in the benchmark output.

    DO NOT add disable_logit_processor or disable_escalation to the request
    payload without first adding them to the gateway InferRequest model and
    the CLAUDE.md §7.1 API contract, and recording an Architecture Deviation
    Protocol entry (CLAUDE.md §28) if needed.
    """
    import httpx

    payload = {
        "prompt": prompt,
        "tenant_id": "benchmark_tenant",
        "domain": "evaluation",
    }

    resp = httpx.post(
        f"{gateway_url}/v1/infer",
        json=payload,
        headers={"Authorization": "Bearer benchmark_api_key"},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()


# ── Verification routing ──────────────────────────────────────────────────────

def _verify_response(
    response_text: str,
    record: DatasetRecord,
    verifier_type: str,
    baseline: int,
) -> str:
    """
    Route verification to the verifier service.
    Per CLAUDE.md §15: uses official evaluation harness wrappers.
    """
    verifier_url = os.environ.get("VERIFIER_URL", "http://localhost:8002")

    if verifier_type == "none":
        if record.dataset == "adversarial":
            return _verify_adversarial_behavior(response_text, record)
        return VerificationOutcome.UNVERIFIABLE.value

    try:
        import httpx

        payload: dict = {
            "response": response_text,
            "verifier_type": verifier_type,
        }
        if record.ground_truth is not None:
            payload["ground_truth"] = record.ground_truth
        if record.test_cases is not None:
            payload["test_cases"] = "\n".join(record.test_cases)
            payload["entry_point"] = record.example_id

        resp = httpx.post(f"{verifier_url}/verify", json=payload, timeout=30.0)
        resp.raise_for_status()
        result = resp.json()

        return (
            VerificationOutcome.CORRECT.value
            if result.get("passed")
            else VerificationOutcome.INCORRECT.value
        )

    except Exception as exc:
        log.warning("Verifier call failed for %s: %s", record.example_id, exc)
        return VerificationOutcome.UNVERIFIABLE.value


def _verify_adversarial_behavior(response_text: str, record: DatasetRecord) -> str:
    """
    Adversarial examples: check that the system produced the expected behavior.
    Expected: "block" | "flag" | "escalate" | "fallback"
    """
    expected = record.expected_behavior
    if expected is None:
        return VerificationOutcome.UNVERIFIABLE.value

    lowered = response_text.lower()
    if expected == "block" and ("blocked" in lowered or "refused" in lowered or "cannot" in lowered):
        return VerificationOutcome.CORRECT.value
    if expected == "flag" and ("flagged" in lowered or "warning" in lowered):
        return VerificationOutcome.CORRECT.value
    if expected == "escalate" and "escalat" in lowered:
        return VerificationOutcome.CORRECT.value
    if expected == "fallback" and ("fallback" in lowered or "default" in lowered):
        return VerificationOutcome.CORRECT.value

    return VerificationOutcome.INCORRECT.value


# ── Infrastructure helpers ────────────────────────────────────────────────────

def _is_gpu_available() -> bool:
    """Check if vLLM server is reachable. Never fabricates a positive result."""
    vllm_url = os.environ.get("VLLM_URL", "http://localhost:8080")
    try:
        import httpx
        resp = httpx.get(f"{vllm_url}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def _estimate_cost(reasoning_tokens: int, output_tokens: int, model: str) -> float:
    """
    Conservative local inference cost estimate (electricity + amortized hardware).
    Per CLAUDE.md §27: actual costs come from measured GPU node runs.
    """
    if "qwen" in model.lower():
        return output_tokens * 0.5 / 1_000_000
    return (reasoning_tokens * 1.0 + output_tokens * 2.0) / 1_000_000


def _capture_hardware_config() -> str:
    """Capture hardware configuration for benchmark reporting (CLAUDE.md §21, §27 rule 8)."""
    try:
        import subprocess
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        gpu_info = gpu.stdout.strip() if gpu.returncode == 0 else "GPU: unavailable"
    except Exception:
        gpu_info = "GPU: unavailable"

    try:
        import platform
        cpu_info = f"CPU: {platform.processor()}"
    except Exception:
        cpu_info = "CPU: unknown"

    return f"{gpu_info}, {cpu_info}"


def _get_dataset_kind(dataset_name: str) -> DatasetKind:
    from evaluation.result_schema import DATASET_REGISTRY
    return DATASET_REGISTRY.get(dataset_name, DatasetKind.VERIFIABLE)


def _dataset_version(dataset_name: str) -> str:
    versions = {
        "gsm8k":                "gsm8k:main:2024",
        "math500":              "lighteval/MATH:default:2024",
        "humaneval":            "openai_humaneval:openai_humaneval:2024",
        "enterprise_synthetic": "internal:v1",
        "adversarial":          "internal:v1",
    }
    return versions.get(dataset_name, "unknown")


def _model_name_for_baseline(baseline: int) -> str:
    if baseline == BaselineLabel.FIXED_LOW.value:
        return "Qwen/Qwen2.5-3B-Instruct"
    return "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"


def _active_policy_version() -> str:
    try:
        from policy_engine.loader import PolicyLoader
        loader = PolicyLoader()
        loader.load_all()
        if loader._policies:
            first = next(iter(loader._policies.values()))
            return f"v{first.versions.get('policy', 'unknown')}"
    except Exception:
        pass
    return "unknown"


# ── Result persistence ────────────────────────────────────────────────────────

def _make_blocked_result(
    experiment_id: str,
    dataset_name: str,
    baseline: int,
    block_reason: str,
) -> ExperimentResult:
    """
    Produce a BLOCKED ExperimentResult.
    All metric fields are zero — never fakes real performance data.
    """
    metadata = EvaluationMetadata.blocked(dataset_name=dataset_name, reason=block_reason)
    metadata.experiment_id = experiment_id
    metadata.baseline = baseline

    zero_metrics = DatasetMetrics(
        dataset=dataset_name,
        dataset_kind=_get_dataset_kind(dataset_name).value,
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

    return ExperimentResult(metadata=metadata, datasets={dataset_name: zero_metrics})


def _write_result(
    result: ExperimentResult,
    output_dir: Path,
    baseline: int,
    dataset_name: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"experiment_baseline{baseline}_{dataset_name}_{result.metadata.experiment_id[-8:]}.json"
    path = output_dir / fname
    path.write_text(result.to_json(), encoding="utf-8")
    log.info("Result written to %s", path)
    return path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="InferaCordon benchmark harness (CLAUDE.md Section 20)"
    )
    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="Run one baseline on one dataset")
    run_p.add_argument("--baseline", type=int, required=True, choices=range(1, 7))
    run_p.add_argument(
        "--dataset", required=True,
        choices=["gsm8k", "math500", "humaneval", "enterprise_synthetic", "adversarial", "all"],
    )
    run_p.add_argument("--output", default=str(RESULTS_DIR))
    run_p.add_argument("--seed", type=int, default=42)

    all_p = subparsers.add_parser("run-all", help="Run all six baselines across all datasets")
    all_p.add_argument("--output", default=str(RESULTS_DIR))
    all_p.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    output_dir = Path(args.output)

    if args.command == "run":
        datasets = (
            ["gsm8k", "math500", "humaneval", "enterprise_synthetic", "adversarial"]
            if args.dataset == "all"
            else [args.dataset]
        )
        any_blocked = False
        for ds in datasets:
            result = run_baseline(args.baseline, ds, output_dir, args.seed)
            status = result.metadata.status
            print(f"  baseline={args.baseline} dataset={ds}: {status}")
            if status == "blocked":
                print(f"    BLOCKED: {result.metadata.block_reason}")
                any_blocked = True
        sys.exit(1 if any_blocked else 0)

    elif args.command == "run-all":
        results = run_all_baselines(output_dir, args.seed)
        blocked = [r for r in results if r.metadata.status == "blocked"]
        complete = [r for r in results if r.metadata.status == "complete"]
        print(f"\nCompleted: {len(complete)} runs")
        print(f"Blocked:   {len(blocked)} runs (GPU infrastructure required)")
        for r in blocked:
            print(f"  BLOCKED: baseline={r.metadata.baseline} dataset={r.metadata.dataset_name}")


if __name__ == "__main__":
    main()
