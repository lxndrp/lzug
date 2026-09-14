#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"
. "$root_dir/scripts/operator-container-contract.sh"
image="${1:-lzug-app:smoke}"
admin_binary="${LZUG_ADMIN_BINARY:-}"

lzug_require_docker

temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-operator-container.XXXXXX")
container="lzug-operator-smoke-$$"
volume="$container-data"
socket_volume="$container-socket"
stage="prepare CLI"
cleanup() {
    status=$?
    trap - EXIT
    if [ "$status" -ne 0 ]; then
        lzug_operator_failure "$status"
    fi
    lzug_cleanup_contract_container "$container" "$volume"
    docker volume rm "$socket_volume" >/dev/null 2>&1 || true
    rm -rf "$temporary_directory"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

lzug_build_operator_cli
stage="prepare private socket volume"
lzug_prepare_operator_socket
stage="generate recipient keys"
lzug_operator_cli recipient-key generate \
    --identity-file "$temporary_directory/backup.agekey" \
    --recipient-file "$temporary_directory/backup.agepub" >/dev/null
lzug_operator_cli recipient-key generate \
    --identity-file "$temporary_directory/wrong.agekey" \
    --recipient-file "$temporary_directory/wrong.agepub" >/dev/null
recipient_public_key=$(cat "$temporary_directory/backup.agepub")

stage="start backend with admin socket"
docker volume create "$volume" >/dev/null
docker run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --env "LZUG_SMTP_USERNAME=diagnostic-operator" \
    --env "LZUG_SMTP_PASSWORD=diagnostic-secret-marker" \
    --mount "type=volume,source=$volume,target=/data" \
    --mount "type=volume,source=$socket_volume,target=/run/lzug-admin,volume-nocopy" \
    "$image" --host 0.0.0.0 --port 8000 --init \
    --admin-socket-dir /run/lzug-admin --admin-socket-gid 10001 >/dev/null
if ! lzug_wait_for_container_health "$container" 30; then
    echo "Container did not become ready for the operator contract." >&2
    exit 1
fi

stage="runtime UID and socket permissions"
lzug_assert_runtime_user "$container"
lzug_assert_operator_socket
stage="matching CLI and container build metadata"
lzug_copy_build_metadata "$container" "$temporary_directory/container-metadata.json"
lzug_operator_cli --build-metadata > "$temporary_directory/cli-metadata.json"
cmp "$temporary_directory/container-metadata.json" "$temporary_directory/cli-metadata.json"

stage="reject legacy container-exec upgrade transport"
lifecycle_status=0
lzug_operator_cli --container "$container" --json \
        upgrade apply --backup-output "$temporary_directory/pre-upgrade.lzug" \
        --identity-file "$temporary_directory/backup.agekey" \
        --confirm-irreversible --force \
        >"$temporary_directory/unverified-release.json" \
        2>"$temporary_directory/unverified-release.stderr" || lifecycle_status=$?
lzug_expect_operator_exit 2 "$lifecycle_status"
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 2 and payload["ok"] is False
assert payload["error"]["class"] == "invalid_invocation"
' "$temporary_directory/unverified-release.json"

stage="reject rollback through live admin socket"
maintenance_status=0
lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
    upgrade rollback >"$temporary_directory/live-server-lifecycle.json" \
    2>"$temporary_directory/live-server-lifecycle.stderr" || maintenance_status=$?
lzug_expect_operator_exit 28 "$maintenance_status"
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["schema_version"] == 1 and payload["protocol_version"] == 1
assert payload["exit_code"] == 28 and payload["ok"] is False
assert payload["error"]["class"] == "rollback_not_supported"
' "$temporary_directory/live-server-lifecycle.json"

stage="account invitation"
invitation=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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
stage="consume account invitation"
consumed=$(
    printf '%s' "$token" | lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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

stage="committee bootstrap"
committee=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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

stage="redacted system diagnostics"
for diagnostic in status config doctor; do
    stage="system $diagnostic and redaction"
    diagnostic_output=$(
        lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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
assert payload["command"] == "system " + command
assert result["runtime"]["state"] == "ready" and result["runtime"]["ready"] is True
assert result["runtime"]["active"] >= 0
assert result["runtime"]["next_action"]["code"] == "none"
assert result["socket"]["state"] == "listening"
assert result["socket"]["protocol"] == 1 and result["socket"]["schema"] == 1
assert result["socket"]["active_connections"] >= 1
assert result["socket"]["max_connections"] > 0
assert result["socket"]["artifact_cleanup_required"] is False
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

stage="configure backup recipient"
lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
    backup recipient set --identity-file "$temporary_directory/backup.agekey" \
    >"$temporary_directory/recipient.json"

stage="create encrypted backup"
backup=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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

stage="verify encrypted backup"
verified_backup=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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

stage="reject wrong recipient key"
wrong_key_status=0
lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
        backup verify --artifact "$backup_artifact" \
        --identity-file "$temporary_directory/wrong.agekey" \
        >"$temporary_directory/wrong-key.json" \
        2>"$temporary_directory/wrong-key.stderr" || wrong_key_status=$?
lzug_expect_operator_exit 2 "$wrong_key_status"
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

stage="create encrypted full export"
full_export=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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
stage="verify encrypted full export"
verified_export=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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

stage="require explicit restore replacement"
replace_required_status=0
lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
        backup restore --artifact "$backup_artifact" \
        --identity-file "$temporary_directory/backup.agekey" --force \
        >"$temporary_directory/replace-required.json" \
        2>"$temporary_directory/replace-required.stderr" || replace_required_status=$?
lzug_expect_operator_exit 29 "$replace_required_status"
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

stage="restore encrypted backup"
restored=$(
    lzug_operator_cli --endpoint unix:///run/lzug-admin/admin.sock --json \
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

stage="private key non-disclosure"
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
if docker logs "$container" 2>&1 | \
    grep -F -f "$temporary_directory/backup.agekey" >/dev/null; then
    echo "Container logs exposed the private recipient key." >&2
    exit 1
fi

echo "Operator CLI-to-container socket administration, diagnostic, and artifact contracts passed with Docker: $image"
