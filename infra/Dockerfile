# Build context: repository root (docker compose -f infra/compose.example.yml build).
# One image: the backend serves the built frontend (FRONTEND_DIST_DIR) with its own security
# headers. TLS, proxy and network are the server's job (docs/DEPLOY.md).

# ---- Stage 1: build the frontend (nothing from this stage but dist/ reaches the runtime) ----
FROM node:24.21.0-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: install the backend into a prefix (pip and the build backend stay here) ----
FROM python:3.15.1-slim AS backend-build
# PIP_CONSTRAINT also reaches pip's isolated build environment, so setuptools is pinned too.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_NO_CACHE_DIR=1 \
    PIP_CONSTRAINT=/constraints.txt
COPY infra/constraints.txt /constraints.txt
COPY backend/pyproject.toml /src/pyproject.toml
COPY backend/app /src/app
RUN pip install --prefix=/install /src

# ---- Stage 3: runtime ----
FROM python:3.15.1-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app /data \
    && chown app:app /data

WORKDIR /app

# The installed package (single copy, in site-packages) and its pinned dependencies come from the
# build stage. pip, setuptools and wheel are removed: nothing in the container installs packages.
COPY --from=backend-build /install /usr/local
RUN python -m pip uninstall -y pip setuptools wheel
COPY backend/migrations ./migrations

# Code is owned by root and read-only for the app user; only /data is writable (plus tmpfs /tmp).
COPY --from=frontend-build /build/dist /app/static
# sed: tolerate a checkout with CRLF line endings (a CRLF shebang makes the kernel look for "sh\r").
COPY infra/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod 0555 /app/entrypoint.sh

ENV MIGRATIONS_DIR=/app/migrations \
    FRONTEND_DIST_DIR=/app/static \
    DATABASE_URL=sqlite:////data/app.db \
    DATA_DIR=/data \
    LIBRARY_PATH=/library

# Release version, passed by the release workflow (--build-arg APP_VERSION=1.2.3). Declared late so
# a different value only invalidates the layers below. The app and the update flow can read it.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
# Static OCI labels; the release workflow adds revision and created. No licence label on purpose.
LABEL org.opencontainers.image.title="biblioteca-pwa" \
      org.opencontainers.image.description="PWA to read manga (CBZ), books (EPUB) and PDF from a server library" \
      org.opencontainers.image.source="https://github.com/Andre-Bueno/biblioteca-pwa" \
      org.opencontainers.image.version=$APP_VERSION

# SQLite database (WAL) lives here; mount a named volume. The library is mounted read-only
# at /library by the compose file.
VOLUME ["/data"]

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status == 200 else 1)"]

# No secrets here: SECRET_KEY and others are provided at runtime via environment.
# The entrypoint refuses to start without SECRET_KEY and FORWARDED_ALLOW_IPS (the IP/CIDR of the
# reverse proxy that connects to this container; no default on purpose, ADR 0011), applies the
# migrations and execs uvicorn with --no-server-header, --proxy-headers and the limits
# UVICORN_LIMIT_CONCURRENCY, UVICORN_TIMEOUT_KEEP_ALIVE, UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN.
ENTRYPOINT ["/app/entrypoint.sh"]
