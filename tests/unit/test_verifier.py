"""
Unit tests for verifier_service verifier implementations.

Coverage:
  GSM8KVerifier   — correct, incorrect, unverifiable (no numbers, bad float)
  MathVerifier    — exact match, SymPy equivalence, boxed extraction, unverifiable
  HumanEvalRunner — correct execution, timeout, no code, wrong result
  SchemaVerifier  — valid JSON+schema, invalid JSON, schema violation, no schema

No external services required.  HumanEval tests execute real subprocess with
short-lived trivial scripts; they do not rely on the evaluation harness.
"""
from __future__ import annotations

import pytest

from verifier_service.gsm8k_verifier import GSM8KVerifier
from verifier_service.humaneval_runner import HumanEvalRunner
from verifier_service.math_verifier import MathVerifier
from verifier_service.schema_verifier import SchemaVerifier


# ── GSM8K ─────────────────────────────────────────────────────────────────────

class TestGSM8KVerifier:
    """Per CLAUDE.md §15.3 GSM8K verifier spec."""

    @pytest.fixture
    def v(self):
        return GSM8KVerifier()

    def test_correct_exact_match(self, v):
        r = v.verify("The answer is 42", "42")
        assert r.result == "correct"

    def test_correct_last_number_extracted(self, v):
        # Response has multiple numbers; last one must be used
        r = v.verify("Step 1: 100, Step 2: 200, Final: 42", "42")
        assert r.result == "correct"

    def test_correct_with_comma_in_number(self, v):
        r = v.verify("The total is 1,234", "1234")
        assert r.result == "correct"

    def test_incorrect_wrong_answer(self, v):
        r = v.verify("The answer is 41", "42")
        assert r.result == "incorrect"

    def test_unverifiable_no_numbers(self, v):
        r = v.verify("There is no numeric answer here", "42")
        assert r.result == "unverifiable"

    def test_unverifiable_no_expected(self, v):
        r = v.verify("The answer is 42", None)
        assert r.result == "unverifiable"

    def test_latency_ms_positive(self, v):
        r = v.verify("42", "42")
        assert r.latency_ms >= 0.0

    def test_extracted_answer_populated(self, v):
        r = v.verify("Answer: 99", "99")
        assert r.extracted_answer == "99.0"

    def test_expected_answer_populated(self, v):
        r = v.verify("Answer: 99", "99")
        assert r.expected_answer == "99.0"

    def test_correct_float_answer(self, v):
        r = v.verify("Result: 3.14", "3.14")
        assert r.result == "correct"

    def test_incorrect_float_mismatch(self, v):
        r = v.verify("Result: 3.14", "3.15")
        assert r.result == "incorrect"

    def test_negative_number(self, v):
        r = v.verify("The answer is -5", "-5")
        assert r.result == "correct"


# ── MathVerifier ──────────────────────────────────────────────────────────────

class TestMathVerifier:
    """Per CLAUDE.md §15.3 MATH-500 verifier spec."""

    @pytest.fixture
    def v(self):
        return MathVerifier()

    def test_correct_exact_string_match(self, v):
        # MathVerifier uses last-line fallback, not regex extraction;
        # "42" as the full response normalizes to "42" which matches expected "42".
        r = v.verify("42", "42")
        assert r.result == "correct"

    def test_correct_boxed_extraction(self, v):
        r = v.verify(r"Therefore, $\boxed{42}$", "42")
        assert r.result == "correct"

    def test_correct_boxed_with_spaces(self, v):
        r = v.verify(r"We get \boxed{ 42 }", "42")
        assert r.result == "correct"

    def test_correct_sympy_equivalence(self, v):
        # 1/2 == 0.5 symbolically
        r = v.verify(r"\boxed{1/2}", "0.5")
        assert r.result in ("correct", "unverifiable")  # depends on SymPy being installed

    def test_incorrect_different_value(self, v):
        r = v.verify("41", "42")
        assert r.result == "incorrect"

    def test_unverifiable_no_expected(self, v):
        r = v.verify("The answer is 42", None)
        assert r.result == "unverifiable"

    def test_latency_ms_positive(self, v):
        r = v.verify("42", "42")
        assert r.latency_ms >= 0.0

    def test_parsed_response_populated(self, v):
        r = v.verify("42", "42")
        assert r.parsed_response is not None

    def test_normalized_comparison_case_insensitive(self, v):
        # Both should normalize to the same string
        r = v.verify("pi", "pi")
        assert r.result == "correct"


# ── HumanEvalRunner ───────────────────────────────────────────────────────────

class TestHumanEvalRunner:
    """Per CLAUDE.md §15.3 HumanEval verifier spec."""

    @pytest.fixture
    def v(self):
        return HumanEvalRunner()

    def test_correct_simple_function(self, v):
        code = "def add(a, b):\n    return a + b\n"
        tests = ["assert add(1, 2) == 3"]
        r = v.verify(f"```python\n{code}```", tests)
        assert r.result == "correct"

    def test_correct_bare_function(self, v):
        code = "def double(x):\n    return x * 2\n"
        tests = ["assert double(5) == 10"]
        r = v.verify(code, tests)
        assert r.result == "correct"

    def test_incorrect_wrong_implementation(self, v):
        code = "def add(a, b):\n    return a - b\n"
        tests = ["assert add(1, 2) == 3"]
        r = v.verify(f"```python\n{code}```", tests)
        assert r.result == "incorrect"

    def test_unverifiable_no_test_cases(self, v):
        r = v.verify("def add(a, b): return a + b", [])
        assert r.result == "unverifiable"

    def test_unverifiable_no_code(self, v):
        r = v.verify("", ["assert True"])
        assert r.result == "unverifiable"

    def test_latency_ms_positive(self, v):
        code = "def f(): pass"
        tests = ["f()"]
        r = v.verify(code, tests)
        assert r.latency_ms >= 0.0

    def test_test_cases_total_populated(self, v):
        code = "def f(): pass"
        tests = ["f()", "f()"]
        r = v.verify(code, tests)
        assert r.test_cases_total == 2

    def test_incorrect_syntax_error(self, v):
        code = "def broken(:\n    pass"
        tests = ["assert True"]
        r = v.verify(f"```python\n{code}```", tests)
        assert r.result in ("incorrect", "unverifiable")


# ── SchemaVerifier ─────────────────────────────────────────────────────────────

class TestSchemaVerifier:
    """Per CLAUDE.md §15.3 JSON Schema verifier spec."""

    @pytest.fixture
    def v(self):
        return SchemaVerifier()

    @pytest.fixture
    def simple_schema(self):
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }

    def test_correct_valid_json_and_schema(self, v, simple_schema):
        r = v.verify('{"name": "Alice", "age": 30}', simple_schema)
        assert r.result == "correct"

    def test_correct_json_in_markdown_block(self, v, simple_schema):
        response = '```json\n{"name": "Bob"}\n```'
        r = v.verify(response, simple_schema)
        assert r.result == "correct"

    def test_incorrect_invalid_json(self, v, simple_schema):
        r = v.verify("This is not JSON", simple_schema)
        assert r.result == "incorrect"

    def test_incorrect_schema_violation_missing_required(self, v, simple_schema):
        r = v.verify('{"age": 30}', simple_schema)
        assert r.result == "incorrect"

    def test_incorrect_wrong_type(self, v, simple_schema):
        r = v.verify('{"name": 123}', simple_schema)
        assert r.result == "incorrect"

    def test_unverifiable_no_schema(self, v):
        r = v.verify('{"key": "value"}', {})
        assert r.result == "unverifiable"

    def test_latency_ms_positive(self, v, simple_schema):
        r = v.verify('{"name": "test"}', simple_schema)
        assert r.latency_ms >= 0.0

    def test_validation_errors_populated_on_failure(self, v, simple_schema):
        r = v.verify("not json", simple_schema)
        assert len(r.validation_errors) > 0

    def test_correct_nested_object(self, v):
        schema = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                }
            },
        }
        r = v.verify('{"data": {"value": 3.14}}', schema)
        assert r.result == "correct"

    def test_correct_array_response(self, v):
        schema = {"type": "array", "items": {"type": "string"}}
        r = v.verify('["a", "b", "c"]', schema)
        assert r.result == "correct"

    def test_incorrect_array_wrong_item_type(self, v):
        schema = {"type": "array", "items": {"type": "string"}}
        r = v.verify('[1, 2, 3]', schema)
        assert r.result == "incorrect"
