FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    apt-transport-https \
    lsb-release \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Azure CLI
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Upgrade pip and install ruff
RUN python -m pip install --upgrade pip ruff

# Set working directory
WORKDIR /app

# Set environment variable for uv venv location
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Copy src directory which contains pyproject.toml and uv.lock
COPY src/ ./src/

# Change to src directory and install dependencies
WORKDIR /app/src
RUN uv sync --frozen

# Change back to app directory
WORKDIR /app

# Expose ports
EXPOSE 8000 8090 18888 18889

# Default command (run from src directory)
CMD ["uv", "run", "--directory", "src", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]