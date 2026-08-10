#!/usr/bin/env sh

set -eu

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
cleanup() {
    "$engine" rm --force "$container" >/dev/null 2>&1 || true
    "$engine" volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

"$engine" volume create "$volume" >/dev/null
"$engine" run --detach --name "$container" \
    --read-only --tmpfs /tmp \
    --publish 127.0.0.1::8000 \
    --mount "type=volume,source=$volume,target=/data" \
    "$image" >/dev/null

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
"$engine" restart "$container" >/dev/null
curl --silent --show-error --fail "$url/api/health" >/dev/null

echo "Container smoke test passed with $engine: $image"
