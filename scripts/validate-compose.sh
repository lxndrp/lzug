#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config_file=$(mktemp "${TMPDIR:-/tmp}/lzug-compose-config.XXXXXX")
trap 'rm -f "$config_file"' EXIT HUP INT TERM

if ! "$root_dir/scripts/compose-command.sh" config --format json >"$config_file"; then
    echo "Compose could not render the configuration for the lzug policy." >&2
    exit 1
fi
python3 "$root_dir/scripts/compose_policy.py" "$config_file"
