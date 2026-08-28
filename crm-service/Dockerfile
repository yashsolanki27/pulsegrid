FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Layout: /workspace/
#   pulsegrid_common/   ← shared lib (not a dep of crm-service, but kept for
#                         structural consistency with access-control pattern)
#   crm-service/        ← this service (WORKDIR)
#
# Build context = repo root (same as access-control).
# crm-service/pyproject.toml has no pulsegrid-common path dependency,
# so no sed patch is required.
WORKDIR /workspace/crm-service

# Copy crm-service project files
COPY crm-service/pyproject.toml crm-service/uv.lock ./
COPY crm-service/app ./app

# Install production dependencies
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
