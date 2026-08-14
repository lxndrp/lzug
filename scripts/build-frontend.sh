#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
metadata="$root_dir/frontend/public/build-metadata.json"
generated=false
if [ ! -f "$metadata" ]; then
    revision=$(git -C "$root_dir" rev-parse HEAD)
    python3 "$root_dir/scripts/build_metadata.py" \
        --revision "$revision" --output "$metadata" >/dev/null
    generated=true
fi
cleanup() {
    if [ "$generated" = true ]; then
        rm -f "$metadata"
    fi
}
trap cleanup EXIT INT TERM

cd "$root_dir/frontend"
configuration=${LZUG_FRONTEND_CONFIGURATION:-production}
case "$configuration" in
    production|demo) ;;
    *) echo "Unsupported frontend configuration: $configuration" >&2; exit 2 ;;
esac
./node_modules/.bin/ng build --configuration "$configuration"
