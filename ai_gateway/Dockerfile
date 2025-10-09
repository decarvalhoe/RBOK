# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ai_gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY ai_gateway/ ./

ARG AI_GATEWAY_PORT=8100
ARG AI_GATEWAY_BACKEND_BASE_URL
ARG AI_GATEWAY_OPENAI_API_KEY
ARG AI_GATEWAY_ALLOWED_ORIGINS
ENV AI_GATEWAY_PORT=${AI_GATEWAY_PORT} \
    AI_GATEWAY_BACKEND_BASE_URL=${AI_GATEWAY_BACKEND_BASE_URL} \
    AI_GATEWAY_OPENAI_API_KEY=${AI_GATEWAY_OPENAI_API_KEY} \
    AI_GATEWAY_ALLOWED_ORIGINS=${AI_GATEWAY_ALLOWED_ORIGINS}

EXPOSE ${AI_GATEWAY_PORT}

CMD ["sh", "-c", "uvicorn ai_gateway.main:app --host 0.0.0.0 --port ${AI_GATEWAY_PORT:-8100}"]
