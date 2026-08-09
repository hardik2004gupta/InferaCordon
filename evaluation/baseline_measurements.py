"""
Baseline measurements for InferaCordon (CLAUDE.md Section 20.2).

Evaluates all six baselines on GSM8K, MATH-500, and HumanEval:
  Baseline 1: Natural completion — no budget, no routing, no stopping
  Baseline 2: Fixed low budget (25th percentile of natural token usage)
  Baseline 3: Fixed medium budget (50th percentile)
  Baseline 4: Policy-selected budget class, no adaptive stopping, no escalation
  Baseline 5: Policy-selected budget class, escalation, no LogitProcessor
  Baseline 6: Full InferaCordon — routing, LogitProcessor, escalation, CBs, cache

Primary metric: cost per correct answer (CLAUDE.md Section 20.1)

BLOCKED STATUS: Requires GPU node with:
  - vLLM running at VLLM_BASE_URL with both DeepSeek-R1-7B and Qwen2.5-3B
  - OPENAI_API_KEY set (for async eval worker)
  - All datasets cached (GSM8K, MATH-500, HumanEval)
  - LogitProcessor validation gate PASSED (run logit_processor_validation.py first)

To run:
  VLLM_BASE_URL=http://localhost:8080 \\
  OPENAI_API_KEY=sk-... \\
  python evaluation/baseline_measurements.py --baseline 1

Results are written to evaluation/results/baseline_<N>_<timestamp>.json
README is NEVER updated manually from this script — see update_readme_metrics.py.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RESULTS_DIR = Path("evaluation/results")

# ── Baseline definitions (per CLAUDE.md Section 20.2) ─────────────────────────

BASELINE_DESCRIPTIONS = {
    1: "Natural completion — no budget, no routing, no stopping",
    2: "Fixed low budget (25th percentile of natural token count)",
    3: "Fixed medium budget (50th percentile of natural token count)",
    4: "Policy-selected budget class, no adaptive stopping, no escalation",
    5: "Policy-selected budget class, escalation, no LogitProcessor stopping",
    6: "Full InferaCordon — routing, LogitProcessor, escalation, CBs, cache",
}

# ── Dataset sizes (per CLAUDE.md Section 20.3) ────────────────────────────────

DATASET_CONFIG = {
    "gsm8k": {"n": 100, "verifier": "gsm8k"},
    "math500": {"n": 100, "verifier": "math"},
    "humaneval": {"n": 50, "verifier": "humaneval"},
}

# Cost model (per CLAUDE.md Section 20.1)
# Approximate cost per reasoning token and output token for DeepSeek-R1-7B on A100.
# Exact values come from measured GPU-hours / requests in baseline 1.
COST_PER_REASONING_TOKEN_USD = 0.0000002    # placeholder — overridden by measurement
COST_PER_OUTPUT_TOKEN_USD = 0.0000002


@dataclass
class SingleResult:
    dataset: str
    example_id: str
    baseline: int
    prompt: str
    response: str
    ground_truth: str
    model_used: str
    reasoning_tokens: int
    output_tokens: int
    stop_reason: str
    verification_passed: bool
    cost_usd: float
    latency_ms: float
    error: Optional[str] = None


@dataclass
class BaselineReport:
    baseline: int
    description: str
    datasets: dict = field(default_factory=dict)  # dataset → metrics dict

    @property
    def total_cost_usd(self) -> float:
        return sum(d.get("total_cost_usd", 0) for d in self.datasets.values())

    @property
    def total_correct(self) -> int:
        return sum(d.get("correct", 0) for d in self.datasets.values())

    @property
    def cost_per_correct_answer(self) -> float:
        if self.total_correct == 0:
            return float("inf")
        return self.total_cost_usd / self.total_correct

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"BASELINE {self.baseline}: {self.description}")
        print(f"{'='*60}")
        for dataset, metrics in self.datasets.items():
            print(f"\n  {dataset}:")
            for k, v in metrics.items():
                print(f"    {k}: {v}")
        print(f"\n  TOTAL:")
        print(f"    Total cost USD:         ${self.total_cost_usd:.4f}")
        print(f"    Total correct:          {self.total_correct}")
        print(f"    Cost per correct ($):   ${self.cost_per_correct_answer:.4f}")
        print(f"{'='*60}\n")


def run_baseline(
    baseline_num: int,
    vllm_base_url: str,
    openai_api_key: str,
) -> BaselineReport:
    """
    Run a specific baseline across all three datasets.

    BLOCKED: Requires GPU node. See module docstring.
    """
    _check_prerequisites(vllm_base_url)

    description = BASELINE_DESCRIPTIONS[baseline_num]
    report = BaselineReport(baseline=baseline_num, description=description)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_name, config in DATASET_CONFIG.items():
        log.info("Running baseline %d on %s (%d examples)...", baseline_num, dataset_name, config["n"])
        examples = _load_dataset(dataset_name, n=config["n"])
        results = []

        for ex in examples:
            result = _evaluate_single(
                baseline=baseline_num,
                dataset=dataset_name,
                example=ex,
                verifier_type=config["verifier"],
                vllm_base_url=vllm_base_url,
                openai_api_key=openai_api_key,
            )
            results.append(result)

        metrics = _compute_metrics(results)
        report.datasets[dataset_name] = metrics

        # Persist per-dataset results
        ts = int(time.time())
        out_path = RESULTS_DIR / f"baseline_{baseline_num}_{dataset_name}_{ts}.json"
        with open(out_path, "w") as f:
            json.dump(
                {
                    "baseline": baseline_num,
                    "dataset": dataset_name,
                    "metrics": metrics,
                    "results": [vars(r) for r in results],
                },
                f,
                indent=2,
            )
        log.info("Results written to %s", out_path)

    report.print_summary()
    return report


def _check_prerequisites(vllm_base_url: str) -> None:
    """Fail fast if environment is not ready for baseline measurements."""
    try:
        import httpx
        resp = httpx.get(f"{vllm_base_url}/health", timeout=5.0)
        resp.raise_for_status()
    except Exception as e:
        log.error(
            "BLOCKED: vLLM not reachable at %s: %s\n"
            "Start vLLM and retry. See module docstring for setup instructions.",
            vllm_base_url, e,
        )
        sys.exit(3)

    from vllm_adapter.constants import DEEPSEEK_R1_EOT_VALIDATED
    if not DEEPSEEK_R1_EOT_VALIDATED:
        log.warning(
            "DeepSeek EOT token not validated. "
            "Baselines 1–3 can still run (no LogitProcessor). "
            "Baseline 6 (full InferaCordon) requires EOT validation."
        )


def _load_dataset(name: str, n: int) -> list[dict]:
    """
    Load dataset examples.

    BLOCKED: Datasets not yet downloaded. On GPU node:
      pip install datasets
      python -c "from datasets import load_dataset; load_dataset('gsm8k', 'main')"

    This function is a skeleton — real loading implemented Week 1 on GPU node.
    """
    log.warning("Dataset loading not yet implemented for %s — running with empty set", name)
    return []


def _evaluate_single(
    baseline: int,
    dataset: str,
    example: dict,
    verifier_type: str,
    vllm_base_url: str,
    openai_api_key: str,
) -> SingleResult:
    """
    Evaluate one example under a specific baseline configuration.
    Baseline behavior:
      1: DeepSeek, max_tokens=4096, no LogitProcessor
      2: DeepSeek, max_tokens=P25_nat_tokens, no LogitProcessor
      3: DeepSeek, max_tokens=P50_nat_tokens, no LogitProcessor
      4: Budget class from complexity scorer, no LogitProcessor, no escalation
      5: Budget class from complexity scorer, escalation, no LogitProcessor
      6: Full pipeline (see gateway/pre_inference_pipeline.py)
    """
    raise NotImplementedError(
        "BLOCKED: GPU node required. "
        "Implement when vLLM is available with both models loaded."
    )


def _compute_metrics(results: list[SingleResult]) -> dict:
    if not results:
        return {"count": 0, "correct": 0, "accuracy": None, "total_cost_usd": 0.0}

    correct = sum(1 for r in results if r.verification_passed and not r.error)
    total_cost = sum(r.cost_usd for r in results)
    avg_reasoning = sum(r.reasoning_tokens for r in results) / len(results)
    avg_output = sum(r.output_tokens for r in results) / len(results)
    avg_latency = sum(r.latency_ms for r in results) / len(results)
    cost_per_correct = total_cost / correct if correct > 0 else float("inf")

    return {
        "count": len(results),
        "correct": correct,
        "accuracy": correct / len(results),
        "total_cost_usd": total_cost,
        "cost_per_correct_answer_usd": cost_per_correct,
        "avg_reasoning_tokens": avg_reasoning,
        "avg_output_tokens": avg_output,
        "avg_latency_ms": avg_latency,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run InferaCordon baseline measurements")
    parser.add_argument("--baseline", type=int, required=True, choices=range(1, 7),
                        help="Baseline number (1–6)")
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_BASE_URL", "http://localhost:8080"))
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    report = run_baseline(
        baseline_num=args.baseline,
        vllm_base_url=args.vllm_url,
        openai_api_key=api_key,
    )
    sys.exit(0)
