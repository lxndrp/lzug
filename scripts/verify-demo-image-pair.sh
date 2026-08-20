#!/usr/bin/env sh

set -eu

if [ "$#" -ne 7 ]; then
    echo "usage: $0 APP_IMAGE SEED_IMAGE PRODUCT_TAG PRODUCT_COMMIT RUNTIME_CONTRACT SCHEMA_FINGERPRINT SEED_REVISION" >&2
    exit 2
fi

app_image=$1
seed_image=$2
product_tag=$3
product_commit=$4
runtime_contract=$5
schema_fingerprint=$6
seed_revision=$7
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/lzug-demo-pair.XXXXXX")
app_container=""
seed_container=""

cleanup() {
    if [ -n "$app_container" ]; then
        docker rm --force "$app_container" >/dev/null 2>&1 || true
    fi
    if [ -n "$seed_container" ]; then
        docker rm --force "$seed_container" >/dev/null 2>&1 || true
    fi
    rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

docker pull "$app_image" >/dev/null
docker pull "$seed_image" >/dev/null
app_container=$(docker create "$app_image")
seed_container=$(docker create "$seed_image")
docker cp "$app_container:/app/demo-app-manifest.json" "$temporary_directory/app.json"
docker cp "$seed_container:/opt/lzug-demo/seed/manifest.json" "$temporary_directory/seed.json"

python3 -m demo.artifacts verify-pair-manifests \
    --app-manifest "$temporary_directory/app.json" \
    --seed-manifest "$temporary_directory/seed.json" \
    --expected-product-tag "$product_tag" \
    --expected-product-commit "$product_commit" \
    --expected-runtime-contract "$runtime_contract" \
    --expected-schema-fingerprint "$schema_fingerprint" \
    --expected-seed-revision "$seed_revision"
