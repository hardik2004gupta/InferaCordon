FROM vllm/vllm-openai:v0.4.2

WORKDIR /app

COPY constants.py serving_config.py logit_processor.py circuit_breakers.py ./

# Model weights downloaded at runtime from HuggingFace (cached via volume mount)
# Week 1: validate that both DeepSeek-R1-7B-Q4 and Qwen2.5-3B-Instruct fit
# on a single A100 80GB GPU with AWQ/GPTQ 4-bit quantization.
#
# Startup command constructed by serving_config.py::generate_startup_command()
# Override with VLLM_CMD env var for custom startup during development.

EXPOSE 8080

CMD ["python", "-m", "vllm.entrypoints.openai.api_server", \
     "--host", "0.0.0.0", \
     "--port", "8080"]
