# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────
# ProjectMultiAgentAI — single-image, multi-service container
#
# Build:
#   docker compose build
#
# Each service overrides CMD to select the component to run.
# ──────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc / buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy full project
COPY . .

# Default entrypoint — overridden per service in docker-compose.yml
ENTRYPOINT ["python", "-m"]
CMD ["Orchestrator", "--run-once"]
