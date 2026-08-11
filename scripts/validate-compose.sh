#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$root_dir/compose.yaml"
engine=${CONTAINER_ENGINE:-}

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

case "$engine" in
    docker)
        compose_command="$engine compose"
        ;;
    podman)
        compose_command="$engine compose"
        ;;
    *)
        echo "CONTAINER_ENGINE must be docker or podman." >&2
        exit 2
        ;;
esac

image=${LZUG_IMAGE:-}
if [ -z "$image" ]; then
    echo "LZUG_IMAGE is required; set a published immutable image or a local test image." >&2
    exit 2
fi
case "$image" in
    *:latest|*/latest|latest|*REPLACE*|*'<'*|*'>'*)
        echo "LZUG_IMAGE must not use latest or a placeholder: $image" >&2
        exit 2
        ;;
esac
semver_pattern=':(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'
if ! printf '%s\n' "$image" | grep -Eq "(@sha256:[0-9a-fA-F]{64}|$semver_pattern)"; then
    echo "LZUG_IMAGE must end in an immutable SemVer tag or sha256 digest: $image" >&2
    exit 2
fi

config_file=$(mktemp "${TMPDIR:-/tmp}/lzug-compose-config.XXXXXX")
trap 'rm -f "$config_file"' EXIT HUP INT TERM

if ! env LZUG_IMAGE="$image" $compose_command -f "$compose_file" config --format json >"$config_file"; then
    echo "Compose configuration is invalid." >&2
    exit 1
fi

python3 - "$config_file" <<'PY'
import json
import sys

path = sys.argv[1]
model = json.loads(open(path, encoding="utf-8").read())
service = model["services"]["lzug"]

assert service["image"]
assert service["user"] == "10001:10001"
assert service["read_only"] is True
assert service["restart"] == "unless-stopped"
assert "ALL" in service["cap_drop"]
assert "no-new-privileges:true" in service["security_opt"]
assert any(volume.get("target") == "/data" for volume in service["volumes"])
assert service["healthcheck"]["test"][-3:] == ["python", "-m", "backend.healthcheck"]
assert service.get("privileged", False) is False
assert all("docker.sock" not in str(volume) for volume in service["volumes"])
environment = service["environment"]
assert environment["LZUG_HTTPS_ONLY"] == "true"
assert environment["LZUG_CORS_ALLOWED_ORIGINS"] in {"", None}
assert environment["LZUG_SESSION_TTL_SECONDS"] == "28800"
assert environment["LZUG_MAX_REQUEST_BYTES"] == "1048576"
assert environment["LZUG_AUTH_RATE_LIMIT"] == "20"
assert environment["LZUG_AUTH_RATE_WINDOW_SECONDS"] == "60"
assert environment["LZUG_MAX_UPLOAD_BYTES"] == "10485760"
assert environment["LZUG_ALLOWED_UPLOAD_MEDIA_TYPES"] == "application/pdf,image/jpeg,image/png,text/plain"
for port in service["ports"]:
    if isinstance(port, dict):
        assert port["host_ip"] in {"127.0.0.1", "::1"}
    else:
        assert port.startswith("127.0.0.1:") or port.startswith("::1:")
print("Compose configuration is valid and hardened.")
PY

if env -u LZUG_IMAGE $compose_command -f "$compose_file" config --quiet >/dev/null 2>&1; then
    echo "Missing LZUG_IMAGE was accepted unexpectedly." >&2
    exit 1
fi

if LZUG_IMAGE=ghcr.io/lxndrp/lzug:latest "$0" >/dev/null 2>&1; then
    echo "Mutable latest image was accepted unexpectedly." >&2
    exit 1
fi

echo "Compose negative checks passed: image is required and mutable tags are rejected."
