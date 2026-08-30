FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context = repo root (Railway uses dockerfilePath = "erp-service/Dockerfile",
# so the build context is the repository root, not this subdirectory).
WORKDIR /workspace/erp-service

# Copy project files (paths relative to repo root)
COPY erp-service/pyproject.toml erp-service/uv.lock ./
COPY erp-service/app ./app

# Install production dependencies
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
