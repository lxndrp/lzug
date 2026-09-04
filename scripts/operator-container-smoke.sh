#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
image="${1:-lzug:smoke}"
admin_binary="${LZUG_ADMIN_BINARY:-}"

lzug_require_container_engine

temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-operator-container.XXXXXX")
container="lzug-operator-smoke-$$"
volume="$container-data"
if [ -z "$admin_binary" ]; then
    admin_binary="$temporary_directory/lzug-admin"
    revision=$(git -C "$root_dir" rev-parse HEAD)
    application_version=$(
        python3 "$root_dir/scripts/build_metadata.py" \
            --revision "$revision" --field identity
    )
    (
        cd "$root_dir/operator-cli"
        go build -trimpath \
            -ldflags="-s -w -X main.applicationVersion=$application_version -X main.applicationRevision=$revision" \
            -o "$admin_binary" ./cmd/lzug-admin
    )
fi
cleanup() {
    lzug_cleanup_contract_container "$container" "$volume"
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

"$admin_binary" recipient-key generate \
    --identity-file "$temporary_directory/backup.agekey" \
    --recipient-file "$temporary_directory/backup.agepub" >/dev/null
"$admin_binary" recipient-key generate \
    --identity-file "$temporary_directory/wrong.agekey" \
    --recipient-file "$temporary_directory/wrong.agepub" >/dev/null
recipient_public_key=$(cat "$temporary_directory/backup.agepub")

"$engine" volume create "$volume" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --env "LZUG_SMTP_USERNAME=diagnostic-operator" \
    --env "LZUG_SMTP_PASSWORD=diagnostic-secret-marker" \
    --mount "type=volume,source=$volume,target=/data" \
    "$image" --host 0.0.0.0 --port 8000 --init >/dev/null
if ! lzug_wait_for_container_health "$container" 30; then
    echo "Container did not become ready for the operator contract." >&2
    "$engine" logs "$container" >&2 || true
    exit 1
fi

lzug_assert_runtime_user "$container"
lzug_copy_build_metadata "$container" "$temporary_directory/container-metadata.json"
"$admin_binary" --build-metadata > "$temporary_directory/cli-metadata.json"
cmp "$temporary_directory/container-metadata.json" "$temporary_directory/cli-metadata.json"

lifecycle_status=0
"$admin_binary" --engine "$engine" --container "$container" --json \
        upgrade apply --backup-output "$temporary_directory/pre-upgrade.lzug" \
        --identity-file "$temporary_directory/backup.agekey" \
        --confirm-irreversible --force \
        >"$temporary_directory/unverified-release.json" \
        2>"$temporary_directory/unverified-release.stderr" || lifecycle_status=$?
test "$lifecycle_status" -eq 33
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 33 and payload["ok"] is False
assert payload["error"]["class"] == "release_artifact_unverified"
' "$temporary_directory/unverified-release.json"

maintenance_status=0
printf '%s\n' '{"version":1,"command":"rollback","arguments":{"target":{"identity":"0.6.0","image":"ghcr.io/lxndrp/lzug@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","release":true,"revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","tag":"v0.6.0"}}}' | \
    "$engine" exec --interactive "$container" python -m backend.admin --protocol 1 \
        >"$temporary_directory/live-server-lifecycle.json" \
        2>"$temporary_directory/live-server-lifecycle.stderr" || maintenance_status=$?
test "$maintenance_status" -eq 33
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["version"] == 1 and payload["ok"] is False
assert payload["error"]["class"] == "maintenance_required"
' "$temporary_directory/live-server-lifecycle.json"

invitation=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        account invite --email cli-contract@example.invalid
)
token=$(printf '%s' "$invitation" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
assert payload["result"]["account"]["email"] == "cli-contract@example.invalid"
assert payload["result"]["kind"] == "invitation"
print(payload["result"]["token"])
')
consumed=$(
    printf '%s' "$token" | "$admin_binary" --engine "$engine" --container "$container" --json \
        account consume-invitation
)
printf '%s' "$consumed" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
assert payload["result"]["account"]["email"] == "cli-contract@example.invalid"
' >/dev/null

committee=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        committee bootstrap \
        --idempotency-key cli-contract-committee \
        --name "CLI-Vertragsausschuss" \
        --ihk "IHK Vertrag" \
        --occupation "Vertragsberuf" \
        --chair-first-name "CLI" \
        --chair-last-name "Vorsitz" \
        --chair-email cli-chair@example.invalid \
        --chair-member-status ordinary \
        --chair-representing-side employee
)
printf '%s' "$committee" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
assert payload["result"]["committee_id"] > 0
assert payload["result"]["bootstrap_state"] == "ready"
assert len(payload["result"]["person_ids"]) == 1
assert len(payload["result"]["membership_ids"]) == 1
assert len(payload["result"]["account_ids"]) == 1
assert len(payload["result"]["invitations"]) == 1
assert payload["result"]["invitations"][0]["token"]
' >/dev/null

for diagnostic in status config doctor; do
    diagnostic_output=$(
        "$admin_binary" --engine "$engine" --container "$container" --json \
            system "$diagnostic"
    )
    printf '%s' "$diagnostic_output" | python3 -c '
import json
import sys

command, invitation_token = sys.argv[1:]
payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
result = payload["result"]
assert result["command"] == command and result["status"] == "ok"
assert result["checks"]
encoded = json.dumps(payload)
for forbidden in (
    "diagnostic-secret-marker",
    "cli-contract@example.invalid",
    "cli-chair@example.invalid",
    invitation_token,
):
    assert forbidden not in encoded
' "$diagnostic" "$token" >/dev/null
done

"$admin_binary" --engine "$engine" --container "$container" --json \
    backup recipient set --identity-file "$temporary_directory/backup.agekey" \
    >"$temporary_directory/recipient.json"

backup=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        backup create --output "$temporary_directory/backup.lzug"
)
backup_artifact=$(printf '%s' "$backup" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
result = payload["result"]
assert result["artifact_type"] == "backup"
assert result["artifact_id"] and result["snapshot_at"]
print(result["artifact"])
')

verified_backup=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        backup verify --artifact "$backup_artifact" \
        --identity-file "$temporary_directory/backup.agekey"
)
printf '%s' "$verified_backup" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
assert payload["result"]["artifact_type"] == "backup"
assert payload["result"]["documents"] >= 0
' >/dev/null

wrong_key_status=0
"$admin_binary" --engine "$engine" --container "$container" --json \
        backup verify --artifact "$backup_artifact" \
        --identity-file "$temporary_directory/wrong.agekey" \
        >"$temporary_directory/wrong-key.json" \
        2>"$temporary_directory/wrong-key.stderr" || wrong_key_status=$?
test "$wrong_key_status" -eq 2
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 2 and payload["ok"] is False
assert payload["error"]["class"] == "recipient_key_mismatch"
assert payload["error"]["phase"] == "local-artifact"
' "$temporary_directory/wrong-key.json"

full_export=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        export create --recipient "$recipient_public_key" \
        --output "$temporary_directory/export.lzug" --force
)
export_artifact=$(printf '%s' "$full_export" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
result = payload["result"]
assert result["artifact_type"] == "full_export"
assert result["artifact_id"] and result["snapshot_at"]
print(result["artifact"])
')
verified_export=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        export verify --artifact "$export_artifact" \
        --identity-file "$temporary_directory/backup.agekey"
)
printf '%s' "$verified_export" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
assert payload["result"]["artifact_type"] == "full_export"
' >/dev/null

replace_required_status=0
"$admin_binary" --engine "$engine" --container "$container" --json \
        backup restore --artifact "$backup_artifact" \
        --identity-file "$temporary_directory/backup.agekey" --force \
        >"$temporary_directory/replace-required.json" \
        2>"$temporary_directory/replace-required.stderr" || replace_required_status=$?
test "$replace_required_status" -eq 29
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 29 and payload["ok"] is False
assert payload["error"]["class"] == "replace_confirmation_required"
assert payload["error"]["phase"] == "precheck"
' "$temporary_directory/replace-required.json"

restored=$(
    "$admin_binary" --engine "$engine" --container "$container" --json \
        backup restore --artifact "$backup_artifact" \
        --identity-file "$temporary_directory/backup.agekey" --replace --force
)
printf '%s' "$restored" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 0 and payload["ok"] is True
result = payload["result"]
assert result["artifact_type"] == "backup"
assert "pre-restore-" in result["safety_artifact"]
assert result["phases"] == [
    "precheck", "prepared_restore", "migration", "postcheck", "activation"
]
assert result["readiness"] in {"ready", "restricted", "not_ready"}
' >/dev/null

if printf '%s\n%s\n%s\n%s\n' \
    "$backup" "$verified_backup" "$full_export" "$restored" | \
    grep -F -f "$temporary_directory/backup.agekey" >/dev/null; then
    echo "Artifact command output exposed the private recipient key." >&2
    exit 1
fi
if grep -F -f "$temporary_directory/backup.agekey" \
    "$temporary_directory/unverified-release.json" \
    "$temporary_directory/unverified-release.stderr" \
    "$temporary_directory/wrong-key.json" \
    "$temporary_directory/wrong-key.stderr" \
    "$temporary_directory/replace-required.json" \
    "$temporary_directory/replace-required.stderr" >/dev/null; then
    echo "Artifact command error output exposed the private recipient key." >&2
    exit 1
fi
if "$engine" logs "$container" 2>&1 | \
    grep -F -f "$temporary_directory/backup.agekey" >/dev/null; then
    echo "Container logs exposed the private recipient key." >&2
    exit 1
fi

echo "Operator CLI-to-container administration, diagnostic, and artifact contracts passed with $engine: $image"
