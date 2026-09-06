#!/usr/bin/env sh

# Shared orchestration for the packaged container contracts. Callers keep the
# contract-specific assertions while using one engine, lifecycle, readiness,
# runtime-user, and build-metadata implementation.

lzug_select_container_engine() {
    engine=${CONTAINER_ENGINE:-}
    if [ -z "$engine" ]; then
        if command -v docker >/dev/null 2>&1; then
            engine=docker
        elif command -v podman >/dev/null 2>&1; then
            engine=podman
        else
            echo "No Docker or Podman executable found." >&2
            exit 77
        fi
    fi
    case "$engine" in
        docker|podman) ;;
        *)
            echo "CONTAINER_ENGINE must be docker or podman." >&2
            exit 64
            ;;
    esac
    if ! command -v "$engine" >/dev/null 2>&1; then
        echo "${engine} executable is unavailable." >&2
        exit 77
    fi
}

lzug_require_container_engine() {
    lzug_select_container_engine
    if ! "$engine" info >/dev/null 2>&1; then
        echo "${engine} is installed but its engine is unavailable." >&2
        exit 77
    fi
}

lzug_start_contract_container() {
    container=$1
    volume=$2
    image=$3
    shift 3

    "$engine" volume create "$volume" >/dev/null
    "$engine" run --detach --name "$container" \
        --read-only --tmpfs /tmp \
        "$@" \
        --mount "type=volume,source=$volume,target=/data" \
        "$image" --host 0.0.0.0 --port 8000 --init >/dev/null
}

lzug_cleanup_contract_container() {
    container=$1
    volume=$2
    "$engine" rm --force "$container" >/dev/null 2>&1 || true
    "$engine" volume rm "$volume" >/dev/null 2>&1 || true
}

lzug_wait_for_http_health() {
    url=$1
    attempts=${2:-30}
    attempt=0
    while [ "$attempt" -lt "$attempts" ]; do
        if lzug_http_health_is_ready "$url"; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

lzug_http_health_is_ready() {
    curl --silent --show-error --fail "$1/api/health" >/dev/null 2>&1
}

lzug_wait_for_container_health() {
    container=$1
    attempts=${2:-30}
    attempt=0
    while [ "$attempt" -lt "$attempts" ]; do
        if "$engine" exec "$container" python -m backend.healthcheck >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

lzug_assert_runtime_user() {
    container=$1
    test "$("$engine" exec "$container" id -u)" = "10001"
}

lzug_copy_build_metadata() {
    container=$1
    destination=$2
    "$engine" exec "$container" cat /app/backend/src/build-metadata.json > "$destination"
}
