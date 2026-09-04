#!/usr/bin/env sh

set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
metadata="$root_dir/frontend/public/build-metadata.json"
generated=false
brand_public_dir="$root_dir/frontend/public/brand"
brand_public_dir_created=false
favicon_staged=false
favicon_ico_staged=false
logo_mark_staged=false
brand_assets="favicon.svg logo-mark-dark.svg"
favicon_asset="favicon.ico"
if [ ! -f "$metadata" ]; then
    revision=$(git -C "$root_dir" rev-parse HEAD)
    python3 "$root_dir/scripts/build_metadata.py" \
        --revision "$revision" --output "$metadata" >/dev/null
    generated=true
fi
cleanup() {
    if [ "$favicon_staged" = true ]; then
        /bin/rm -f "$brand_public_dir/favicon.svg"
    fi
    if [ "$logo_mark_staged" = true ]; then
        /bin/rm -f "$brand_public_dir/logo-mark-dark.svg"
    fi
    if [ "$favicon_ico_staged" = true ]; then
        /bin/rm -f "$root_dir/frontend/public/$favicon_asset"
    fi
    if [ "$brand_public_dir_created" = true ]; then
        rmdir "$brand_public_dir"
    fi
    if [ "$generated" = true ]; then
        /bin/rm -f "$metadata"
    fi
}
trap cleanup EXIT INT TERM

if [ ! -d "$brand_public_dir" ]; then
    brand_public_dir_created=true
fi
mkdir -p "$brand_public_dir"
for asset in $brand_assets; do
    if [ ! -f "$brand_public_dir/$asset" ]; then
        cp "$root_dir/brand/derived/$asset" "$brand_public_dir/$asset"
        if [ "$asset" = favicon.svg ]; then
            favicon_staged=true
        else
            logo_mark_staged=true
        fi
    fi
done
if [ ! -f "$root_dir/frontend/public/$favicon_asset" ]; then
    cp "$root_dir/brand/derived/$favicon_asset" "$root_dir/frontend/public/$favicon_asset"
    favicon_ico_staged=true
fi

cd "$root_dir/frontend"
configuration=${LZUG_FRONTEND_CONFIGURATION:-production}
case "$configuration" in
    production|demo) ;;
    *) echo "Unsupported frontend configuration: $configuration" >&2; exit 2 ;;
esac
./node_modules/.bin/ng build --configuration "$configuration"
