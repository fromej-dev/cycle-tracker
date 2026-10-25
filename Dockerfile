# syntax=docker/dockerfile:1.4

# Stage 1: Frontend build (Node.js + Alpine)
FROM node:lts-alpine as frontend_builder
WORKDIR /app/frontend
# Copy package.json and lock file first to leverage Docker cache
COPY frontend/package*.json ./
RUN npm ci
# Copy the rest of the frontend code
COPY frontend/ .
RUN npm run build

# Stage 2: Backend build (Python env and compiled dependencies - MUSL based)
# Use the uv image based on Python 3.12 and ALPINE for musl compatibility
FROM ghcr.io/astral-sh/uv:python3.12-alpine as backend_build

# Set work directory for the backend build
WORKDIR /app/backend_build

# Install system dependencies needed specifically for Python packages during build (like psycopg2 build deps)
# Use apk add for Alpine packages
# libpq-dev and build-base are needed here during the uv sync build step to compile psycopg2 on Alpine
RUN apk add --no-cache libpq-dev build-base

# Copy pyproject.toml and requirements.lock from your backend directory
# IMPORTANT: Ensure you have run 'uv pip compile pyproject.toml -o requirements.lock' locally
COPY backend/pyproject.toml .
COPY backend/uv.lock .

# Use uv sync to install dependencies into the WORKDIR/.venv within this musl stage
# This forces compilation against musl
RUN uv sync --frozen --no-dev --no-install-project

# Copy backend application code source files into this stage
# This makes them available to be copied into the final runner stage
COPY backend/ /app/backend_build/app_source/

# Stage 3: Runner (Minimal Alpine image)
# This stage takes the artifacts from previous stages and puts them in a small Alpine image
FROM ghcr.io/astral-sh/uv:python3.12-alpine as runner

# Set the final application work directory
WORKDIR /app

# Install necessary runtime system dependencies in Alpine:
# libpq is needed at runtime to connect to PostgreSQL (Alpine package name for the client library)
# ca-certificates for SSL connections
# NO gcompat needed because the VENV will be MUSL-based, matching the base image
RUN apk add --no-cache libpq ca-certificates

# Copy the virtual environment from the backend_build stage
# This venv was built against musl, and runs directly on Alpine without gcompat
COPY --from=backend_build /app/backend_build/.venv /app/.venv

# Copy the entrypoint script and make it executable
COPY backend/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy *only* the backend application code source files from the backend_build stage
# We copy from the 'app_source' subdirectory we created in Stage 2
# IMPORTANT: Adjust this COPY command if you copied your backend source differently in Stage 2
COPY --from=backend_build /app/backend_build/app_source/app /app/app
COPY --from=backend_build /app/backend_build/app_source/migrations /app/migrations

# Set the PATH environment variable to include the virtual environment's bin directory
ENV PATH="/app/.venv/bin:$PATH"

# Production config by default: the app refuses to start without strong
# SECRET_KEY / JWT_SECRET_KEY. Override with FLASK_ENV=development for local hacking.
ENV FLASK_ENV=production

# Copy frontend build output from the frontend_builder stage
# This will be served by Flask from the static directory configured in your app
COPY --from=frontend_builder /app/frontend/dist /app/app/static

# Optional: Set a non-root user for added security (Alpine adduser usage)
# RUN adduser -u 1001 -D nonrootuser
# USER nonrootuser

# Persistent data (SQLite) lives under /app/instance; mount a volume here if you use SQLite.
RUN mkdir -p /app/instance

# gunicorn binds to 0.0.0.0:${PORT:-5000} (Railway and most PaaS inject PORT).
# See docker-entrypoint.sh for WEB_CONCURRENCY, GUNICORN_THREADS, GUNICORN_TIMEOUT.
EXPOSE 5000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# No CMD: the entrypoint starts gunicorn by default. Pass a command to override it.
