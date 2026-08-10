#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$root_dir/compose.yaml"
engine=${CONTAINER_ENGINE:-}
image=${LZUG_IMAGE:-}

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
if [ -z "$image" ]; then
    echo "Set LZUG_IMAGE to an existing local or published immutable image." >&2
    exit 2
fi
if ! "$engine" info >/dev/null 2>&1; then
    echo "$engine is installed but its engine is unavailable." >&2
    exit 77
fi

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

"$root_dir/scripts/validate-compose.sh" >/dev/null
compose up -d
port="$(compose port lzug "$container_port/tcp" | sed -n 's/.*://p' | head -n 1)"
if [ -z "$port" ]; then
    echo "Compose did not publish an ephemeral host port." >&2
    compose logs >&2 || true
    exit 1
fi
url="http://127.0.0.1:$port"

wait_ready() {
    attempts=0
    while [ "$attempts" -lt 45 ]; do
        if curl --silent --show-error --fail "$url/api/health" >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    compose logs >&2 || true
    return 1
}

wait_ready
test "$(compose ps --format json | python3 -c '
import json
import sys

raw = sys.stdin.read().strip()
try:
    parsed = json.loads(raw)
except json.JSONDecodeError:
    parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
if isinstance(parsed, dict):
    parsed = [parsed]
print(parsed[0]["Health"])
')" = "healthy"
test "$(compose exec -T lzug id -u)" = "10001"
compose exec -T lzug python -c 'from pathlib import Path; Path("/data/compose-smoke-marker").write_text("persisted", encoding="utf-8")' >/dev/null
compose restart lzug >/dev/null
wait_ready
test "$(compose exec -T lzug python -c 'from pathlib import Path; print(Path("/data/compose-smoke-marker").read_text(encoding="utf-8"))')" = "persisted"
compose stop lzug >/dev/null
compose start lzug >/dev/null
wait_ready
test "$(compose exec -T lzug python -c 'from pathlib import Path; print(Path("/data/compose-smoke-marker").read_text(encoding="utf-8"))')" = "persisted"

echo "Compose runtime, health, restart, stop/start, and /data persistence checks passed with $engine: $image"
