FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy into the package subdirectory so `from verifier_service.xxx import` resolves.
COPY . ./verifier_service/

EXPOSE 8002

CMD ["uvicorn", "verifier_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
