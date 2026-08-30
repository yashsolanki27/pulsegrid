FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context = erp-service/ (Railway Root Directory set to erp-service in dashboard).
# erp-service has no pulsegrid_common path dependency, so repo-root context is not needed.
WORKDIR /workspace/erp-service

# Copy project files (paths relative to erp-service/ context)
COPY pyproject.toml uv.lock ./
COPY app ./app

# Install production dependencies
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
