# syntax=docker/dockerfile:1.8
# check=skip=InvalidDefaultArgInFrom

# The Task entry point supplies these versions from the project lockfile and host tools.
ARG MISE_VERSION
ARG DOCKER_CLI_VERSION
ARG PLAYWRIGHT_VERSION
ARG RUNNER_UID=1001

FROM ghcr.io/jdx/mise:${MISE_VERSION} AS mise
FROM docker:${DOCKER_CLI_VERSION}-cli AS docker-cli

FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble AS runner
ARG RUNNER_UID

USER root

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential ca-certificates curl file git jq \
    && rm -rf /var/lib/apt/lists/* \
    && install -d --owner=pwuser --group=pwuser \
        /home/pwuser/.cache/go-build \
        /home/pwuser/.cache/mise \
        /home/pwuser/.cache/npm \
        /home/pwuser/.cache/uv \
        /home/pwuser/.local/state/mise/trusted-configs \
        /home/pwuser/.local/share/mise \
        /home/pwuser/go/pkg/mod
RUN current_uid="$(id -u pwuser)" \
    && if [ "$current_uid" != "$RUNNER_UID" ]; then \
        if getent passwd "$RUNNER_UID" >/dev/null; then \
            echo "RUNNER_UID $RUNNER_UID already belongs to another image user." >&2; \
            exit 1; \
        fi; \
        usermod --uid "$RUNNER_UID" pwuser; \
    fi \
    && chown -R "$RUNNER_UID":pwuser /home/pwuser

COPY --from=mise /usr/local/bin/mise /usr/local/bin/mise
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli \
    /usr/local/libexec/docker/cli-plugins/docker-buildx \
    /usr/local/libexec/docker/cli-plugins/docker-buildx
COPY --from=docker-cli \
    /usr/local/libexec/docker/cli-plugins/docker-compose \
    /usr/local/libexec/docker/cli-plugins/docker-compose

ENV HOME=/home/pwuser \
    MISE_CACHE_DIR=/home/pwuser/.cache/mise \
    MISE_DATA_DIR=/home/pwuser/.local/share/mise \
    NPM_CONFIG_CACHE=/home/pwuser/.cache/npm \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/home/pwuser/.cache/uv \
    GOCACHE=/home/pwuser/.cache/go-build \
    GOMODCACHE=/home/pwuser/go/pkg/mod

USER pwuser

WORKDIR /workspace

CMD ["/bin/sh"]
