"""
GSM8K verifier: numeric answer extraction from reasoning model output.

Per CLAUDE.md Section 15.3 — exact implementation specified verbatim:
  matches = re.findall(r"[-\\d,]+\\.?\\d*", response)
  predicted = float(matches[-1].replace(",", ""))
  expected = float(ground_truth.replace(",", ""))
  passed = abs(predicted - expected) < 1e-6
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass


@dataclass
class GSM8KResult:
    result: str            # "correct" | "incorrect" | "unverifiable"
    extracted_answer: str | None
    expected_answer: str | None
    latency_ms: float


class GSM8KVerifier:
    """
    Verifies GSM8K-style arithmetic responses by extracting the final
    numeric value and comparing to ground truth.
    Per CLAUDE.md Section 15.3.
    """

    def verify(self, response: str, expected_answer: str | None = None) -> GSM8KResult:
        t0 = time.perf_counter()

        if expected_answer is None:
            return GSM8KResult(
                result="unverifiable",
                extracted_answer=None,
                expected_answer=None,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Per CLAUDE.md §15.3 verbatim
        matches = re.findall(r"[-\d,]+\.?\d*", response)
        if not matches:
            return GSM8KResult(
                result="unverifiable",
                extracted_answer=None,
                expected_answer=expected_answer,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        try:
            predicted = float(matches[-1].replace(",", ""))
            expected = float(expected_answer.replace(",", ""))
        except ValueError:
            return GSM8KResult(
                result="unverifiable",
                extracted_answer=matches[-1],
                expected_answer=expected_answer,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        passed = abs(predicted - expected) < 1e-6

        return GSM8KResult(
            result="correct" if passed else "incorrect",
            extracted_answer=str(predicted),
            expected_answer=str(expected),
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )
