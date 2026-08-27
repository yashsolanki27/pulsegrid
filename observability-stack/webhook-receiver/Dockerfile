FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy pulsegrid_common first (path dependency)
COPY pulsegrid_common /pulsegrid_common

# Copy the webhook-receiver project files
COPY observability-stack/webhook-receiver/pyproject.toml .
COPY observability-stack/webhook-receiver/app ./app

# Install dependencies (including pulsegrid-common via path ref)
RUN uv sync --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9094"]
