#!/usr/bin/env python3
"""Generate the low-level TypeScript transport types from FastAPI OpenAPI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend" / "src" / "app" / "api" / "generated"
CONFIG = ROOT / "frontend" / "openapi-ts.config.mjs"
GENERATOR = ROOT / "frontend" / "node_modules" / ".bin" / "openapi-ts"


def openapi_document(database: Path) -> dict[str, object]:
    """Return the canonical application contract without starting a server."""

    from backend.fastapi_assembly import FastAPIConfig, create_app

    return create_app(
        FastAPIConfig(
            db_path=database,
            session_cookie_name="lzug_session",
            cookie_secure=False,
            https_only=False,
        )
    ).openapi()


def generate_candidate(directory: Path) -> Path:
    """Generate a complete candidate directory in an isolated location."""

    if not GENERATOR.is_file():
        raise RuntimeError("OpenAPI generator is missing; run npm ci --prefix frontend")

    schema = directory / "openapi.json"
    output = directory / "generated"
    schema.write_text(
        json.dumps(
            openapi_document(directory / "openapi.sqlite3"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "LZUG_OPENAPI_INPUT": str(schema),
            "LZUG_TRANSPORT_OUTPUT": str(output),
        }
    )
    subprocess.run(
        [str(GENERATOR), "--file", str(CONFIG), "--no-log-file", "--silent"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    return output


def files(directory: Path) -> dict[Path, bytes]:
    """Return relative file paths and bytes for one generated directory."""

    if not directory.is_dir():
        return {}
    return {
        path.relative_to(directory): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def changed_paths(candidate: Path, target: Path = TARGET) -> list[Path]:
    """Return missing, stale, or unexpected generated files."""

    expected = files(candidate)
    actual = files(target)
    return sorted(
        path for path in expected.keys() | actual.keys() if expected.get(path) != actual.get(path)
    )


def replace_generated(candidate: Path, target: Path = TARGET) -> None:
    """Replace only the owned generated directory with the candidate files."""

    target.mkdir(parents=True, exist_ok=True)
    expected = files(candidate)
    for relative in files(target).keys() - expected.keys():
        (target / relative).unlink()
    for relative, content in expected.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    for directory in sorted(
        (path for path in target.rglob("*") if path.is_dir()),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()


def generate(*, check: bool) -> list[Path]:
    """Generate tracked output or report drift without modifying it."""

    with tempfile.TemporaryDirectory(prefix="lzug-openapi-") as temporary:
        candidate = generate_candidate(Path(temporary))
        changed = changed_paths(candidate)
        if not check:
            replace_generated(candidate)
        return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the tracked TypeScript transport types are stale",
    )
    args = parser.parse_args()
    changed = generate(check=args.check)
    if args.check and changed:
        print("Generated frontend transport types are stale:")
        for path in changed:
            print(f"- {path}")
        print("Run `task frontend:transport:generate` and commit the result.")
        return 1
    if args.check:
        print("Generated frontend transport types are current.")
    else:
        print(f"Generated frontend transport types in {TARGET.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
