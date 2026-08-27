FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Layout: /workspace/
#   pulsegrid_common/        ← shared lib (one level above WORKDIR)
#   webhook-receiver/        ← this service (WORKDIR)
#
# pyproject.toml uses path = "../../pulsegrid_common" (relative to
# webhook-receiver/ in the repo tree). Inside Docker we keep one less nesting
# level, so we patch the path to "../pulsegrid_common" before uv sync.
WORKDIR /workspace/webhook-receiver

# Place pulsegrid_common one level above (../pulsegrid_common from WORKDIR)
COPY pulsegrid_common /workspace/pulsegrid_common

# Copy the webhook-receiver project files
COPY observability-stack/webhook-receiver/pyproject.toml .
COPY observability-stack/webhook-receiver/app ./app

# Patch the path dep so it resolves within the Docker filesystem hierarchy
RUN sed -i 's|path = "../../pulsegrid_common"|path = "../pulsegrid_common"|' pyproject.toml

# Install dependencies (including pulsegrid-common via patched path ref)
RUN uv sync --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9094"]
