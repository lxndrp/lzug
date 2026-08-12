#!/usr/bin/env python3
"""Create a deterministic, metadata-only inventory for the release review.

The script reads the npm lockfile and the metadata of the checked, locked uv
environment. It emits package metadata only; it never includes source contents,
environment variables, secrets, or personal data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

PYTHON_METADATA_COLLECTOR = r"""
import json
import platform
import sys
from importlib.metadata import distributions

packages = []
for distribution in distributions():
    name = distribution.metadata.get("Name")
    if not name:
        continue
    packages.append(
        {
            "name": name,
            "version": distribution.version,
            "license_expression": distribution.metadata.get("License-Expression"),
            "license": distribution.metadata.get("License"),
            "classifiers": [
                value
                for value in distribution.metadata.get_all("Classifier", [])
                if value.startswith("License ::")
            ],
        }
    )

print(
    json.dumps(
        {
            "environment": {
                "implementation": platform.python_implementation(),
                "platform": sys.platform,
                "python": platform.python_version(),
            },
            "packages": sorted(packages, key=lambda item: item["name"].lower()),
        }
    )
)
"""

LEGACY_LICENSE_VALUES = {
    "0BSD": "0BSD",
    "Apache 2.0": "Apache-2.0",
    "Apache Software License": "Apache-2.0",
    "Apache-2.0": "Apache-2.0",
    "BSD-2-Clause": "BSD-2-Clause",
    "BSD-3-Clause": "BSD-3-Clause",
    "ISC": "ISC",
    "MIT": "MIT",
    "MPL-2.0": "MPL-2.0",
    "PSFL": "PSF-2.0",
}

LICENSE_CLASSIFIERS = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_package_name(value: str) -> str:
    """Return the normalized Python package key used for lock comparisons."""

    return re.sub(r"[-_.]+", "-", value).lower()


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
    documentation_files = {
        "README.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
    }

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

    inventory = [
        {
            "path": package_path,
            "name": package_name(package_path),
            "version": package["version"],
            "license": package.get("license", "unknown"),
            "development": package.get("dev", False),
            "optional": package.get("optional", False),
        }
        for package_path, package in sorted(packages.items())
        if package_path.startswith("node_modules/")
    ]
    all_license_counts = Counter(package["license"] for package in inventory)
    runtime_license_counts = Counter(
        package["license"] for package in inventory if not package["development"]
    )
    unknown = [package for package in inventory if package["license"] == "unknown"]

    return {
        "lockfile_version": lockfile["lockfileVersion"],
        "package_entries": len(inventory),
        "packages": inventory,
        "licenses": dict(sorted(all_license_counts.items())),
        "runtime_licenses": dict(sorted(runtime_license_counts.items())),
        "unknown_license_entries": unknown,
        "review_summary": {
            "resolved": len(inventory) - len(unknown),
            "unknown": len(unknown),
        },
        "direct_runtime": direct(root_package.get("dependencies", {})),
        "direct_development": direct(root_package.get("devDependencies", {})),
    }


def _compact_legacy_license(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if len(normalized) <= 160 and "\n" not in normalized:
        return normalized
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"[long license text omitted; sha256:{digest}]"


def resolve_python_license(package: dict[str, Any]) -> dict[str, Any]:
    """Classify installed distribution metadata without claiming legal certainty."""

    expression = (package.get("license_expression") or "").strip()
    legacy = (package.get("license") or "").strip()
    classifiers = sorted(set(package.get("classifiers", [])))
    result = {
        "name": package["name"],
        "version": package["version"],
        "declared_license_expression": expression or None,
        "legacy_license": _compact_legacy_license(legacy),
        "license_classifiers": classifiers,
    }

    if expression and expression.upper() != "UNKNOWN":
        return {
            **result,
            "license_expression": expression,
            "resolution": "declared-license-expression",
            "review_status": "metadata-resolved",
        }

    if legacy in LEGACY_LICENSE_VALUES:
        return {
            **result,
            "license_expression": LEGACY_LICENSE_VALUES[legacy],
            "resolution": "normalized-legacy-license-field",
            "review_status": "legacy-metadata-resolved",
        }

    classifier_expressions = sorted(
        {
            LICENSE_CLASSIFIERS[classifier]
            for classifier in classifiers
            if classifier in LICENSE_CLASSIFIERS
        }
    )
    has_generic_bsd = "License :: OSI Approved :: BSD License" in classifiers
    if len(classifier_expressions) == 1 and not has_generic_bsd:
        return {
            **result,
            "license_expression": classifier_expressions[0],
            "resolution": "normalized-license-classifier",
            "review_status": "legacy-metadata-resolved",
        }

    candidates = list(classifier_expressions)
    if has_generic_bsd:
        candidates.append("unspecified BSD variant")
    if legacy and legacy.upper() != "UNKNOWN" and legacy not in candidates:
        candidates.append(legacy)
    if candidates:
        return {
            **result,
            "license_expression": None,
            "resolution": "ambiguous-legacy-metadata",
            "review_status": "manual-review-required",
            "candidates": candidates,
        }

    return {
        **result,
        "license_expression": None,
        "resolution": "no-usable-license-metadata",
        "review_status": "unknown",
        "candidates": [],
    }


def _default_venv_python(root: Path) -> Path:
    candidates = (root / ".venv/bin/python", root / ".venv/Scripts/python.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("locked .venv is missing; run `uv sync --locked --extra dev`")


def installed_python_metadata(root: Path, python: Path | None = None) -> dict[str, Any]:
    """Read metadata only after uv confirms that the environment is locked."""

    subprocess.run(
        ["uv", "sync", "--locked", "--extra", "dev", "--check"],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    interpreter = python or _default_venv_python(root)
    result = subprocess.run(
        [str(interpreter), "-c", PYTHON_METADATA_COLLECTOR],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return json.loads(result.stdout)


def summarize_python_inventory(
    lockfile: dict[str, Any], installed: dict[str, Any]
) -> dict[str, Any]:
    locked = {
        canonical_package_name(package["name"]): {
            "name": package["name"],
            "version": package["version"],
        }
        for package in lockfile.get("package", [])
    }
    installed_by_name = {
        canonical_package_name(package["name"]): package for package in installed["packages"]
    }
    unexpected = sorted(set(installed_by_name) - set(locked))
    mismatches = sorted(
        {
            name: {
                "installed": installed_by_name[name]["version"],
                "locked": locked[name]["version"],
            }
            for name in set(installed_by_name) & set(locked)
            if installed_by_name[name]["version"] != locked[name]["version"]
        }.items()
    )
    if unexpected or mismatches:
        raise RuntimeError(
            f"installed Python environment differs from uv.lock: "
            f"unexpected={unexpected!r}, mismatches={mismatches!r}"
        )
    if "lzug" not in installed_by_name:
        raise RuntimeError("locked Python environment does not contain the lzug distribution")

    packages = [
        resolve_python_license(package)
        for name, package in sorted(installed_by_name.items())
        if name != "lzug"
    ]
    manual = [
        package for package in packages if package["review_status"] == "manual-review-required"
    ]
    unknown = [package for package in packages if package["review_status"] == "unknown"]
    license_counts = Counter(
        package["license_expression"] or package["review_status"] for package in packages
    )
    not_installed = [locked[name] for name in sorted(set(locked) - set(installed_by_name))]

    return {
        "environment": installed["environment"],
        "lockfile_packages": len(locked),
        "installed_third_party_packages": len(packages),
        "packages": packages,
        "licenses": dict(sorted(license_counts.items())),
        "manual_review_entries": manual,
        "unknown_license_entries": unknown,
        "locked_but_not_installed": not_installed,
        "review_summary": {
            "metadata_resolved": sum(
                package["review_status"] == "metadata-resolved" for package in packages
            ),
            "legacy_metadata_resolved": sum(
                package["review_status"] == "legacy-metadata-resolved" for package in packages
            ),
            "manual_review_required": len(manual),
            "unknown": len(unknown),
        },
        "project_distribution": resolve_python_license(installed_by_name["lzug"]),
    }


def python_summary(path: Path, root: Path, python: Path | None = None) -> dict[str, Any]:
    lockfile = tomllib.loads(path.read_text(encoding="utf-8"))
    installed = installed_python_metadata(root, python)
    return summarize_python_inventory(lockfile, installed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--python",
        type=Path,
        help="locked environment interpreter; defaults to .venv/bin/python",
    )
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
        "schema_version": 2,
        "inputs": {name: {"sha256": sha256(path), "path": name} for name, path in inputs.items()},
        "files": source_summary(paths, root),
        "npm": npm_summary(inputs["frontend/package-lock.json"]),
        "python": python_summary(inputs["uv.lock"], root, args.python),
        "assessment_boundary": (
            "metadata inventory for release review; not legal advice or a guarantee of "
            "license compatibility"
        ),
        "sbom": {
            "status": "generated separately from the qualified OCI image",
            "format": "CycloneDX JSON",
            "owner": "release pipeline",
        },
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
