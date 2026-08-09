"""
vLLM adapter constants — model-specific token IDs and runtime configuration.

Per CLAUDE.md Section 9.5:
  The end_of_thinking_token_id MUST be discovered from the model tokenizer
  during Week 1 validation. The discovery function below performs this
  resolution at import time if the tokenizer is cached locally.

Discovery command (run on GPU node after model download):
  python -c "
  from transformers import AutoTokenizer
  tok = AutoTokenizer.from_pretrained('deepseek-ai/DeepSeek-R1-Distill-Qwen-7B')
  eot = tok.convert_tokens_to_ids('</think>')
  print(f'</think> token ID: {eot}')
  print(f'<think> token ID: {tok.convert_tokens_to_ids(\"<think>\")}')
  "

VALIDATION STATUS: BLOCKED — DeepSeek tokenizer not available in this environment.
                   Run discovery on GPU node and commit the discovered value.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from typing import Optional

# Module-level import so tests can patch "vllm_adapter.constants.AutoTokenizer"
try:
    from transformers import AutoTokenizer  # type: ignore
except ImportError:
    AutoTokenizer = None  # type: ignore

log = logging.getLogger(__name__)

# ── Sentinel value ─────────────────────────────────────────────────────────────
# -1 indicates "not yet discovered". The LogitProcessor refuses to instantiate
# when end_of_thinking_token_id == _UNDISCOVERED_SENTINEL.
_UNDISCOVERED_SENTINEL: int = -1

# ── Model HuggingFace repository IDs ──────────────────────────────────────────
# These are the exact model identifiers. Substituting any other model requires
# the Architecture Deviation Protocol (CLAUDE.md Section 28).
DEEPSEEK_HF_MODEL_ID: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
QWEN_HF_MODEL_ID: str = "Qwen/Qwen2.5-3B-Instruct"

# ── Model name aliases (match policy YAML `model` fields) ─────────────────────
DEEPSEEK_MODEL_NAME: str = "deepseek-r1-7b"
QWEN_MODEL_NAME: str = "qwen25-3b"

# ── Budget class reasoning-token caps (per CLAUDE.md Section 12) ───────────────
BUDGET_CLASS_REASONING_TOKENS: dict[str, int] = {
    "low": 0,
    "medium": 512,
    "high": 1024,
    "critical": 2048,
}

# ── vLLM serving endpoints ─────────────────────────────────────────────────────
VLLM_PORT: int = 8080
VLLM_HEALTH_ENDPOINT: str = "/health"
VLLM_COMPLETIONS_ENDPOINT: str = "/v1/chat/completions"
VLLM_METRICS_ENDPOINT: str = "/metrics"
VLLM_MODELS_ENDPOINT: str = "/v1/models"


# ── Token discovery ─────────────────────────────────────────────────────────────

@dataclasses.dataclass
class TokenDiscoveryResult:
    """Result of end-of-thinking token ID discovery."""
    model_id: str
    token_string: str
    token_id: int
    validated: bool          # True only when discovered from real tokenizer
    error: Optional[str]     # Reason for failure if not validated

    def assert_valid(self) -> None:
        """Raise ValueError if token was not successfully discovered."""
        if not self.validated or self.token_id == _UNDISCOVERED_SENTINEL:
            raise ValueError(
                f"End-of-thinking token ID for {self.model_id!r} has not been "
                f"discovered. Run the discovery command on a node that has the "
                f"model tokenizer cached. Error: {self.error}"
            )


def discover_eot_token_id(model_id: str, token_string: str = "</think>") -> TokenDiscoveryResult:
    """
    Attempt to discover the end-of-thinking delimiter token ID from the tokenizer.

    Per CLAUDE.md Section 9.5 — exact discovery procedure:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        token_id  = tokenizer.convert_tokens_to_ids(token_string)

    Returns a TokenDiscoveryResult with validated=False if the tokenizer
    is not available locally. Never blocks or downloads at runtime.

    Args:
        model_id:      HuggingFace model repository ID.
        token_string:  The token string to look up (default "</think>").

    Returns:
        TokenDiscoveryResult with token_id=-1 and validated=False on failure.
    """
    try:
        if AutoTokenizer is None:
            raise ImportError("transformers not installed")
        tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
        unk_id = getattr(tokenizer, "unk_token_id", None)

        token_id = tokenizer.convert_tokens_to_ids(token_string)

        # convert_tokens_to_ids returns unk_token_id when the token is not in vocab
        if token_id == unk_id or token_id is None:
            # Fallback: encode and check single-token result
            encoded = tokenizer.encode(token_string, add_special_tokens=False)
            if len(encoded) == 1:
                token_id = encoded[0]
                log.info(
                    "EOT token %r found via encode fallback: ID=%d (model=%s)",
                    token_string, token_id, model_id,
                )
            else:
                return TokenDiscoveryResult(
                    model_id=model_id,
                    token_string=token_string,
                    token_id=_UNDISCOVERED_SENTINEL,
                    validated=False,
                    error=(
                        f"Token {token_string!r} encodes to multiple token IDs "
                        f"{encoded} — incompatible with per-step delimiter detection."
                    ),
                )

        log.info(
            "EOT token discovered: %r → ID %d (model=%s)",
            token_string, token_id, model_id,
        )
        return TokenDiscoveryResult(
            model_id=model_id,
            token_string=token_string,
            token_id=token_id,
            validated=True,
            error=None,
        )

    except ImportError as exc:
        return TokenDiscoveryResult(
            model_id=model_id,
            token_string=token_string,
            token_id=_UNDISCOVERED_SENTINEL,
            validated=False,
            error=f"transformers not importable: {exc}",
        )
    except Exception as exc:
        return TokenDiscoveryResult(
            model_id=model_id,
            token_string=token_string,
            token_id=_UNDISCOVERED_SENTINEL,
            validated=False,
            error=str(exc),
        )


# ── Module-level discovery (non-blocking, best-effort) ─────────────────────────
# These are attempted once at import time using local tokenizer cache.
# If the model is not cached, they return validated=False and the raw serving
# infrastructure refuses to use _UNDISCOVERED_SENTINEL for real inference.

_DEEPSEEK_DISCOVERY: TokenDiscoveryResult = discover_eot_token_id(
    DEEPSEEK_HF_MODEL_ID, "</think>"
)

# The actual resolved token ID (or sentinel -1 if not yet discovered)
DEEPSEEK_R1_EOT_TOKEN_ID: int = _DEEPSEEK_DISCOVERY.token_id
DEEPSEEK_R1_EOT_VALIDATED: bool = _DEEPSEEK_DISCOVERY.validated

if not DEEPSEEK_R1_EOT_VALIDATED:
    log.warning(
        "DeepSeek EOT token ID not discovered: %s  "
        "BudgetLogitProcessor cannot be used until the tokenizer is available.",
        _DEEPSEEK_DISCOVERY.error,
    )

# Qwen2.5-3B does not use </think> (low-budget route, 0 reasoning tokens).
# Token ID is defined for completeness but never used by the LogitProcessor.
QWEN25_EOT_TOKEN_ID: int = _UNDISCOVERED_SENTINEL
QWEN25_EOT_VALIDATED: bool = False
