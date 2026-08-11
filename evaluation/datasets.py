"""
Dataset schema, registry, and loading infrastructure.

Per CLAUDE.md Section 20.3, five datasets are required:
  - GSM8K:                100 examples, exact-match numerical, ground truth available
  - MATH-500:             100 examples, normalized symbolic (SymPy), ground truth available
  - HumanEval:            50 examples, sandboxed test runner Pass@1
  - Enterprise Synthetic: 200 examples, LLM judge (GPT-4o-mini), 10% human-reviewed
  - Adversarial:          50 examples, system behavior correctness

EXECUTION STATUS: BLOCKED for all datasets.
  Datasets require: pip install datasets; huggingface download.
  They are not committed to the repository (large external assets).
  Loading functions return [] with a BLOCKED status when unavailable.

Per CLAUDE.md Section 27 rule 2: never substitute another dataset.
Per phase spec §30: if dataset unavailable, mark as BLOCKED — do not substitute.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from evaluation.result_schema import DatasetKind, DATASET_EXPECTED_COUNTS, DATASET_REGISTRY

log = logging.getLogger(__name__)


# ── Dataset record schema ─────────────────────────────────────────────────────

@dataclass
class DatasetRecord:
    """
    One evaluation example ready for inference.
    Per CLAUDE.md: ground truth available for GSM8K, MATH-500, HumanEval.
    """
    example_id: str                         # Unique within dataset
    dataset: str                            # Matches DATASET_REGISTRY keys
    prompt: str                             # Input to the model
    ground_truth: Optional[str]             # None for enterprise_synthetic, adversarial
    test_cases: Optional[list[str]]         # HumanEval only
    expected_behavior: Optional[str]        # Adversarial: "block" | "flag" | "escalate"
    task_category: str                      # For per-slice regression gate


@dataclass
class DatasetLoadResult:
    """Result of a dataset loading attempt."""
    dataset: str
    records: list[DatasetRecord]
    status: str                             # "loaded" | "blocked" | "partial"
    block_reason: Optional[str] = None
    expected_count: int = 0
    loaded_count: int = 0

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def count_matches(self) -> bool:
        return self.loaded_count == self.expected_count


# ── Dataset loading ───────────────────────────────────────────────────────────

def load_dataset(name: str) -> DatasetLoadResult:
    """
    Load a dataset by name.

    BLOCKED when:
      - huggingface `datasets` library is not installed
      - dataset is not cached locally

    Per CLAUDE.md §27 rule 2: never substitute with another dataset.
    Per phase spec §30: if model/dataset unavailable, mark BLOCKED, do not fake.
    """
    expected = DATASET_EXPECTED_COUNTS.get(name, 0)

    if name not in DATASET_REGISTRY:
        return DatasetLoadResult(
            dataset=name,
            records=[],
            status="blocked",
            block_reason=f"Unknown dataset: {name!r}. Valid: {list(DATASET_REGISTRY.keys())}",
            expected_count=expected,
            loaded_count=0,
        )

    loaders = {
        "gsm8k":                _load_gsm8k,
        "math500":              _load_math500,
        "humaneval":            _load_humaneval,
        "enterprise_synthetic": _load_enterprise_synthetic,
        "adversarial":          _load_adversarial,
    }

    return loaders[name](expected)


def validate_dataset(result: DatasetLoadResult) -> list[str]:
    """
    Validate a loaded dataset for integrity.
    Per §38: check for duplicates, missing ground truth, malformed records.
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    if result.is_blocked:
        return [f"BLOCKED: {result.block_reason}"]

    # Duplicate example_id check
    ids = [r.example_id for r in result.records]
    if len(ids) != len(set(ids)):
        from collections import Counter
        dupes = [eid for eid, cnt in Counter(ids).items() if cnt > 1]
        errors.append(f"Duplicate example_ids: {dupes}")

    # Count check
    if result.loaded_count != result.expected_count:
        errors.append(
            f"Loaded {result.loaded_count} examples but expected {result.expected_count}"
        )

    # Per-record validation
    kind = DATASET_REGISTRY.get(result.dataset)
    for r in result.records:
        if not r.prompt:
            errors.append(f"example_id={r.example_id}: empty prompt")
        if kind == DatasetKind.VERIFIABLE and r.ground_truth is None and r.test_cases is None:
            errors.append(f"example_id={r.example_id}: verifiable dataset missing ground_truth/test_cases")
        if result.dataset == "adversarial" and r.expected_behavior is None:
            errors.append(f"example_id={r.example_id}: adversarial example missing expected_behavior")

    return errors


# ── Private loaders (all BLOCKED — GPU node required) ─────────────────────────

_BLOCK_REASON_HF = (
    "BLOCKED — GPU node required. "
    "Install datasets: pip install datasets. "
    "Download and cache the dataset before running. "
    "See evaluation/baseline_measurements.py module docstring."
)


def _load_gsm8k(expected: int) -> DatasetLoadResult:
    """
    Load GSM8K test set, 100 examples.
    Source: huggingface datasets 'gsm8k', config='main', split='test'.
    """
    try:
        from datasets import load_dataset as hf_load  # type: ignore
    except ImportError:
        return DatasetLoadResult(
            dataset="gsm8k", records=[], status="blocked",
            block_reason=_BLOCK_REASON_HF, expected_count=expected, loaded_count=0,
        )
    try:
        ds = hf_load("gsm8k", "main", split="test")
        records = []
        for i, ex in enumerate(ds):
            if i >= expected:
                break
            records.append(DatasetRecord(
                example_id=f"gsm8k_{i:04d}",
                dataset="gsm8k",
                prompt=ex["question"],
                ground_truth=_extract_gsm8k_answer(ex["answer"]),
                test_cases=None,
                expected_behavior=None,
                task_category="arithmetic",
            ))
        return DatasetLoadResult(
            dataset="gsm8k", records=records, status="loaded",
            expected_count=expected, loaded_count=len(records),
        )
    except Exception as exc:
        return DatasetLoadResult(
            dataset="gsm8k", records=[], status="blocked",
            block_reason=f"BLOCKED — dataset load failed: {exc}",
            expected_count=expected, loaded_count=0,
        )


def _extract_gsm8k_answer(answer_text: str) -> str:
    """Extract the final numeric answer from GSM8K answer field."""
    lines = answer_text.strip().split("\n")
    for line in reversed(lines):
        if "####" in line:
            return line.split("####")[-1].strip().replace(",", "")
    return lines[-1].strip() if lines else ""


def _load_math500(expected: int) -> DatasetLoadResult:
    """
    Load MATH-500 test set, 100 examples.
    Source: huggingface datasets 'hendrycks/competition_math' or 'lighteval/MATH'.
    """
    try:
        from datasets import load_dataset as hf_load  # type: ignore
    except ImportError:
        return DatasetLoadResult(
            dataset="math500", records=[], status="blocked",
            block_reason=_BLOCK_REASON_HF, expected_count=expected, loaded_count=0,
        )
    try:
        ds = hf_load("lighteval/MATH", split="test")
        records = []
        for i, ex in enumerate(ds):
            if i >= expected:
                break
            records.append(DatasetRecord(
                example_id=f"math500_{i:04d}",
                dataset="math500",
                prompt=ex["problem"],
                ground_truth=ex.get("solution", ""),
                test_cases=None,
                expected_behavior=None,
                task_category=ex.get("type", "math"),
            ))
        return DatasetLoadResult(
            dataset="math500", records=records, status="loaded",
            expected_count=expected, loaded_count=len(records),
        )
    except Exception as exc:
        return DatasetLoadResult(
            dataset="math500", records=[], status="blocked",
            block_reason=f"BLOCKED — dataset load failed: {exc}",
            expected_count=expected, loaded_count=0,
        )


def _load_humaneval(expected: int) -> DatasetLoadResult:
    """
    Load HumanEval, 50 examples.
    Source: huggingface datasets 'openai_humaneval'.
    """
    try:
        from datasets import load_dataset as hf_load  # type: ignore
    except ImportError:
        return DatasetLoadResult(
            dataset="humaneval", records=[], status="blocked",
            block_reason=_BLOCK_REASON_HF, expected_count=expected, loaded_count=0,
        )
    try:
        ds = hf_load("openai_humaneval", split="test")
        records = []
        for i, ex in enumerate(ds):
            if i >= expected:
                break
            # test field contains executable assertions
            test_str = ex.get("test", "")
            test_cases = [line for line in test_str.split("\n") if line.strip().startswith("assert")]
            records.append(DatasetRecord(
                example_id=f"humaneval_{ex['task_id'].replace('/', '_')}",
                dataset="humaneval",
                prompt=ex["prompt"],
                ground_truth=None,
                test_cases=test_cases if test_cases else [test_str],
                expected_behavior=None,
                task_category="code_completion",
            ))
        return DatasetLoadResult(
            dataset="humaneval", records=records, status="loaded",
            expected_count=expected, loaded_count=len(records),
        )
    except Exception as exc:
        return DatasetLoadResult(
            dataset="humaneval", records=[], status="blocked",
            block_reason=f"BLOCKED — dataset load failed: {exc}",
            expected_count=expected, loaded_count=0,
        )


def _load_enterprise_synthetic(expected: int) -> DatasetLoadResult:
    """
    Load enterprise synthetic dataset, 200 examples.
    Per CLAUDE.md §20.3: 10% human-reviewed, LLM judge for rest.
    Not publicly available — must be provided as evaluation/data/enterprise_synthetic.jsonl.
    """
    import json
    from pathlib import Path
    data_path = Path("evaluation/data/enterprise_synthetic.jsonl")
    if not data_path.exists():
        return DatasetLoadResult(
            dataset="enterprise_synthetic", records=[], status="blocked",
            block_reason=(
                "BLOCKED — evaluation/data/enterprise_synthetic.jsonl not found. "
                "This dataset is not publicly available. "
                "Provide as JSONL with fields: id, prompt, task_category, expected_schema (optional)."
            ),
            expected_count=expected, loaded_count=0,
        )
    try:
        records = []
        with open(data_path) as f:
            for i, line in enumerate(f):
                if i >= expected:
                    break
                ex = json.loads(line)
                records.append(DatasetRecord(
                    example_id=ex.get("id", f"es_{i:04d}"),
                    dataset="enterprise_synthetic",
                    prompt=ex["prompt"],
                    ground_truth=None,
                    test_cases=None,
                    expected_behavior=None,
                    task_category=ex.get("task_category", "general"),
                ))
        return DatasetLoadResult(
            dataset="enterprise_synthetic", records=records, status="loaded",
            expected_count=expected, loaded_count=len(records),
        )
    except Exception as exc:
        return DatasetLoadResult(
            dataset="enterprise_synthetic", records=[], status="blocked",
            block_reason=f"BLOCKED — load failed: {exc}",
            expected_count=expected, loaded_count=0,
        )


def _load_adversarial(expected: int) -> DatasetLoadResult:
    """
    Load adversarial dataset, 50 examples.
    Per CLAUDE.md §20.3: covers prompt injection, PII, pathological inputs,
    schema violations, requests designed to trigger each of the 10 failure modes.
    Not publicly available — must be provided as evaluation/data/adversarial.jsonl.
    """
    import json
    from pathlib import Path
    data_path = Path("evaluation/data/adversarial.jsonl")
    if not data_path.exists():
        return DatasetLoadResult(
            dataset="adversarial", records=[], status="blocked",
            block_reason=(
                "BLOCKED — evaluation/data/adversarial.jsonl not found. "
                "This dataset is not publicly available. "
                "Provide as JSONL with fields: id, prompt, expected_behavior, task_category."
            ),
            expected_count=expected, loaded_count=0,
        )
    try:
        records = []
        with open(data_path) as f:
            for i, line in enumerate(f):
                if i >= expected:
                    break
                ex = json.loads(line)
                records.append(DatasetRecord(
                    example_id=ex.get("id", f"adv_{i:04d}"),
                    dataset="adversarial",
                    prompt=ex["prompt"],
                    ground_truth=None,
                    test_cases=None,
                    expected_behavior=ex.get("expected_behavior"),
                    task_category=ex.get("task_category", "adversarial"),
                ))
        return DatasetLoadResult(
            dataset="adversarial", records=records, status="loaded",
            expected_count=expected, loaded_count=len(records),
        )
    except Exception as exc:
        return DatasetLoadResult(
            dataset="adversarial", records=[], status="blocked",
            block_reason=f"BLOCKED — load failed: {exc}",
            expected_count=expected, loaded_count=0,
        )
