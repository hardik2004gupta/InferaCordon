FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build context is repo root (docker-compose.yml context: .)
# Copies only the packages that gateway.main imports.
COPY gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ ./gateway/
COPY telemetry/ ./telemetry/
COPY policy_engine/ ./policy_engine/

RUN mkdir -p /tmp/prometheus-gateway /app/audit

EXPOSE 8000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
