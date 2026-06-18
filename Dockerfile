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

# Cache-bust: bump BENE_SITE_REV to force the build cache to miss from here down
# so the COPY site/ layer is rebuilt from a fresh clone. The ai-builders/Koyeb
# deploy otherwise reuses a cached image on a same-branch re-deploy, leaving the
# served /bene/ stale even after the site/ content changed in git.
ARG BENE_SITE_REV=2026-06-18T06Z-converge-clean
RUN echo "bene /bene/ site rev: ${BENE_SITE_REV}"

# BENE landing + docs (static, served at /bene/ by the gateway when present).
COPY site/ ./site/

# agentdex landing (static, served at / for browsers by the gateway when present).
COPY web/ ./web/

# Strip dev-only tools that the bene-main → agentdex-cli site/ sync carries
# along but that have no business reaching production users via /bene/:
#   - build-docs.py: deterministic Markdown→HTML builder (build-time only)
#   - test-harness.html: headless-chromium render-verify harness (its own
#     comment self-declares "not linked from the site")
# Source-of-truth in bene-main/site/ is unchanged; this just keeps them out
# of the deploy image. (round-3 claim-audit: public-exposure-scan dim.)
# (2026-06-15: dropped check-i18n-parity.mjs — removed from bene-main
# in commit f58f9ae after the 2026-06-14 URL-based i18n migration made
# the key-tree-diff architecture obsolete.)
RUN rm -f site/build-docs.py site/test-harness.html

# Expose port (PORT will be set at runtime by Koyeb)
EXPOSE 8000

# Start application
CMD sh -c "HOST=0.0.0.0 uv run --no-dev --frozen python -m agentdex_arena"
