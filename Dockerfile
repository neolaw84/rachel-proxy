# Stage 1: Build multi-tenant cloud frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY vite.config.mjs ./
COPY frontend/ ./frontend/
RUN npm run build:cloud

# Stage 2: Production Python container for GCP Cloud Run
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    RACHEL_SANDBOX_ENGINE=v8

WORKDIR /app

# Install system dependencies (build-essential for C extensions if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition
COPY pyproject.toml configs.yaml README.md ./
COPY src/ ./src/

# Copy compiled cloud frontend static assets directly into Python package static directory
COPY --from=frontend-builder /app/frontend/dist/cloud/ ./src/rachel/static/

# Install python package with cloud optional dependencies
RUN pip install --no-cache-dir .[cloud]

# Create non-root user (UID 1000) for security and cloud container compatibility
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "rachel.entrypoints.cloud:app", "--host", "0.0.0.0", "--port", "8000"]
