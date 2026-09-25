# syntax=docker/dockerfile:1

FROM scratch AS powershell-amd64
ADD --checksum=sha256:5c74e0bbafd8be59e72267f05700fd6615344d9cf4d30460d9b6d12cd4a88a8c https://github.com/PowerShell/PowerShell/releases/download/v7.5.3/powershell-7.5.3-linux-x64.tar.gz /powershell.tar.gz

FROM scratch AS powershell-arm64
ADD --checksum=sha256:4a6b656dd0e751e82c5df9b9a4245bd1ec7d21de5334afbbd802dfd009595599 https://github.com/PowerShell/PowerShell/releases/download/v7.5.3/powershell-7.5.3-linux-arm64.tar.gz /powershell.tar.gz

FROM powershell-${TARGETARCH} AS powershell

FROM python:3.14.6-slim-bookworm AS backend-build

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
WORKDIR /src
COPY LICENSE pyproject.toml ./
COPY backend/src ./backend/src
RUN uv build --wheel --out-dir /dist

FROM python:3.14.6-slim-bookworm AS build-metadata

ARG BUILD_IDENTITY
ARG RELEASE_TAG=""
ARG VCS_REF
ENV PYTHONPATH="/src/backend/src"
WORKDIR /src
COPY backend/src ./backend/src
COPY scripts/build_metadata.py ./scripts/
RUN set -eu; \
    test -n "$BUILD_IDENTITY"; \
    test -n "$VCS_REF"; \
    if [ -n "$RELEASE_TAG" ]; then \
      BUILD_REVISION="$VCS_REF" BUILD_RELEASE_TAG="$RELEASE_TAG" python -c \
        'import os; from pathlib import Path; from backend.build_metadata import BuildMetadata; tag=os.environ["BUILD_RELEASE_TAG"]; BuildMetadata.create(os.environ["BUILD_REVISION"], tag, allow_demo_snapshot=tag.startswith("snapshot/")).write(Path("/build-metadata.json"))'; \
    else \
      python scripts/build_metadata.py --revision "$VCS_REF" \
        --output /build-metadata.json >/dev/null; \
    fi; \
    test "$(python -c 'from pathlib import Path; from backend.build_metadata import BuildMetadata; print(BuildMetadata.read(Path("/build-metadata.json")).identity)')" = "$BUILD_IDENTITY"

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

COPY --from=powershell /powershell.tar.gz /tmp/powershell.tar.gz
RUN apt-get update \
    && apt-get install --no-install-recommends -y libicu72 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/microsoft/powershell/7 \
    && tar -xzf /tmp/powershell.tar.gz -C /opt/microsoft/powershell/7 \
    && chmod +x /opt/microsoft/powershell/7/pwsh \
    && rm /tmp/powershell.tar.gz
ENV PATH="/opt/microsoft/powershell/7:$PATH"

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/angular.json frontend/tsconfig.app.json frontend/tsconfig.json ./
COPY brand/tokens.css /src/brand/
COPY brand/derived/favicon.ico brand/derived/favicon.svg brand/derived/logo-mark-dark.svg /src/brand/derived/
COPY frontend/public ./public
COPY --from=build-metadata /build-metadata.json ./public/build-metadata.json
COPY frontend/src ./src
COPY fixtures/synthetic-fixtures.json /src/fixtures/synthetic-fixtures.json
COPY scripts/build-frontend.ps1 /src/scripts/build-frontend.ps1
RUN npm run build:ci

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
