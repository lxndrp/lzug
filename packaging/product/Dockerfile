# syntax=docker/dockerfile:1

FROM python:3.14.6-slim-bookworm AS backend-build

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
WORKDIR /src
COPY LICENSE pyproject.toml uv.lock ./
COPY backend/src ./backend/src
RUN uv sync --locked --extra dev
RUN uv build --wheel --out-dir /dist
RUN mkdir -p /transport \
    && uv run --locked --extra dev python -m backend.fastapi_assembly --profile transport /transport/openapi.json

FROM python:3.14.6-slim-bookworm AS build-metadata

ARG BUILD_IDENTITY
ARG RELEASE_TAG=""
ARG VCS_REF
ENV PYTHONPATH="/src/backend/src"
WORKDIR /src
COPY backend/src ./backend/src
RUN set -eu; \
    test -n "$BUILD_IDENTITY"; \
    test -n "$VCS_REF"; \
    set -- --revision "$VCS_REF"; \
    if [ -n "$RELEASE_TAG" ]; then \
      set -- "$@" --tag "$RELEASE_TAG"; \
      case "$RELEASE_TAG" in snapshot/*-SNAPSHOT.*) set -- "$@" --allow-demo-snapshot ;; esac; \
    fi; \
    python -m backend.version "$@" --output /build-metadata.json >/dev/null; \
    test "$(python -m backend.version "$@" --field identity)" = "$BUILD_IDENTITY"

FROM --platform=$BUILDPLATFORM golang:1.26.8-bookworm AS operator-cli-build

ARG BUILD_IDENTITY
ARG RELEASE_TAG=""
ARG TARGETOS
ARG TARGETARCH
ARG VCS_REF
WORKDIR /src/operator-cli
COPY operator-cli/go.mod operator-cli/go.sum ./
RUN go mod download
COPY operator-cli ./
RUN set -eu; \
    test -n "$BUILD_IDENTITY"; \
    test -n "$VCS_REF"; \
    CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
      go build -trimpath \
      -ldflags="-s -w -X main.applicationVersion=$BUILD_IDENTITY -X main.applicationRevision=$VCS_REF -X main.applicationTag=$RELEASE_TAG" \
      -o /dist/lzug-admin ./cmd/lzug-admin

FROM node:26.5.0-bookworm-slim AS frontend-build

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/angular.json frontend/tsconfig.app.json frontend/tsconfig.json frontend/openapi-ts.config.mjs ./
COPY frontend/public/notification-sw.js ./public/notification-sw.js
RUN mkdir -p public/brand src/brand
COPY brand/tokens.css ./src/brand/tokens.css
COPY brand/derived/favicon.ico ./public/favicon.ico
COPY brand/derived/favicon.svg brand/derived/logo-mark-dark.svg ./public/brand/
COPY --from=build-metadata /build-metadata.json ./public/build-metadata.json
COPY --from=backend-build /transport/openapi.json ./openapi.json
COPY frontend/src ./src
COPY fixtures/synthetic-fixtures.json /src/fixtures/synthetic-fixtures.json
RUN LZUG_OPENAPI_INPUT=openapi.json LZUG_TRANSPORT_OUTPUT=src/app/api/generated \
      ./node_modules/.bin/openapi-ts --file openapi-ts.config.mjs --no-log-file --silent \
    && node node_modules/@angular/cli/bin/ng.js build --configuration production

FROM python:3.14.6-slim-bookworm AS python-dependencies

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY --from=backend-build /dist/*.whl /dist/
RUN uv sync --locked --no-dev --no-install-project --no-editable --compile-bytecode --no-cache
RUN mkdir -p /src/backend/src \
    && uv pip install --python /src/.venv/bin/python --target /src/backend/src \
       --no-deps /dist/*.whl

FROM python:3.14.6-slim-bookworm AS runtime

ARG BUILD_IDENTITY
ARG VCS_REF
LABEL org.opencontainers.image.title="lzug" \
      org.opencontainers.image.description="lzug Angular frontend and Python REST API" \
      org.opencontainers.image.source="https://github.com/lxndrp/lzug" \
      org.opencontainers.image.version="$BUILD_IDENTITY" \
      org.opencontainers.image.revision="$VCS_REF"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/backend/src" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1" \
    LZUG_DATA_DIR="/data" \
    LZUG_STATIC_DIR="/app/frontend"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --only-upgrade -y libpcre2-8-0 \
    && dpkg --compare-versions "$(dpkg-query --showformat='${Version}' --show libpcre2-8-0)" ge "10.42-1+deb12u1" \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 lzug \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent \
       --shell /usr/sbin/nologin lzug \
    && mkdir -p /app/backend/src /app/backend/db/migrations /app/frontend /data/documents /data/backups /run/lzug-admin \
    && chown -R 10001:10001 /app /data

COPY --from=python-dependencies --chown=10001:10001 /src/.venv /opt/venv
COPY --from=python-dependencies --chown=10001:10001 /src/backend/src ./backend/src
COPY --from=build-metadata --chown=10001:10001 /build-metadata.json ./backend/src/build-metadata.json
COPY --chown=10001:10001 backend/db ./backend/db
COPY --from=frontend-build --chown=10001:10001 /src/frontend/dist/frontend/browser ./frontend
COPY --from=operator-cli-build --chown=10001:10001 /dist/lzug-admin /usr/local/bin/lzug-admin

USER 10001:10001
EXPOSE 8000
VOLUME ["/data"]
STOPSIGNAL SIGTERM
# Process liveness only; deployment acceptance separately checks /api/ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-m", "backend.healthcheck"]

ENTRYPOINT ["python", "-m", "backend.server"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--init", "--admin-socket-dir", "/run/lzug-admin", "--admin-socket-gid", "10001"]
