#!/usr/bin/env python3
"""Create a deterministic, metadata-only inventory for the release review.

The script deliberately reads lockfiles instead of resolving packages. It emits
counts and package metadata only; it never reads environment variables that may
contain secrets and never includes source contents or personal data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [path for path in result.stdout.decode().split("\0") if path]


def source_summary(paths: list[str], root: Path) -> dict[str, Any]:
    source_roots = (
        "backend/",
        "db/",
        "fixtures/",
        "frontend/src/",
        "frontend/public/",
        "prototypes/",
        "scripts/",
    )
    documentation_roots = ("docs/",)
    documentation_files = {"README.md", "CONTRIBUTING.md", "CHANGELOG.md", "CODE_OF_CONDUCT.md"}

    def summarize(selected: list[str]) -> dict[str, Any]:
        extensions = Counter(Path(path).suffix.lower() or "[no extension]" for path in selected)
        bytes_total = sum((root / path).stat().st_size for path in selected)
        return {
            "files": len(selected),
            "bytes": bytes_total,
            "extensions": dict(sorted(extensions.items())),
        }

    source_paths = [path for path in paths if path.startswith(source_roots)]
    documentation_paths = [
        path
        for path in paths
        if path.startswith(documentation_roots) or path in documentation_files
    ]
    return {
        "tracked_files": len(paths),
        "source": summarize(source_paths),
        "documentation": summarize(documentation_paths),
    }


def npm_summary(path: Path) -> dict[str, Any]:
    lockfile = json.loads(path.read_text(encoding="utf-8"))
    packages = lockfile["packages"]
    root_package = packages[""]

    def package_name(package_path: str) -> str:
        return package_path.rsplit("node_modules/", 1)[-1]

    def direct(names: dict[str, str]) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "requested": specifier,
                "version": packages[f"node_modules/{name}"]["version"],
                "license": packages[f"node_modules/{name}"].get("license", "unknown"),
            }
            for name, specifier in sorted(names.items())
        ]

    all_license_counts = Counter(
        package.get("license", "unknown")
        for package_path, package in packages.items()
        if package_path.startswith("node_modules/")
    )
    runtime_license_counts = Counter(
        package.get("license", "unknown")
        for package_path, package in packages.items()
        if package_path.startswith("node_modules/") and not package.get("dev", False)
    )
    unknown = sorted(
        package_name(package_path)
        for package_path, package in packages.items()
        if package_path.startswith("node_modules/") and not package.get("license")
    )

    return {
        "lockfile_version": lockfile["lockfileVersion"],
        "package_entries": len(packages) - 1,
        "licenses": dict(sorted(all_license_counts.items())),
        "runtime_licenses": dict(sorted(runtime_license_counts.items())),
        "unknown_license_entries": unknown,
        "direct_runtime": direct(root_package.get("dependencies", {})),
        "direct_development": direct(root_package.get("devDependencies", {})),
    }


def python_summary(path: Path) -> dict[str, Any]:
    lockfile = tomllib.loads(path.read_text(encoding="utf-8"))
    packages = [
        {"name": package["name"], "version": package["version"]}
        for package in lockfile.get("package", [])
    ]
    return {
        "lockfile_packages": len(packages),
        "packages": packages,
        "license_metadata": (
            "uv.lock does not encode license expressions; resolve distribution metadata "
            "in the locked environment before release"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()

    inputs = {
        "frontend/package-lock.json": root / "frontend/package-lock.json",
        "uv.lock": root / "uv.lock",
    }
    missing = [name for name, path in inputs.items() if not path.is_file()]
    if missing:
        parser.error(f"missing input(s): {', '.join(missing)}")

    paths = tracked_paths(root)
    report = {
        "schema_version": 1,
        "inputs": {name: {"sha256": sha256(path), "path": name} for name, path in inputs.items()},
        "files": source_summary(paths, root),
        "npm": npm_summary(inputs["frontend/package-lock.json"]),
        "python": python_summary(inputs["uv.lock"]),
        "sbom": {
            "status": "not generated by this script",
            "planned_format": "CycloneDX JSON",
            "planned_owners": {
                "Python_and_npm": "repository maintainers",
                "OCI": "release pipeline owner when OCI packaging exists",
            },
        },
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
