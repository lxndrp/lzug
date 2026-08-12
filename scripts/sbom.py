#!/usr/bin/env python3
"""Generate and validate the canonical lzug CycloneDX SBOM artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CYCLONEDX_SPEC_VERSION = "1.6"
DEPENDENCY_SOURCE_NAME = "lzug-dependencies"
CLI_SOURCE_NAME = "lzug-admin"
SYFT_TOOL_KEY = "aqua:anchore/syft"


def configured_syft_version(root: Path = ROOT) -> str:
    """Return the Syft version pinned by the repository toolchain."""

    config = tomllib.loads((root / ".mise.toml").read_text(encoding="utf-8"))
    return str(config["tools"][SYFT_TOOL_KEY])


def syft_binary() -> str:
    """Return the CI-provided Syft path or the executable from PATH."""

    configured = os.environ.get("SYFT_BINARY")
    if configured:
        return configured
    executable = shutil.which("syft")
    if executable:
        return executable
    result = subprocess.run(
        ["mise", "which", "syft"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def require_pinned_syft(root: Path = ROOT) -> str:
    """Fail unless the active Syft binary matches the repository pin."""

    expected = configured_syft_version(root)
    result = subprocess.run(
        [syft_binary(), "version", "-o", "json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    actual = str(json.loads(result.stdout)["version"])
    if actual != expected:
        raise RuntimeError(f"Syft {expected} is required, found {actual}")
    return actual


def dependency_command(output: Path, source_version: str) -> list[str]:
    """Build the pinned Syft command for the cross-ecosystem dependency SBOM."""

    return [
        syft_binary(),
        "scan",
        "dir:.",
        "--source-name",
        DEPENDENCY_SOURCE_NAME,
        "--source-version",
        source_version,
        "--override-default-catalogers",
        (
            "python-installed-package-cataloger,"
            "javascript-lock-cataloger,"
            "go-module-file-cataloger"
        ),
        "--exclude",
        "./.git/**",
        "--exclude",
        "./.venv/**/__pycache__/**",
        "--exclude",
        "./frontend/node_modules/**",
        "--exclude",
        "./frontend/dist/**",
        "--exclude",
        "./lzug.egg-info/**",
        "--exclude",
        "./site/**",
        "--exclude",
        "./lzug-admin",
        "--output",
        f"cyclonedx-json@{CYCLONEDX_SPEC_VERSION}={output}",
    ]


def image_command(output: Path, image: str) -> list[str]:
    """Build the pinned Syft command for the exact final OCI image."""

    return [
        syft_binary(),
        "scan",
        image,
        "--output",
        f"cyclonedx-json@{CYCLONEDX_SPEC_VERSION}={output}",
    ]


def cli_command(
    output: Path, artifact: Path, source_version: str, source_name: str = CLI_SOURCE_NAME
) -> list[str]:
    """Build the pinned Syft command for one already built native CLI artifact."""

    return [
        syft_binary(),
        "scan",
        f"file:{artifact.resolve()}",
        "--source-name",
        source_name,
        "--source-version",
        source_version,
        "--output",
        f"cyclonedx-json@{CYCLONEDX_SPEC_VERSION}={output}",
    ]


def run_syft(command: list[str], root: Path = ROOT) -> None:
    """Run Syft offline with stable formatting and cataloger policy."""

    environment = os.environ.copy()
    environment.update(
        {
            "SYFT_CACHE_DIR": "/tmp/lzug-syft-cache",
            "SYFT_CHECK_FOR_APP_UPDATE": "false",
            "SYFT_FILE_METADATA_SELECTION": "none",
            "SYFT_FORMAT_PRETTY": "true",
            "SYFT_JAVASCRIPT_INCLUDE_DEV_DEPENDENCIES": "true",
        }
    )
    subprocess.run(command, cwd=root, env=environment, check=True)


def generate_dependencies(args: argparse.Namespace) -> None:
    """Generate the dependency-review SBOM from locks and installed metadata."""

    require_pinned_syft()
    if not (ROOT / ".venv").is_dir():
        raise RuntimeError(".venv is missing; run task setup before generating the SBOM")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_syft(dependency_command(output, args.source_version))


def generate_image(args: argparse.Namespace) -> None:
    """Generate the OCI SBOM from one exact locally available image."""

    require_pinned_syft()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_syft(image_command(output, args.image))


def generate_cli(args: argparse.Namespace) -> None:
    """Generate an SBOM for one native CLI binary built by the caller."""

    require_pinned_syft()
    artifact = Path(args.artifact).resolve()
    if not artifact.is_file():
        raise RuntimeError(f"CLI artifact does not exist: {artifact}")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_syft(cli_command(output, artifact, args.source_version, args.source_name))


def component_purl_type(component: dict[str, Any]) -> str | None:
    """Return the Package URL type for a CycloneDX component."""

    purl = component.get("purl")
    if not isinstance(purl, str) or not purl.startswith("pkg:"):
        return None
    return purl.removeprefix("pkg:").split("/", 1)[0]


def component_has_license(component: dict[str, Any]) -> bool:
    """Return whether a component carries at least one declared license value."""

    return bool(component.get("licenses"))


def validate_common(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the common CycloneDX and Syft provenance contract."""

    if payload.get("bomFormat") != "CycloneDX":
        raise ValueError("SBOM must use CycloneDX")
    if payload.get("specVersion") != CYCLONEDX_SPEC_VERSION:
        raise ValueError(f"SBOM must use CycloneDX {CYCLONEDX_SPEC_VERSION}")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("SBOM contains no components")
    for component in components:
        if component_purl_type(component) and (
            not component.get("name") or not component.get("version")
        ):
            raise ValueError("every package component must have a name and version")
    tools = payload.get("metadata", {}).get("tools", {}).get("components", [])
    syft_tools = [tool for tool in tools if tool.get("name") == "syft"]
    if len(syft_tools) != 1:
        raise ValueError("SBOM must identify exactly one Syft generator")
    expected_version = configured_syft_version()
    if syft_tools[0].get("version") != expected_version:
        raise ValueError(f"SBOM must be generated by Syft {expected_version}")
    return components


def go_module_contract(go_mod: str) -> tuple[str, set[str]]:
    """Return the main module and required third-party modules from go.mod."""

    module_match = re.search(r"(?m)^module\s+(\S+)\s*$", go_mod)
    if not module_match:
        raise ValueError("go.mod must declare a module")

    required: set[str] = set()
    in_require_block = False
    for raw_line in go_mod.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if line == "require (":
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue
        if in_require_block and line:
            required.add(line.split()[0])
        elif line.startswith("require "):
            required.add(line.removeprefix("require ").split()[0])
    return module_match.group(1), required


def go_component_names(components: list[dict[str, Any]]) -> set[str]:
    """Return normalized Go package names represented by CycloneDX components."""

    return {
        str(item.get("name"))
        for item in components
        if component_purl_type(item) == "golang" and item.get("name")
    }


def validate_dependencies(payload: dict[str, Any], go_mod: str) -> dict[str, Any]:
    """Validate the dependency-review SBOM and return its visible review summary."""

    components = validate_common(payload)
    source = payload.get("metadata", {}).get("component", {})
    if source.get("name") != DEPENDENCY_SOURCE_NAME:
        raise ValueError(f"dependency SBOM source must be {DEPENDENCY_SOURCE_NAME}")

    counts = Counter(filter(None, (component_purl_type(item) for item in components)))
    for required in ("pypi", "npm"):
        if not counts[required]:
            raise ValueError(f"dependency SBOM contains no {required} components")

    npm_missing_licenses = sorted(
        f"{item['name']}@{item['version']}"
        for item in components
        if component_purl_type(item) == "npm" and not component_has_license(item)
    )
    if npm_missing_licenses:
        raise ValueError(
            "npm components without license metadata: " + ", ".join(npm_missing_licenses)
        )

    project_components = [
        item
        for item in components
        if component_purl_type(item) == "pypi" and item.get("name", "").lower() == "lzug"
    ]
    if len(project_components) != 1 or not component_has_license(project_components[0]):
        raise ValueError("dependency SBOM must contain one licensed lzug Python distribution")

    main_module, required_go_modules = go_module_contract(go_mod)
    represented_go_modules = go_component_names(components)
    external_go_modules = represented_go_modules - {main_module, "stdlib"}
    missing_go_modules = sorted(required_go_modules - represented_go_modules)
    if missing_go_modules:
        raise ValueError(
            "go.mod modules missing from the dependency SBOM: " + ", ".join(missing_go_modules)
        )
    unexpected_go_modules = sorted(external_go_modules - required_go_modules)
    if unexpected_go_modules:
        raise ValueError(
            "dependency SBOM contains undeclared Go modules: " + ", ".join(unexpected_go_modules)
        )

    python_missing_licenses = sorted(
        f"{item['name']}@{item['version']}"
        for item in components
        if component_purl_type(item) == "pypi"
        and item.get("name", "").lower() != "lzug"
        and not component_has_license(item)
    )
    return {
        "components": len(components),
        "purl_types": dict(sorted(counts.items())),
        "python_missing_license_metadata": python_missing_licenses,
        "go_boundary": (
            f"{len(required_go_modules)} declared third-party module components"
            if required_go_modules
            else "go.mod declares no third-party modules"
        ),
    }


def validate_cli(payload: dict[str, Any], go_mod: str) -> dict[str, Any]:
    """Validate a CycloneDX SBOM for one already built native CLI artifact."""

    components = validate_common(payload)
    source = payload.get("metadata", {}).get("component", {})
    if source.get("type") != "file" or not source.get("name"):
        raise ValueError("CLI SBOM source must identify the scanned file")

    main_module, required_go_modules = go_module_contract(go_mod)
    represented_go_modules = go_component_names(components)
    for required in (main_module, "stdlib"):
        if required not in represented_go_modules:
            raise ValueError(f"CLI SBOM is missing Go component {required}")
    missing_go_modules = sorted(required_go_modules - represented_go_modules)
    if missing_go_modules:
        raise ValueError(
            "CLI SBOM is missing declared Go modules: " + ", ".join(missing_go_modules)
        )
    return {
        "artifact": source["name"],
        "components": len(components),
        "go_components": len(represented_go_modules),
        "scope": "one native CLI binary and the Go modules embedded in that binary",
    }


def validate_image(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate that the OCI SBOM describes only the final runtime contents."""

    components = validate_common(payload)
    counts = Counter(filter(None, (component_purl_type(item) for item in components)))
    if not counts["pypi"]:
        raise ValueError("image SBOM contains no installed Python components")
    unexpected = sorted(kind for kind in ("npm", "golang") if counts[kind])
    if unexpected:
        raise ValueError(
            "final image unexpectedly contains build-only ecosystems: " + ", ".join(unexpected)
        )
    return {
        "components": len(components),
        "purl_types": dict(sorted(counts.items())),
        "scope": "final OCI image; npm build dependencies and the separate Go CLI are excluded",
    }


def validate(args: argparse.Namespace) -> None:
    """Validate and summarize one canonical CycloneDX artifact."""

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.kind == "dependencies":
        summary = validate_dependencies(payload, (ROOT / "go.mod").read_text(encoding="utf-8"))
    elif args.kind == "cli":
        summary = validate_cli(payload, (ROOT / "go.mod").read_text(encoding="utf-8"))
    else:
        summary = validate_image(payload)
    print(json.dumps(summary, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    """Create the SBOM command-line parser."""

    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    dependencies = commands.add_parser("generate-dependencies")
    dependencies.add_argument("--output", required=True)
    dependencies.add_argument("--source-version", required=True)
    dependencies.set_defaults(handler=generate_dependencies)

    image = commands.add_parser("generate-image")
    image.add_argument("--image", required=True)
    image.add_argument("--output", required=True)
    image.set_defaults(handler=generate_image)

    cli = commands.add_parser("generate-cli")
    cli.add_argument("--artifact", required=True)
    cli.add_argument("--source-name", default=CLI_SOURCE_NAME)
    cli.add_argument("--source-version", required=True)
    cli.add_argument("--output", required=True)
    cli.set_defaults(handler=generate_cli)

    check = commands.add_parser("validate")
    check.add_argument("--kind", choices=("dependencies", "image", "cli"), required=True)
    check.add_argument("--input", required=True)
    check.set_defaults(handler=validate)
    return root


def main() -> None:
    """Run the selected SBOM command."""

    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"SBOM error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
