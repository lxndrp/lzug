#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
app_image=${1:-lzug-demo-app:local}
seed_image=${2:-lzug-demo-seed:local}
product_image=${3:-lzug:0.0.0-dev.local}
expected_seed_revision=${4:-}
lzug_require_container_engine

suffix="lzug-demo-smoke-$$"
volume="$suffix-data"
container="$suffix-app"
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-demo-smoke.XXXXXX")
cleanup() {
    "$engine" rm --force "$container" >/dev/null 2>&1 || true
    "$engine" volume rm "$volume" >/dev/null 2>&1 || true
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

"$engine" volume create "$volume" >/dev/null

run_seed() {
    "$engine" run --rm --read-only --tmpfs /tmp \
        --mount "type=volume,source=$volume,target=/data" \
        "$seed_image"
}

start_app() {
    "$engine" run --detach --name "$container" --read-only --tmpfs /tmp \
        --publish 127.0.0.1::8000 \
        --env LZUG_HTTPS_ONLY=false \
        --mount "type=volume,source=$volume,target=/data" \
        "$app_image" >/dev/null
    port=$("$engine" port "$container" 8000/tcp | sed 's/.*://')
    url="http://127.0.0.1:$port"
    if ! lzug_wait_for_http_health "$url" 30; then
        "$engine" logs "$container" >&2 || true
        return 1
    fi
}

assert_status() {
    description=$1
    expected=$2
    actual=$3
    if [ "$actual" != "$expected" ]; then
        echo "$description: expected HTTP $expected, received $actual." >&2
        exit 1
    fi
}

echo "Verifying product/demo physical assembly separation."
"$engine" run --rm --entrypoint sh "$product_image" -c \
    'test ! -e /app/demo && ! grep -R -F "/api/demo" /app/backend /app/frontend >/dev/null 2>&1'

echo "Initializing and starting the bound demo image pair."
run_seed
start_app
lzug_assert_runtime_user "$container"

status_file="$temporary_directory/status.json"
curl --silent --show-error --fail "$url/api/demo/status" > "$status_file"
python3 -c '
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["mode"] == "demo"
assert payload["initialized"] is True
assert payload["initialization_status"] == "ready"
assert payload["runtime_contract"] == "lzug-demo-health-ready-v1"
assert payload["reset_status"] == "scheduled"
assert len(payload["seed_revision"]) == 64
assert payload["reset_timezone"] == "Europe/Berlin"
assert "snapshot_sha256" not in payload
if sys.argv[2]:
    assert payload["seed_revision"] == sys.argv[2]
' "$status_file" "$expected_seed_revision"
curl --silent --show-error --fail "$url/" | grep -F '<app-root' >/dev/null
"$engine" exec "$container" grep -R -F "/api/demo/session" /app/frontend >/dev/null

headers="$temporary_directory/session.headers"
body="$temporary_directory/session.json"
session_status=$(curl --silent --show-error --dump-header "$headers" --output "$body" \
    --write-out '%{http_code}' --request POST --header 'Content-Type: application/json' \
    --data '{"role":"chair"}' "$url/api/demo/session")
assert_status "Create chair demo session" 201 "$session_status"
session_token=$(sed -n 's/^Set-Cookie: lzug_session=\([^;]*\).*/\1/ip' "$headers" | tr -d '\r' | head -1)
csrf_token=$(sed -n 's/^Set-Cookie: lzug_csrf=\([^;]*\).*/\1/ip' "$headers" | tr -d '\r' | head -1)
test -n "$session_token"
test -n "$csrf_token"

curl --silent --show-error --fail \
    --header "Cookie: lzug_session=$session_token; lzug_csrf=$csrf_token" \
    "$url/api/session" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload["demo_role"] == "chair"
assert "planning-proposal:generate" in payload["capabilities"]
'

denied_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --request DELETE \
    --header "Cookie: lzug_session=$session_token; lzug_csrf=$csrf_token" \
    --header "X-CSRF-Token: $csrf_token" "$url/api/candidates/1")
assert_status "Default-deny delete" 403 "$denied_status"

curl --silent --show-error --fail --request POST \
    --header 'Content-Type: application/json' \
    --header "Cookie: lzug_session=$session_token; lzug_csrf=$csrf_token" \
    --header "X-CSRF-Token: $csrf_token" \
    --data '{"round_id":1}' "$url/api/planning-proposals" >/dev/null
"$engine" exec "$container" sh -c 'printf demo > /data/documents/temporary.txt'

echo "Reinitializing the same volume and verifying reset semantics."
"$engine" rm --force "$container" >/dev/null
run_seed
start_app
old_session_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --header "Cookie: lzug_session=$session_token; lzug_csrf=$csrf_token" \
    "$url/api/session")
assert_status "Old session after reset" 401 "$old_session_status"
"$engine" exec "$container" test ! -e /data/documents/temporary.txt
curl --silent --show-error --fail "$url/api/demo/status" | \
    python3 -c 'import json,sys; assert json.load(sys.stdin)["initialized"] is True'

echo "Demo assembly, policy, seed, and reset smoke test passed with $engine."
