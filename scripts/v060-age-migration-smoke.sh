#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
current_image="${1:-lzug:smoke}"
v060_image="${LZUG_V060_IMAGE:-ghcr.io/lxndrp/lzug@sha256:00e467d8acd6602ba8b4259b3f2a4e51ec98273e0be551f367e5979d5c780fe6}"

lzug_require_container_engine

temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-v060-migration.XXXXXX")
container="lzug-v060-migration-$$"
volume="$container-data"
admin_binary="$temporary_directory/lzug-admin"
cleanup() {
    lzug_cleanup_contract_container "$container" "$volume"
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

revision=$(git -C "$root_dir" rev-parse HEAD)
application_version=$(
    python3 "$root_dir/scripts/build_metadata.py" \
        --revision "$revision" --field identity
)
(
    cd "$root_dir/operator-cli"
    GOCACHE="${LZUG_GO_CACHE:-${TMPDIR:-/tmp}/lzug-go-build-cache}" go build -trimpath \
        -ldflags="-s -w -X main.applicationVersion=$application_version -X main.applicationRevision=$revision" \
        -o "$admin_binary" ./cmd/lzug-admin
)

"$engine" pull "$v060_image" >/dev/null
legacy_keys=$("$engine" run --rm --entrypoint python "$v060_image" -c '
import json
from backend.backup_restore import generate_recipient_keypair

public_key, private_key = generate_recipient_keypair()
print(json.dumps({"public": public_key, "private": private_key}))
')
legacy_public=$(printf '%s' "$legacy_keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["public"])')
legacy_private=$(printf '%s' "$legacy_keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["private"])')

"$engine" volume create "$volume" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --env "LZUG_BACKUP_RECIPIENT_PUBLIC_KEY=$legacy_public" \
    --mount "type=volume,source=$volume,target=/data" \
    "$v060_image" --host 0.0.0.0 --port 8000 --init >/dev/null
if ! lzug_wait_for_container_health "$container" 30; then
    echo "The pinned v0.6.0 container did not become ready." >&2
    "$engine" logs "$container" >&2 || true
    exit 1
fi

legacy_backup=$(
    printf '%s\n' '{"version":1,"command":"backup-create","arguments":{}}' | \
        "$engine" exec --interactive "$container" python -m backend.admin --protocol 1
)
legacy_artifact=$(printf '%s' "$legacy_backup" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
print(payload["result"]["artifact"])
')

legacy_verified=$(
    printf '%s\n%s\n' "$legacy_artifact" "$legacy_private" | python3 -c '
import json
import sys

artifact = sys.stdin.readline().rstrip("\n")
private_key = sys.stdin.readline().rstrip("\n")
print(json.dumps({
    "version": 1,
    "command": "artifact-verify",
    "arguments": {
        "artifact": artifact,
        "recipient_private_key": private_key,
    },
}))
' | "$engine" exec --interactive "$container" python -m backend.admin --protocol 1
)
printf '%s' "$legacy_verified" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
assert payload["result"]["artifact_type"] == "backup"
assert payload["result"]["source_application_version"] == "0.6.0"
assert payload["result"]["readiness"] in {"ready", "restricted", "not_ready"}
' >/dev/null

legacy_restored=$(
    printf '%s\n%s\n' "$legacy_artifact" "$legacy_private" | python3 -c '
import json
import sys

artifact = sys.stdin.readline().rstrip("\n")
private_key = sys.stdin.readline().rstrip("\n")
print(json.dumps({
    "version": 1,
    "command": "backup-restore",
    "arguments": {
        "artifact": artifact,
        "recipient_private_key": private_key,
        "replace": True,
    },
}))
' | "$engine" exec --interactive "$container" python -m backend.admin --protocol 1
)
printf '%s' "$legacy_restored" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
assert payload["result"]["source_application_version"] == "0.6.0"
assert payload["result"]["phases"] == [
    "precheck", "prepared_restore", "migration", "postcheck", "activation"
]
' >/dev/null
"$engine" cp "$container:/data/backups/$legacy_artifact" "$temporary_directory/legacy.lzug"

legacy_status=0
"$admin_binary" --json artifact inspect \
    --artifact "$temporary_directory/legacy.lzug" \
    >"$temporary_directory/legacy-inspect.json" \
    2>"$temporary_directory/legacy-inspect.stderr" || legacy_status=$?
test "$legacy_status" -eq 40
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["exit_code"] == 40 and payload["ok"] is False
assert payload["error"]["class"] == "artifact_legacy_v1"
assert "v0.6.0" in payload["error"]["message"]
' "$temporary_directory/legacy-inspect.json"

"$engine" rm --force "$container" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --mount "type=volume,source=$volume,target=/data" \
    "$current_image" --host 0.0.0.0 --port 8000 --init >/dev/null
if ! lzug_wait_for_container_health "$container" 30; then
    echo "The upgraded current container did not become ready." >&2
    "$engine" logs "$container" >&2 || true
    exit 1
fi

"$engine" exec "$container" python -c '
from backend.database import database_path, migration_status

status = migration_status(database_path())
assert status["state"] == "ready"
assert status["current"] == "028_add_exam_venue_change_notifications.sql"
'

"$admin_binary" recipient-key generate \
    --identity-file "$temporary_directory/current.agekey" \
    --recipient-file "$temporary_directory/current.agepub" >/dev/null
"$admin_binary" --engine "$engine" --container "$container" --json \
    backup recipient set --identity-file "$temporary_directory/current.agekey" \
    >"$temporary_directory/recipient.json"
"$admin_binary" --engine "$engine" --container "$container" --json \
    backup create --output "$temporary_directory/current.lzug" \
    >"$temporary_directory/current-backup.json"
"$admin_binary" --engine "$engine" --container "$container" --json \
    backup verify --artifact "$temporary_directory/current.lzug" \
    --identity-file "$temporary_directory/current.agekey" \
    >"$temporary_directory/current-verify.json"
"$admin_binary" --json artifact inspect \
    --artifact "$temporary_directory/current.lzug" \
    >"$temporary_directory/current-inspect.json"
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    created = json.load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    verified = json.load(stream)
with open(sys.argv[3], encoding="utf-8") as stream:
    inspected = json.load(stream)
assert created["ok"] is True and created["result"]["artifact_type"] == "backup"
assert verified["ok"] is True and verified["result"]["artifact_type"] == "backup"
assert inspected["ok"] is True and inspected["result"]["protection"] == "age-x25519-v1"
assert created["result"]["recipient_key_fingerprint"] == inspected["result"]["recipient_key_fingerprint"]
' "$temporary_directory/current-backup.json" "$temporary_directory/current-verify.json" "$temporary_directory/current-inspect.json"

echo "v0.6.0 restore, current schema upgrade, and new age backup path passed with $engine"
