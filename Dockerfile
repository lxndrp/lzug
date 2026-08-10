# syntax=docker/dockerfile:1

FROM node:26.5.0-bookworm-slim AS frontend-build

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/angular.json frontend/tsconfig.app.json frontend/tsconfig.json ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN npm run build:ci

FROM python:3.14.6-slim-bookworm AS python-dependencies

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable --compile-bytecode --no-cache

FROM python:3.14.6-slim-bookworm AS runtime

ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="lzug" \
      org.opencontainers.image.description="lzug Angular frontend and Python REST API" \
      org.opencontainers.image.source="https://github.com/lxndrp/lzug" \
      org.opencontainers.image.revision="$VCS_REF"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1" \
    LZUG_DATA_DIR="/data" \
    LZUG_STATIC_DIR="/app/frontend"

WORKDIR /app

RUN groupadd --system --gid 10001 lzug \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent \
       --shell /usr/sbin/nologin lzug \
    && mkdir -p /app/backend /app/db/migrations /app/frontend /data/documents /data/backups \
    && chown -R 10001:10001 /app /data

COPY --from=python-dependencies --chown=10001:10001 /src/.venv /opt/venv
COPY --chown=10001:10001 \
    backend/__init__.py backend/admin.py backend/admin_service.py backend/app.py backend/auth.py backend/authorization.py \
    backend/candidate_days.py backend/contract.py backend/database.py \
    backend/document_storage.py backend/documents.py backend/hateoas.py \
    backend/healthcheck.py backend/holiday_provider.py backend/models.py \
    backend/openapi.py backend/planning.py backend/repositories.py backend/store.py \
    ./backend/
COPY --chown=10001:10001 db/schema.sql ./db/schema.sql
COPY --chown=10001:10001 db/migrations ./db/migrations
COPY --from=frontend-build --chown=10001:10001 /src/frontend/dist/frontend/browser ./frontend

USER 10001:10001
EXPOSE 8000
VOLUME ["/data"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-m", "backend.healthcheck"]

ENTRYPOINT ["python", "-m", "backend.app"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--init"]
