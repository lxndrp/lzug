#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
compose_file="$root_dir/compose.yaml"
image=${LZUG_IMAGE:-}

if [ -z "$image" ]; then
    echo "Set LZUG_IMAGE to an existing local or published immutable image." >&2
    exit 2
fi
lzug_require_container_engine

project="lzug-compose-smoke-$$"
volume="$project-data"
container_port=${LZUG_PORT:-8000}
compose() {
    LZUG_IMAGE="$image" LZUG_DATA_VOLUME="$volume" LZUG_HOST_PORT=0 \
        "$engine" compose -p "$project" -f "$compose_file" "$@"
}
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

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

health_status() {
    compose ps --format json | python3 -c '
import json
import sys

raw = sys.stdin.read().strip()
try:
    parsed = json.loads(raw)
except json.JSONDecodeError:
    parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
if isinstance(parsed, dict):
    parsed = [parsed]
print(parsed[0].get("Health", "") if parsed else "")
'
}

wait_ready() {
    attempts=0
    while [ "$attempts" -lt 45 ]; do
        if lzug_http_health_is_ready "$url" \
            && [ "$(health_status)" = "healthy" ]; then
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    compose logs >&2 || true
    return 1
}

wait_ready
container_id=$(compose ps -q lzug)
test -n "$container_id"
lzug_assert_runtime_user "$container_id"
compose exec -T lzug python -c 'from pathlib import Path; Path("/data/compose-smoke-marker").write_text("persisted", encoding="utf-8")' >/dev/null
compose restart lzug >/dev/null
resolve_url
wait_ready
test "$(compose exec -T lzug python -c 'from pathlib import Path; print(Path("/data/compose-smoke-marker").read_text(encoding="utf-8"))')" = "persisted"
compose stop lzug >/dev/null
compose start lzug >/dev/null
resolve_url
wait_ready
test "$(compose exec -T lzug python -c 'from pathlib import Path; print(Path("/data/compose-smoke-marker").read_text(encoding="utf-8"))')" = "persisted"

echo "Compose runtime, health, restart, stop/start, and /data persistence checks passed with $engine: $image"
