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

lzug_start_contract_container "$container" "$volume" "$image" \
    --env "LZUG_SMTP_USERNAME=diagnostic-operator" \
    --env "LZUG_SMTP_PASSWORD=diagnostic-secret-marker"
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

echo "Operator CLI-to-container administration and diagnostic contracts passed with $engine: $image"
