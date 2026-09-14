#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
compose_file="$root_dir/compose.yaml"
image=${LZUG_IMAGE:-}
ready_timeout_seconds=${LZUG_COMPOSE_READY_TIMEOUT_SECONDS:-90}
ready_interval_seconds=${LZUG_COMPOSE_READY_INTERVAL_SECONDS:-1}

if [ -z "$image" ]; then
    echo "Set LZUG_IMAGE to an existing local or published immutable image." >&2
    exit 2
fi
case "$ready_timeout_seconds" in
    ''|*[!0-9]*|0)
        echo "LZUG_COMPOSE_READY_TIMEOUT_SECONDS must be a positive integer." >&2
        exit 2
        ;;
esac
case "$ready_interval_seconds" in
    ''|*[!0-9]*)
        echo "LZUG_COMPOSE_READY_INTERVAL_SECONDS must be a non-negative integer." >&2
        exit 2
        ;;
esac
lzug_require_docker

project="lzug-compose-smoke-$$"
volume="$project-data"
container_port=${LZUG_PORT:-8000}
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-compose-smoke.XXXXXX")
socket_directory="$temporary_directory/admin"
mkdir "$socket_directory"
compose() {
    LZUG_IMAGE="$image" LZUG_DATA_VOLUME="$volume" LZUG_HOST_PORT=0 \
        LZUG_ADMIN_SOCKET_DIR="$socket_directory" \
        LZUG_DATABASE_PATH=/data/lzug.sqlite LZUG_DATABASE_URL= \
        LZUG_DOCUMENTS_PATH=/data/documents LZUG_BACKUPS_PATH=/data/backups \
        docker compose -p "$project" -f "$compose_file" "$@"
}
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    # The host owns the parent and can remove an empty UID-10001 child.
    # Preserve unexpected files or a stale socket if shutdown failed.
    rmdir "$socket_directory" "$temporary_directory" || true
}
trap cleanup EXIT HUP INT TERM

# Prepare only this smoke's disposable bind mount, as a Linux operator would.
# The service itself retains user 10001:10001 and all dropped capabilities.
compose run --rm --no-deps --user 0:0 --cap-add CHOWN --cap-add FOWNER \
    --entrypoint sh lzug -c \
    'chown 10001:10001 /run/lzug-admin && chmod 0750 /run/lzug-admin'
# The published service does not initialize storage implicitly.
compose run --rm --no-deps --entrypoint python lzug -c \
    'from backend.persistence.database import initialize; initialize()'
compose up -d

resolve_url() {
    port="$(compose port lzug "$container_port" | sed -n 's/.*://p' | head -n 1)"
    if [ -z "$port" ]; then
        echo "Compose did not publish an ephemeral host port." >&2
        compose logs >&2 || true
        exit 1
    fi
    url="http://127.0.0.1:$port"
}

resolve_url

compose_status() {
    field=$1
    fallback=$2
    raw_status=$(compose ps --all --format json 2>/dev/null) || {
        echo "$fallback"
        return
    }
    printf '%s' "$raw_status" | python3 -c '
import json
import sys

raw = sys.stdin.read().strip()
field = sys.argv[1]
fallback = sys.argv[2]
try:
    parsed = json.loads(raw)
except json.JSONDecodeError:
    try:
        parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except json.JSONDecodeError:
        print("unknown")
        raise SystemExit
if isinstance(parsed, dict):
    parsed = [parsed]
status = parsed[0].get(field, "") if parsed else ""
print(status or fallback)
' "$field" "$fallback"
}

health_status() {
    compose_status Health unavailable
}

lifecycle_status() {
    compose_status State unknown
}

http_status() {
    status=$(curl --silent --show-error --output /dev/null \
        --write-out '%{http_code}' --max-time 5 "$url/api/ready" 2>/dev/null) \
        || status="unreachable"
    if [ -z "$status" ]; then
        status="unreachable"
    fi
    printf '%s\n' "$status"
}

wait_ready() {
    lifecycle_step=$1
    deadline=$(($(date +%s) + ready_timeout_seconds))
    last_http_status="not-checked"
    last_docker_health="unknown"

    echo "Waiting for Compose readiness after $lifecycle_step."
    while :; do
        last_http_status=$(http_status)
        if [ "$last_http_status" = "200" ]; then
            return 0
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            break
        fi
        sleep "$ready_interval_seconds"
    done

    last_docker_health=$(health_status)
    echo "Compose readiness timed out after $lifecycle_step: timeout=${ready_timeout_seconds}s http_status=$last_http_status docker_health=$last_docker_health" >&2
    echo "Compose service state:" >&2
    compose ps --all >&2 || true
    echo "Compose logs:" >&2
    compose logs >&2 || true
    return 1
}

wait_stopped() {
    deadline=$(($(date +%s) + ready_timeout_seconds))
    last_lifecycle_status="unknown"

    echo "Waiting for Compose stop to complete."
    while :; do
        last_lifecycle_status=$(lifecycle_status)
        if [ "$last_lifecycle_status" = "exited" ]; then
            return 0
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            break
        fi
        sleep "$ready_interval_seconds"
    done

    echo "Compose stop timed out: timeout=${ready_timeout_seconds}s lifecycle_status=$last_lifecycle_status" >&2
    echo "Compose service state:" >&2
    compose ps --all >&2 || true
    echo "Compose logs:" >&2
    compose logs >&2 || true
    return 1
}

assert_admin_socket() {
    compose exec -T lzug python -c '
import os
import stat
from pathlib import Path

assert (os.geteuid(), os.getegid()) == (10001, 10001)
directory = Path("/run/lzug-admin")
for path, expected_type, mode in (
    (directory, stat.S_ISDIR, 0o750),
    (directory / "admin.sock", stat.S_ISSOCK, 0o660),
):
    info = path.lstat()
    assert expected_type(info.st_mode), path.name
    assert (info.st_uid, info.st_gid) == (10001, 10001), path.name
    assert stat.S_IMODE(info.st_mode) == mode, path.name
print("Compose admin socket: uid=10001 gid=10001 directory=0750 socket=0660")
'
}

wait_ready "start"
assert_admin_socket
container_id=$(compose ps -q lzug)
test -n "$container_id"
lzug_assert_runtime_user "$container_id"
compose exec -T lzug python -c 'from pathlib import Path; Path("/data/compose-smoke-marker").write_text("persisted", encoding="utf-8")' >/dev/null
compose restart lzug >/dev/null
resolve_url
wait_ready "restart"
assert_admin_socket
test "$(compose exec -T lzug python -c 'from pathlib import Path; print(Path("/data/compose-smoke-marker").read_text(encoding="utf-8"))')" = "persisted"
compose stop lzug >/dev/null
wait_stopped
compose start lzug >/dev/null
resolve_url
wait_ready "stop/start"
assert_admin_socket
test "$(compose exec -T lzug python -c 'from pathlib import Path; print(Path("/data/compose-smoke-marker").read_text(encoding="utf-8"))')" = "persisted"

echo "Compose runtime, admin socket, health, restart, stop/start, and /data persistence checks passed with Docker: $image"
