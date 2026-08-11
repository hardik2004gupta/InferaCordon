FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy into the package subdirectory so `from guardrail_service.xxx import` resolves.
COPY . ./guardrail_service/

# Model directory is mounted as /app/models via docker-compose volume.
RUN mkdir -p /app/models

EXPOSE 8001

CMD ["uvicorn", "guardrail_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
