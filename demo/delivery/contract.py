"""Command-line interface for the shared demo delivery contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from demo.contract import (
    DemoArtifactPair,
    DemoContractError,
    demo_identity,
    validate_deployment_source,
    validate_manifest,
    validate_manifest_pair,
    validate_public_demo_url,
)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoContractError(f"Could not read demo manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise DemoContractError(f"Demo manifest {path} must be a JSON object")
    return value


def _add_pair_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--seed-image", required=True)
    parser.add_argument("--product-tag", required=True)
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--runtime-contract", required=True)
    parser.add_argument("--schema-fingerprint", required=True)
    parser.add_argument("--seed-revision", required=True)


def _pair_from_args(args: argparse.Namespace) -> DemoArtifactPair:
    pair = DemoArtifactPair(
        app_image=args.app_image,
        seed_image=args.seed_image,
        product_tag=args.product_tag,
        product_commit=args.product_commit,
        runtime_contract=args.runtime_contract,
        schema_fingerprint=args.schema_fingerprint,
        seed_revision=args.seed_revision,
    )
    pair.validate()
    return pair


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    identity = commands.add_parser("identity")
    identity.add_argument("--tag", required=True)
    identity.add_argument("--commit", required=True)
    identity.add_argument("--channel", choices=("release", "snapshot", "stable"))
    identity.add_argument(
        "--field",
        choices=("identity", "oci_tag", "target_version", "tag", "commit", "channel"),
        default="identity",
    )

    url = commands.add_parser("validate-url")
    url.add_argument("--value", required=True)
    url.add_argument("--canonical", action="store_true")

    deployment = commands.add_parser("validate-deployment")
    _add_pair_arguments(deployment)
    deployment.add_argument("--demo-url", required=True)
    deployment.add_argument("--promotion-channel", required=True)
    deployment.add_argument("--operation", required=True)
    deployment.add_argument("--github-ref", required=True)

    pair = commands.add_parser("validate-pair")
    _add_pair_arguments(pair)

    signer = commands.add_parser("signer-workflow")
    _add_pair_arguments(signer)

    manifest = commands.add_parser("manifest-field")
    manifest.add_argument("--manifest", type=Path, required=True)
    manifest.add_argument("--kind", choices=("app", "seed"), required=True)
    manifest.add_argument(
        "--field",
        choices=("runtime_contract", "schema_fingerprint", "seed_revision"),
        required=True,
    )
    manifest.add_argument("--expected-product-tag")
    manifest.add_argument("--expected-product-commit")

    manifests = commands.add_parser("verify-pair-manifests")
    manifests.add_argument("--app-manifest", type=Path, required=True)
    manifests.add_argument("--seed-manifest", type=Path, required=True)
    manifests.add_argument("--expected-product-tag", required=True)
    manifests.add_argument("--expected-product-commit", required=True)
    manifests.add_argument("--expected-runtime-contract", required=True)
    manifests.add_argument("--expected-schema-fingerprint", required=True)
    manifests.add_argument("--expected-seed-revision", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "identity":
            print(getattr(demo_identity(args.tag, args.commit, args.channel), args.field))
        elif args.command == "validate-url":
            print(validate_public_demo_url(args.value, require_canonical=args.canonical))
        elif args.command == "validate-deployment":
            pair = _pair_from_args(args)
            validate_deployment_source(
                promotion_channel=args.promotion_channel,
                operation=args.operation,
                product_tag=pair.product_tag,
                product_commit=pair.product_commit,
                github_ref=args.github_ref,
            )
            validate_public_demo_url(args.demo_url, require_canonical=True)
        elif args.command == "validate-pair":
            _pair_from_args(args)
        elif args.command == "signer-workflow":
            print(_pair_from_args(args).signer_workflow)
        elif args.command == "manifest-field":
            manifest = validate_manifest(_read_manifest(args.manifest), args.kind)
            if (args.expected_product_tag is None) != (args.expected_product_commit is None):
                raise DemoContractError("expected product tag and commit must be provided together")
            if args.expected_product_tag is not None:
                expected = demo_identity(
                    args.expected_product_tag, args.expected_product_commit
                ).product
                if manifest["product"] != expected:
                    raise DemoContractError(
                        f"{args.kind.capitalize()} manifest does not match the expected product"
                    )
            value = (
                manifest["schema"]["fingerprint"]
                if args.field == "schema_fingerprint"
                else manifest[args.field]
            )
            print(value)
        else:
            validate_manifest_pair(
                _read_manifest(args.app_manifest),
                _read_manifest(args.seed_manifest),
                expected_product_tag=args.expected_product_tag,
                expected_product_commit=args.expected_product_commit,
                expected_runtime_contract=args.expected_runtime_contract,
                expected_schema_fingerprint=args.expected_schema_fingerprint,
                expected_seed_revision=args.expected_seed_revision,
            )
    except DemoContractError as error:
        print(f"demo contract rejected: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
