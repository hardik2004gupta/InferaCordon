"""
Update README.md with measured benchmark results.

Per CLAUDE.md Section 27 (Benchmark Integrity Rules):
  Rule 2: Never manually invent benchmark numbers.
  Rule 6: README metrics must come from benchmark scripts.
         The README lead statement template uses [X]%, [Y]%, etc. placeholders
         that are filled by this script.

This script:
  1. Reads all ExperimentResult JSON files from evaluation/results/
  2. Identifies the canonical baseline-3 (fixed medium) and baseline-6 (full) results
  3. Computes the primary metric and delta values
  4. Replaces the <!-- METRICS:BEGIN --> ... <!-- METRICS:END --> block in README.md

IMPORTANT: This script NEVER writes fabricated data.
  - If results directory is empty or results are BLOCKED, it writes a
    "⚠ METRICS NOT YET MEASURED" block and exits 0.
  - It does NOT substitute placeholder numbers.
  - It does NOT infer metrics from targets in CLAUDE.md Section 20.6.

CLI:
  python evaluation/update_readme_metrics.py \
    --results evaluation/results/ \
    --readme README.md
"""
from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path
from typing import Optional

from evaluation.metric_calculator import compute_accuracy_delta_pp, compute_cost_reduction_pct
from evaluation.result_schema import (
    BaselineLabel,
    DatasetMetrics,
    ExperimentResult,
)

log = logging.getLogger(__name__)

METRICS_BEGIN = "<!-- METRICS:BEGIN -->"
METRICS_END   = "<!-- METRICS:END -->"

RESULTS_DIR = Path("evaluation/results")
README_PATH = Path("README.md")


# ── Public API ────────────────────────────────────────────────────────────────

def load_results(results_dir: Path) -> dict[int, dict[str, ExperimentResult]]:
    """
    Load all ExperimentResult JSON files from results_dir.
    Returns {baseline: {dataset_name: ExperimentResult}}.
    """
    loaded: dict[int, dict[str, ExperimentResult]] = {}

    for path in sorted(results_dir.glob("experiment_baseline*.json")):
        try:
            text = path.read_text(encoding="utf-8")
            result = ExperimentResult.from_json(text)
            b = result.metadata.baseline
            ds = result.metadata.dataset_name
            if b not in loaded:
                loaded[b] = {}
            # Keep the most recent result for each (baseline, dataset)
            existing = loaded[b].get(ds)
            if existing is None or result.metadata.timestamp_iso > existing.metadata.timestamp_iso:
                loaded[b][ds] = result
        except Exception as exc:
            log.warning("Skipping %s: %s", path, exc)

    return loaded


def build_metrics_block(
    all_results: dict[int, dict[str, ExperimentResult]],
) -> str:
    """
    Build the markdown metrics block for README insertion.

    If no complete results exist, returns a NOT-YET-MEASURED block.
    Never writes fabricated numbers.
    """
    baseline3 = all_results.get(BaselineLabel.FIXED_MEDIUM.value, {})
    baseline6 = all_results.get(BaselineLabel.FULL_INFERACORDON.value, {})

    complete3 = {ds: r for ds, r in baseline3.items() if r.metadata.status == "complete"}
    complete6 = {ds: r for ds, r in baseline6.items() if r.metadata.status == "complete"}

    if not complete3 or not complete6:
        return _not_measured_block(all_results)

    lines = [
        METRICS_BEGIN,
        "",
        "## Benchmark Results",
        "",
        "> All numbers produced by `evaluation/benchmark_harness.py` and",
        "> `evaluation/update_readme_metrics.py`. Never hand-written. (CLAUDE.md §27)",
        "",
    ]

    # Primary metric table
    lines += _primary_metric_table(complete3, complete6)
    lines += [""]

    # Per-dataset accuracy table
    lines += _accuracy_table(complete3, complete6)
    lines += [""]

    # Hardware and run metadata
    lines += _metadata_block(complete6)
    lines += [""]

    lines.append(METRICS_END)
    return "\n".join(lines)


def update_readme(readme_path: Path, metrics_block: str) -> bool:
    """
    Replace the <!-- METRICS:BEGIN --> ... <!-- METRICS:END --> block in readme_path.
    Returns True if update was successful.
    """
    if not readme_path.exists():
        log.error("README not found at %s", readme_path)
        return False

    content = readme_path.read_text(encoding="utf-8")

    begin_idx = content.find(METRICS_BEGIN)
    end_idx   = content.find(METRICS_END)

    if begin_idx == -1 or end_idx == -1:
        log.warning(
            "README has no %s / %s markers — appending metrics block at end.",
            METRICS_BEGIN, METRICS_END,
        )
        content = content.rstrip() + "\n\n" + metrics_block + "\n"
    else:
        content = content[:begin_idx] + metrics_block + content[end_idx + len(METRICS_END):]

    readme_path.write_text(content, encoding="utf-8")
    log.info("README updated at %s", readme_path)
    return True


# ── Block builders ────────────────────────────────────────────────────────────

def _not_measured_block(all_results: dict) -> str:
    blocked_count = sum(
        1
        for bmap in all_results.values()
        for r in bmap.values()
        if r.metadata.status == "blocked"
    )
    return "\n".join([
        METRICS_BEGIN,
        "",
        "## Benchmark Results",
        "",
        "> ⚠ **METRICS NOT YET MEASURED**",
        ">",
        "> No complete benchmark runs found in `evaluation/results/`.",
        f"> {blocked_count} run(s) are BLOCKED (GPU infrastructure required).",
        ">",
        "> To produce metrics:",
        "> ```",
        "> docker compose up",
        "> python evaluation/benchmark_harness.py run --baseline 3 --dataset all",
        "> python evaluation/benchmark_harness.py run --baseline 6 --dataset all",
        "> python evaluation/update_readme_metrics.py",
        "> ```",
        ">",
        "> Per CLAUDE.md Section 27: metrics may not be hand-written.",
        "",
        METRICS_END,
    ])


def _primary_metric_table(
    complete3: dict[str, ExperimentResult],
    complete6: dict[str, ExperimentResult],
) -> list[str]:
    """Primary metric: cost per correct answer, delta vs baseline-3."""
    rows = []
    for ds in sorted(set(complete3) & set(complete6)):
        m3 = _first_dataset_metrics(complete3[ds])
        m6 = _first_dataset_metrics(complete6[ds])
        if m3 is None or m6 is None:
            continue
        cost_delta = compute_cost_reduction_pct(m3, m6)
        acc_delta  = compute_accuracy_delta_pp(m3, m6)

        cost_str = f"{cost_delta:+.1f}%" if cost_delta is not None else "N/A"
        acc_str  = f"{acc_delta:+.2f}pp"
        rows.append(f"| {ds} | ${m3.cost_per_correct_usd:.4f} | ${m6.cost_per_correct_usd:.4f} | {cost_str} | {acc_str} |")

    if not rows:
        return ["> No overlapping complete datasets between baseline-3 and baseline-6."]

    return [
        "### Primary Metric: Cost per Correct Answer",
        "",
        "| Dataset | Baseline-3 (fixed medium) | Baseline-6 (full) | Cost Δ | Accuracy Δ |",
        "|---------|--------------------------|-------------------|--------|------------|",
    ] + rows


def _accuracy_table(
    complete3: dict[str, ExperimentResult],
    complete6: dict[str, ExperimentResult],
) -> list[str]:
    """Accuracy breakdown across all evaluated datasets."""
    all_datasets = sorted(set(complete3) | set(complete6))
    rows = []
    for ds in all_datasets:
        m3 = _first_dataset_metrics(complete3.get(ds))
        m6 = _first_dataset_metrics(complete6.get(ds))
        acc3 = f"{m3.accuracy:.1%}" if m3 and m3.sample_count > 0 else "BLOCKED"
        acc6 = f"{m6.accuracy:.1%}" if m6 and m6.sample_count > 0 else "BLOCKED"
        n3   = m3.sample_count if m3 else 0
        n6   = m6.sample_count if m6 else 0
        rows.append(f"| {ds} | {acc3} (n={n3}) | {acc6} (n={n6}) |")

    return [
        "### Accuracy by Dataset",
        "",
        "| Dataset | Baseline-3 Accuracy | Baseline-6 Accuracy |",
        "|---------|---------------------|---------------------|",
    ] + rows


def _metadata_block(complete6: dict[str, ExperimentResult]) -> list[str]:
    """Hardware and run metadata."""
    sample_result = next(iter(complete6.values())) if complete6 else None
    if sample_result is None:
        return []

    meta = sample_result.metadata
    return [
        "### Run Metadata",
        "",
        f"- **Git commit:** `{meta.git_commit}`",
        f"- **Hardware:** {meta.hardware_config}",
        f"- **Random seed:** {meta.random_seed}",
        f"- **Policy version:** {meta.policy_version}",
        f"- **Complexity scorer version:** {meta.complexity_scorer_version}",
    ]


def _first_dataset_metrics(result: Optional[ExperimentResult]) -> Optional[DatasetMetrics]:
    if result is None or not result.datasets:
        return None
    return next(iter(result.datasets.values()))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Update README.md with measured benchmark metrics (CLAUDE.md §27)"
    )
    parser.add_argument("--results", default=str(RESULTS_DIR), help="Path to results directory")
    parser.add_argument("--readme", default=str(README_PATH), help="Path to README.md")
    parser.add_argument("--dry-run", action="store_true", help="Print block without writing")
    args = parser.parse_args()

    results_dir = Path(args.results)
    readme_path = Path(args.readme)

    if not results_dir.exists():
        log.warning("Results directory %s does not exist — no metrics to report.", results_dir)
        all_results: dict = {}
    else:
        all_results = load_results(results_dir)
        log.info(
            "Loaded results: %d baselines, %d total runs",
            len(all_results),
            sum(len(v) for v in all_results.values()),
        )

    block = build_metrics_block(all_results)

    if args.dry_run:
        print(block)
        return

    ok = update_readme(readme_path, block)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
