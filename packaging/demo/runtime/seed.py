"""Initialize a disposable demo data directory from one verified seed snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .validation import DemoRuntimeError, load_manifest, validate_fixture_contract


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def initialize_workdir(seed_database: Path, seed_manifest: Path, target: Path) -> None:
    manifest = load_manifest(seed_manifest, "seed")
    validate_fixture_contract(manifest)
    if _sha256_file(seed_database) != manifest.get("snapshot_sha256"):
        raise DemoRuntimeError("Seed snapshot digest does not match its manifest")

    resolved = target.resolve()
    if resolved == Path("/") or len(resolved.parts) < 2:
        raise DemoRuntimeError(f"Unsafe demo data target: {resolved}")
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-database", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        initialize_workdir(args.seed_database, args.seed_manifest, args.target)
    except DemoRuntimeError as error:
        raise SystemExit(f"Demo seed initialization failed: {error}") from error


if __name__ == "__main__":
    main()
