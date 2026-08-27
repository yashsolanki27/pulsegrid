FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy pulsegrid_common first (path dependency)
COPY pulsegrid_common /pulsegrid_common

# Copy the access-control project files
COPY access-control/pyproject.toml .
COPY access-control/app ./app
COPY access-control/templates ./templates

# Install dependencies (including pulsegrid-common via path ref)
RUN uv sync --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
