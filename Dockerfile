FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy metadata first for cache efficiency.
COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --upgrade pip \
 && pip install -e .

ENV PATH="/app/.venv/bin:${PATH}" \
    PORT=8501

EXPOSE 8501 8080

CMD ["python", "-m", "copytrader.runtime.web_main"]
