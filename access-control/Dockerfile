FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Layout: /workspace/
#   pulsegrid_common/   ← shared lib
#   access-control/     ← this service (WORKDIR)
#
# pyproject.toml on the host uses path = "../../pulsegrid_common" (relative to
# access-control/ inside the repo tree). Inside Docker we keep one less nesting
# level, so we patch the path to "../pulsegrid_common" before running uv sync.
WORKDIR /workspace/access-control

# Place pulsegrid_common one level above (../pulsegrid_common from our WORKDIR)
COPY pulsegrid_common /workspace/pulsegrid_common

# Copy the access-control project files
COPY access-control/pyproject.toml .
COPY access-control/app ./app
COPY access-control/templates ./templates

# Patch the path dep so it resolves within the Docker filesystem hierarchy
RUN sed -i 's|path = "../../pulsegrid_common"|path = "../pulsegrid_common"|' pyproject.toml

# Install dependencies (including pulsegrid-common via patched path ref)
RUN uv sync --no-dev

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
