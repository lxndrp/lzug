"""Build and verify the content-addressed seed contract for disposable runtimes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from demo.contract import (
    DIGEST_PATTERN,
    MANIFEST_VERSION,
    RUNTIME_CONTRACT,
    DemoContractError,
    canonical_digest,
    demo_identity,
    validate_manifest,
    validate_manifest_pair,
    validate_runtime_manifest_pair,
)
from demo.identity import DemoIdentity

FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"
TIMESTAMP_COLUMNS = {
    "actual_completed_at",
    "actual_started_at",
    "applied_at",
    "assigned_at",
    "consumed_at",
    "created_at",
    "expires_at",
    "last_login_at",
    "last_seen_at",
    "reported_at",
    "responded_at",
    "revoked_at",
    "decided_at",
    "opened_at",
    "completed_at",
    "generated_at",
    "superseded_at",
    "terminal_at",
    "status_changed_at",
    "updated_at",
}


class DemoArtifactError(ValueError):
    """Signal an invalid or incompatible demo artifact."""


def _artifact_identity(product_tag: str, product_commit: str) -> DemoIdentity:
    try:
        return demo_identity(product_tag, product_commit)
    except DemoContractError as error:
        raise DemoArtifactError(str(error)) from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_binding(source_root: Path) -> dict[str, Any]:
    paths = [
        source_root / "db" / "schema.sql",
        *sorted((source_root / "db/migrations").glob("*.sql")),
    ]
    files = [
        {"path": path.relative_to(source_root).as_posix(), "sha256": sha256_file(path)}
        for path in paths
    ]
    return {"fingerprint": canonical_digest(files), "files": files}


def _normalize_timestamps(database: Path) -> None:
    with closing(sqlite3.connect(database)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            if table == "exam_round_decision":
                continue
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for column in sorted(columns & TIMESTAMP_COLUMNS):
                connection.execute(
                    f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" IS NOT NULL',
                    (FIXED_TIMESTAMP,),
                )
        if "instance_metadata" in tables:
            connection.execute(
                "UPDATE instance_metadata SET instance_id = ? WHERE id = 1",
                ("00000000-0000-4000-a000-000000000001",),
            )
        connection.commit()

    # Changing a SQLite journal mode needs an exclusive lock.  Keep it in a
    # separate connection after all timestamp updates have committed and closed.
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("VACUUM")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise DemoArtifactError(f"Seed integrity check failed: {integrity!r}")


def _validate_synthetic_content(database: Path, runtime_profile: dict[str, Any]) -> None:
    demo_account_ids = ", ".join(
        str(role["account_id"]) for role in runtime_profile.get("roles", {}).values()
    )
    checks = {
        "person names": (
            "SELECT COUNT(*) FROM person WHERE trim(first_name) = '' OR trim(last_name) = ''",
            0,
        ),
        "person e-mail addresses": (
            "SELECT COUNT(*) FROM person WHERE email NOT LIKE '%@demo.lzug.invalid'",
            0,
        ),
        "person phone numbers": (
            "SELECT COUNT(*) FROM person WHERE mobile IS NOT NULL",
            0,
        ),
        "candidate names": (
            "SELECT COUNT(*) FROM candidate WHERE trim(first_name) = '' OR trim(last_name) = ''",
            0,
        ),
        "candidate numbers": (
            "SELECT COUNT(*) FROM candidate WHERE ihk_exam_number NOT LIKE 'ATHEN-DEMO-%'",
            0,
        ),
        "canonical demo roles": (
            f"SELECT COUNT(*) FROM user_account WHERE id IN ({demo_account_ids}) AND is_active = 1",
            3,
        ),
        "fictional organizations": (
            "SELECT COUNT(*) FROM committee "
            "WHERE ihk NOT LIKE 'Industrie- und Handelskammer % (Demo)'",
            0,
        ),
    }
    with closing(sqlite3.connect(database)) as connection:
        for label, (query, expected) in checks.items():
            actual = connection.execute(query).fetchone()[0]
            if actual != expected:
                raise DemoArtifactError(
                    f"Synthetic seed check failed for {label}: expected {expected}, got {actual}"
                )

        connection.commit()


def build_seed(
    source_root: Path,
    database: Path,
    manifest_path: Path,
    *,
    product_tag: str,
    product_commit: str,
) -> dict[str, Any]:
    from backend.database import database_readiness, initialize
    from fixtures.generate import load_source, render_profile_sql, runtime_profile

    fixture_data = load_source()
    fixture_runtime = runtime_profile(fixture_data, "public-demo")
    fixture_catalog = {
        "version": fixture_data["version"],
        "revision": fixture_data["revision"],
        "demo_matrix_version": fixture_data["demo_matrix_version"],
    }
    profile = fixture_data["profiles"]["public-demo"]
    seed_sql = render_profile_sql(fixture_data, "public-demo")

    if not product_tag or not product_commit:
        raise DemoArtifactError("Product tag and commit are required")
    identity = _artifact_identity(product_tag, product_commit)
    database.parent.mkdir(parents=True, exist_ok=True)
    initialize(
        database,
        seed_sql=seed_sql,
        reset=True,
        backup_dir=database.parent / "backups",
        migration_backup_name="demo-seed.migration-safety.sqlite",
        migration_timestamp=FIXED_TIMESTAMP,
    )
    _normalize_timestamps(database)
    _validate_synthetic_content(database, fixture_runtime)
    readiness = database_readiness(database)
    if not readiness["ready"]:
        raise DemoArtifactError(f"Prepared seed is not ready: {readiness['reason']}")

    schema = schema_binding(source_root)
    binding = {
        "manifest_version": MANIFEST_VERSION,
        "product": identity.product,
        "runtime_contract": RUNTIME_CONTRACT,
        "schema": schema,
        "fixture_catalog": {
            **fixture_catalog,
        },
        "fixture_profile": {
            "name": "public-demo",
            "reference_time": profile["reference_time"],
            "scenarios": profile["scenarios"],
            **fixture_runtime,
        },
        "fixture_sha256": sha256_file(source_root / "fixtures/synthetic-fixtures.json"),
        "generator_sha256": sha256_file(source_root / "fixtures/generate.py"),
        "seed_sql_sha256": hashlib.sha256(seed_sql.encode("utf-8")).hexdigest(),
        "snapshot_sha256": sha256_file(database),
        "reset": {"time": "03:00", "timezone": "Europe/Berlin"},
    }
    manifest = {**binding, "seed_revision": canonical_digest(binding)}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_app_manifest(
    source_root: Path,
    output: Path,
    *,
    product_tag: str,
    product_commit: str,
    seed_revision: str,
) -> dict[str, Any]:
    if DIGEST_PATTERN.fullmatch(seed_revision) is None:
        raise DemoArtifactError("App manifest requires a canonical seed revision")
    identity = _artifact_identity(product_tag, product_commit)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "product": identity.product,
        "runtime_contract": RUNTIME_CONTRACT,
        "schema": schema_binding(source_root),
        "seed_revision": seed_revision,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoArtifactError(f"Could not read demo manifest {path}: {error}") from error
    try:
        return validate_manifest(manifest, "app")
    except DemoContractError as error:
        raise DemoArtifactError(str(error)) from error


def load_runtime_manifests(
    app_manifest_path: Path, seed_manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate one runtime-bound app/seed manifest pair."""

    app_manifest = load_manifest(app_manifest_path)
    seed_manifest = load_manifest(seed_manifest_path)
    _validate_fixture_contract(seed_manifest)
    try:
        return validate_runtime_manifest_pair(app_manifest, seed_manifest)
    except DemoContractError as error:
        message = str(error)
        replacements = {
            "Seed manifest does not match the expected product": (
                "Demo app and seed target different product identities"
            ),
            "Seed manifest does not match the expected runtime contract": (
                "Demo app and seed target different runtime contracts"
            ),
            "Seed manifest does not match the expected schema fingerprint": (
                "Demo app and seed target different schema fingerprints"
            ),
            "Seed manifest does not match the expected seed revision": (
                "Demo app and seed target different seed revisions"
            ),
        }
        raise DemoArtifactError(replacements.get(message, message)) from error


def _validate_fixture_contract(manifest: dict[str, Any]) -> None:
    catalog = manifest.get("fixture_catalog")
    if (
        not isinstance(catalog, dict)
        or not isinstance(catalog.get("version"), int)
        or not isinstance(catalog.get("revision"), str)
        or not isinstance(catalog.get("demo_matrix_version"), str)
    ):
        raise DemoArtifactError("Seed fixture catalog is incomplete")
    profile = manifest.get("fixture_profile")
    if not isinstance(profile, dict) or profile.get("name") != "public-demo":
        raise DemoArtifactError("Seed fixture profile is not public-demo")
    if profile.get("demo_matrix_version") != catalog["demo_matrix_version"]:
        raise DemoArtifactError("Seed fixture catalog does not match the demo matrix")


def _validate_seed_manifest(manifest: dict[str, Any]) -> None:
    try:
        validate_manifest(manifest, "seed")
    except DemoContractError as error:
        raise DemoArtifactError(str(error)) from error
    _validate_fixture_contract(manifest)


def verify_seed(
    database: Path,
    manifest_path: Path,
    *,
    expected_manifest_path: Path | None = None,
    expected_revision: str | None = None,
    expected_product_tag: str | None = None,
    expected_product_commit: str | None = None,
    expected_schema_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Verify a prepared seed and its optional publish-time expectations."""
    manifest = load_manifest(manifest_path)
    _validate_seed_manifest(manifest)
    if sha256_file(database) != manifest.get("snapshot_sha256"):
        raise DemoArtifactError("Seed snapshot digest does not match its manifest")
    if expected_manifest_path is not None:
        expected_manifest = load_manifest(expected_manifest_path)
        _validate_seed_manifest(expected_manifest)
        if manifest_path.read_bytes() != expected_manifest_path.read_bytes():
            raise DemoArtifactError("Seed manifest does not match the expected manifest")
    if expected_revision is not None and manifest["seed_revision"] != expected_revision:
        raise DemoArtifactError("Seed revision does not match the expected revision")
    product = manifest["product"]
    if expected_product_tag is not None and expected_product_commit is not None:
        try:
            expected_product = demo_identity(expected_product_tag, expected_product_commit).product
        except DemoContractError as error:
            raise DemoArtifactError(str(error)) from error
        if product != expected_product:
            raise DemoArtifactError("Seed manifest does not match the expected product")
    else:
        if expected_product_tag is not None and product["tag"] != expected_product_tag:
            raise DemoArtifactError("Seed manifest does not match the expected product tag")
        if expected_product_commit is not None and product["commit"] != expected_product_commit:
            raise DemoArtifactError("Seed manifest does not match the expected product commit")
    if (
        expected_schema_fingerprint is not None
        and manifest.get("schema", {}).get("fingerprint") != expected_schema_fingerprint
    ):
        raise DemoArtifactError("Seed manifest does not match the expected schema fingerprint")
    return manifest


def verify_pair_manifests(
    app_manifest_path: Path,
    seed_manifest_path: Path,
    *,
    expected_product_tag: str,
    expected_product_commit: str,
    expected_runtime_contract: str,
    expected_schema_fingerprint: str,
    expected_seed_revision: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify the digest-bound app/seed metadata before any Azure mutation."""
    try:
        return validate_manifest_pair(
            load_manifest(app_manifest_path),
            load_manifest(seed_manifest_path),
            expected_product_tag=expected_product_tag,
            expected_product_commit=expected_product_commit,
            expected_runtime_contract=expected_runtime_contract,
            expected_schema_fingerprint=expected_schema_fingerprint,
            expected_seed_revision=expected_seed_revision,
        )
    except DemoContractError as error:
        raise DemoArtifactError(str(error)) from error


def initialize_workdir(seed_database: Path, seed_manifest: Path, target: Path) -> None:
    manifest = verify_seed(seed_database, seed_manifest)
    resolved = target.resolve()
    if resolved == Path("/") or len(resolved.parts) < 2:
        raise DemoArtifactError(f"Unsafe demo data target: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    for child in resolved.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    temporary = resolved / ".lzug-demo-seed.sqlite"
    shutil.copyfile(seed_database, temporary)
    temporary.replace(resolved / "lzug.sqlite")
    shutil.copyfile(seed_manifest, resolved / "demo-seed-manifest.json")
    (resolved / "documents").mkdir()
    (resolved / "backups").mkdir()
    initialized_at = datetime.now(UTC).isoformat()
    runtime_status = {
        "initialized": True,
        "initialization_status": "ready",
        "initialized_at": initialized_at,
        "last_reset_at": initialized_at,
        "seed_revision": manifest["seed_revision"],
    }
    temporary_status = resolved / ".demo-runtime-status.json"
    temporary_status.write_text(
        json.dumps(runtime_status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_status.replace(resolved / "demo-runtime-status.json")


def load_runtime_status(data_dir: Path, seed_manifest: dict[str, Any]) -> dict[str, Any]:
    status_path = data_dir / "demo-runtime-status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoArtifactError(
            f"Could not read demo runtime status {status_path}: {error}"
        ) from error
    if status.get("initialized") is not True or status.get("initialization_status") != "ready":
        raise DemoArtifactError("Demo runtime initialization is not ready")
    if status.get("seed_revision") != seed_manifest.get("seed_revision"):
        raise DemoArtifactError("Demo runtime status targets a different seed revision")
    for field in ("initialized_at", "last_reset_at"):
        value = status.get(field)
        if not isinstance(value, str):
            raise DemoArtifactError(f"Demo runtime status is missing {field}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise DemoArtifactError(f"Demo runtime status has invalid {field}") from error
        if parsed.tzinfo is None:
            raise DemoArtifactError(f"Demo runtime status {field} must include a timezone")
    return status


def validate_runtime_binding(app_manifest_path: Path, data_dir: Path) -> tuple[dict, dict]:
    from backend.database import database_readiness

    app_manifest, seed_manifest = load_runtime_manifests(
        app_manifest_path, data_dir / "demo-seed-manifest.json"
    )
    load_runtime_status(data_dir, seed_manifest)
    database = data_dir / "lzug.sqlite"
    readiness = database_readiness(database)
    if not readiness["ready"]:
        raise DemoArtifactError(f"Demo database is not ready: {readiness['reason']}")
    return app_manifest, seed_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("build-seed")
    seed.add_argument("--source-root", type=Path, default=Path("."))
    seed.add_argument("--database", type=Path, required=True)
    seed.add_argument("--manifest", type=Path, required=True)
    seed.add_argument("--product-tag", required=True)
    seed.add_argument("--product-commit", required=True)

    verify = subparsers.add_parser("verify-seed")
    verify.add_argument("--database", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--expected-manifest", type=Path)
    verify.add_argument("--expected-revision")
    verify.add_argument("--expected-product-tag")
    verify.add_argument("--expected-product-commit")
    verify.add_argument("--expected-schema-fingerprint")

    app = subparsers.add_parser("build-app-manifest")
    app.add_argument("--source-root", type=Path, default=Path("."))
    app.add_argument("--output", type=Path, required=True)
    app.add_argument("--product-tag", required=True)
    app.add_argument("--product-commit", required=True)
    app.add_argument("--seed-revision", required=True)

    pair = subparsers.add_parser("verify-pair-manifests")
    pair.add_argument("--app-manifest", type=Path, required=True)
    pair.add_argument("--seed-manifest", type=Path, required=True)
    pair.add_argument("--expected-product-tag", required=True)
    pair.add_argument("--expected-product-commit", required=True)
    pair.add_argument("--expected-runtime-contract", required=True)
    pair.add_argument("--expected-schema-fingerprint", required=True)
    pair.add_argument("--expected-seed-revision", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--seed-database", type=Path, required=True)
    init.add_argument("--seed-manifest", type=Path, required=True)
    init.add_argument("--target", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build-seed":
        build_seed(
            args.source_root,
            args.database,
            args.manifest,
            product_tag=args.product_tag,
            product_commit=args.product_commit,
        )
    elif args.command == "verify-seed":
        verify_seed(
            args.database,
            args.manifest,
            expected_manifest_path=args.expected_manifest,
            expected_revision=args.expected_revision,
            expected_product_tag=args.expected_product_tag,
            expected_product_commit=args.expected_product_commit,
            expected_schema_fingerprint=args.expected_schema_fingerprint,
        )
    elif args.command == "build-app-manifest":
        build_app_manifest(
            args.source_root,
            args.output,
            product_tag=args.product_tag,
            product_commit=args.product_commit,
            seed_revision=args.seed_revision,
        )
    elif args.command == "verify-pair-manifests":
        verify_pair_manifests(
            args.app_manifest,
            args.seed_manifest,
            expected_product_tag=args.expected_product_tag,
            expected_product_commit=args.expected_product_commit,
            expected_runtime_contract=args.expected_runtime_contract,
            expected_schema_fingerprint=args.expected_schema_fingerprint,
            expected_seed_revision=args.expected_seed_revision,
        )
    else:
        initialize_workdir(args.seed_database, args.seed_manifest, args.target)


if __name__ == "__main__":
    main()
