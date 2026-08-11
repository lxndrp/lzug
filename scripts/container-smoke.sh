#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
image="${1:-lzug:smoke}"
engine="${CONTAINER_ENGINE:-}"

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

suffix="lzug-smoke-$$"
volume="$suffix-data"
container="$suffix-app"
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-container-smoke.XXXXXX")
cleanup() {
    "$engine" rm --force "$container" >/dev/null 2>&1 || true
    "$engine" volume rm "$volume" >/dev/null 2>&1 || true
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

"$engine" volume create "$volume" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --publish 127.0.0.1::8000 \
    --mount "type=volume,source=$volume,target=/data" \
    --mount "type=bind,source=$root_dir/db/seed_demo.sql,target=/app/db/seed_demo.sql,readonly" \
    "$image" --host 0.0.0.0 --port 8000 --init --seed >/dev/null

port="$("$engine" port "$container" 8000/tcp | sed 's/.*://')"
url="http://127.0.0.1:$port"

i=0
while [ "$i" -lt 30 ]; do
    if curl --silent --show-error --fail "$url/api/health" >/dev/null 2>&1; then
        break
    fi
    i=$((i + 1))
    sleep 1
done
if [ "$i" -eq 30 ]; then
    echo "Container did not become ready." >&2
    "$engine" logs "$container" >&2 || true
    exit 1
fi

curl --silent --show-error --fail "$url/" | grep -F '<app-root' >/dev/null
curl --silent --show-error --fail "$url/dashboard" | grep -F '<app-root' >/dev/null
[ "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/assets/missing.svg")" = 404 ]

test "$("$engine" exec "$container" id -u)" = "10001"
curl --silent --show-error --fail "$url/api/health" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload == {"status": "ok", "_links": {"self": {"href": "/api/health"}}}
'

headers="$temporary_directory/headers"
curl --silent --show-error --dump-header "$headers" --output /dev/null "$url/api/health"
grep -Eiq '^Content-Security-Policy: .*frame-ancestors.*none' "$headers"
grep -Eiq '^Strict-Transport-Security: max-age=31536000' "$headers"
grep -Eiq '^X-Content-Type-Options: nosniff' "$headers"
grep -Eiq '^X-Frame-Options: DENY' "$headers"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/api/candidates")" = "401"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/api")" = "401"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --header 'Origin: https://blocked.example.invalid' "$url/api/health")" = "403"

operator_credentials=$("$engine" exec "$container" python -c '
import json
from backend.auth import AuthenticationRepository

repository = AuthenticationRepository()
account = repository.create_account("operator@example.invalid", is_operator=True)
credentials = repository.create_session(account["id"])
print(json.dumps({"token": credentials.token, "csrf": credentials.csrf_token}))
')
operator_token=$(printf '%s' "$operator_credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --header "Cookie: __Host-lzug_session=$operator_token" "$url/api/candidates")" = "403"

actor_credentials=$("$engine" exec "$container" python -c '
import json
from backend.auth import AuthenticationRepository

credentials = AuthenticationRepository().create_session(1)
print(json.dumps({"token": credentials.token, "csrf": credentials.csrf_token}))
')
actor_token=$(printf '%s' "$actor_credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
actor_csrf=$(printf '%s' "$actor_credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["csrf"])')

isolated_round=$("$engine" exec "$container" python -c '
from backend.models import COMMITTEE, EXAM_ROUND
from backend.repositories import ResourceRepository

repository = ResourceRepository()
committee = repository.create(COMMITTEE, {"name": "Isolated committee", "occupation": "Test"})
membership = repository.create_membership({
    "person_id": 2,
    "committee_id": committee["id"],
    "member_status": "ordinary",
    "committee_role": "chair",
    "representing_side": "employer",
    "is_active": 1,
})
exam_round = repository.create(EXAM_ROUND, {
    "exam_half_year_id": 1,
    "committee_id": committee["id"],
    "name": "Isolated round",
    "created_by_member_id": membership["id"],
})
print(exam_round["id"])
')
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --header "Cookie: __Host-lzug_session=$actor_token" \
    "$url/api/exam-rounds/$isolated_round")" = "403"

half_year=$(curl --silent --show-error --fail \
    --request POST \
    --header 'Content-Type: application/json' \
    --header "Cookie: __Host-lzug_session=$actor_token" \
    --header "X-CSRF-Token: $actor_csrf" \
    --data '{"season":"summer","year":2030,"status":"draft"}' \
    "$url/api/exam-half-years")
half_year_id=$(printf '%s' "$half_year" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
created_round=$(curl --silent --show-error --fail \
    --request POST \
    --header 'Content-Type: application/json' \
    --header "Cookie: __Host-lzug_session=$actor_token" \
    --header "X-CSRF-Token: $actor_csrf" \
    --data "{\"exam_half_year_id\":$half_year_id,\"committee_id\":1,\"name\":\"Actor boundary\",\"created_by_member_id\":999999}" \
    "$url/api/exam-rounds")
test "$(printf '%s' "$created_round" | python3 -c 'import json,sys; print(json.load(sys.stdin)["created_by_member_id"])')" = "1"

curl --silent --show-error --dump-header "$headers" --output /dev/null \
    --request POST \
    --header "Cookie: __Host-lzug_session=$actor_token" \
    --header "X-CSRF-Token: $actor_csrf" \
    "$url/api/session/rotate"
grep -Eiq '^Set-Cookie: __Host-lzug_session=.*Secure.*HttpOnly' "$headers"
grep -Eiq '^Set-Cookie: lzug_csrf=.*SameSite=Strict.*Secure' "$headers"

log_marker="container-secret-marker-$$"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --request POST \
    --header 'Content-Type: application/json' \
    --data "{\"email\":\"$log_marker@example.invalid\",\"password\":\"$log_marker\",\"second_factor\":\"000000\"}" \
    "$url/api/auth/login")" = "401"
if "$engine" logs "$container" 2>&1 | grep -F "$log_marker" >/dev/null; then
    echo "Container logs exposed request secret material." >&2
    exit 1
fi

"$engine" restart "$container" >/dev/null
curl --silent --show-error --fail "$url/api/health" >/dev/null

echo "Container runtime, authentication isolation, and security smoke test passed with $engine: $image"
