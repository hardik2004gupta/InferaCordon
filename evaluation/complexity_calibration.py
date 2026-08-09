"""
Complexity scorer calibration against Week 1 baseline token counts.

Per CLAUDE.md Section 10.4:
  Natural completion token counts are collected for all benchmark queries.
  Feature weights are adjusted using simple linear regression to minimize
  MAE between predicted budget class and optimal budget class.
  Calibration is done ONCE, offline, after Week 1 baselines.
  Resulting weights are committed to the codebase.

Usage:
  After running baseline_measurements.py --baseline 1, this script reads
  the natural completion results and fits the calibration.

  python evaluation/complexity_calibration.py \\
    --input evaluation/results/baseline_1_*.json \\
    --output evaluation/calibration_weights.json

The output JSON is loaded by the gateway at startup via get_scorer(calibration_weights=...).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Budget class thresholds (from CLAUDE.md Section 10.5) ────────────────────
LOW_MAX = 3.5
MEDIUM_MAX = 6.5
HIGH_MAX = 8.5


def natural_tokens_to_optimal_class(nat_tokens: int) -> str:
    """
    Map natural completion token count to the optimal budget class.

    Logic: the optimal class is the one whose ceiling is just above the
    natural completion count. This is what the scorer should predict.
    """
    if nat_tokens <= 256:    # Low budget max_output_tokens
        return "low"
    elif nat_tokens <= 512:
        return "medium"
    elif nat_tokens <= 1024:
        return "high"
    return "critical"


def load_baseline_results(paths: List[str]) -> List[dict]:
    """Load all baseline 1 result files."""
    all_results = []
    for path in paths:
        with open(path) as f:
            data = json.load(f)
        results = data.get("results", [])
        all_results.extend(results)
    log.info("Loaded %d results from %d file(s)", len(all_results), len(paths))
    return all_results


def compute_feature_scores(results: List[dict]) -> tuple[List[List[float]], List[str]]:
    """
    Run the complexity scorer on all prompts and extract per-group scores.
    Returns (X matrix of feature group scores, y list of optimal classes).
    """
    from gateway.complexity_scorer import ComplexityScorer
    scorer = ComplexityScorer()

    X = []
    y = []
    for result in results:
        prompt = result.get("prompt", "")
        nat_tokens = result.get("reasoning_tokens", 0) + result.get("output_tokens", 0)

        if not prompt or nat_tokens == 0:
            continue

        cr = scorer.score(prompt)
        features = [
            cr.feature_breakdown["constraint_density"],
            cr.feature_breakdown["structural_signals"],
            cr.feature_breakdown["technical_domain"],
            cr.feature_breakdown["length_signal"],
            cr.feature_breakdown["output_format"],
        ]
        X.append(features)
        y.append(natural_tokens_to_optimal_class(nat_tokens))

    return X, y


def class_to_score_midpoint(cls: str) -> float:
    """Map budget class to the midpoint of its score range for regression target."""
    midpoints = {
        "low":      LOW_MAX / 2,
        "medium":   (LOW_MAX + MEDIUM_MAX) / 2,
        "high":     (MEDIUM_MAX + HIGH_MAX) / 2,
        "critical": (HIGH_MAX + 10.0) / 2,
    }
    return midpoints[cls]


def fit_calibration(X: List[List[float]], y: List[str]) -> Dict[str, float]:
    """
    Fit a simple linear regression to find per-group weight multipliers.

    Minimizes MAE between predicted budget class score and target midpoint.
    Returns dict of {groupN: weight_multiplier}.
    """
    if not X:
        log.warning("No data for calibration. Using default weights (1.0).")
        return {f"group{i+1}": 1.0 for i in range(5)}

    try:
        import numpy as np
    except ImportError:
        log.error("numpy required for calibration: pip install numpy")
        return {f"group{i+1}": 1.0 for i in range(5)}

    X_arr = np.array(X)
    y_scores = np.array([class_to_score_midpoint(cls) for cls in y])

    # Solve the least-squares problem: X @ w ≈ y_scores, w >= 0
    # Use non-negative least squares to keep weights positive
    from scipy.optimize import nnls
    w, residual = nnls(X_arr, y_scores)

    # Normalize weights relative to default (1.0 baseline)
    # The raw weights are the absolute group contributions; convert to multipliers
    baseline_weights = np.ones(5)
    multipliers = w / baseline_weights if baseline_weights.sum() > 0 else w

    # Cap multipliers to [0.1, 5.0] to avoid degenerate fits
    multipliers = np.clip(multipliers, 0.1, 5.0)

    # Evaluate accuracy
    raw_scores = X_arr @ multipliers
    pred_classes = [_score_to_class(s) for s in raw_scores]
    accuracy = sum(p == actual for p, actual in zip(pred_classes, y)) / len(y)
    log.info("Calibration accuracy: %.1f%%", accuracy * 100)

    mae = float(np.mean(np.abs(raw_scores - y_scores)))
    log.info("Mean absolute error (score units): %.3f", mae)

    return {
        "group1": float(multipliers[0]),
        "group2": float(multipliers[1]),
        "group3": float(multipliers[2]),
        "group4": float(multipliers[3]),
        "group5": float(multipliers[4]),
        "_metadata": {
            "n_samples": len(X),
            "accuracy": accuracy,
            "mae": mae,
        }
    }


def _score_to_class(score: float) -> str:
    if score <= LOW_MAX:
        return "low"
    if score <= MEDIUM_MAX:
        return "medium"
    if score <= HIGH_MAX:
        return "high"
    return "critical"


def analyze_score_distribution(results: List[dict]) -> None:
    """Print descriptive statistics of the natural token distribution."""
    from gateway.complexity_scorer import ComplexityScorer
    scorer = ComplexityScorer()

    scores = []
    token_counts = []
    for result in results:
        prompt = result.get("prompt", "")
        nat = result.get("reasoning_tokens", 0) + result.get("output_tokens", 0)
        if prompt and nat > 0:
            cr = scorer.score(prompt)
            scores.append(cr.score)
            token_counts.append(nat)

    if not scores:
        log.warning("No valid results for distribution analysis.")
        return

    try:
        import numpy as np
        print(f"\nComplexity Score Distribution ({len(scores)} samples):")
        print(f"  Mean:   {np.mean(scores):.2f}")
        print(f"  Median: {np.median(scores):.2f}")
        print(f"  P25:    {np.percentile(scores, 25):.2f}")
        print(f"  P75:    {np.percentile(scores, 75):.2f}")
        print(f"  Max:    {np.max(scores):.2f}")

        print(f"\nNatural Token Count Distribution:")
        print(f"  Mean:   {np.mean(token_counts):.0f}")
        print(f"  P25:    {np.percentile(token_counts, 25):.0f}  ← low budget ceiling")
        print(f"  P50:    {np.percentile(token_counts, 50):.0f}  ← medium budget ceiling")
        print(f"  P75:    {np.percentile(token_counts, 75):.0f}")
        print(f"  Max:    {np.max(token_counts):.0f}")
    except ImportError:
        log.warning("numpy not available for distribution analysis.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate complexity scorer against baseline 1 results")
    parser.add_argument("--input", nargs="+", required=True, help="Baseline 1 result JSON files")
    parser.add_argument("--output", default="evaluation/calibration_weights.json",
                        help="Output path for calibration weights")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Only print distribution analysis; do not fit")
    args = parser.parse_args()

    results = load_baseline_results(args.input)
    analyze_score_distribution(results)

    if not args.analyze_only:
        X, y = compute_feature_scores(results)
        weights = fit_calibration(X, y)

        with open(args.output, "w") as f:
            json.dump(weights, f, indent=2)
        log.info("Calibration weights written to %s", args.output)
        print(f"\nCalibration weights:")
        for k, v in weights.items():
            if not k.startswith("_"):
                print(f"  {k}: {v:.4f}")
        print(f"\nCommit {args.output} to the repository.")
        print("Load in gateway: get_scorer(calibration_weights=weights)")
