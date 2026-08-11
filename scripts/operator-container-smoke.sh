#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
image="${1:-lzug:smoke}"
engine="${CONTAINER_ENGINE:-}"
admin_binary="${LZUG_ADMIN_BINARY:-}"

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
if ! "$engine" info >/dev/null 2>&1; then
    echo "${engine} is installed but its engine is unavailable." >&2
    exit 77
fi

temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-operator-container.XXXXXX")
container="lzug-operator-smoke-$$"
volume="$container-data"
if [ -z "$admin_binary" ]; then
    admin_binary="$temporary_directory/lzug-admin"
    application_version=$(cat "$root_dir/VERSION")
    (
        cd "$root_dir"
        go build -trimpath \
            -ldflags="-s -w -X main.applicationVersion=$application_version" \
            -o "$admin_binary" ./cmd/lzug-admin
    )
fi
cleanup() {
    "$engine" rm --force "$container" >/dev/null 2>&1 || true
    "$engine" volume rm "$volume" >/dev/null 2>&1 || true
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

"$engine" volume create "$volume" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --mount "type=volume,source=$volume,target=/data" \
    --mount "type=bind,source=$root_dir/db/seed_demo.sql,target=/app/db/seed_demo.sql,readonly" \
    "$image" --host 0.0.0.0 --port 8000 --init --seed >/dev/null

attempt=0
while [ "$attempt" -lt 30 ]; do
    if "$engine" exec "$container" python -m backend.healthcheck >/dev/null 2>&1; then
        break
    fi
    attempt=$((attempt + 1))
    sleep 1
done
if [ "$attempt" -eq 30 ]; then
    echo "Container did not become ready for the operator contract." >&2
    "$engine" logs "$container" >&2 || true
    exit 1
fi

invitation=$(
    "$admin_binary" --engine "$engine" --container "$container" \
        invite --email cli-contract@example.invalid
)
token=$(printf '%s' "$invitation" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
assert payload["result"]["account"]["email"] == "cli-contract@example.invalid"
assert payload["result"]["kind"] == "invitation"
print(payload["result"]["token"])
')
consumed=$(
    printf '%s' "$token" | "$admin_binary" --engine "$engine" --container "$container" \
        consume-invitation
)
printf '%s' "$consumed" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
assert payload["result"]["account"]["email"] == "cli-contract@example.invalid"
' >/dev/null

echo "Operator CLI-to-container invitation contract passed with $engine: $image"
