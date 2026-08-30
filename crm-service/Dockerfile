FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context = crm-service/ (Railway Root Directory set to crm-service in dashboard).
# crm-service has no pulsegrid_common path dependency, so repo-root context is not needed.
WORKDIR /workspace/crm-service

# Copy project files (paths relative to crm-service/ context)
COPY pyproject.toml uv.lock ./
COPY app ./app

# Install production dependencies
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
