FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
COPY nobla/ ./nobla/
RUN pip install --no-cache-dir .

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY nobla/ ./nobla/
RUN useradd -r nobla
USER nobla
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "nobla.main:app", "--host", "0.0.0.0", "--port", "8000"]
