"""Pure validation contract shared by every demo delivery path."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from demo.identity import STABLE_VERSION, DemoIdentity

MANIFEST_VERSION = 1
RUNTIME_CONTRACT = "lzug-demo-health-ready-v1"
CANONICAL_DEMO_URL = "https://demo.lzug.repertoire.papaspyrou.name"

APP_IMAGE_PATTERN = re.compile(r"^ghcr\.io/lxndrp/lzug-demo-app@sha256:[0-9a-f]{64}$")
SEED_IMAGE_PATTERN = re.compile(r"^ghcr\.io/lxndrp/lzug-demo-seed@sha256:[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

IdentityChannel = Literal["release", "snapshot", "stable"]
ManifestKind = Literal["app", "seed"]


class DemoContractError(ValueError):
    """Signal an invalid demo identity, manifest, pair, URL, or delivery source."""


def canonical_digest(value: Any) -> str:
    """Return the canonical digest used for schema and seed bindings."""

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def demo_identity(tag: str, commit: str, channel: IdentityChannel | None = None) -> DemoIdentity:
    """Build one canonical release or snapshot identity and optionally constrain its channel."""

    try:
        identity = DemoIdentity.create(tag, commit)
    except ValueError as error:
        raise DemoContractError(str(error)) from error
    if channel == "snapshot" and not identity.is_snapshot:
        raise DemoContractError("demo identity must use the snapshot channel")
    if channel in {"release", "stable"} and identity.is_snapshot:
        raise DemoContractError("demo identity must use the release channel")
    if channel == "stable" and STABLE_VERSION.fullmatch(tag) is None:
        raise DemoContractError("demo identity must use a stable SemVer product tag")
    return identity


def validate_public_demo_url(value: str, *, require_canonical: bool = False) -> str:
    """Validate a dedicated HTTPS origin and return its slash-terminated form."""

    parsed = urlsplit(value)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or "*" in value
        or hostname in {"lxndrp.github.io", "stage.papaspyrou.name"}
        or hostname.endswith(".azurecontainerapps.io")
    ):
        raise DemoContractError(
            "demo URL must be a dedicated HTTPS origin without credentials, path, wildcard, "
            "inherited account domain, or Azure platform hostname"
        )
    if require_canonical and value != CANONICAL_DEMO_URL:
        raise DemoContractError("DEMO_URL must be the confirmed repository demo origin")
    return value.rstrip("/") + "/"


def _canonical_product(manifest: dict[str, Any], label: str) -> DemoIdentity:
    product = manifest.get("product")
    if not isinstance(product, dict):
        raise DemoContractError(f"{label} manifest has no product identity")
    tag = product.get("tag")
    commit = product.get("commit")
    if not isinstance(tag, str) or not isinstance(commit, str):
        raise DemoContractError(f"{label} manifest has an invalid product identity")
    identity = demo_identity(tag, commit)
    if product != identity.product:
        raise DemoContractError(f"{label} manifest has a non-canonical product identity")
    return identity


def validate_manifest(manifest: Any, kind: ManifestKind) -> dict[str, Any]:
    """Validate one app or seed manifest without performing file or registry I/O."""

    label = kind.capitalize()
    if not isinstance(manifest, dict):
        raise DemoContractError(f"{label} manifest must be a JSON object")
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise DemoContractError("Unsupported demo manifest version")
    if manifest.get("runtime_contract") != RUNTIME_CONTRACT:
        raise DemoContractError("Unsupported demo runtime contract")
    _canonical_product(manifest, label)
    schema = manifest.get("schema")
    if not isinstance(schema, dict) or not isinstance(schema.get("fingerprint"), str):
        raise DemoContractError(f"{label} manifest has an invalid schema contract")
    if DIGEST_PATTERN.fullmatch(schema["fingerprint"]) is None:
        raise DemoContractError(f"{label} manifest has an invalid schema fingerprint")
    seed_revision = manifest.get("seed_revision")
    if not isinstance(seed_revision, str) or DIGEST_PATTERN.fullmatch(seed_revision) is None:
        raise DemoContractError(f"{label} manifest has an invalid seed revision")
    if kind == "seed":
        binding = {key: value for key, value in manifest.items() if key != "seed_revision"}
        if canonical_digest(binding) != seed_revision:
            raise DemoContractError("Seed revision does not match its manifest")
    return manifest


@dataclass(frozen=True)
class DemoArtifactPair:
    """One immutable app/seed pair passed between publish, deploy, and rollback paths."""

    app_image: str
    seed_image: str
    product_tag: str
    product_commit: str
    runtime_contract: str
    schema_fingerprint: str
    seed_revision: str

    def validate(self) -> None:
        checks = (
            (APP_IMAGE_PATTERN, self.app_image, "app_image"),
            (SEED_IMAGE_PATTERN, self.seed_image, "seed_image"),
            (COMMIT_PATTERN, self.product_commit, "product_commit"),
            (DIGEST_PATTERN, self.schema_fingerprint, "schema_fingerprint"),
            (DIGEST_PATTERN, self.seed_revision, "seed_revision"),
        )
        for pattern, value, label in checks:
            if pattern.fullmatch(value) is None:
                raise DemoContractError(f"Invalid immutable demo pair field: {label}")
        if self.runtime_contract != RUNTIME_CONTRACT:
            raise DemoContractError("Invalid immutable demo pair field: runtime_contract")
        try:
            demo_identity(self.product_tag, self.product_commit)
        except DemoContractError as error:
            raise DemoContractError("Invalid immutable demo pair field: product_tag") from error

    @property
    def identity(self) -> DemoIdentity:
        self.validate()
        return demo_identity(self.product_tag, self.product_commit)

    @property
    def signer_workflow(self) -> str:
        workflow = "demo-snapshot.yml" if self.identity.is_snapshot else "demo-publish.yml"
        return f"lxndrp/lzug/.github/workflows/{workflow}"


def validate_manifest_pair(
    app_manifest: Any,
    seed_manifest: Any,
    *,
    expected_product_tag: str,
    expected_product_commit: str,
    expected_runtime_contract: str,
    expected_schema_fingerprint: str,
    expected_seed_revision: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate both manifests against one explicit immutable pair contract."""

    app = validate_manifest(app_manifest, "app")
    seed = validate_manifest(seed_manifest, "seed")
    expected_product = demo_identity(expected_product_tag, expected_product_commit).product
    if app["product"] != expected_product:
        raise DemoContractError("App manifest does not match the expected product")
    if seed["product"] != expected_product:
        raise DemoContractError("Seed manifest does not match the expected product")
    if expected_runtime_contract != RUNTIME_CONTRACT:
        raise DemoContractError("Expected runtime contract is unsupported")
    for manifest, label in ((app, "App"), (seed, "Seed")):
        if manifest["runtime_contract"] != expected_runtime_contract:
            raise DemoContractError(
                f"{label} manifest does not match the expected runtime contract"
            )
        if manifest["schema"]["fingerprint"] != expected_schema_fingerprint:
            raise DemoContractError(
                f"{label} manifest does not match the expected schema fingerprint"
            )
        if manifest["seed_revision"] != expected_seed_revision:
            raise DemoContractError(f"{label} manifest does not match the expected seed revision")
    return app, seed


def validate_runtime_manifest_pair(
    app_manifest: Any, seed_manifest: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a runtime pair using the app manifest as the explicit expectation."""

    app = validate_manifest(app_manifest, "app")
    return validate_manifest_pair(
        app,
        seed_manifest,
        expected_product_tag=app["product"]["tag"],
        expected_product_commit=app["product"]["commit"],
        expected_runtime_contract=app["runtime_contract"],
        expected_schema_fingerprint=app["schema"]["fingerprint"],
        expected_seed_revision=app["seed_revision"],
    )


def validate_deployment_source(
    *,
    promotion_channel: str,
    operation: str,
    product_tag: str,
    product_commit: str,
    github_ref: str,
) -> DemoIdentity:
    """Validate the source/ref relationship shared by deploy and manual rollback."""

    identity = demo_identity(product_tag, product_commit)
    if promotion_channel == "":
        if operation not in {"deploy", "rollback"} or github_ref != "refs/heads/master":
            raise DemoContractError("manual demo deployment must be dispatched from master")
        return identity
    if promotion_channel == "snapshot":
        if operation != "deploy" or not identity.is_snapshot:
            raise DemoContractError("snapshot promotion requires a snapshot deployment")
        if github_ref != f"refs/tags/{product_tag}":
            raise DemoContractError("snapshot deployment must remain bound to its immutable tag")
        return identity
    if promotion_channel == "stable":
        demo_identity(product_tag, product_commit, "stable")
        if operation != "deploy" or github_ref != "refs/heads/master":
            raise DemoContractError(
                "stable demo promotion must be called from the release workflow on master"
            )
        return identity
    raise DemoContractError("unsupported demo deployment operation or source channel")


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
