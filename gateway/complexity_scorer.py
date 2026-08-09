"""
Heuristic complexity scorer — routes prompts to budget classes.

Per CLAUDE.md Section 10. Five feature groups, score 0–10, <3ms on CPU.
No ML inference, no network calls, no external dependencies.

Feature groups (canonical from CLAUDE.md Section 10.2):
  Group 1: Constraint keyword density      0–3.0
  Group 2: Structural signals              0–2.0
  Group 3: Technical domain signals        0–2.0
  Group 4: Length signal                   0–1.5
  Group 5: Output format complexity        0–1.5
  Total raw range: 0–10 → clamped to [0, 10]

Budget class thresholds (CLAUDE.md Section 10.5):
  complexity_score ≤ 3.5  → low
  complexity_score ≤ 6.5  → medium
  complexity_score ≤ 8.5  → high
  complexity_score > 8.5  → critical

Calibration (CLAUDE.md Section 10.4):
  Feature weights are adjusted once offline against Week 1 baseline token counts.
  See evaluation/complexity_calibration.py for the calibration script.
  Committed calibration weights override DEFAULT_THRESHOLDS below.
"""
from __future__ import annotations

import dataclasses
import re
import time
from typing import Dict, Optional

# ── Budget class thresholds ────────────────────────────────────────────────────

DEFAULT_THRESHOLDS: dict[str, float] = {
    "low_max": 3.5,
    "medium_max": 6.5,
    "high_max": 8.5,
}

# ── Feature group keyword vocabularies ─────────────────────────────────────────
# Per CLAUDE.md Section 10.2 — Feature Group 1: Constraint Keyword Density

_TIER3_KEYWORDS = [
    "prove", "derive", "demonstrate that", "show that", "verify that",
    "find all", "for all", "if and only if", "necessary and sufficient",
]
_TIER2_KEYWORDS = [
    "compare", "contrast", "analyze", "analyse", "evaluate", "explain why",
    "step by step", "what are the implications", "both", "unless", "however",
    "except when",
]
_TIER1_KEYWORDS = [
    "describe", "summarize", "summarise", "list", "what is", "who", "when", "where",
]

# Precompile keyword patterns (whole-word, case-insensitive)
_TIER3_PATTERNS = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in _TIER3_KEYWORDS]
_TIER2_PATTERNS = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in _TIER2_KEYWORDS]
_TIER1_PATTERNS = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in _TIER1_KEYWORDS]

# Per CLAUDE.md Section 10.2 — Feature Group 3: Technical Domain Signals
_CODE_BLOCK_RE = re.compile(r"(```|^    )", re.MULTILINE)
_MATH_NOTATION_RE = re.compile(r"(\$[^$]+\$|\$\$[^$]+\$\$|\\[a-zA-Z]+\{|[αβγδεζηθλμνξπρστυφχψω])", re.UNICODE)
_FORMAL_LOGIC_RE = re.compile(r"[∀∃→↔⟹⟺¬∧∨⊢⊨]")
_JSON_XML_RE = re.compile(r'(\{[^{}]{0,200}\}|<[a-zA-Z][^>]{0,100}/>|<[a-zA-Z][^>]{0,100}>.*?</[a-zA-Z]+>)', re.DOTALL)

# Per CLAUDE.md Section 10.2 — Feature Group 2: Structural Signals
_MULTI_STEP_RE = re.compile(
    r"(first\b.{1,200}then\b.{1,200}finally\b|step\s*1\b|step\s*one\b)",
    re.IGNORECASE | re.DOTALL,
)
_BULLET_RE = re.compile(r"^[\s]*[-*•]\s+|^\s*\d+[.)]\s+", re.MULTILINE)

# Per CLAUDE.md Section 10.2 — Feature Group 5: Output Format Complexity
_STRUCTURED_OUTPUT_RE = re.compile(
    r"\b(JSON|json|table|numbered list|code block|XML|YAML|CSV|markdown)\b",
    re.IGNORECASE,
)
_SECTIONS_RE = re.compile(r"(sections?|headers?|subheadings?|parts?)", re.IGNORECASE)
_FORMAT_CONSTRAINT_RE = re.compile(
    r"(exactly\s+\d+\s+word|must include|must contain|format|structure|schema|output format)",
    re.IGNORECASE,
)


# ── Result and scorer ──────────────────────────────────────────────────────────

@dataclasses.dataclass
class ComplexityResult:
    """Fully attributed complexity result per CLAUDE.md Section 10."""
    score: float                            # Final clamped score 0.0–10.0
    budget_class: str                       # "low" | "medium" | "high" | "critical"
    feature_breakdown: Dict[str, float]     # Group scores for observability
    latency_ms: float                       # Scoring wall time

    @property
    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "budget_class": self.budget_class,
            "feature_breakdown": self.feature_breakdown,
            "latency_ms": self.latency_ms,
        }


class ComplexityScorer:
    """
    Deterministic heuristic complexity scorer.

    All computation is pure Python/regex — no I/O, no ML, no network.
    Meets <3ms latency requirement on CPU per CLAUDE.md Section 10.1.

    Calibration is done offline (evaluation/complexity_calibration.py).
    The resulting weight adjustments are applied by passing custom weights
    to __init__. Default weights are per-spec in CLAUDE.md Section 10.
    """

    def __init__(
        self,
        thresholds: Optional[dict] = None,
        group1_weight: float = 1.0,
        group2_weight: float = 1.0,
        group3_weight: float = 1.0,
        group4_weight: float = 1.0,
        group5_weight: float = 1.0,
    ) -> None:
        """
        Args:
            thresholds:    Budget class thresholds. Defaults to CLAUDE.md values.
            groupN_weight: Calibration multipliers per feature group (default 1.0 = no adjustment).
                           Updated by evaluation/complexity_calibration.py after Week 1 baseline run.
        """
        self._thresholds = thresholds or dict(DEFAULT_THRESHOLDS)
        self._w = [
            group1_weight,
            group2_weight,
            group3_weight,
            group4_weight,
            group5_weight,
        ]

    # ── Public interface ───────────────────────────────────────────────────────

    def score(self, prompt: str) -> ComplexityResult:
        """
        Score a prompt and return a ComplexityResult with full feature attribution.
        Must complete in <3ms. No I/O permitted inside this method.
        """
        t0 = time.perf_counter()

        if not prompt or not prompt.strip():
            return ComplexityResult(
                score=0.0,
                budget_class="low",
                feature_breakdown={
                    "constraint_density": 0.0,
                    "structural_signals": 0.0,
                    "technical_domain": 0.0,
                    "length_signal": 0.0,
                    "output_format": 0.0,
                    "raw_score": 0.0,
                },
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
            )

        g1 = self._group1_constraint_density(prompt)
        g2 = self._group2_structural_signals(prompt)
        g3 = self._group3_technical_domain(prompt)
        g4 = self._group4_length_signal(prompt)
        g5 = self._group5_output_format(prompt)

        raw = (
            g1 * self._w[0]
            + g2 * self._w[1]
            + g3 * self._w[2]
            + g4 * self._w[3]
            + g5 * self._w[4]
        )
        final = float(min(10.0, max(0.0, raw)))
        budget_class = self._classify(final)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return ComplexityResult(
            score=final,
            budget_class=budget_class,
            feature_breakdown={
                "constraint_density": round(g1, 4),
                "structural_signals": round(g2, 4),
                "technical_domain": round(g3, 4),
                "length_signal": round(g4, 4),
                "output_format": round(g5, 4),
                "raw_score": round(raw, 4),
            },
            latency_ms=round(latency_ms, 3),
        )

    def classify(self, score: float) -> str:
        """Public: map a pre-computed score to a budget class string."""
        return self._classify(score)

    # ── Private: budget class mapping ─────────────────────────────────────────

    def _classify(self, score: float) -> str:
        """Map raw score to budget class using configured thresholds."""
        if score <= self._thresholds["low_max"]:
            return "low"
        if score <= self._thresholds["medium_max"]:
            return "medium"
        if score <= self._thresholds["high_max"]:
            return "high"
        return "critical"

    # ── Feature Group 1: Constraint Keyword Density (0–3.0) ───────────────────

    def _group1_constraint_density(self, prompt: str) -> float:
        """
        Per CLAUDE.md Section 10.2 — Feature Group 1.
        Tier weights: 3→1.5, 2→1.0, 1→0.5. Sum normalized to 0–3.
        """
        tier3_count = sum(len(p.findall(prompt)) for p in _TIER3_PATTERNS)
        tier2_count = sum(len(p.findall(prompt)) for p in _TIER2_PATTERNS)
        tier1_count = sum(len(p.findall(prompt)) for p in _TIER1_PATTERNS)

        raw = tier3_count * 1.5 + tier2_count * 1.0 + tier1_count * 0.5
        # Normalize to 0–3 (raw >= 2.0 maps to 3.0 ceiling)
        return float(min(3.0, raw))

    # ── Feature Group 2: Structural Signals (0–2.0) ───────────────────────────

    def _group2_structural_signals(self, prompt: str) -> float:
        """
        Per CLAUDE.md Section 10.2 — Feature Group 2.
        Components: question marks, sentence count, bullets, multi-step pattern.
        """
        # Question mark count: 0 → 0, 3+ → 1.0 (normalized)
        qmarks = prompt.count("?")
        q_score = min(1.0, qmarks / 3.0)

        # Sentence count: 0 → 0, 10+ → 1.0
        sentences = len(re.split(r"[.!?]+", prompt))
        s_score = min(1.0, sentences / 10.0)

        # Bullet/numbered list items
        bullets = len(_BULLET_RE.findall(prompt))
        b_score = min(0.5, bullets * 0.1)

        # Multi-step instruction pattern (binary 0 or 1)
        ms_score = 1.0 if _MULTI_STEP_RE.search(prompt) else 0.0

        # Weighted sum normalized to 0–2
        raw = q_score * 0.5 + s_score * 0.5 + b_score + ms_score * 0.5
        return float(min(2.0, raw))

    # ── Feature Group 3: Technical Domain Signals (0–2.0) ─────────────────────

    def _group3_technical_domain(self, prompt: str) -> float:
        """
        Per CLAUDE.md Section 10.2 — Feature Group 3.
        Code block: 1.0, math notation: 1.0, formal logic: 1.5, JSON/XML: 0.5.
        Sum capped at 2.0.
        """
        code_score = 1.0 if _CODE_BLOCK_RE.search(prompt) else 0.0
        math_score = 1.0 if _MATH_NOTATION_RE.search(prompt) else 0.0
        logic_score = 1.5 if _FORMAL_LOGIC_RE.search(prompt) else 0.0
        json_score = 0.5 if _JSON_XML_RE.search(prompt) else 0.0

        return float(min(2.0, code_score + math_score + logic_score + json_score))

    # ── Feature Group 4: Length Signal (0–1.5) ────────────────────────────────

    def _group4_length_signal(self, prompt: str) -> float:
        """
        Per CLAUDE.md Section 10.2 — Feature Group 4.
        Token count estimated as char_count / 4 (fast approximation).
        Buckets: <50 → 0, 50–200 → 0.5, 200–500 → 1.0, >500 → 1.5.
        """
        estimated_tokens = len(prompt) / 4.0
        if estimated_tokens < 50:
            return 0.0
        if estimated_tokens < 200:
            return 0.5
        if estimated_tokens < 500:
            return 1.0
        return 1.5

    # ── Feature Group 5: Output Format Complexity (0–1.5) ─────────────────────

    def _group5_output_format(self, prompt: str) -> float:
        """
        Per CLAUDE.md Section 10.2 — Feature Group 5.
        Structured output request: 0.5, multiple sections: 0.5, format constraints: 1.0.
        Sum capped at 1.5.
        """
        structured = 0.5 if _STRUCTURED_OUTPUT_RE.search(prompt) else 0.0
        sections = 0.5 if _SECTIONS_RE.search(prompt) else 0.0
        constraints = 1.0 if _FORMAT_CONSTRAINT_RE.search(prompt) else 0.0

        return float(min(1.5, structured + sections + constraints))


# ── Module-level singleton (used by the gateway pre-inference pipeline) ────────

_DEFAULT_SCORER: Optional[ComplexityScorer] = None


def get_scorer(
    thresholds: Optional[dict] = None,
    calibration_weights: Optional[dict] = None,
) -> ComplexityScorer:
    """
    Return the module-level ComplexityScorer, creating it on first call.

    Args:
        thresholds:           Budget class thresholds (defaults to CLAUDE.md values).
        calibration_weights:  Per-group weight multipliers from offline calibration.
                              Keys: "group1", "group2", "group3", "group4", "group5".
    """
    global _DEFAULT_SCORER
    if _DEFAULT_SCORER is None:
        weights = calibration_weights or {}
        _DEFAULT_SCORER = ComplexityScorer(
            thresholds=thresholds,
            group1_weight=weights.get("group1", 1.0),
            group2_weight=weights.get("group2", 1.0),
            group3_weight=weights.get("group3", 1.0),
            group4_weight=weights.get("group4", 1.0),
            group5_weight=weights.get("group5", 1.0),
        )
    return _DEFAULT_SCORER
