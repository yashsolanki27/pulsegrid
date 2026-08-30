FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context = repo root (Railway uses dockerfilePath = "crm-service/Dockerfile",
# so the build context is the repository root, not this subdirectory).
WORKDIR /workspace/crm-service

# Copy project files (paths relative to repo root)
COPY crm-service/pyproject.toml crm-service/uv.lock ./
COPY crm-service/app ./app

# Install production dependencies
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
