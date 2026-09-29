"""Validate the manifests and initialized state required by the demo runtime."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from demo.contract import (
    DemoContractError,
    ManifestKind,
    validate_manifest,
    validate_runtime_manifest_pair,
)


class DemoRuntimeError(ValueError):
    """Signal an invalid or incomplete demo runtime assembly."""


def load_manifest(path: Path, kind: ManifestKind) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoRuntimeError(f"Could not read demo manifest {path}: {error}") from error
    try:
        return validate_manifest(manifest, kind)
    except DemoContractError as error:
        raise DemoRuntimeError(str(error)) from error


def validate_fixture_contract(manifest: dict[str, Any]) -> None:
    catalog = manifest.get("fixture_catalog")
    if (
        not isinstance(catalog, dict)
        or not isinstance(catalog.get("version"), int)
        or not isinstance(catalog.get("revision"), str)
        or not isinstance(catalog.get("demo_matrix_version"), str)
    ):
        raise DemoRuntimeError("Seed fixture catalog is incomplete")
    profile = manifest.get("fixture_profile")
    if not isinstance(profile, dict) or profile.get("name") != "public-demo":
        raise DemoRuntimeError("Seed fixture profile is not public-demo")
    if profile.get("demo_matrix_version") != catalog["demo_matrix_version"]:
        raise DemoRuntimeError("Seed fixture catalog does not match the demo matrix")


def load_runtime_manifests(
    app_manifest_path: Path, seed_manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate one runtime-bound app/seed manifest pair."""

    app_manifest = load_manifest(app_manifest_path, "app")
    seed_manifest = load_manifest(seed_manifest_path, "seed")
    validate_fixture_contract(seed_manifest)
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
        raise DemoRuntimeError(replacements.get(message, message)) from error


def load_runtime_status(data_dir: Path, seed_manifest: dict[str, Any]) -> dict[str, Any]:
    status_path = data_dir / "demo-runtime-status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoRuntimeError(
            f"Could not read demo runtime status {status_path}: {error}"
        ) from error
    if status.get("initialized") is not True or status.get("initialization_status") != "ready":
        raise DemoRuntimeError("Demo runtime initialization is not ready")
    if status.get("seed_revision") != seed_manifest.get("seed_revision"):
        raise DemoRuntimeError("Demo runtime status targets a different seed revision")
    for field in ("initialized_at", "last_reset_at"):
        value = status.get(field)
        if not isinstance(value, str):
            raise DemoRuntimeError(f"Demo runtime status is missing {field}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise DemoRuntimeError(f"Demo runtime status has invalid {field}") from error
        if parsed.tzinfo is None:
            raise DemoRuntimeError(f"Demo runtime status {field} must include a timezone")
    return status


def validate_runtime_binding(app_manifest_path: Path, data_dir: Path) -> tuple[dict, dict]:
    from backend.persistence.database import database_readiness

    app_manifest, seed_manifest = load_runtime_manifests(
        app_manifest_path, data_dir / "demo-seed-manifest.json"
    )
    load_runtime_status(data_dir, seed_manifest)
    database = data_dir / "lzug.sqlite"
    readiness = database_readiness(database)
    if not readiness["ready"]:
        raise DemoRuntimeError(f"Demo database is not ready: {readiness['reason']}")
    return app_manifest, seed_manifest
