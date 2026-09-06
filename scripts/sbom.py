#!/usr/bin/env python3
"""Generate and validate the canonical lzug CycloneDX SBOM artifacts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CYCLONEDX_SPEC_VERSION = "1.6"
DEPENDENCY_SOURCE_NAME = "lzug-dependencies"
CLI_SOURCE_NAME = "lzug-admin"
RELEASE_SOURCE_NAME = "lzug-release"
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


def require_pinned_syft(executable: str, root: Path = ROOT) -> str:
    """Fail unless the active Syft binary matches the repository pin."""

    expected = configured_syft_version(root)
    result = subprocess.run(
        [executable, "version", "-o", "json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    actual = str(json.loads(result.stdout)["version"])
    if actual != expected:
        raise RuntimeError(f"Syft {expected} is required, found {actual}")
    return actual


def dependency_command(output: Path, source_version: str, executable: str = "syft") -> list[str]:
    """Build the pinned Syft command for the cross-ecosystem dependency SBOM."""

    return [
        executable,
        "scan",
        "dir:.",
        "--source-name",
        DEPENDENCY_SOURCE_NAME,
        "--source-version",
        source_version,
        "--override-default-catalogers",
        ("python-installed-package-cataloger,javascript-lock-cataloger,go-module-file-cataloger"),
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
        "./backend/src/lzug.egg-info/**",
        "--exclude",
        "./site/**",
        "--exclude",
        "./operator-cli/lzug-admin",
        "--output",
        f"cyclonedx-json@{CYCLONEDX_SPEC_VERSION}={output}",
    ]


def image_command(output: Path, image: str, executable: str = "syft") -> list[str]:
    """Build the pinned Syft command for the exact final OCI image."""

    return [
        executable,
        "scan",
        image,
        "--output",
        f"cyclonedx-json@{CYCLONEDX_SPEC_VERSION}={output}",
    ]


def cli_command(
    output: Path,
    artifact: Path,
    source_version: str,
    source_name: str = CLI_SOURCE_NAME,
    executable: str = "syft",
) -> list[str]:
    """Build the pinned Syft command for one already built native CLI artifact."""

    return [
        executable,
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

    executable = syft_binary()
    require_pinned_syft(executable)
    if not (ROOT / ".venv").is_dir():
        raise RuntimeError(".venv is missing; run task setup before generating the SBOM")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_syft(dependency_command(output, args.source_version, executable))


def generate_image(args: argparse.Namespace) -> None:
    """Generate the OCI SBOM from one exact locally available image."""

    executable = syft_binary()
    require_pinned_syft(executable)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_syft(image_command(output, args.image, executable))


def generate_cli(args: argparse.Namespace) -> None:
    """Generate an SBOM for one native CLI binary built by the caller."""

    executable = syft_binary()
    require_pinned_syft(executable)
    artifact = Path(args.artifact).resolve()
    if not artifact.is_file():
        raise RuntimeError(f"CLI artifact does not exist: {artifact}")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_syft(cli_command(output, artifact, args.source_version, args.source_name, executable))


def _component_key(component: dict[str, Any]) -> str:
    normalized = copy.deepcopy(component)
    normalized.pop("bom-ref", None)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def aggregate_release_sbom(
    payloads: list[dict[str, Any]],
    source_version: str,
    release_tag: str,
    revision: str,
) -> dict[str, Any]:
    """Combine temporary detailed SBOMs into one deterministic release inventory."""

    if release_tag != f"v{source_version}":
        raise ValueError("release tag must match the aggregate SBOM version")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("release revision must be a full commit SHA")
    if len(payloads) != 8:
        raise ValueError("release aggregation requires dependency, image, and six CLI SBOMs")

    components_by_key: dict[str, tuple[dict[str, Any], set[str]]] = {}
    syft_tool: dict[str, Any] | None = None
    for payload in payloads:
        components = validate_common(payload)
        source = payload.get("metadata", {}).get("component", {})
        source_name = source.get("name")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("detailed SBOM has no source component name")
        tools = payload.get("metadata", {}).get("tools", {}).get("components", [])
        current_syft = next(tool for tool in tools if tool.get("name") == "syft")
        if syft_tool is None:
            syft_tool = copy.deepcopy(current_syft)

        for component in components:
            key = _component_key(component)
            if key not in components_by_key:
                normalized = copy.deepcopy(component)
                normalized.pop("bom-ref", None)
                components_by_key[key] = (normalized, set())
            components_by_key[key][1].add(source_name)

    merged_components: list[dict[str, Any]] = []
    for key, (component, sources) in sorted(components_by_key.items()):
        component["bom-ref"] = (
            "urn:lzug:component:sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        )
        properties = component.setdefault("properties", [])
        if not isinstance(properties, list):
            raise ValueError("detailed SBOM component properties must be a list")
        properties.append({"name": "lzug:release:sbom-sources", "value": ",".join(sorted(sources))})
        merged_components.append(component)

    serial = uuid.uuid5(
        uuid.NAMESPACE_URL, f"https://github.com/lxndrp/lzug/{release_tag}/{revision}"
    )
    return {
        "$schema": f"https://cyclonedx.org/schema/bom-{CYCLONEDX_SPEC_VERSION}.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": f"pkg:generic/lzug@{source_version}",
                "type": "application",
                "name": RELEASE_SOURCE_NAME,
                "version": source_version,
            },
            "tools": {
                "components": [
                    syft_tool,
                    {
                        "type": "application",
                        "name": "lzug-sbom-aggregate",
                        "version": "1",
                    },
                ]
            },
            "properties": [
                {"name": "lzug:release:tag", "value": release_tag},
                {"name": "lzug:release:revision", "value": revision},
                {"name": "lzug:release:detailed-sbom-count", "value": str(len(payloads))},
            ],
        },
        "components": merged_components,
    }


def aggregate(args: argparse.Namespace) -> None:
    """Write the visible aggregate release SBOM from temporary detailed inputs."""

    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.input]
    result = aggregate_release_sbom(
        payloads,
        args.source_version,
        args.release_tag,
        args.revision,
    )
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def go_sum_module_names(go_sum: str) -> set[str]:
    """Return module paths anchored by entries in go.sum."""

    modules: set[str] = set()
    for raw_line in go_sum.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 3 or not fields[0] or not fields[1] or not fields[2]:
            raise ValueError("go.sum contains an invalid module checksum entry")
        modules.add(fields[0].removesuffix("/go.mod"))
    return modules


def go_module_graph(
    go_mod: str,
    module_dir: Path = ROOT / "operator-cli",
    go_sum: str | None = None,
) -> tuple[str, set[str]]:
    """Return the main module and lockfile-backed modules from Go's full graph."""

    main_module, _ = go_module_contract(go_mod)
    result = subprocess.run(
        ["go", "list", "-mod=readonly", "-m", "-json", "all"],
        cwd=module_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    decoder = json.JSONDecoder()
    modules: list[dict[str, Any]] = []
    position = 0
    while position < len(result.stdout):
        while position < len(result.stdout) and result.stdout[position].isspace():
            position += 1
        if position == len(result.stdout):
            break
        try:
            module, position = decoder.raw_decode(result.stdout, position)
        except json.JSONDecodeError as error:
            raise ValueError("go list returned an invalid module graph") from error
        if not isinstance(module, dict) or not isinstance(module.get("Path"), str):
            raise ValueError("go list returned an invalid module entry")
        modules.append(module)

    graph_modules = {module["Path"] for module in modules}
    main_modules = {module["Path"] for module in modules if module.get("Main") is True}
    if main_modules != {main_module} or main_module not in graph_modules:
        raise ValueError("go list module graph does not identify the declared main module")
    if go_sum is None:
        go_sum = (module_dir / "go.sum").read_text(encoding="utf-8")
    return main_module, (graph_modules & go_sum_module_names(go_sum)) - {main_module}


def go_component_names(components: list[dict[str, Any]]) -> set[str]:
    """Return normalized Go package names represented by CycloneDX components."""

    return {
        str(item.get("name"))
        for item in components
        if component_purl_type(item) == "golang" and item.get("name")
    }


def validate_dependencies(
    payload: dict[str, Any], go_mod: str, go_modules: set[str] | None = None
) -> dict[str, Any]:
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

    main_module, _ = go_module_contract(go_mod)
    if go_modules is None:
        _, go_modules = go_module_graph(go_mod)
    represented_go_modules = go_component_names(components)
    external_go_modules = represented_go_modules - {main_module, "stdlib"}
    missing_go_modules = sorted(go_modules - represented_go_modules)
    if missing_go_modules:
        raise ValueError(
            "Go module graph modules missing from the dependency SBOM: "
            + ", ".join(missing_go_modules)
        )
    unexpected_go_modules = sorted(external_go_modules - go_modules)
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
            f"{len(go_modules)} resolved third-party module components"
            if go_modules
            else "Go resolves no third-party modules"
        ),
    }


def validate_cli(
    payload: dict[str, Any], go_mod: str, go_modules: set[str] | None = None
) -> dict[str, Any]:
    """Validate a CycloneDX SBOM for one already built native CLI artifact."""

    components = validate_common(payload)
    source = payload.get("metadata", {}).get("component", {})
    if source.get("type") != "file" or not source.get("name"):
        raise ValueError("CLI SBOM source must identify the scanned file")

    main_module, _ = go_module_contract(go_mod)
    if go_modules is None:
        _, go_modules = go_module_graph(go_mod)
    represented_go_modules = go_component_names(components)
    for required in (main_module, "stdlib"):
        if required not in represented_go_modules:
            raise ValueError(f"CLI SBOM is missing Go component {required}")
    missing_go_modules = sorted(go_modules - represented_go_modules)
    if missing_go_modules:
        raise ValueError(
            "CLI SBOM is missing Go module graph modules: " + ", ".join(missing_go_modules)
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


def validate_release(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the single aggregate visible release inventory."""

    components = validate_common(payload)
    source = payload.get("metadata", {}).get("component", {})
    version = source.get("version")
    if source.get("name") != RELEASE_SOURCE_NAME or not isinstance(version, str):
        raise ValueError(f"release SBOM source must be {RELEASE_SOURCE_NAME}")
    properties = {
        item.get("name"): item.get("value")
        for item in payload.get("metadata", {}).get("properties", [])
        if isinstance(item, dict)
    }
    if properties.get("lzug:release:tag") != f"v{version}":
        raise ValueError("release SBOM tag does not match its version")
    if not re.fullmatch(r"[0-9a-f]{40}", str(properties.get("lzug:release:revision", ""))):
        raise ValueError("release SBOM has no full revision")
    if properties.get("lzug:release:detailed-sbom-count") != "8":
        raise ValueError("release SBOM must aggregate exactly eight detailed SBOMs")

    counts = Counter(filter(None, (component_purl_type(item) for item in components)))
    for required in ("pypi", "npm", "golang"):
        if not counts[required]:
            raise ValueError(f"release SBOM contains no {required} components")
    return {
        "components": len(components),
        "purl_types": dict(sorted(counts.items())),
        "scope": "aggregate dependency inventory for the OCI image and six native CLI builds",
    }


def validate(args: argparse.Namespace) -> None:
    """Validate and summarize one canonical CycloneDX artifact."""

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    go_mod = (ROOT / "operator-cli/go.mod").read_text(encoding="utf-8")
    go_modules = go_module_graph(go_mod)[1] if args.kind in ("dependencies", "cli") else None
    if args.kind == "dependencies":
        summary = validate_dependencies(payload, go_mod, go_modules)
    elif args.kind == "cli":
        summary = validate_cli(payload, go_mod, go_modules)
    elif args.kind == "image":
        summary = validate_image(payload)
    else:
        summary = validate_release(payload)
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

    aggregate_command = commands.add_parser("aggregate")
    aggregate_command.add_argument("--input", action="append", required=True)
    aggregate_command.add_argument("--output", required=True)
    aggregate_command.add_argument("--release-tag", required=True)
    aggregate_command.add_argument("--revision", required=True)
    aggregate_command.add_argument("--source-version", required=True)
    aggregate_command.set_defaults(handler=aggregate)

    check = commands.add_parser("validate")
    check.add_argument("--kind", choices=("dependencies", "image", "cli", "release"), required=True)
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
