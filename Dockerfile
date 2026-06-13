FROM python:3.11-slim

# Install Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy python project files
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/

# Install python packages and sync workspace
RUN uv sync --frozen --no-dev

# Install all workspace packages as editable installs
RUN uv pip install \
    -e packages/adx_bridges \
    -e packages/agentdex_cli \
    -e packages/agentdex_observe \
    -e packages/agentdex_engine \
    -e packages/kaos \
    -e packages/agentdex_arena \
    -e packages/adx_showdown \
    -e packages/helios_client \
    -e packages/agentdex_plugin

# Install npm dependencies for sidecar
RUN cd packages/adx_showdown && npm ci --omit=dev

# BENE landing + docs (static, served at /bene/ by the gateway when present).
COPY site/ ./site/

# Expose port (PORT will be set at runtime by Koyeb)
EXPOSE 8000

# Start application
CMD sh -c "HOST=0.0.0.0 uv run --no-dev --frozen python -m agentdex_arena"
