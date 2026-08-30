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
        cd "$root_dir"
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

recipient_keys=$("$engine" run --rm --entrypoint python "$image" -c '
import json
from backend.backup_restore import generate_recipient_keypair

public_key, private_key = generate_recipient_keypair()
_, wrong_private_key = generate_recipient_keypair()
print(json.dumps({
    "public": public_key,
    "private": private_key,
    "wrong_private": wrong_private_key,
}))
')
recipient_public_key=$(printf '%s' "$recipient_keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["public"])')
recipient_private_key=$(printf '%s' "$recipient_keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["private"])')
wrong_private_key=$(printf '%s' "$recipient_keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["wrong_private"])')

"$engine" volume create "$volume" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --env "LZUG_BACKUP_RECIPIENT_PUBLIC_KEY=$recipient_public_key" \
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

committee=$(
    "$admin_binary" --engine "$engine" --container "$container" \
        committee-bootstrap \
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
assert payload["version"] == 1 and payload["ok"] is True
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
        "$admin_binary" --engine "$engine" --container "$container" "$diagnostic"
    )
    printf '%s' "$diagnostic_output" | python3 -c '
import json
import sys

command, invitation_token = sys.argv[1:]
payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
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

backup=$(
    "$admin_binary" --engine "$engine" --container "$container" backup-create
)
backup_artifact=$(printf '%s' "$backup" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
result = payload["result"]
assert result["artifact_type"] == "backup"
assert result["artifact_id"] and result["snapshot_at"]
print(result["artifact"])
')

verified_backup=$(
    printf '%s' "$recipient_private_key" | \
        "$admin_binary" --engine "$engine" --container "$container" \
            artifact-verify --artifact "$backup_artifact"
)
printf '%s' "$verified_backup" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
assert payload["result"]["artifact_type"] == "backup"
assert payload["result"]["documents"] >= 0
' >/dev/null

wrong_key_status=0
printf '%s' "$wrong_private_key" | \
    "$admin_binary" --engine "$engine" --container "$container" \
        artifact-verify --artifact "$backup_artifact" \
        >"$temporary_directory/wrong-key.json" \
        2>"$temporary_directory/wrong-key.stderr" || wrong_key_status=$?
test "$wrong_key_status" -eq 27
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["version"] == 1 and payload["ok"] is False
assert payload["error"]["class"] == "recipient_key_mismatch"
assert payload["error"]["phase"] == "precheck"
' "$temporary_directory/wrong-key.json"

full_export=$(
    "$admin_binary" --engine "$engine" --container "$container" \
        full-export --recipient-public-key "$recipient_public_key"
)
export_artifact=$(printf '%s' "$full_export" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
result = payload["result"]
assert result["artifact_type"] == "full_export"
assert result["artifact_id"] and result["snapshot_at"]
print(result["artifact"])
')
verified_export=$(
    printf '%s' "$recipient_private_key" | \
        "$admin_binary" --engine "$engine" --container "$container" \
            artifact-verify --artifact "$export_artifact"
)
printf '%s' "$verified_export" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
assert payload["result"]["artifact_type"] == "full_export"
' >/dev/null

replace_required_status=0
printf '%s' "$recipient_private_key" | \
    "$admin_binary" --engine "$engine" --container "$container" \
        backup-restore --artifact "$backup_artifact" \
        >"$temporary_directory/replace-required.json" \
        2>"$temporary_directory/replace-required.stderr" || replace_required_status=$?
test "$replace_required_status" -eq 29
python3 -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
assert payload["version"] == 1 and payload["ok"] is False
assert payload["error"]["class"] == "replace_confirmation_required"
assert payload["error"]["phase"] == "precheck"
' "$temporary_directory/replace-required.json"

restored=$(
    printf '%s' "$recipient_private_key" | \
        "$admin_binary" --engine "$engine" --container "$container" \
            backup-restore --artifact "$backup_artifact" --replace
)
printf '%s' "$restored" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["version"] == 1 and payload["ok"] is True
result = payload["result"]
assert result["artifact_type"] == "backup"
assert result["safety_artifact"].startswith("pre-restore-")
assert result["phases"] == [
    "precheck", "prepared_restore", "migration", "postcheck", "activation"
]
assert result["readiness"] in {"ready", "restricted", "not_ready"}
' >/dev/null

if printf '%s\n%s\n%s\n%s\n' \
    "$backup" "$verified_backup" "$full_export" "$restored" | \
    grep -F "$recipient_private_key" >/dev/null; then
    echo "Artifact command output exposed the private recipient key." >&2
    exit 1
fi
if grep -F "$recipient_private_key" \
    "$temporary_directory/wrong-key.json" \
    "$temporary_directory/wrong-key.stderr" \
    "$temporary_directory/replace-required.json" \
    "$temporary_directory/replace-required.stderr" >/dev/null; then
    echo "Artifact command error output exposed the private recipient key." >&2
    exit 1
fi
if "$engine" logs "$container" 2>&1 | grep -F "$recipient_private_key" >/dev/null; then
    echo "Container logs exposed the private recipient key." >&2
    exit 1
fi

echo "Operator CLI-to-container administration, diagnostic, and artifact contracts passed with $engine: $image"
