"""Build and verify the content-addressed seed contract for disposable runtimes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from backend.build_metadata import BuildMetadata

MANIFEST_VERSION = 1
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
    "status_changed_at",
    "updated_at",
}


class DemoArtifactError(ValueError):
    """Signal an invalid or incompatible demo artifact."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    with sqlite3.connect(database) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for column in sorted(columns & TIMESTAMP_COLUMNS):
                connection.execute(
                    f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" IS NOT NULL',
                    (FIXED_TIMESTAMP,),
                )
        connection.commit()
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("VACUUM")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise DemoArtifactError(f"Seed integrity check failed: {integrity!r}")


def _validate_synthetic_content(database: Path) -> None:
    checks = {
        "person names": (
            "SELECT COUNT(*) FROM person WHERE first_name != 'Testperson'",
            0,
        ),
        "person e-mail addresses": (
            "SELECT COUNT(*) FROM person WHERE email NOT LIKE '%@example.invalid'",
            0,
        ),
        "candidate names": (
            "SELECT COUNT(*) FROM candidate WHERE first_name != 'Prüfling'",
            0,
        ),
        "candidate numbers": (
            "SELECT COUNT(*) FROM candidate WHERE ihk_exam_number NOT LIKE 'TEST-%'",
            0,
        ),
        "demo roles": (
            "SELECT COUNT(*) FROM user_account WHERE person_id IN (1, 3) AND is_active = 1",
            2,
        ),
    }
    with sqlite3.connect(database) as connection:
        for label, (query, expected) in checks.items():
            actual = connection.execute(query).fetchone()[0]
            if actual != expected:
                raise DemoArtifactError(
                    f"Synthetic seed check failed for {label}: expected {expected}, got {actual}"
                )


def build_seed(
    source_root: Path,
    database: Path,
    manifest_path: Path,
    *,
    product_tag: str,
    product_commit: str,
) -> dict[str, Any]:
    from backend.database import database_readiness, initialize

    if not product_tag or not product_commit:
        raise DemoArtifactError("Product tag and commit are required")
    BuildMetadata.create(product_commit, product_tag)
    database.parent.mkdir(parents=True, exist_ok=True)
    initialize(database, with_seed=True, reset=True, backup_dir=database.parent / "backups")
    _normalize_timestamps(database)
    _validate_synthetic_content(database)
    readiness = database_readiness(database)
    if not readiness["ready"]:
        raise DemoArtifactError(f"Prepared seed is not ready: {readiness['reason']}")

    schema = schema_binding(source_root)
    binding = {
        "manifest_version": MANIFEST_VERSION,
        "product": {"tag": product_tag, "commit": product_commit},
        "schema": schema,
        "fixture_sha256": sha256_file(source_root / "fixtures/synthetic-fixtures.json"),
        "generator_sha256": sha256_file(source_root / "scripts/generate_synthetic_fixtures.py"),
        "seed_sql_sha256": sha256_file(source_root / "db/seed_demo.sql"),
        "init_logic_sha256": sha256_file(source_root / "demo/artifacts.py"),
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
) -> dict[str, Any]:
    metadata = BuildMetadata.create(product_commit, product_tag)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "product": {
            "tag": product_tag,
            "version": metadata.identity,
            "commit": product_commit,
        },
        "schema": schema_binding(source_root),
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
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise DemoArtifactError("Unsupported demo manifest version")
    return manifest


def initialize_workdir(seed_database: Path, seed_manifest: Path, target: Path) -> None:
    manifest = load_manifest(seed_manifest)
    if sha256_file(seed_database) != manifest.get("snapshot_sha256"):
        raise DemoArtifactError("Seed snapshot digest does not match its manifest")
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


def validate_runtime_binding(app_manifest_path: Path, data_dir: Path) -> tuple[dict, dict]:
    from backend.database import database_readiness

    app_manifest = load_manifest(app_manifest_path)
    seed_manifest = load_manifest(data_dir / "demo-seed-manifest.json")
    if app_manifest["product"]["tag"] != seed_manifest.get("product", {}).get("tag"):
        raise DemoArtifactError("Demo app and seed target different product tags")
    if app_manifest["product"]["commit"] != seed_manifest.get("product", {}).get("commit"):
        raise DemoArtifactError("Demo app and seed target different product commits")
    if app_manifest["schema"]["fingerprint"] != seed_manifest.get("schema", {}).get("fingerprint"):
        raise DemoArtifactError("Demo app and seed target different schema fingerprints")
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

    app = subparsers.add_parser("build-app-manifest")
    app.add_argument("--source-root", type=Path, default=Path("."))
    app.add_argument("--output", type=Path, required=True)
    app.add_argument("--product-tag", required=True)
    app.add_argument("--product-commit", required=True)

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
    elif args.command == "build-app-manifest":
        build_app_manifest(
            args.source_root,
            args.output,
            product_tag=args.product_tag,
            product_commit=args.product_commit,
        )
    else:
        initialize_workdir(args.seed_database, args.seed_manifest, args.target)


if __name__ == "__main__":
    main()
