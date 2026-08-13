#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root_dir/scripts/container-contract.sh"

lzug_select_container_engine
exec "$engine" compose -f "$root_dir/compose.yaml" "$@"
