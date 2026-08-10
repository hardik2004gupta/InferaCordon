"""
MATH-500 verifier: symbolic equivalence check using SymPy.

Per CLAUDE.md Section 15.3:
  - Extract content within \boxed{} if present
  - Attempt exact string match after normalization
  - Fall back to SymPy: sympy.simplify(expr_predicted - expr_expected) == 0
  - Return parse_failed if SymPy cannot parse
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

try:
    import sympy
    from sympy.parsing.sympy_parser import (
        parse_expr,
        standard_transformations,
        implicit_multiplication_application,
    )
    _SYMPY_AVAILABLE = True
except ImportError:
    _SYMPY_AVAILABLE = False


@dataclass
class MathResult:
    result: str            # "correct" | "incorrect" | "unverifiable"
    parsed_response: str | None
    expected: str | None
    latency_ms: float


def _extract_boxed(text: str) -> str | None:
    """Extract the innermost \\boxed{...} content, handling nested braces."""
    start = text.rfind(r"\boxed{")
    if start == -1:
        return None
    content_start = start + len(r"\boxed{")
    depth = 0
    for i in range(content_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            if depth == 0:
                return text[content_start:i].strip()
            depth -= 1
    return None


def _normalize(s: str) -> str:
    return s.strip().replace(" ", "").replace("$", "").lower()


def _latex_to_sympy_str(s: str) -> str:
    """Convert basic LaTeX math notation to SymPy-parseable string."""
    s = s.replace("$", "").strip()
    # \frac{a}{b} → (a)/(b)
    def _frac(m: re.Match) -> str:
        return f"({m.group(1)})/({m.group(2)})"
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", _frac, s)
    # \sqrt{a} → sqrt(a)
    s = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", s)
    # \sqrt[n]{a} → (a)**(1/n)
    s = re.sub(r"\\sqrt\[([^\]]+)\]\{([^{}]+)\}", r"(\2)**(1/\1)", s)
    # \times → *, \div → /
    s = s.replace(r"\times", "*").replace(r"\div", "/")
    # Remove display formatting commands that carry no math meaning
    s = re.sub(r"\\(left|right|cdot|,|;|!| )", "", s)
    # Remove remaining unknown backslash commands
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    return s.strip()


def _sympy_equal(a: str, b: str) -> bool | None:
    """
    Returns True if SymPy considers a == b symbolically, False if not,
    None if either expression cannot be parsed.
    """
    if not _SYMPY_AVAILABLE:
        return None
    transformations = standard_transformations + (implicit_multiplication_application,)
    try:
        ea = parse_expr(_latex_to_sympy_str(a), transformations=transformations, evaluate=True)
        eb = parse_expr(_latex_to_sympy_str(b), transformations=transformations, evaluate=True)
        return sympy.simplify(ea - eb) == 0
    except Exception:
        return None


class MathVerifier:
    """
    Verifies MATH-500-style responses using symbolic equivalence.
    Per CLAUDE.md Section 15.3.
    """

    def verify(self, response: str, expected: str | None = None) -> MathResult:
        t0 = time.perf_counter()

        if expected is None:
            return MathResult(
                result="unverifiable",
                parsed_response=None,
                expected=None,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Extract predicted answer from \boxed{} if present
        predicted_raw = _extract_boxed(response)
        if predicted_raw is None:
            # Fall back to the last non-empty line
            lines = [ln.strip() for ln in response.strip().splitlines() if ln.strip()]
            predicted_raw = lines[-1] if lines else response.strip()

        predicted_str = predicted_raw.strip()
        expected_str = expected.strip()

        # 1. Exact match after normalization
        if _normalize(predicted_str) == _normalize(expected_str):
            return MathResult(
                result="correct",
                parsed_response=predicted_str,
                expected=expected_str,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # 2. SymPy symbolic equivalence (per CLAUDE.md §15.3)
        sym = _sympy_equal(predicted_str, expected_str)
        if sym is True:
            return MathResult(
                result="correct",
                parsed_response=predicted_str,
                expected=expected_str,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
        if sym is False:
            return MathResult(
                result="incorrect",
                parsed_response=predicted_str,
                expected=expected_str,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # SymPy parse failed
        return MathResult(
            result="unverifiable",
            parsed_response=predicted_str,
            expected=expected_str,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )
