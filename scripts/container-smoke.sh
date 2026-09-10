#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
image="${1:-lzug-app:smoke}"
lzug_require_docker

suffix="lzug-smoke-$$"
volume="$suffix-data"
container="$suffix-app"
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-container-smoke.XXXXXX")
cleanup() {
    lzug_cleanup_contract_container "$container" "$volume"
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

lzug_start_contract_container "$container" "$volume" "$image" \
    --publish 127.0.0.1::8000

resolve_url() {
    port="$(docker port "$container" 8000/tcp | sed 's/.*://')"
    url="http://127.0.0.1:$port"
}

resolve_url

wait_for_health() {
    if ! lzug_wait_for_http_health "$url" 30; then
        echo "Container did not become ready." >&2
        docker logs "$container" >&2 || true
        return 1
    fi
}

assert_status() {
    description=$1
    expected=$2
    actual=$3
    response_body=${4:-}
    if [ "$actual" != "$expected" ]; then
        echo "$description: expected HTTP $expected, received $actual." >&2
        if [ -n "$response_body" ] && [ -s "$response_body" ]; then
            echo "Response body:" >&2
            cat "$response_body" >&2
            echo >&2
        fi
        exit 1
    fi
}

wait_for_health

echo "Verifying operator bootstrap on an empty product database."
docker exec "$container" python -c '
from backend.identity.committee_admin import CommitteeAdminService
from backend.persistence.models import EXAM_HALF_YEAR
from backend.application.repositories import ResourceRepository

CommitteeAdminService().bootstrap({
    "idempotency_key": "container-smoke-initial-committee",
    "committee": {
        "name": "Initial smoke committee",
        "ihk": "IHK Container Smoke",
        "occupation": "Test occupation",
    },
    "chair": {
        "mode": "new",
        "first_name": "Initial",
        "last_name": "Chair",
        "email": "initial.chair@example.invalid",
        "member_status": "ordinary",
        "representing_side": "employer",
    },
})
ResourceRepository().create(
    EXAM_HALF_YEAR,
    {"season": "summer", "year": 2030, "status": "active"},
)
'

echo "Verifying container readiness and public HTTP boundary."
curl --silent --show-error --fail "$url/" | grep -F '<app-root' >/dev/null
curl --silent --show-error --fail "$url/dashboard" | grep -F '<app-root' >/dev/null
assert_status "Missing static asset" 404 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/assets/missing.svg")"

lzug_assert_runtime_user "$container"
lzug_copy_build_metadata "$container" "$temporary_directory/backend-metadata.json"
docker exec "$container" cat /app/frontend/build-metadata.json > "$temporary_directory/frontend-metadata.json"
cmp "$temporary_directory/backend-metadata.json" "$temporary_directory/frontend-metadata.json"
expected_version=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' \
    < "$temporary_directory/backend-metadata.json")
metadata_revision=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["revision"])' \
    < "$temporary_directory/backend-metadata.json")
expected_revision=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")
expected_image_version=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image")
test "$metadata_revision" = "$expected_revision"
test "$expected_version" = "$expected_image_version"
headers="$temporary_directory/headers"
curl --silent --show-error --fail --dump-header "$headers" "$url/api/health" | \
    EXPECTED_VERSION="$expected_version" EXPECTED_REVISION="$expected_revision" python3 -c '
import json
import os
import sys

payload = json.load(sys.stdin)
assert payload == {
    "status": "ok",
    "version": os.environ["EXPECTED_VERSION"],
    "revision": os.environ["EXPECTED_REVISION"],
    "_links": {"self": {"href": "/api/health"}},
}
'

grep -Eiq '^Content-Security-Policy: .*frame-ancestors.*none' "$headers"
grep -Eiq '^Strict-Transport-Security: max-age=31536000' "$headers"
grep -Eiq '^X-Content-Type-Options: nosniff' "$headers"
grep -Eiq '^X-Frame-Options: DENY' "$headers"
assert_status "Unauthenticated domain API" 401 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/api/candidates")"
assert_status "Unauthenticated API root" 401 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/api")"
assert_status "Disallowed Origin" 403 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --header 'Origin: https://blocked.example.invalid' "$url/api/health")"

echo "Verifying operator, actor, and committee isolation."
operator_credentials=$(docker exec "$container" python -c '
import json
from backend.identity.auth import AuthenticationRepository

repository = AuthenticationRepository()
account = repository.create_account("operator@example.invalid", is_operator=True)
credentials = repository.create_session(account["id"])
print(json.dumps({"token": credentials.token, "csrf": credentials.csrf_token}))
')
operator_token=$(printf '%s' "$operator_credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
assert_status "Operator without domain role" 403 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --header "Cookie: __Host-lzug_session=$operator_token" "$url/api/candidates")"
echo "Operator/domain-role separation passed."

actor_credentials=$(docker exec "$container" python -c '
import json
from backend.identity.auth import AuthenticationRepository

credentials = AuthenticationRepository().create_session(1)
print(json.dumps({"token": credentials.token, "csrf": credentials.csrf_token}))
')
actor_token=$(printf '%s' "$actor_credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
actor_csrf=$(printf '%s' "$actor_credentials" | python3 -c 'import json,sys; print(json.load(sys.stdin)["csrf"])')
echo "Actor session created."

isolated_round=$(docker exec "$container" python -c '
import json
from backend.identity.committee_admin import CommitteeAdminService
from backend.persistence.models import EXAM_ROUND
from backend.application.repositories import ResourceRepository

repository = ResourceRepository()
committee = CommitteeAdminService().bootstrap({
    "idempotency_key": "container-smoke-isolated",
    "committee": {
        "name": "Isolated committee",
        "ihk": "IHK Container Smoke",
        "occupation": "Test occupation",
    },
    "chair": {
        "mode": "new",
        "first_name": "Isolated",
        "last_name": "Chair",
        "email": "isolated.chair@example.invalid",
        "member_status": "ordinary",
        "representing_side": "employer",
    },
})
exam_round = repository.create(EXAM_ROUND, {
    "exam_half_year_id": 1,
    "committee_id": committee["committee_id"],
    "name": "Isolated round",
    "created_by_member_id": committee["membership_ids"][0],
})
print(json.dumps({"committee_id": committee["committee_id"], "round_id": exam_round["id"]}))
')
isolated_committee_id=$(printf '%s' "$isolated_round" | python3 -c 'import json,sys; print(json.load(sys.stdin)["committee_id"])')
isolated_round_id=$(printf '%s' "$isolated_round" | python3 -c 'import json,sys; print(json.load(sys.stdin)["round_id"])')
assert_status "Concealed foreign committee round" 404 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --header "Cookie: __Host-lzug_session=$actor_token" \
        "$url/api/exam-rounds/$isolated_round_id")"
foreign_write_body="$temporary_directory/foreign-write-response.json"
foreign_write_status=$(curl --silent --output "$foreign_write_body" --write-out '%{http_code}' \
        --request POST \
        --header 'Content-Type: application/json' \
        --header "Cookie: __Host-lzug_session=$actor_token" \
        --header "X-CSRF-Token: $actor_csrf" \
        --data "{\"exam_half_year_id\":1,\"committee_id\":$isolated_committee_id,\"name\":\"Forbidden round\",\"created_by_member_id\":1}" \
        "$url/api/exam-rounds")
assert_status "Foreign committee write" 403 "$foreign_write_status" "$foreign_write_body"
echo "Committee read concealment and write isolation passed."

created_round=$(curl --silent --show-error --fail \
    --request POST \
    --header 'Content-Type: application/json' \
    --header "Cookie: __Host-lzug_session=$actor_token" \
    --header "X-CSRF-Token: $actor_csrf" \
    --data '{"season":"summer","year":2030,"committee_id":1,"name":"Actor boundary","created_by_member_id":999999}' \
    "$url/api/exam-rounds")
created_by=$(printf '%s' "$created_round" | python3 -c 'import json,sys; print(json.load(sys.stdin)["created_by_member_id"])')
if [ "$created_by" != "1" ]; then
    echo "Server-derived actor: expected member 1, received $created_by." >&2
    exit 1
fi
echo "Atomic half-year context and server-derived actor passed."

echo "Verifying session-cookie and secret-free logging boundaries."
curl --silent --show-error --dump-header "$headers" --output /dev/null \
    --request POST \
    --header "Cookie: __Host-lzug_session=$actor_token" \
    --header "X-CSRF-Token: $actor_csrf" \
    "$url/api/session/rotate"
grep -Eiq '^Set-Cookie: __Host-lzug_session=.*Secure.*HttpOnly' "$headers"
grep -Eiq '^Set-Cookie: lzug_csrf=.*SameSite=Strict.*Secure' "$headers"

log_marker="container-secret-marker-$$"
invalid_login_body="$temporary_directory/invalid-login-response.json"
invalid_login_status=$(curl --silent --output "$invalid_login_body" --write-out '%{http_code}' \
    --request POST \
    --header 'Content-Type: application/json' \
    --data "{\"email\":\"$log_marker@example.invalid\",\"password\":\"$log_marker\",\"second_factor\":\"000000\"}" \
    "$url/api/auth/login")
assert_status "Invalid login" 401 "$invalid_login_status" "$invalid_login_body"
if docker logs "$container" 2>&1 | grep -F "$log_marker" >/dev/null; then
    echo "Container logs exposed request secret material." >&2
    exit 1
fi

echo "Verifying live but not ready operation with a pending migration."
docker stop "$container" >/dev/null
docker rm "$container" >/dev/null
# Only the disposable smoke volume is modified, with its server stopped.
docker run --rm --read-only --tmpfs /tmp \
    --mount "type=volume,source=$volume,target=/data" --entrypoint python "$image" -c '
import shutil, sqlite3
shutil.copyfile("/data/lzug.sqlite", "/data/lifecycle-smoke.sqlite")
with sqlite3.connect("/data/lzug.sqlite") as db:
    name = db.execute("SELECT MAX(name) FROM schema_migration").fetchone()[0]
    db.execute("DELETE FROM schema_migration_checksum WHERE name = ?", (name,))
    db.execute("DELETE FROM schema_migration WHERE name = ?", (name,))
'
docker run --detach --name "$container" --read-only --tmpfs /tmp \
    --publish 127.0.0.1::8000 --mount "type=volume,source=$volume,target=/data" \
    "$image" --host 0.0.0.0 --port 8000 >/dev/null
resolve_url
if ! lzug_wait_for_container_health "$container" 30; then
    echo "Pending migration lost process liveness." >&2
    exit 1
fi
assert_status "Pending migration readiness" 503 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/api/ready")"
curl --silent --show-error --fail "$url/api/lifecycle" | python3 -c '
import json, sys
p = json.load(sys.stdin)
assert p["state"] == "migration_required" and p["ready"] is False
assert set(p) == {"status", "state", "ready", "version", "revision", "_links"}
'
curl --silent --show-error --fail "$url/dashboard" | grep -F '<app-root' >/dev/null
assert_status "Pending migration business API" 503 \
    "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/api/candidates")"
docker stop "$container" >/dev/null
docker rm "$container" >/dev/null
docker run --rm --read-only --tmpfs /tmp \
    --mount "type=volume,source=$volume,target=/data" --entrypoint python "$image" -c '
from pathlib import Path
Path("/data/lifecycle-smoke.sqlite").replace("/data/lzug.sqlite")
'
docker run --detach --name "$container" --read-only --tmpfs /tmp \
    --publish 127.0.0.1::8000 --mount "type=volume,source=$volume,target=/data" \
    "$image" --host 0.0.0.0 --port 8000 >/dev/null
resolve_url
wait_for_health

echo "Container runtime, lifecycle, authentication isolation, and security smoke test passed with Docker: $image"
