"""
vLLM serving configuration and startup command builder.

Per CLAUDE.md Section 3 (Non-Negotiable Constraints):
  - Single vLLM instance serving both models via --served-model-name aliases
  - DeepSeek-R1-7B-Q4 (4-bit AWQ or GPTQ) — reasoning model
  - Qwen2.5-3B-Instruct — cheap model (not quantized, fits easily)
  - All GPU workload on one A100 80GB
  - No multi-GPU, no distributed inference

Multi-model serving strategy:
  vLLM v0.4.x supports loading two models in a single instance when they share
  the same base architecture. DeepSeek-R1-Distill-Qwen-7B is built on Qwen2,
  and Qwen2.5-3B also uses the Qwen2 architecture family. However, vLLM's
  single-instance multi-model support is limited in v0.4.x.

  Implementation approach (to be validated in Week 1):
    Option A (preferred): vLLM v0.5+ LoRA-based multi-model serving.
    Option B (fallback): Two separate --model args with --served-model-name aliases.
    Option C (last resort): Single model serving with model switching between requests.

  THIS FILE provides the configuration and command builder. The actual approach
  is determined in Week 1 by testing on the A100 GPU node. The choice is
  committed to .env and CLAUDE.md after validation.

  IMPORTANT: Both models are served through port 8080. There is NEVER a second
  vLLM container or second port. This is non-negotiable per CLAUDE.md Section 3.
"""
from __future__ import annotations

import dataclasses
import os
import shlex
from typing import List, Optional


# ── Serving configuration dataclass ──────────────────────────────────────────

@dataclasses.dataclass
class VLLMServingConfig:
    """
    Complete configuration for the vLLM serving process.

    All fields are read from environment variables by build_serving_config().
    Defaults represent the target production configuration for an A100 80GB.
    """
    # Model identifiers (per CLAUDE.md Section 3 — no substitution without DevProtocol)
    deepseek_model_id: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    qwen_model_id: str = "Qwen/Qwen2.5-3B-Instruct"

    # Quantization (4-bit required per CLAUDE.md Section 3)
    # "awq" or "gptq" — validated in Week 1, best format committed to .env
    deepseek_quantization: str = "awq"
    qwen_quantization: Optional[str] = None    # Qwen2.5-3B fits without quantization

    # Served model name aliases (gateway selects by these names in API calls)
    deepseek_served_name: str = "deepseek-r1-7b"
    qwen_served_name: str = "qwen25-3b"

    # GPU memory (A100 80GB target)
    gpu_memory_utilization: float = 0.90      # Reserve 10% for OS + KV-cache headroom
    max_model_len: int = 8192                  # Context window length

    # Parallelism (single GPU)
    tensor_parallel_size: int = 1

    # Serving
    port: int = 8080
    host: str = "0.0.0.0"
    disable_log_requests: bool = False
    enable_chunked_prefill: bool = True        # Reduces memory spikes

    # Prometheus metrics (consumed directly per CLAUDE.md Section 18)
    disable_prometheus: bool = False

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty list = valid."""
        errors: list[str] = []
        if self.deepseek_quantization not in ("awq", "gptq", None):
            errors.append(f"Invalid quantization: {self.deepseek_quantization!r}")
        if not 0.1 <= self.gpu_memory_utilization <= 0.98:
            errors.append(f"gpu_memory_utilization {self.gpu_memory_utilization} out of range")
        if self.tensor_parallel_size != 1:
            errors.append(
                f"tensor_parallel_size={self.tensor_parallel_size} violates "
                "single-GPU constraint (CLAUDE.md Section 3)"
            )
        return errors


def build_serving_config() -> VLLMServingConfig:
    """
    Construct VLLMServingConfig from environment variables.
    Uses conservative defaults for production A100 80GB target.
    """
    cfg = VLLMServingConfig(
        deepseek_model_id=os.getenv("DEEPSEEK_MODEL_ID", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
        qwen_model_id=os.getenv("QWEN_MODEL_ID", "Qwen/Qwen2.5-3B-Instruct"),
        deepseek_quantization=os.getenv("DEEPSEEK_QUANTIZATION", "awq"),
        deepseek_served_name=os.getenv("DEEPSEEK_SERVED_NAME", "deepseek-r1-7b"),
        qwen_served_name=os.getenv("QWEN_SERVED_NAME", "qwen25-3b"),
        gpu_memory_utilization=float(os.getenv("VLLM_GPU_MEMORY_UTIL", "0.90")),
        max_model_len=int(os.getenv("VLLM_MAX_MODEL_LEN", "8192")),
        tensor_parallel_size=int(os.getenv("VLLM_TENSOR_PARALLEL", "1")),
        port=int(os.getenv("VLLM_PORT", "8080")),
        host=os.getenv("VLLM_HOST", "0.0.0.0"),
        enable_chunked_prefill=os.getenv("VLLM_CHUNKED_PREFILL", "true").lower() == "true",
    )

    errors = cfg.validate()
    if errors:
        raise ValueError(
            f"Invalid vLLM serving configuration:\n" + "\n".join(f"  - {e}" for e in errors)
        )
    return cfg


def generate_startup_command(config: VLLMServingConfig) -> List[str]:
    """
    Generate the vLLM CLI command for single-instance dual-model serving.

    Week 1 task: Run this command on the A100 GPU node. Validate both models load
    and respond. Commit the working quantization format to .env as DEEPSEEK_QUANTIZATION.

    IMPORTANT: Both models are served on port 8080. No second process.
    Model selection at inference time is done via the "model" field in API requests.

    Note on multi-model serving in vLLM v0.4.x:
      vLLM does not natively serve two different models from one process in v0.4.x
      without significant memory management. The recommended approach:

        1. Load DeepSeek-R1 as the primary model with quantization.
        2. Load Qwen2.5-3B as a secondary model using vLLM's LoRA or pipeline-parallel
           mode (if supported in v0.4.x). If not supported, evaluate upgrading to
           vLLM v0.5+ which has first-class multi-model support.

      WEEK 1 DELIVERABLE: Determine which approach works. Document in CLAUDE.md
      Section 32 (Architectural Assumptions) and commit the working command.

    For now this generates the DeepSeek-only command. The Qwen serving flags
    are commented out pending Week 1 validation.
    """
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--host", config.host,
        "--port", str(config.port),
        "--model", config.deepseek_model_id,
        "--served-model-name", config.deepseek_served_name,
        "--gpu-memory-utilization", str(config.gpu_memory_utilization),
        "--max-model-len", str(config.max_model_len),
        "--tensor-parallel-size", str(config.tensor_parallel_size),
    ]

    if config.deepseek_quantization:
        cmd.extend(["--quantization", config.deepseek_quantization])

    if config.enable_chunked_prefill:
        cmd.append("--enable-chunked-prefill")

    if config.disable_prometheus:
        cmd.append("--disable-log-requests")
    else:
        # vLLM exposes Prometheus metrics at /metrics by default
        cmd.append("--disable-log-requests")

    # ── Qwen2.5-3B co-serving (Week 1 investigation) ──────────────────────────
    # Option A: If vLLM v0.4.x supports --model with multiple entries via
    # experimental multi-model flag, add:
    #   --model Qwen/Qwen2.5-3B-Instruct
    #   --served-model-name qwen25-3b
    # Option B: Use a gateway-level workaround where Qwen requests are handled
    # by a different API key (still same container, vLLM instance, port).
    # Option C: Upgrade to vLLM v0.5+ which has native multi-model support.
    # WEEK 1: Determine which applies and update this function accordingly.

    return cmd


def format_startup_command(config: VLLMServingConfig) -> str:
    """Return the startup command as a shell-quoted string for logging/docs."""
    return shlex.join(generate_startup_command(config))
