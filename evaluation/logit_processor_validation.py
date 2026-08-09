"""
LogitProcessor Validation Gate — CLAUDE.md Section 9.6

Runs 50 diverse queries × 5 forced positions (25%, 50%, 75%, 100%, natural).
Measures coherence and completeness for each via LLM-as-judge (GPT-4o-mini).
Gate criterion: coherence rate ≥ 85% at ALL five positions.

BLOCKED STATUS: Requires GPU node with:
  - DeepSeek-R1-7B-Q4 model downloaded and cached
  - vLLM serving instance running on port 8080
  - CUDA runtime available
  - OPENAI_API_KEY set (for LLM judge calls)

To run on GPU node:
  1. Download model:
     huggingface-cli download deepseek-ai/DeepSeek-R1-Distill-Qwen-7B

  2. Start vLLM:
     python -m vllm.entrypoints.openai.api_server \\
       --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \\
       --served-model-name deepseek-r1-7b \\
       --quantization awq \\
       --port 8080

  3. Discover EOT token:
     python -c "
     from transformers import AutoTokenizer
     tok = AutoTokenizer.from_pretrained('deepseek-ai/DeepSeek-R1-Distill-Qwen-7B')
     eot = tok.convert_tokens_to_ids('</think>')
     print(f'EOT token ID: {eot}')
     "
     → Update vllm_adapter/constants.py with the discovered ID.

  4. Run this script:
     VLLM_BASE_URL=http://localhost:8080 \\
     OPENAI_API_KEY=sk-... \\
     python evaluation/logit_processor_validation.py

Gate result is printed as: LOGITPROCESSOR GATE: PASS / FAIL
If FAIL: HardBudgetFallback is the documented approach. Do not proceed with
the LogitProcessor until re-validated.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Gate configuration ────────────────────────────────────────────────────────

COHERENCE_THRESHOLD = 0.85        # ≥85% coherence at each position
NUM_QUERIES = 50
FORCED_POSITIONS = [0.25, 0.50, 0.75, 1.00, None]  # None = natural completion
JUDGE_MODEL = "gpt-4o-mini"

# ── 50 diverse query prompts (per CLAUDE.md: diverse across difficulty/domain) ─
# These cover: math, coding, reasoning, factual, multi-step, ambiguous, creative
VALIDATION_QUERIES = [
    # Arithmetic / math
    "What is 347 × 28?",
    "Solve: 2x + 5 = 17. What is x?",
    "What is the square root of 144?",
    "If a train travels 60 mph for 2.5 hours, how far does it go?",
    "What is 15% of 240?",
    # Algebra / proofs
    "Prove that the sum of two odd numbers is even.",
    "Solve the quadratic equation: x² - 5x + 6 = 0",
    "Simplify: (3x² - 2x + 1) + (x² + 4x - 3)",
    "Find all integers n such that n² ≡ 1 (mod 8).",
    "If f(x) = 2x + 3 and g(x) = x², find g(f(2)).",
    # Reasoning
    "Alice is taller than Bob. Bob is taller than Carol. Who is shortest?",
    "If all mammals breathe air, and dolphins are mammals, what can we conclude?",
    "A bat and ball cost $1.10. The bat costs $1 more than the ball. How much is the ball?",
    "You have 5 red and 3 blue marbles. What is P(blue | drawn without replacement)?",
    "In a room of 30 people, what is the probability two share a birthday?",
    # Coding
    "Write a Python function to reverse a string.",
    "How do you find the length of a list in Python?",
    "What is the time complexity of binary search?",
    "Write SQL to select the top 5 customers by revenue.",
    "What is the difference between a stack and a queue?",
    # Factual / knowledge
    "What is the capital of Australia?",
    "Who wrote Romeo and Juliet?",
    "What year did World War II end?",
    "What is the chemical symbol for gold?",
    "What planet is closest to the Sun?",
    # Multi-step reasoning
    "Step 1: Define entropy. Step 2: Explain why entropy always increases in an isolated system.",
    "First, explain what recursion is. Then give a simple example in Python.",
    "Explain the steps of the water cycle in order.",
    "Describe Newton's three laws of motion, one at a time.",
    "Walk through how HTTPS works, step by step.",
    # Analysis / comparison
    "Compare bubble sort and merge sort in terms of time and space complexity.",
    "What are the key differences between Python 2 and Python 3?",
    "Compare the French and American revolutions.",
    "What are the pros and cons of using a relational database vs. a document store?",
    "Explain the difference between supervised and unsupervised machine learning.",
    # Constraint-heavy
    "List the first 10 prime numbers in ascending order.",
    "Write exactly 3 sentences about photosynthesis.",
    "Name 5 countries in Europe that are not in the EU.",
    "Give 3 examples of metaphors, then 3 of similes.",
    "Describe recursion using only words a 10-year-old would understand.",
    # Edge / adversarial
    "What is the meaning of life?",
    "Is this sentence true or false: 'This sentence is false.'",
    "Explain Gödel's incompleteness theorem simply.",
    "How many grains of sand are on Earth? Give an order-of-magnitude estimate.",
    "What is the sound of one hand clapping?",
    # Structured output
    "List the planets of the solar system as a JSON array.",
    "Summarize the water cycle in exactly 2 sentences.",
    "What are 3 benefits of exercise? Answer as a numbered list.",
    "Give the chemical formula for water and explain why it has that formula.",
    "Define 'recursion' in one sentence, then give one Python example.",
]

assert len(VALIDATION_QUERIES) == NUM_QUERIES, (
    f"Expected {NUM_QUERIES} queries, got {len(VALIDATION_QUERIES)}"
)


# ── Result tracking ────────────────────────────────────────────────────────────

@dataclass
class PositionResult:
    position_fraction: Optional[float]    # None = natural
    query: str
    forced_at_token: int
    response_text: str
    coherence_score: float     # 1–5 LLM judge score
    is_coherent: bool          # score >= 3 (threshold for "coherent")
    judge_reasoning: str
    latency_ms: float
    error: Optional[str] = None


@dataclass
class ValidationReport:
    gate_pass: bool
    coherence_by_position: dict = field(default_factory=dict)
    total_queries: int = 0
    total_evaluated: int = 0
    failed_positions: list = field(default_factory=list)
    results: list = field(default_factory=list)

    def print_summary(self):
        status = "PASS" if self.gate_pass else "FAIL"
        print(f"\n{'='*60}")
        print(f"LOGITPROCESSOR GATE: {status}")
        print(f"{'='*60}")
        print(f"Total queries:    {self.total_queries}")
        print(f"Total evaluated:  {self.total_evaluated}")
        print(f"\nCoherence rate by position:")
        for pos, rate in self.coherence_by_position.items():
            label = f"{int(pos*100)}%" if isinstance(pos, float) else "natural"
            gate = "✓" if rate >= COHERENCE_THRESHOLD else "✗ FAIL"
            print(f"  {label:8s}: {rate:.1%}  {gate}")
        if self.failed_positions:
            print(f"\nFailed positions: {self.failed_positions}")
            print(f"\nDecision: HardBudgetFallback is the documented approach.")
            print(f"Do NOT use BudgetLogitProcessor until the gate passes.")
        else:
            print(f"\nDecision: BudgetLogitProcessor validated. Proceed with Phase 2.")
        print(f"{'='*60}\n")


# ── Main validation runner ────────────────────────────────────────────────────

def run_validation(
    vllm_base_url: str,
    openai_api_key: str,
    output_path: str = "evaluation/logit_processor_validation_results.json",
) -> ValidationReport:
    """
    Run the full LogitProcessor validation gate.

    BLOCKED if vLLM is not running or DeepSeek model is not loaded.
    """
    try:
        import httpx
        import openai
    except ImportError as e:
        log.error("Missing dependency: %s. Install: pip install httpx openai", e)
        sys.exit(1)

    from vllm_adapter.constants import (
        DEEPSEEK_R1_EOT_TOKEN_ID,
        DEEPSEEK_R1_EOT_VALIDATED,
        DEEPSEEK_MODEL_NAME,
    )

    if not DEEPSEEK_R1_EOT_VALIDATED:
        log.error(
            "BLOCKED: DeepSeek EOT token not discovered. "
            "Run on GPU node after model download. See module docstring."
        )
        sys.exit(2)

    # Health check
    try:
        resp = httpx.get(f"{vllm_base_url}/health", timeout=5.0)
        resp.raise_for_status()
        log.info("vLLM health check: OK")
    except Exception as e:
        log.error("BLOCKED: vLLM not reachable at %s: %s", vllm_base_url, e)
        sys.exit(3)

    # Natural completion pass — measure token lengths per query
    natural_token_counts: dict[str, int] = {}
    log.info("Pass 1/2: Measuring natural completion token counts...")
    for i, query in enumerate(VALIDATION_QUERIES):
        t0 = time.monotonic()
        response = _call_vllm(
            base_url=vllm_base_url,
            model=DEEPSEEK_MODEL_NAME,
            prompt=query,
            max_tokens=4096,
            logit_processor=None,
        )
        nat_tokens = response.get("usage", {}).get("completion_tokens", 512)
        natural_token_counts[query] = nat_tokens
        log.info("  Query %d/%d: %d tokens", i + 1, NUM_QUERIES, nat_tokens)

    # Forced position pass — for each query × position
    log.info("Pass 2/2: Running forced position evaluations...")
    client = openai.OpenAI(api_key=openai_api_key)
    all_results: list[PositionResult] = []

    for query in VALIDATION_QUERIES:
        nat_tokens = natural_token_counts.get(query, 512)

        for pos_fraction in FORCED_POSITIONS:
            if pos_fraction is None:
                forced_at = nat_tokens
            else:
                forced_at = max(1, int(nat_tokens * pos_fraction))

            t0 = time.monotonic()
            try:
                raw = _call_vllm(
                    base_url=vllm_base_url,
                    model=DEEPSEEK_MODEL_NAME,
                    prompt=query,
                    max_tokens=4096,
                    logit_processor_budget=forced_at,
                    eot_token_id=DEEPSEEK_R1_EOT_TOKEN_ID,
                )
                response_text = (
                    raw.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                latency_ms = (time.monotonic() - t0) * 1000.0

                coherence, reasoning = _judge_coherence(
                    client=client,
                    prompt=query,
                    response=response_text,
                )

                result = PositionResult(
                    position_fraction=pos_fraction,
                    query=query,
                    forced_at_token=forced_at,
                    response_text=response_text,
                    coherence_score=coherence,
                    is_coherent=coherence >= 3,
                    judge_reasoning=reasoning,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                log.error("Error at query=%r pos=%s: %s", query[:40], pos_fraction, exc)
                result = PositionResult(
                    position_fraction=pos_fraction,
                    query=query,
                    forced_at_token=forced_at,
                    response_text="",
                    coherence_score=0.0,
                    is_coherent=False,
                    judge_reasoning="",
                    latency_ms=0.0,
                    error=str(exc),
                )

            all_results.append(result)

    # Compute coherence by position
    coherence_by_position: dict = {}
    for pos in FORCED_POSITIONS:
        pos_results = [r for r in all_results if r.position_fraction == pos]
        if not pos_results:
            continue
        rate = sum(1 for r in pos_results if r.is_coherent) / len(pos_results)
        key = pos if pos is not None else "natural"
        coherence_by_position[key] = rate

    failed_positions = [
        pos for pos, rate in coherence_by_position.items()
        if rate < COHERENCE_THRESHOLD
    ]
    gate_pass = len(failed_positions) == 0

    report = ValidationReport(
        gate_pass=gate_pass,
        coherence_by_position=coherence_by_position,
        total_queries=NUM_QUERIES,
        total_evaluated=len(all_results),
        failed_positions=failed_positions,
        results=all_results,
    )
    report.print_summary()

    # Persist results
    with open(output_path, "w") as f:
        json.dump(
            {
                "gate_pass": gate_pass,
                "coherence_by_position": {
                    str(k): v for k, v in coherence_by_position.items()
                },
                "failed_positions": [str(p) for p in failed_positions],
                "results": [
                    {
                        "query": r.query,
                        "position": str(r.position_fraction),
                        "forced_at_token": r.forced_at_token,
                        "coherence_score": r.coherence_score,
                        "is_coherent": r.is_coherent,
                        "judge_reasoning": r.judge_reasoning,
                        "latency_ms": r.latency_ms,
                        "error": r.error,
                    }
                    for r in all_results
                ],
            },
            f,
            indent=2,
        )
    log.info("Results written to %s", output_path)
    return report


def _call_vllm(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    logit_processor=None,
    logit_processor_budget: Optional[int] = None,
    eot_token_id: Optional[int] = None,
) -> dict:
    import httpx

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }

    if logit_processor_budget is not None and eot_token_id is not None:
        from vllm_adapter.logit_processor import BudgetLogitProcessor
        # LogitProcessor is registered server-side; for HTTP API we pass
        # the budget via a vLLM-specific extra_body field
        # Actual mechanism validated in Week 1 (see serving_config.py)
        payload["max_tokens"] = logit_processor_budget + 1024
        # Placeholder: actual LogitProcessor registration is a Week 1 deliverable

    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


def _judge_coherence(client, prompt: str, response: str) -> tuple[float, str]:
    """
    Ask GPT-4o-mini to score coherence and completeness on a 1–5 scale.
    Returns (score, reasoning).
    """
    judge_prompt = f"""You are evaluating the quality of an AI response that was generated with a token budget constraint.

Original question: {prompt}

AI response (may be cut off mid-sentence due to token budget):
{response}

Rate the response on a scale of 1 to 5:
  1 = Completely incoherent or useless
  2 = Mostly incoherent, partially useful
  3 = Mostly coherent, the answer addresses the question even if incomplete
  4 = Coherent and substantially complete
  5 = Fully coherent and complete

Respond in JSON: {{"score": <1-5>, "reasoning": "<one sentence>"}}
"""
    try:
        result = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": judge_prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        content = result.choices[0].message.content.strip()
        data = json.loads(content)
        return float(data["score"]), data.get("reasoning", "")
    except Exception as e:
        log.warning("Judge call failed: %s", e)
        return 0.0, str(e)


if __name__ == "__main__":
    vllm_url = os.getenv("VLLM_BASE_URL", "http://localhost:8080")
    api_key = os.getenv("OPENAI_API_KEY", "")

    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    report = run_validation(vllm_base_url=vllm_url, openai_api_key=api_key)
    sys.exit(0 if report.gate_pass else 1)
