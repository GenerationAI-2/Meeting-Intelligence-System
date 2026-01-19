# Stage 1: Build React App
FROM node:20-slim AS builder
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
# Force Cache Bust: 2026-01-19 - Ensure VITE args are picked up
# Fix for Auth: Ensure VITE env vars are baked in during build? 
# No, Vite env vars are build-time. We must pass them as ARGs.
ARG VITE_SPA_CLIENT_ID
ARG VITE_API_CLIENT_ID
ARG VITE_AZURE_TENANT_ID
ARG VITE_API_URL
ENV VITE_SPA_CLIENT_ID=$VITE_SPA_CLIENT_ID \
    VITE_API_CLIENT_ID=$VITE_API_CLIENT_ID \
    VITE_AZURE_TENANT_ID=$VITE_AZURE_TENANT_ID \
    VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Python Runtime
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV ACCEPT_EULA=Y

# Install system dependencies (ODBC driver for SQL Server)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc-dev \
    libgssapi-krb5-2 && \
    curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    rm packages-microsoft-prod.deb && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy requirements
COPY server/requirements.txt .

# Install dependencies
RUN uv pip install --system -r requirements.txt

# Copy source code
ARG CACHEBUST=1
COPY server/src/ src/

# Copy built frontend from Stage 1
COPY --from=builder /app/dist/ static/

# Expose port
EXPOSE 8000

# Run the API server
ENV PYTHONUNBUFFERED=1

# Run the API server
CMD ["sh", "-c", "echo '🚀 STARTING DEPLOYMENT V11 (Fix Auth Path)' && python -m src.main --http"]
