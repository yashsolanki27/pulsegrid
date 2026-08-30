FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context = repo root. No rootDirectory is set in railway.json, so Railway
# uses the repository root as the Docker build context for all services.
# The dockerfilePath ("crm-service/Dockerfile") only locates the Dockerfile — it
# does NOT set the build context to that subfolder.
# IMPORTANT: repo root has its own uv.lock (a 7-line stub for the root pyproject.toml).
# COPY paths must be fully qualified from repo root to get the correct service lockfile.
WORKDIR /workspace/crm-service

# Copy project files — fully-qualified from repo root to avoid picking up root uv.lock stub
COPY crm-service/pyproject.toml crm-service/uv.lock ./
COPY crm-service/app ./app

# Install production dependencies
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
