"""
HumanEval verifier: sandboxed Python code execution.

Per CLAUDE.md Section 15.3:
  - Runs code extracted from response in a sandboxed subprocess
  - CPU time limit: 2 seconds
  - Memory limit: 256MB (Linux only via resource.setrlimit)
  - Uses subprocess.run([sys.executable, "-u", tmpfile], capture_output=True, timeout=2.0)

Security note:
  Full sandbox (os.setuid, network isolation) requires Linux.
  On Windows (dev host), only subprocess.timeout=2s applies; Docker container
  runs on Linux where full resource limits are enforced.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass


@dataclass
class HumanEvalResult:
    result: str            # "correct" | "incorrect" | "unverifiable"
    test_cases_passed: int
    test_cases_total: int
    latency_ms: float


def _extract_code(response: str) -> str | None:
    """Extract Python code from the response, preferring fenced blocks."""
    # Markdown Python block
    m = re.search(r"```python\s*\n(.*?)```", response, re.DOTALL)
    if m:
        return m.group(1)
    # Generic fenced block
    m = re.search(r"```\s*\n(.*?)```", response, re.DOTALL)
    if m:
        return m.group(1)
    # Bare function definition (greedy to end of response)
    m = re.search(r"(def \w+\(.*)", response, re.DOTALL)
    if m:
        return m.group(1)
    stripped = response.strip()
    return stripped if stripped else None


def _make_resource_preexec():
    """
    Build a preexec_fn that sets CPU and memory resource limits.
    Linux only — returns None on other platforms.
    Per CLAUDE.md §15.3: CPU=2s, Memory=256MB.
    """
    if sys.platform != "linux":
        return None
    try:
        import resource  # noqa: PLC0415

        def _limit() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
            _256mb = 256 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (_256mb, _256mb))

        return _limit
    except (ImportError, AttributeError):
        return None


class HumanEvalRunner:
    """
    Verifies HumanEval-style responses by executing extracted code in a
    sandboxed subprocess and running the provided test cases.
    Per CLAUDE.md Section 15.3.
    """

    def verify(self, response: str, test_cases: list[str]) -> HumanEvalResult:
        t0 = time.perf_counter()
        total = len(test_cases)

        if not test_cases:
            return HumanEvalResult(
                result="unverifiable",
                test_cases_passed=0,
                test_cases_total=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        code = _extract_code(response)
        if not code:
            return HumanEvalResult(
                result="unverifiable",
                test_cases_passed=0,
                test_cases_total=total,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        script = f"{code}\n\n" + "\n".join(test_cases) + "\n"
        tmpfile: str | None = None
        result = "unverifiable"

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, prefix="ic_heval_"
            ) as f:
                f.write(script)
                tmpfile = f.name

            preexec = _make_resource_preexec()
            proc = subprocess.run(
                [sys.executable, "-u", tmpfile],
                capture_output=True,
                timeout=2.0,
                text=True,
                preexec_fn=preexec,
            )
            result = "correct" if proc.returncode == 0 else "incorrect"

        except subprocess.TimeoutExpired:
            result = "incorrect"
        except Exception:
            result = "unverifiable"
        finally:
            if tmpfile:
                try:
                    os.unlink(tmpfile)
                except OSError:
                    pass

        return HumanEvalResult(
            result=result,
            test_cases_passed=total if result == "correct" else 0,
            test_cases_total=total,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )
