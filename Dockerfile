FROM python:3.12-slim AS base

ARG GIT_SHA=dev
ARG BUILD_TIME=dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl ca-certificates build-essential gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy metadata first for cache efficiency.
COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --upgrade pip \
 && pip install -e .

ENV PORT=8501

EXPOSE 8501 8080

# Default to web; fly.toml overrides per-process.
CMD ["python", "-m", "copytrader.runtime.web_main"]
