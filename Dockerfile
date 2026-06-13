FROM python:3.11-slim

WORKDIR /app

# Install uv for fast, reliable workspace builds
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the project files
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/

# Install the workspace dependencies and packages
RUN uv sync --frozen --no-dev

# Expose port (PORT will be set at runtime by Koyeb)
EXPOSE 8000

# Start the application using PORT environment variable
CMD sh -c "HOST=0.0.0.0 uv run --frozen python -m agentdex_arena"
