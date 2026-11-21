#!/bin/sh
# Container entrypoint: validate the required settings, apply database migrations, start uvicorn.
# No secrets here: everything comes from the environment (see .env.example and docs/DEPLOY.md).
set -eu

fail() {
    echo "entrypoint: ERROR: $1" >&2
    exit 1
}

# Required, no default on purpose (ADR 0011 for FORWARDED_ALLOW_IPS).
[ -n "${SECRET_KEY:-}" ] || fail "SECRET_KEY is not set (>= 32 chars; generate: python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
[ "${#SECRET_KEY}" -ge 32 ] || fail "SECRET_KEY is too short (minimum 32 characters)"
[ -n "${FORWARDED_ALLOW_IPS:-}" ] || fail "FORWARDED_ALLOW_IPS is not set: use the IP/CIDR of the reverse proxy that connects to this container ('*' only if the port is not reachable directly). See docs/DEPLOY.md"

# ALLOWED_ORIGINS is optional: the app serves the frontend itself, so empty means same-origin.
# An empty value would not parse as a list, so drop it.
if [ -z "${ALLOWED_ORIGINS:-}" ]; then
    unset ALLOWED_ORIGINS
fi

[ -d "${LIBRARY_PATH:-/library}" ] || echo "entrypoint: WARNING: library folder ${LIBRARY_PATH:-/library} is not mounted; scans will fail until it is" >&2

echo "entrypoint: applying database migrations"
python -m app.cli migrate

echo "entrypoint: starting uvicorn"
# --no-server-header: do not announce "Server: uvicorn". The app keeps in-memory state (rate limits,
# scan status), so there is a single worker and no --limit-max-requests recycling.
exec uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --no-server-header \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}" \
    --limit-concurrency "${UVICORN_LIMIT_CONCURRENCY:-100}" \
    --timeout-keep-alive "${UVICORN_TIMEOUT_KEEP_ALIVE:-5}" \
    --timeout-graceful-shutdown "${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-20}"
