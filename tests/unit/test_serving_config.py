"""
Unit tests for VLLMServingConfig (CLAUDE.md Section 3 / serving_config.py).

Tests:
  - Default config builds without errors
  - Validation rejects invalid quantization
  - Validation rejects multi-GPU (tensor_parallel > 1)
  - GPU memory utilization must be in [0.1, 0.98]
  - Environment variable overrides respected
  - Startup command includes required flags
  - Startup command enforces single port (8080)
  - format_startup_command returns non-empty string
"""
import os
import pytest
from unittest.mock import patch

from vllm_adapter.serving_config import (
    VLLMServingConfig,
    build_serving_config,
    generate_startup_command,
    format_startup_command,
)


# ── 1. Default config validity ────────────────────────────────────────────────

class TestDefaultConfig:

    def test_default_config_is_valid(self):
        cfg = VLLMServingConfig()
        errors = cfg.validate()
        assert errors == [], f"Default config has errors: {errors}"

    def test_default_port_is_8080(self):
        cfg = VLLMServingConfig()
        assert cfg.port == 8080

    def test_default_deepseek_model_id(self):
        cfg = VLLMServingConfig()
        assert "DeepSeek-R1" in cfg.deepseek_model_id

    def test_default_qwen_model_id(self):
        cfg = VLLMServingConfig()
        assert "Qwen" in cfg.qwen_model_id

    def test_default_tensor_parallel_is_one(self):
        cfg = VLLMServingConfig()
        assert cfg.tensor_parallel_size == 1

    def test_default_quantization_is_awq_or_gptq(self):
        cfg = VLLMServingConfig()
        assert cfg.deepseek_quantization in ("awq", "gptq", None)

    def test_default_gpu_memory_utilization_range(self):
        cfg = VLLMServingConfig()
        assert 0.1 <= cfg.gpu_memory_utilization <= 0.98


# ── 2. Validation errors ──────────────────────────────────────────────────────

class TestValidation:

    def test_invalid_quantization_rejected(self):
        cfg = VLLMServingConfig(deepseek_quantization="int8")
        errors = cfg.validate()
        assert any("quantization" in e for e in errors)

    def test_tensor_parallel_greater_than_one_rejected(self):
        cfg = VLLMServingConfig(tensor_parallel_size=2)
        errors = cfg.validate()
        assert any("tensor_parallel" in e or "single-GPU" in e for e in errors)

    def test_gpu_memory_too_high_rejected(self):
        cfg = VLLMServingConfig(gpu_memory_utilization=0.99)
        errors = cfg.validate()
        assert any("gpu_memory_utilization" in e for e in errors)

    def test_gpu_memory_too_low_rejected(self):
        cfg = VLLMServingConfig(gpu_memory_utilization=0.05)
        errors = cfg.validate()
        assert any("gpu_memory_utilization" in e for e in errors)

    def test_valid_gptq_quantization(self):
        cfg = VLLMServingConfig(deepseek_quantization="gptq")
        errors = cfg.validate()
        assert errors == []

    def test_none_quantization_valid(self):
        cfg = VLLMServingConfig(deepseek_quantization=None)
        errors = cfg.validate()
        assert errors == []


# ── 3. Environment variable overrides ─────────────────────────────────────────

class TestEnvOverrides:

    def test_port_override(self, monkeypatch):
        monkeypatch.setenv("VLLM_PORT", "9090")
        cfg = build_serving_config()
        assert cfg.port == 9090

    def test_gpu_memory_override(self, monkeypatch):
        monkeypatch.setenv("VLLM_GPU_MEMORY_UTIL", "0.85")
        cfg = build_serving_config()
        assert abs(cfg.gpu_memory_utilization - 0.85) < 1e-9

    def test_max_model_len_override(self, monkeypatch):
        monkeypatch.setenv("VLLM_MAX_MODEL_LEN", "4096")
        cfg = build_serving_config()
        assert cfg.max_model_len == 4096

    def test_invalid_env_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("VLLM_TENSOR_PARALLEL", "4")
        with pytest.raises(ValueError, match="tensor_parallel"):
            build_serving_config()

    def test_chunked_prefill_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("VLLM_CHUNKED_PREFILL", "false")
        cfg = build_serving_config()
        assert cfg.enable_chunked_prefill is False


# ── 4. Startup command generation ────────────────────────────────────────────

class TestStartupCommand:

    def test_command_is_list_of_strings(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        assert isinstance(cmd, list)
        assert all(isinstance(arg, str) for arg in cmd)

    def test_command_starts_with_python(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        assert cmd[0] == "python"

    def test_command_includes_model(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        assert "--model" in cmd

    def test_command_includes_correct_port(self):
        cfg = VLLMServingConfig(port=8080)
        cmd = generate_startup_command(cfg)
        assert "--port" in cmd
        port_idx = cmd.index("--port")
        assert cmd[port_idx + 1] == "8080"

    def test_command_includes_host(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        assert "--host" in cmd

    def test_command_includes_served_model_name(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        assert "--served-model-name" in cmd

    def test_command_includes_tensor_parallel(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        assert "--tensor-parallel-size" in cmd
        tp_idx = cmd.index("--tensor-parallel-size")
        assert cmd[tp_idx + 1] == "1"

    def test_command_includes_quantization_when_set(self):
        cfg = VLLMServingConfig(deepseek_quantization="awq")
        cmd = generate_startup_command(cfg)
        assert "--quantization" in cmd

    def test_command_omits_quantization_when_none(self):
        cfg = VLLMServingConfig(deepseek_quantization=None)
        cmd = generate_startup_command(cfg)
        assert "--quantization" not in cmd

    def test_single_port_no_duplicate_model_args(self):
        cfg = VLLMServingConfig()
        cmd = generate_startup_command(cfg)
        # Ensure only one --port (no second vLLM container implied)
        assert cmd.count("--port") == 1

    def test_format_startup_command_returns_string(self):
        cfg = VLLMServingConfig()
        cmd_str = format_startup_command(cfg)
        assert isinstance(cmd_str, str)
        assert len(cmd_str) > 0

    def test_format_includes_model_path(self):
        cfg = VLLMServingConfig()
        cmd_str = format_startup_command(cfg)
        assert "DeepSeek" in cmd_str or "deepseek" in cmd_str.lower()
